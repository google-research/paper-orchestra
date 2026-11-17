# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""ACP (Agent Client Protocol) backend for the PaperOrchestra pipeline.

Lets any ACP-compatible coding agent (e.g. Devin CLI via `devin acp`) drive
pipeline stages. Model names prefixed with ``acp:`` are routed here by
``utils/llm_backend_utils.py``.

Selection rules for ``acp:<spec>`` model names:

* ``acp:devin``        -> ``devin acp`` (requires `devin auth login`)
* ``acp:gemini``       -> ``gemini --experimental-acp``
* ``acp:cmd:<string>`` -> arbitrary command, e.g. ``acp:cmd:devin acp --model opus``

The agent subprocess is spawned lazily, once per (command, workspace) per
process, and reused across calls on a background asyncio thread. Each call
gets a fresh ACP session so prompts stay isolated.

Requires the optional ``agent-client-protocol`` package.
"""

import asyncio
import atexit
import os
import shlex
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

import dotenv

dot_file = os.path.join(os.path.dirname(__file__), "../.env")
dotenv.load_dotenv(dot_file)

ACP_MODEL_PREFIX = "acp:"

# Aliases -> argv for well-known ACP agents.
ACP_AGENT_COMMANDS = {
    "devin": ["devin", "acp"],
    "gemini": ["gemini", "--experimental-acp"],
}

# Permission option kinds, most to least preferred for auto-approval.
_ALLOW_KINDS = ("allow_once", "allow_always")
# Devin advertises a plan-mode bypass option that should never be auto-selected.
_SKIPPED_OPTION_IDS = {"plan_bypass"}
_READ_ONLY_KINDS = {"read", "search", "think"}

MAX_TERMINAL_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_LIVE_TERMINALS = 16

_MIME_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
    "text/plain": ".txt",
}

_workspace_root: Optional[str] = None
_ACP_CONFIG: Dict[str, Any] = {}


def is_acp_model(model_name: Optional[str]) -> bool:
    return bool(model_name) and model_name.lower().startswith(ACP_MODEL_PREFIX)


def configure_acp(
    acp_command: Optional[str] = None,
    acp_args: Optional[str] = None,
    permission_mode: Optional[str] = None,
    enable_terminal: Optional[bool] = None,
    verbose: Optional[bool] = None,
    workspace_root: Optional[str] = None,
) -> None:
    """Set process-wide defaults for ACP calls (from CLI flags)."""
    if acp_command is not None:
        _ACP_CONFIG["acp_command"] = acp_command
    if acp_args is not None:
        _ACP_CONFIG["acp_args"] = acp_args
    if permission_mode is not None:
        _ACP_CONFIG["permission_mode"] = permission_mode
    if enable_terminal is not None:
        _ACP_CONFIG["enable_terminal"] = enable_terminal
    if verbose is not None:
        _ACP_CONFIG["verbose"] = verbose
    if workspace_root is not None:
        set_acp_workspace(workspace_root)


def set_acp_workspace(root: str) -> None:
    """Confine agent file writes and terminal cwd to this directory."""
    global _workspace_root
    _workspace_root = os.path.realpath(root)


def _get_workspace_root() -> str:
    return _workspace_root or os.path.realpath(
        os.environ.get("PAPER_ACP_WORKSPACE") or os.getcwd()
    )


def resolve_acp_command(
    model_name: str,
    acp_command: Optional[str] = None,
    acp_args: Optional[str] = None,
) -> List[str]:
    """Resolve an ``acp:`` model name into an argv list."""
    if acp_command:
        argv = shlex.split(acp_command)
    else:
        spec = model_name[len(ACP_MODEL_PREFIX):].strip()
        if spec.startswith("cmd:"):
            argv = shlex.split(spec[len("cmd:"):])
        elif spec in ACP_AGENT_COMMANDS:
            argv = list(ACP_AGENT_COMMANDS[spec])
        elif os.sep in spec or spec.endswith((".py", ".sh")):
            argv = shlex.split(spec)
        else:
            raise ValueError(
                f"Unknown ACP agent '{spec}'. Known aliases: "
                f"{sorted(ACP_AGENT_COMMANDS)}, or use acp:cmd:<command> "
                "or --acp_command."
            )
    if not argv:
        raise ValueError(f"Could not resolve ACP command from '{model_name}'")
    if acp_args:
        argv.extend(shlex.split(acp_args))
    return argv


def _acp_imports():
    try:
        import acp  # noqa: F401
        import acp.schema as schema
        from acp import RequestError, spawn_agent_process
        from acp.interfaces import Client
    except ImportError as e:
        raise ImportError(
            "The 'agent-client-protocol' package is required for acp: models. "
            "Install it with: pip install agent-client-protocol"
        ) from e
    return schema, RequestError, spawn_agent_process, Client


def _confined(path: str, root: str, must_exist: bool = False) -> str:
    """Resolve path against root; raises RequestError if it escapes."""
    _, RequestError, _, _ = _acp_imports()
    candidate = path if os.path.isabs(path) else os.path.join(root, path)
    resolved = os.path.realpath(candidate)
    if os.path.commonpath([resolved, root]) != root:
        raise RequestError.invalid_params(
            f"Path '{path}' is outside the ACP workspace '{root}'"
        )
    if must_exist and not os.path.exists(resolved):
        raise RequestError.invalid_params(f"Path '{path}' does not exist")
    return resolved


def _decode_buffer(buf: bytearray, truncated: bool) -> str:
    data = bytes(buf)
    if truncated:
        # Spec: truncation must land on a UTF-8 character boundary.
        start = 0
        while start < len(data) and (data[start] & 0b1100_0000) == 0b1000_0000:
            start += 1
        data = data[start:]
    return data.decode("utf-8", errors="replace")


class _Terminal:
    __slots__ = ("proc", "buffer", "limit", "truncated", "exit_status", "released")

    def __init__(self, proc, limit: int):
        self.proc = proc
        self.buffer = bytearray()
        self.limit = limit
        self.truncated = False
        self.exit_status = None
        self.released = False


def _make_client_class():
    """Build the acp.Client subclass (deferred so acp import stays optional)."""
    schema, RequestError, _, Client = _acp_imports()

    class PaperAcpClient(Client):
        def __init__(self, workspace_root, permission_mode, enable_terminal, verbose):
            self._root = workspace_root
            self._permission_mode = permission_mode
            self._enable_terminal = enable_terminal
            self._verbose = verbose
            self._buffers: Dict[str, List[str]] = {}
            self._terminals: Dict[str, _Terminal] = {}
            self._term_lock = asyncio.Lock()

        # --- turn bookkeeping -------------------------------------------------

        def begin_turn(self, session_id: str) -> None:
            self._buffers[session_id] = []

        def end_turn(self, session_id: str) -> str:
            return "".join(self._buffers.pop(session_id, []))

        # --- notifications ----------------------------------------------------

        async def session_update(self, session_id, update, **kwargs):
            kind = getattr(update, "session_update", None)
            if kind == "agent_message_chunk":
                content = getattr(update, "content", None)
                if getattr(content, "type", None) == "text":
                    self._buffers.setdefault(session_id, []).append(content.text)
            elif kind == "agent_thought_chunk" and self._verbose:
                content = getattr(update, "content", None)
                if getattr(content, "type", None) == "text":
                    print(f"  [acp thought] {content.text[:200]}")
            elif kind == "tool_call" and self._verbose:
                print(
                    f"  [acp tool] {getattr(update, 'title', '')} "
                    f"({getattr(update, 'kind', '')})"
                )

        # --- permissions --------------------------------------------------------

        async def request_permission(self, session_id, tool_call, options, **kwargs):
            tool_kind = getattr(tool_call, "kind", None) or "other"
            allowed_kinds = set(_ALLOW_KINDS)
            candidates = [
                o
                for o in options
                if getattr(o, "kind", None) in allowed_kinds
                and getattr(o, "option_id", "") not in _SKIPPED_OPTION_IDS
            ]

            grant = False
            if self._permission_mode == "auto":
                grant = True
            elif self._permission_mode == "read_only":
                grant = tool_kind in _READ_ONLY_KINDS

            if grant and candidates:
                candidates.sort(
                    key=lambda o: _ALLOW_KINDS.index(getattr(o, "kind", "allow_once"))
                    if getattr(o, "kind", None) in _ALLOW_KINDS
                    else len(_ALLOW_KINDS)
                )
                return schema.RequestPermissionResponse(
                    outcome=schema.AllowedOutcome(
                        outcome="selected", option_id=candidates[0].option_id
                    )
                )
            return schema.RequestPermissionResponse(
                outcome=schema.DeniedOutcome(outcome="cancelled")
            )

        # --- file system --------------------------------------------------------

        async def read_text_file(self, session_id, path, line=None, limit=None, **kwargs):
            resolved = _confined(path, self._root, must_exist=True)
            with open(resolved, "r", errors="replace") as f:
                if line is None:
                    content = f.read()
                else:
                    lines = f.readlines()[max(line - 1, 0):]
                    if limit is not None:
                        lines = lines[:limit]
                    content = "".join(lines)
            return schema.ReadTextFileResponse(content=content)

        async def write_text_file(self, session_id, path, content, **kwargs):
            resolved = _confined(path, self._root)
            os.makedirs(os.path.dirname(resolved), exist_ok=True)
            with open(resolved, "w") as f:
                f.write(content)
            return schema.WriteTextFileResponse()

        # --- terminals ----------------------------------------------------------

        async def create_terminal(
            self, session_id, command, args=None, env=None, cwd=None,
            output_byte_limit=None, **kwargs,
        ):
            if not self._enable_terminal:
                raise RequestError.method_not_found(
                    "Terminal capability is disabled (--acp_no_terminal)"
                )
            async with self._term_lock:
                live = sum(
                    1 for t in self._terminals.values() if t.proc.returncode is None
                )
                if live >= MAX_LIVE_TERMINALS:
                    raise RequestError.internal_error(
                        f"Too many live terminals ({MAX_LIVE_TERMINALS})"
                    )
                resolved_cwd = _confined(cwd, self._root) if cwd else self._root
                merged_env = dict(os.environ)
                for var in env or []:
                    merged_env[getattr(var, "name", "")] = getattr(var, "value", "")
                limit = min(
                    output_byte_limit or MAX_TERMINAL_OUTPUT_BYTES,
                    MAX_TERMINAL_OUTPUT_BYTES,
                )
                proc = await asyncio.create_subprocess_exec(
                    command,
                    *(args or []),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    cwd=resolved_cwd,
                    env=merged_env,
                )
                terminal_id = uuid.uuid4().hex
                term = _Terminal(proc, limit)
                self._terminals[terminal_id] = term
                asyncio.create_task(self._pump_terminal(term))
                return schema.CreateTerminalResponse(terminal_id=terminal_id)

        async def _pump_terminal(self, term: _Terminal) -> None:
            try:
                while True:
                    chunk = await term.proc.stdout.read(64 * 1024)
                    if not chunk:
                        break
                    term.buffer.extend(chunk)
                    if len(term.buffer) > term.limit:
                        del term.buffer[: len(term.buffer) - term.limit]
                        term.truncated = True
            finally:
                rc = await term.proc.wait()
                term.exit_status = schema.TerminalExitStatus(
                    exit_code=rc, signal=None
                )

        def _get_terminal(self, terminal_id: str) -> _Terminal:
            term = self._terminals.get(terminal_id)
            if term is None:
                raise RequestError.invalid_params(
                    f"Unknown terminal '{terminal_id}'"
                )
            return term

        async def terminal_output(self, session_id, terminal_id, **kwargs):
            term = self._get_terminal(terminal_id)
            return schema.TerminalOutputResponse(
                output=_decode_buffer(term.buffer, term.truncated),
                truncated=term.truncated,
                exit_status=term.exit_status,
            )

        async def wait_for_terminal_exit(self, session_id, terminal_id, **kwargs):
            term = self._get_terminal(terminal_id)
            await term.proc.wait()
            return schema.WaitForTerminalExitResponse(
                exit_code=term.proc.returncode, signal=None
            )

        async def kill_terminal(self, session_id, terminal_id, **kwargs):
            term = self._get_terminal(terminal_id)
            if term.proc.returncode is None:
                term.proc.kill()
            return schema.KillTerminalResponse()

        async def release_terminal(self, session_id, terminal_id, **kwargs):
            term = self._terminals.pop(terminal_id, None)
            if term is not None and term.proc.returncode is None:
                term.proc.kill()
            return schema.ReleaseTerminalResponse()

    return PaperAcpClient


class _AcpRuntime:
    """One ACP agent subprocess on a dedicated asyncio thread, per process."""

    _instances: Dict[tuple, "_AcpRuntime"] = {}
    _instances_lock = threading.Lock()

    def __init__(self, argv, workspace_root, permission_mode, enable_terminal, verbose):
        self._argv = argv
        self._workspace_root = workspace_root
        self._permission_mode = permission_mode
        self._enable_terminal = enable_terminal
        self._verbose = verbose
        self._loop = None
        self._conn = None
        self._proc = None
        self._ctx = None
        self._client = None
        self._thread = None
        self._call_lock = threading.Lock()
        self._started = threading.Event()
        self._start_error: Optional[BaseException] = None

    @classmethod
    def for_command(cls, argv, workspace_root, permission_mode, enable_terminal, verbose):
        key = (
            tuple(argv),
            os.path.realpath(workspace_root),
            permission_mode,
            enable_terminal,
        )
        with cls._instances_lock:
            rt = cls._instances.get(key)
            if rt is None or not rt.is_alive():
                rt = cls(argv, workspace_root, permission_mode, enable_terminal, verbose)
                rt.start()
                cls._instances[key] = rt
            return rt

    def is_alive(self) -> bool:
        return (
            self._thread is not None
            and self._thread.is_alive()
            and self._proc is not None
            and self._proc.returncode is None
        )

    def start(self) -> None:
        self._thread = threading.Thread(target=self._thread_main, daemon=True)
        self._thread.start()
        if not self._started.wait(timeout=180):
            raise TimeoutError(
                f"Timed out starting ACP agent: {' '.join(self._argv)}"
            )
        if self._start_error is not None:
            raise RuntimeError(
                f"Failed to start ACP agent '{' '.join(self._argv)}': "
                f"{self._start_error}"
            ) from self._start_error

    def _thread_main(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._connect())
        except BaseException as e:  # noqa: BLE001 - surfaced via start()
            self._start_error = e
        finally:
            self._started.set()
        self._loop.run_forever()
        self._loop.close()

    async def _connect(self) -> None:
        schema, _, spawn_agent_process, _ = _acp_imports()
        client_cls = _make_client_class()
        self._client = client_cls(
            self._workspace_root,
            self._permission_mode,
            self._enable_terminal,
            self._verbose,
        )
        self._ctx = spawn_agent_process(self._client, *self._argv)
        self._conn, self._proc = await self._ctx.__aenter__()
        await self._conn.initialize(
            protocol_version=acp_protocol_version(),
            client_capabilities=schema.ClientCapabilities(
                fs=schema.FileSystemCapabilities(
                    read_text_file=True, write_text_file=True
                ),
                terminal=self._enable_terminal,
            ),
            client_info=schema.Implementation(
                name="paper-orchestra", title="PaperOrchestra", version="1.0.0"
            ),
        )

    def call(self, blocks, cwd) -> str:
        with self._call_lock:
            future = asyncio.run_coroutine_threadsafe(
                self._prompt(blocks, cwd), self._loop
            )
            return future.result()

    async def _prompt(self, blocks, cwd) -> str:
        session = await self._conn.new_session(cwd=cwd, mcp_servers=[])
        session_id = session.session_id
        self._client.begin_turn(session_id)
        try:
            await self._conn.prompt(session_id=session_id, prompt=blocks)
            return self._client.end_turn(session_id)
        finally:
            self._client.end_turn(session_id)
            try:
                await self._conn.close_session(session_id=session_id)
            except Exception:
                pass

    def shutdown(self) -> None:
        proc = self._proc
        if proc is not None and proc.returncode is None:
            try:
                proc.kill()
            except Exception:
                pass
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)


def acp_protocol_version() -> int:
    import acp

    return getattr(acp, "PROTOCOL_VERSION", 1)


def _shutdown_all_runtimes() -> None:
    with _AcpRuntime._instances_lock:
        for rt in _AcpRuntime._instances.values():
            rt.shutdown()
        _AcpRuntime._instances.clear()


atexit.register(_shutdown_all_runtimes)


def _resource_link_for_path(path: str, schema) -> Any:
    abs_path = os.path.abspath(path)
    mime = None
    ext = os.path.splitext(abs_path)[1].lower()
    for m, e in _MIME_EXTENSIONS.items():
        if e == ext:
            mime = m
            break
    return schema.ResourceContentBlock(
        type="resource_link",
        uri=f"file://{abs_path}",
        name=os.path.basename(abs_path),
        mime_type=mime,
    )


def _blob_resource(data: bytes, mime_type: Optional[str], workspace: str, schema) -> Any:
    blob_dir = os.path.join(workspace, ".acp_blobs")
    os.makedirs(blob_dir, exist_ok=True)
    ext = _MIME_EXTENSIONS.get(mime_type or "", ".bin")
    path = os.path.join(blob_dir, f"{uuid.uuid4().hex}{ext}")
    with open(path, "wb") as f:
        f.write(data)
    return _resource_link_for_path(path, schema)


def _contents_to_blocks(contents, workspace: str, schema) -> List[Any]:
    """Convert google.genai Part/Content objects (or plain strings) to ACP blocks."""
    blocks: List[Any] = []

    def add_part(part) -> None:
        text = getattr(part, "text", None)
        if text:
            blocks.append(schema.TextContentBlock(type="text", text=text))
            return
        inline = getattr(part, "inline_data", None)
        if inline is not None and getattr(inline, "data", None):
            blocks.append(
                _blob_resource(
                    inline.data, getattr(inline, "mime_type", None), workspace, schema
                )
            )
            return
        file_data = getattr(part, "file_data", None)
        if file_data is not None and getattr(file_data, "file_uri", None):
            uri = file_data.file_uri
            if uri.startswith("file://"):
                blocks.append(_resource_link_for_path(uri[len("file://"):], schema))
            else:
                blocks.append(
                    schema.ResourceContentBlock(
                        type="resource_link",
                        uri=uri,
                        name=os.path.basename(uri),
                        mime_type=getattr(file_data, "mime_type", None),
                    )
                )
            return
        if isinstance(part, str):
            blocks.append(schema.TextContentBlock(type="text", text=part))

    def add_item(item) -> None:
        parts = getattr(item, "parts", None)
        if parts is not None:
            for p in parts:
                add_part(p)
        else:
            add_part(item)

    for item in contents or []:
        add_item(item)
    return blocks


def call_acp_agent(
    blocks_or_contents,
    model_name: str,
    acp_command: Optional[str] = None,
    acp_args: Optional[str] = None,
    workspace_root: Optional[str] = None,
    permission_mode: str = "auto",
    enable_terminal: bool = True,
    verbose: bool = False,
    contents_are_acp_blocks: bool = False,
    result_parsing_func: Optional[Callable] = None,
    check_parsed_response_not_none: bool = True,
    max_retries: int = 5,
    base_interval_sec: int = 5,
) -> Dict[str, Any]:
    """Send a prompt to an ACP agent; mirrors the gemini_utils call contract."""
    schema, _, _, _ = _acp_imports()
    workspace = os.path.realpath(workspace_root or _get_workspace_root())
    argv = resolve_acp_command(
        model_name,
        acp_command if acp_command is not None else _ACP_CONFIG.get("acp_command"),
        acp_args if acp_args is not None else _ACP_CONFIG.get("acp_args"),
    )
    permission_mode = (
        permission_mode
        if permission_mode != "auto"
        else _ACP_CONFIG.get("permission_mode", "auto")
    )
    enable_terminal = _ACP_CONFIG.get("enable_terminal", enable_terminal)
    verbose = _ACP_CONFIG.get("verbose", verbose)
    parser = result_parsing_func or (lambda r: r)

    if contents_are_acp_blocks:
        blocks = blocks_or_contents
    else:
        blocks = _contents_to_blocks(blocks_or_contents, workspace, schema)

    raw_response = None
    parsed_response = None
    for attempt in range(max_retries):
        try:
            runtime = _AcpRuntime.for_command(
                argv, workspace, permission_mode, enable_terminal, verbose
            )
            raw_response = runtime.call(blocks, workspace)
            parsed_response = parser(raw_response)
            if check_parsed_response_not_none:
                assert (
                    parsed_response is not None
                ), f"Parsed response is None. Raw response:\n{raw_response}"
            return {
                "raw_response": raw_response,
                "parsed_response": parsed_response,
            }
        except Exception as e:
            print(
                f"Warning: ACP call failed on attempt {attempt + 1} of "
                f"{max_retries}. Error: {e}"
            )
            with _AcpRuntime._instances_lock:
                for key, rt in list(_AcpRuntime._instances.items()):
                    if not rt.is_alive():
                        rt.shutdown()
                        del _AcpRuntime._instances[key]
            if attempt + 1 == max_retries:
                print("Error: All ACP retry attempts failed.")
                raise
            delay = base_interval_sec * (2 ** (attempt - 1)) if attempt > 0 else 0
            if delay > 0:
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
    return {"raw_response": raw_response, "parsed_response": parsed_response}


def call_acp_with_text_prompt(
    prompt: str,
    model_name: str,
    system_instruction: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    schema, _, _, _ = _acp_imports()
    blocks = []
    if system_instruction:
        blocks.append(
            schema.TextContentBlock(
                type="text", text=f"[System instruction]\n{system_instruction}"
            )
        )
    blocks.append(schema.TextContentBlock(type="text", text=prompt))
    return call_acp_agent(
        blocks, model_name, contents_are_acp_blocks=True, **kwargs
    )


def call_acp_with_images(
    prompt: str,
    images: List[str],
    model_name: str,
    system_instruction: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    schema, _, _, _ = _acp_imports()
    blocks = []
    if system_instruction:
        blocks.append(
            schema.TextContentBlock(
                type="text", text=f"[System instruction]\n{system_instruction}"
            )
        )
    blocks.append(schema.TextContentBlock(type="text", text=prompt))
    for image_path in images:
        blocks.append(_resource_link_for_path(image_path, schema))
    return call_acp_agent(
        blocks, model_name, contents_are_acp_blocks=True, **kwargs
    )


def call_acp_with_pdf(
    pdf_path: str,
    prompt: str,
    model_name: str,
    system_instruction: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    schema, _, _, _ = _acp_imports()
    blocks = [schema.TextContentBlock(type="text", text=prompt)]
    if system_instruction:
        blocks.insert(
            0,
            schema.TextContentBlock(
                type="text", text=f"[System instruction]\n{system_instruction}"
            ),
        )
    blocks.append(_resource_link_for_path(pdf_path, schema))
    return call_acp_agent(
        blocks, model_name, contents_are_acp_blocks=True, **kwargs
    )


def generate_diagram_with_acp(
    prompt: str,
    model_name: str,
    system_instruction: Optional[str] = None,
    aspect_ratio: str = "16:9",
    workspace_root: Optional[str] = None,
    max_retries: int = 5,
    base_interval_sec: int = 5,
) -> str:
    """Generate a diagram via an ACP agent and return it as a base64 string.

    ACP has no image-generation channel, so the agent is asked to render the
    image to disk inside the workspace (matplotlib, graphviz, PIL, etc.) and
    the resulting file is read back and base64-encoded, matching the return
    contract of generate_image_with_gemini.
    """
    import base64 as _base64

    schema, _, _, _ = _acp_imports()
    workspace = os.path.realpath(workspace_root or _get_workspace_root())
    blob_dir = os.path.join(workspace, ".acp_blobs")
    os.makedirs(blob_dir, exist_ok=True)
    output_path = os.path.join(blob_dir, f"diagram_{uuid.uuid4().hex}.png")

    instruction_lines = [
        f"Create a diagram image and save it to this exact path: {output_path}",
        f"Desired aspect ratio: {aspect_ratio}.",
        "Write and run code (e.g. Python matplotlib/PIL, graphviz, or another "
        "tool already available) to render it. Verify the file exists and is a "
        "valid image before finishing. Do not include figure titles in the "
        "image. Reply with only the output file path once done.",
    ]
    if system_instruction:
        instruction_lines.insert(0, f"[System instruction]\n{system_instruction}")

    blocks = [
        schema.TextContentBlock(type="text", text="\n".join(instruction_lines)),
        schema.TextContentBlock(type="text", text=prompt),
    ]

    for attempt in range(max_retries):
        try:
            call_acp_agent(
                blocks,
                model_name,
                workspace_root=workspace,
                contents_are_acp_blocks=True,
                max_retries=1,
            )
            if not os.path.isfile(output_path):
                raise RuntimeError(
                    f"ACP agent did not create the diagram file: {output_path}"
                )
            with open(output_path, "rb") as f:
                return _base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            print(
                f"Warning: ACP diagram generation failed on attempt "
                f"{attempt + 1} of {max_retries}. Error: {e}"
            )
            if attempt + 1 == max_retries:
                raise
            delay = base_interval_sec * (2 ** (attempt - 1)) if attempt > 0 else 0
            if delay > 0:
                time.sleep(delay)
    raise RuntimeError("All ACP diagram generation attempts failed.")
