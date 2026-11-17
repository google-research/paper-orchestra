"""Claude Messages adapter. Credentials stay in the environment, never in logs."""

import base64
import json
import mimetypes
import math
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5-5")
_client = None
_client_lock = threading.Lock()


def validate_model(model_name):
    if not isinstance(model_name, str) or not model_name.startswith("claude-"):
        raise ValueError("This fork uses Claude only; supply a claude-* model ID")


def get_anthropic_client():
    global _client
    with _client_lock:
        if _client is None:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise ValueError("Set ANTHROPIC_API_KEY in your environment or private .env")
            from anthropic import Anthropic
            # The SDK honors ANTHROPIC_BASE_URL and standard HTTPS_PROXY variables.
            _client = Anthropic(timeout=600.0, max_retries=2)
    return _client


def text_part(text):
    return {"type": "text", "text": text}


def bytes_part(data, mime_type):
    if mime_type == "application/pdf":
        kind = "document"
    elif mime_type in {"image/png", "image/jpeg", "image/gif", "image/webp"}:
        kind = "image"
    else:
        raise ValueError(f"Unsupported Claude input media type: {mime_type}")
    return {"type": kind, "source": {
        "type": "base64", "media_type": mime_type,
        "data": base64.b64encode(data).decode("ascii"),
    }}


def image_part(path):
    return bytes_part(Path(path).read_bytes(), mimetypes.guess_type(str(path))[0])


def _configured_prices():
    raw_in = os.environ.get("ANTHROPIC_PRICE_INPUT_PER_MILLION")
    raw_out = os.environ.get("ANTHROPIC_PRICE_OUTPUT_PER_MILLION")
    if not raw_in and not raw_out:
        return None
    if not raw_in or not raw_out:
        raise ValueError("Configure both Anthropic input and output prices, or neither")
    prices = (float(raw_in), float(raw_out))
    if any(not math.isfinite(value) or value < 0 for value in prices):
        raise ValueError("Anthropic prices must be finite and nonnegative")
    return prices


def _log_usage(response, model_name, request_id=None, prices=None):
    usage = response.usage
    usage_data = usage.model_dump() if hasattr(usage, "model_dump") else dict(usage)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model_name, "resolved_model": response.model,
        "response_id": response.id,
        "request_id": request_id or getattr(response, "_request_id", None),
        "stop_reason": response.stop_reason, "usage": usage_data,
    }
    if prices is not None:
        record["cost_usd"] = (
            usage_data.get("input_tokens", 0) * prices[0]
            + usage_data.get("output_tokens", 0) * prices[1]
        ) / 1_000_000
    destination = os.environ.get("PAPER_ORCHESTRA_USAGE_LOG")
    if destination:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, (json.dumps(record) + "\n").encode("utf-8"))
        finally:
            os.close(fd)
    return record


def call_claude_with_contents(
    contents, model_name=DEFAULT_MODEL, generation_configs=None,
    result_parsing_func=None, check_parsed_response_not_none=True,
):
    validate_model(model_name)
    prices = _configured_prices()
    config = dict(generation_configs or {})
    system = config.pop("system_instruction", None)
    max_tokens = int(config.pop("max_tokens", os.environ.get("ANTHROPIC_MAX_TOKENS", 16384)))
    # Legacy prompts specify temperature. Newer Claude models restrict sampling
    # controls, so only an explicit environment override forwards this parameter.
    config.pop("temperature", None)
    if config:
        raise ValueError(f"Unsupported Claude generation options: {', '.join(sorted(config))}")
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    if isinstance(contents, (str, dict)):
        contents = [contents]
    parts = [text_part(part) if isinstance(part, str) else part for part in contents]
    if not parts or any(not isinstance(part, dict) for part in parts):
        raise ValueError("contents must contain text or Claude content blocks")
    parts = [part for part in parts if part.get("type") != "text" or part.get("text", "").strip()]
    if not parts:
        raise ValueError("Cannot send empty content")
    kwargs = {"model": model_name, "max_tokens": max_tokens,
              "messages": [{"role": "user", "content": parts}]}
    if system:
        kwargs["system"] = system
    if os.environ.get("ANTHROPIC_TEMPERATURE"):
        kwargs["temperature"] = float(os.environ["ANTHROPIC_TEMPERATURE"])
    client = get_anthropic_client()
    with client.messages.stream(**kwargs) as stream:
        response = stream.get_final_message()
        request_id = stream.response.headers.get("request-id")
    record = _log_usage(response, model_name, request_id=request_id, prices=prices)
    if response.stop_reason not in {"end_turn", "stop_sequence"}:
        raise ValueError(f"Claude response is incomplete: stop_reason={response.stop_reason}")
    raw = "\n".join(block.text for block in response.content if block.type == "text")
    if not raw.strip():
        raise ValueError("Claude returned no text")
    parsed = result_parsing_func(raw) if result_parsing_func else raw
    if check_parsed_response_not_none and parsed is None:
        raise ValueError("Claude output did not match the requested response format")
    return {"raw_response": raw, "parsed_response": parsed, **record}
