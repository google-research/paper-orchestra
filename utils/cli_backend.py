# Local addition (not upstream).
#
# Sends PaperOrchestra's LLM calls to a logged-in Claude Code or Codex CLI
# instead of the Gemini API, so they are billed to that subscription.
#
#   PAPER_LLM_BACKEND=claude | codex   (unset or "gemini" = Gemini API as upstream)
#   PAPER_CLI_MODEL                    model for the main backend (claude default: opus;
#                                      the claude CLI's own default may need paid credits)
#   PAPER_CLI_SEARCH_MODEL             model for literature-search calls (claude default: sonnet;
#                                      there are 100+ of them per paper)
#   PAPER_CLI_CONCURRENCY              max CLI sessions at once (default 3)
#   PAPER_CLI_TIMEOUT                  seconds per call (default 900)
#
# When a usage limit is hit (e.g. Claude's 5-hour limit):
#   PAPER_CLI_FALLBACK=codex|claude    switch to the other CLI for the rest of the run
#   PAPER_CLI_FALLBACK_MODEL           model for the fallback CLI (optional)
#   PAPER_CLI_ON_LIMIT=wait|stop       otherwise wait for the limit to reset (default) or stop
#   PAPER_CLI_WAIT_MINUTES             minutes between retries while waiting (default 10)
#   PAPER_CLI_MAX_WAIT_HOURS           give up after waiting this long in total (default 6)
#
# Hooked in at utils/gemini_utils.py:call_gemini_with_contents, which every
# Gemini call in the pipeline goes through (except image generation, which is
# only used by the plotting agent).

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time

_BACKENDS = ("claude", "codex")


class CliFatalError(RuntimeError):
    """Login problem, or a usage limit we gave up waiting for: the run must stop."""


class CliLimitError(RuntimeError):
    """The CLI's usage limit was hit; waiting or switching CLI may help."""


_LIMIT_RE = re.compile(
    r"hit your .*limit|out of usage|usage limit|usage credits|credits_required|"
    r"\d+-hour limit|weekly limit|rate.?limit|quota|too many requests|resets? (at |in )?\d",
    re.IGNORECASE,
)
_AUTH_RE = re.compile(
    r"not logged in|please log ?in|run /login|authentication|unauthori[sz]ed|invalid api key",
    re.IGNORECASE,
)


def _raise_cli_error(msg: str):
    if _AUTH_RE.search(msg):
        raise CliFatalError(msg)
    if _LIMIT_RE.search(msg):
        raise CliLimitError(msg)
    raise RuntimeError(msg)


_sem = None
_sem_lock = threading.Lock()
_state_lock = threading.Lock()
_calls = 0
_active = None  # backend in use; may switch to the fallback after a limit
_waited_s = 0.0


def cli_backend() -> str:
    name = (os.getenv("PAPER_LLM_BACKEND") or "").strip().lower()
    return name if name in _BACKENDS else ""


def _active_backend() -> str:
    global _active
    with _state_lock:
        if _active is None:
            _active = cli_backend()
        return _active


def _model_for(backend: str, search: bool):
    primary = backend == cli_backend()
    if search and os.getenv("PAPER_CLI_SEARCH_MODEL"):
        return os.environ["PAPER_CLI_SEARCH_MODEL"]
    model = os.getenv("PAPER_CLI_MODEL" if primary else "PAPER_CLI_FALLBACK_MODEL") or None
    if backend == "claude":
        if search and not os.getenv("PAPER_CLI_SEARCH_MODEL"):
            return "sonnet"
        return model or "opus"
    return model


def _semaphore():
    global _sem
    with _sem_lock:
        if _sem is None:
            _sem = threading.Semaphore(int(os.getenv("PAPER_CLI_CONCURRENCY", "3")))
    return _sem


def _pdf_to_text(data: bytes, tmpdir: str, idx: int) -> str:
    path = os.path.join(tmpdir, f"attachment_{idx}.pdf")
    with open(path, "wb") as f:
        f.write(data)
    from utils.pdf_utils import load_paper  # lazy: avoids an import cycle

    return load_paper(path, min_size=100)


def _flatten(contents, tmpdir: str):
    """Turn Gemini `contents` into (prompt text, list of image paths)."""
    if not isinstance(contents, (list, tuple)):
        contents = [contents]
    texts, images = [], []
    for idx, part in enumerate(contents):
        if isinstance(part, str):
            texts.append(part)
            continue
        text = getattr(part, "text", None)
        if text:
            texts.append(text)
            continue
        blob = getattr(part, "inline_data", None)
        if blob is None or blob.data is None:
            continue
        mime = blob.mime_type or ""
        if mime == "application/pdf":
            texts.append(
                "--- Attached PDF (text extracted) ---\n"
                + _pdf_to_text(blob.data, tmpdir, idx)
                + "\n--- End of attached PDF ---"
            )
        elif mime.startswith("image/"):
            ext = mime.split("/", 1)[1].replace("jpeg", "jpg")
            path = os.path.join(tmpdir, f"image_{idx}.{ext}")
            with open(path, "wb") as f:
                f.write(blob.data)
            images.append(path)
    return "\n\n".join(texts), images


def _wants_search(generation_configs: dict) -> bool:
    for tool in generation_configs.get("tools") or []:
        if getattr(tool, "google_search", None) is not None:
            return True
        if isinstance(tool, dict) and "google_search" in tool:
            return True
    return False


def _run(cmd, prompt: str, cwd: str, timeout: int) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        cmd,
        input=prompt,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=timeout,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        try:  # claude -p --output-format json puts the reason in "result"
            data = json.loads(proc.stdout)
            detail = f"{data.get('result')} {data.get('api_error_code') or ''}".strip() or detail
        except Exception:
            detail = detail[-800:]
        _raise_cli_error(f"{cmd[0]} exited {proc.returncode}: {detail}")
    return proc


def _call_claude(prompt, images, system, search, model, tmpdir, timeout) -> str:
    tools = ["Read"] + (["WebSearch", "WebFetch"] if search else [])
    cmd = [
        "claude", "-p",
        "--output-format", "json",
        "--no-session-persistence",
        "--strict-mcp-config",
        "--tools", ",".join(tools),
        "--allowedTools", ",".join(tools),
        "--add-dir", tmpdir,
        "--model", model,
    ]
    if system:
        cmd += ["--append-system-prompt", system]
    if images:
        prompt += (
            "\n\nAttached images (use the Read tool to view each one before answering):\n"
            + "\n".join(images)
        )
    out = _run(cmd, prompt, tmpdir, timeout).stdout
    data = json.loads(out)
    if data.get("is_error"):
        _raise_cli_error(
            f"claude returned an error: {str(data.get('result'))[:800]} {data.get('api_error_code') or ''}"
        )
    return data.get("result") or ""


def _call_codex(prompt, images, system, search, model, tmpdir, timeout) -> str:
    out_file = os.path.join(tmpdir, "last_message.txt")
    cmd = ["codex"] + (["--search"] if search else []) + [
        "exec",
        "--skip-git-repo-check",
        "--ephemeral",
        "-s", "read-only",
        "-C", tmpdir,
        "-o", out_file,
    ]
    for img in images:
        cmd += ["-i", img]
    if model:
        cmd += ["-m", model]
    cmd.append("-")  # read the prompt from stdin
    if system:
        prompt = f"<system_instructions>\n{system}\n</system_instructions>\n\n{prompt}"
    _run(cmd, prompt, tmpdir, timeout)
    with open(out_file) as f:
        return f.read()


def _handle_limit(backend: str, err: Exception) -> None:
    """Decide what to do after a usage limit: switch CLI, wait, or stop (raise)."""
    global _active, _waited_s
    fallback = (os.getenv("PAPER_CLI_FALLBACK") or "").strip().lower()
    with _state_lock:
        if _active != backend:  # another thread already switched
            return
        if fallback in _BACKENDS and fallback != backend and backend == cli_backend():
            _active = fallback
            print(f"\n🔁 {backend} hit its usage limit; switching to {fallback} for the rest of the run.\n"
                  f"   ({err})", flush=True)
            return

    if (os.getenv("PAPER_CLI_ON_LIMIT") or "wait").strip().lower() != "wait":
        raise CliFatalError(f"{err}\nStopped (PAPER_CLI_ON_LIMIT=stop). Rerun later with --resume.")

    wait_s = float(os.getenv("PAPER_CLI_WAIT_MINUTES", "10")) * 60
    max_s = float(os.getenv("PAPER_CLI_MAX_WAIT_HOURS", "6")) * 3600
    with _state_lock:
        if _waited_s >= max_s:
            raise CliFatalError(
                f"{err}\nGave up after waiting {_waited_s / 3600:.1f} h. Rerun later with --resume."
            )
        _waited_s += wait_s
        total = _waited_s
    print(f"\n⏳ {backend} usage limit: {err}\n   Waiting {wait_s / 60:.0f} min, then retrying "
          f"(waited {total / 3600:.1f} h of {max_s / 3600:.0f} h max). Ctrl+C is safe: rerun with --resume.",
          flush=True)
    time.sleep(wait_s)


def call_cli(contents, generation_configs: dict = None) -> str:
    """Run one LLM call through the configured CLI and return its text answer."""
    global _calls
    generation_configs = generation_configs or {}
    system = generation_configs.get("system_instruction")
    if system is not None and not isinstance(system, str):
        system = str(system)
    search = _wants_search(generation_configs)
    timeout = int(os.getenv("PAPER_CLI_TIMEOUT", "900"))

    tmpdir = tempfile.mkdtemp(prefix="paper_cli_")
    try:
        prompt, images = _flatten(contents, tmpdir)
        while True:
            backend = _active_backend()
            model = _model_for(backend, search)
            try:
                with _semaphore():
                    with _state_lock:
                        _calls += 1
                        n = _calls
                    print(
                        f"🤖 {backend}{'/' + model if model else ''} call {n}: {len(prompt):,} chars"
                        f"{', ' + str(len(images)) + ' images' if images else ''}"
                        f"{', web search' if search else ''}",
                        flush=True,
                    )
                    fn = _call_claude if backend == "claude" else _call_codex
                    return fn(prompt, images, system, search, model, tmpdir, timeout)
            except CliLimitError as err:
                _handle_limit(backend, err)  # raises CliFatalError when it is time to stop
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
