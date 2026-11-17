# Local addition (not upstream).
#
# Sends PaperOrchestra's LLM calls to a logged-in Claude Code or Codex CLI
# instead of the Gemini API, so they are billed to that subscription.
#
#   PAPER_LLM_BACKEND=claude | codex   (unset or "gemini" = Gemini API as upstream)
#   PAPER_CLI_MODEL                    model passed to the CLI (claude default: opus;
#                                      the claude CLI's own default may need paid credits)
#   PAPER_CLI_CONCURRENCY              max CLI sessions at once (default 3)
#   PAPER_CLI_TIMEOUT                  seconds per call (default 900)
#
# Hooked in at utils/gemini_utils.py:call_gemini_with_contents, which every
# Gemini call in the pipeline goes through (except image generation, which is
# only used by the plotting agent).

import json
import os
import shutil
import subprocess
import tempfile
import threading

_BACKENDS = ("claude", "codex")


class CliFatalError(RuntimeError):
    """Usage limit or auth problem: retrying will not help, so the caller should stop."""


_FATAL_MARKERS = (
    "usage credits", "usage limit", "rate_limit", "credits_required", "not logged in",
    "please log in", "login", "authentication", "quota",
)


def _raise_cli_error(msg: str):
    if any(m in msg.lower() for m in _FATAL_MARKERS):
        raise CliFatalError(msg)
    raise RuntimeError(msg)
_sem = None
_sem_lock = threading.Lock()
_count_lock = threading.Lock()
_calls = 0


def cli_backend() -> str:
    name = (os.getenv("PAPER_LLM_BACKEND") or "").strip().lower()
    return name if name in _BACKENDS else ""


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
            detail = str(json.loads(proc.stdout).get("result")) or detail
        except Exception:
            detail = detail[-800:]
        _raise_cli_error(f"{cmd[0]} exited {proc.returncode}: {detail}")
    return proc


def _call_claude(prompt, images, system, search, tmpdir, timeout) -> str:
    tools = ["Read"] + (["WebSearch", "WebFetch"] if search else [])
    cmd = [
        "claude", "-p",
        "--output-format", "json",
        "--no-session-persistence",
        "--strict-mcp-config",
        "--tools", ",".join(tools),
        "--allowedTools", ",".join(tools),
        "--add-dir", tmpdir,
    ]
    if system:
        cmd += ["--append-system-prompt", system]
    cmd += ["--model", os.getenv("PAPER_CLI_MODEL") or "opus"]
    if images:
        prompt += (
            "\n\nAttached images (use the Read tool to view each one before answering):\n"
            + "\n".join(images)
        )
    out = _run(cmd, prompt, tmpdir, timeout).stdout
    data = json.loads(out)
    if data.get("is_error"):
        _raise_cli_error(f"claude returned an error: {str(data.get('result'))[:800]}")
    return data.get("result") or ""


def _call_codex(prompt, images, system, search, tmpdir, timeout) -> str:
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
    if os.getenv("PAPER_CLI_MODEL"):
        cmd += ["-m", os.environ["PAPER_CLI_MODEL"]]
    cmd.append("-")  # read the prompt from stdin
    if system:
        prompt = f"<system_instructions>\n{system}\n</system_instructions>\n\n{prompt}"
    _run(cmd, prompt, tmpdir, timeout)
    with open(out_file) as f:
        return f.read()


def call_cli(contents, generation_configs: dict = None) -> str:
    """Run one LLM call through the configured CLI and return its text answer."""
    global _calls
    backend = cli_backend()
    generation_configs = generation_configs or {}
    system = generation_configs.get("system_instruction")
    if system is not None and not isinstance(system, str):
        system = str(system)
    search = _wants_search(generation_configs)
    timeout = int(os.getenv("PAPER_CLI_TIMEOUT", "900"))

    tmpdir = tempfile.mkdtemp(prefix="paper_cli_")
    try:
        prompt, images = _flatten(contents, tmpdir)
        with _semaphore():
            with _count_lock:
                _calls += 1
                n = _calls
            print(
                f"🤖 {backend} call {n}: {len(prompt):,} chars"
                f"{', ' + str(len(images)) + ' images' if images else ''}"
                f"{', web search' if search else ''}",
                flush=True,
            )
            fn = _call_claude if backend == "claude" else _call_codex
            return fn(prompt, images, system, search, tmpdir, timeout)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
