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

from typing import Any, Optional
import base64
import mimetypes
import os
import threading
import time

import anthropic  # type: ignore
from dotenv import load_dotenv  # type: ignore
from google.genai import types

from utils.gemini_utils import parse_gemini_json_results

dot_file = os.path.join(os.path.dirname(__file__), "../.env")
load_dotenv(dot_file)

_anthropic_client = None
_anthropic_client_lock = threading.Lock()

DEFAULT_MAX_TOKENS = 64000
_FALLBACK_MODEL_PREFIXES = (
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-sonnet-5-5",
    "claude-fable-5",
)
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
_DROPPED_CONFIG_KEYS = ("temperature", "top_p", "top_k")
_NON_RETRYABLE_ERRORS = (
    anthropic.BadRequestError,
    anthropic.AuthenticationError,
    anthropic.PermissionDeniedError,
    anthropic.NotFoundError,
)


class ClaudeRequestError(Exception):
    """A Claude request that should not be retried (refusal or unsupported config)."""


def get_anthropic_client() -> anthropic.Anthropic:
    """Returns a shared Anthropic client, creating it on first use.

    The client is created lazily so that ANTHROPIC_API_KEY is only required
    when a Claude model is actually called.
    """
    global _anthropic_client
    if _anthropic_client is None:
        with _anthropic_client_lock:
            if _anthropic_client is None:
                api_key = os.environ.get("ANTHROPIC_API_KEY")
                if not api_key:
                    raise ValueError("ANTHROPIC_API_KEY must be set to use Claude models.")
                _anthropic_client = anthropic.Anthropic(api_key=api_key)
    return _anthropic_client


def is_claude_model(model_name: str) -> bool:
    return model_name.lower().startswith("claude-")


def _b64(data: bytes) -> str:
    return base64.standard_b64encode(data).decode()


def gemini_contents_to_claude_blocks(contents) -> list[dict]:
    """Converts google-genai contents (str / Part / Content, or a list of them)
    into Anthropic content blocks, preserving order."""
    if not isinstance(contents, (list, tuple)):
        contents = [contents]

    blocks: list[dict] = []
    for item in contents:
        if isinstance(item, str):
            blocks.append({"type": "text", "text": item})
        elif isinstance(item, types.Content):
            blocks.extend(gemini_contents_to_claude_blocks(list(item.parts or [])))
        elif isinstance(item, types.Part):
            if item.text is not None:
                blocks.append({"type": "text", "text": item.text})
            elif item.inline_data is not None:
                mime = item.inline_data.mime_type or ""
                data = item.inline_data.data
                if mime.startswith("image/"):
                    blocks.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime,
                                "data": _b64(data),
                            },
                        }
                    )
                elif mime == "application/pdf":
                    blocks.append(
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": _b64(data),
                            },
                        }
                    )
                else:
                    raise ValueError(f"Unsupported mime type for Claude: '{mime}'")
            else:
                raise ValueError("Empty Part cannot be converted to a Claude block")
        else:
            raise ValueError(f"Unsupported content item type: {type(item)}")
    return blocks


def image_block_from_path(path: str) -> dict:
    media_type = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        data = f.read()
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": _b64(data)},
    }


def pdf_block_from_path(path: str) -> dict:
    with open(path, "rb") as f:
        data = f.read()
    return {
        "type": "document",
        "source": {
            "type": "base64",
            "media_type": "application/pdf",
            "data": _b64(data),
        },
    }


def _build_request_kwargs(model_name: str, generation_configs: Optional[dict]) -> dict:
    """Maps google-genai style generation_configs onto Messages API arguments."""
    kwargs: dict[str, Any] = {"max_tokens": DEFAULT_MAX_TOKENS}
    for k, v in (generation_configs or {}).items():
        if k == "system_instruction":
            if isinstance(v, str):
                kwargs["system"] = v
            else:
                kwargs["system"] = "\n".join(
                    b["text"] for b in gemini_contents_to_claude_blocks(v)
                )
        elif k in _DROPPED_CONFIG_KEYS:
            continue
        elif k == "max_output_tokens":
            kwargs["max_tokens"] = v
        else:
            raise ClaudeRequestError(
                f"generation_configs key '{k}' is not supported for Claude models"
            )
    return kwargs


def call_claude_with_content(
    content_blocks: list[dict],
    model_name: str,
    max_retries: int = 5,
    base_interval_sec: int = 5,
    result_parsing_func: callable = parse_gemini_json_results,
    generation_configs: Optional[dict] = None,
    check_parsed_response_not_none: bool = True,
):
    raw_response = None
    parsed_response = None

    # Raised before any API call (config errors, missing key).
    request_kwargs = _build_request_kwargs(model_name, generation_configs)
    client = get_anthropic_client()
    messages = [{"role": "user", "content": content_blocks}]

    for attempt in range(max_retries):
        try:
            if model_name.lower().startswith(_FALLBACK_MODEL_PREFIXES):
                stream_cm = client.beta.messages.stream(
                    model=model_name,
                    messages=messages,
                    betas=[_FALLBACK_BETA],
                    fallbacks="default",
                    **request_kwargs,
                )
            else:
                stream_cm = client.messages.stream(
                    model=model_name,
                    messages=messages,
                    **request_kwargs,
                )
            with stream_cm as stream:
                msg = stream.get_final_message()

            if msg.stop_reason == "refusal":
                raise ClaudeRequestError(
                    f"Claude refused the request (model={model_name}). "
                    f"stop_details: {msg.stop_details}"
                )
            if msg.stop_reason == "max_tokens":
                print(
                    f"Warning: Claude response (model={model_name}) was truncated at max_tokens."
                )

            # With server-side fallback, content can hold a partial answer from
            # the declining model, then a "fallback" block, then the full answer.
            # Keep only the text after the last fallback block.
            last_fallback = max(
                (i for i, b in enumerate(msg.content) if b.type == "fallback"),
                default=-1,
            )
            raw_response = "".join(
                block.text
                for block in msg.content[last_fallback + 1 :]
                if block.type == "text"
            )
            parsed_response = result_parsing_func(raw_response)

            if check_parsed_response_not_none:
                assert (
                    parsed_response is not None
                ), f"Parsed response is None, Here is the raw response:\n{raw_response}"

            return {
                "raw_response": raw_response,
                "parsed_response": parsed_response,
            }

        except (ClaudeRequestError,) + _NON_RETRYABLE_ERRORS as e:
            print(
                f"Warning: Claude API call (model={model_name}) failed with a non-retryable error. Error: {e}",
            )
            raise e

        except Exception as e:
            print(
                f"Warning: Claude API call (model={model_name}) failed on attempt {attempt + 1} of {max_retries}. Error: {e}",
            )

            if attempt + 1 == max_retries:
                print(f"Error: All {max_retries} retry attempts failed.")
                raise e

            delay = base_interval_sec * (2 ** (attempt - 1)) if attempt > 0 else 0
            print(f"Retrying in {delay} seconds...")
            if delay > 0:
                time.sleep(delay)

    print("Error: Exited retry loop unexpectedly.")
    return {
        "raw_response": raw_response,
        "parsed_response": parsed_response,
    }


def call_claude_with_text_prompt(
    prompt: str,
    model_name: str,
    result_parsing_func: callable = parse_gemini_json_results,
    generation_configs: Optional[dict] = None,
    check_parsed_response_not_none: bool = True,
    max_retries: int = 5,
    base_interval_sec: int = 5,
):
    return call_claude_with_content(
        content_blocks=[{"type": "text", "text": prompt}],
        model_name=model_name,
        max_retries=max_retries,
        base_interval_sec=base_interval_sec,
        result_parsing_func=result_parsing_func,
        generation_configs=generation_configs,
        check_parsed_response_not_none=check_parsed_response_not_none,
    )


def call_claude_with_contents(
    contents,
    model_name: str,
    max_retries: int = 5,
    base_interval_sec: int = 5,
    result_parsing_func: callable = parse_gemini_json_results,
    generation_configs: Optional[dict] = None,
    check_parsed_response_not_none: bool = True,
):
    return call_claude_with_content(
        content_blocks=gemini_contents_to_claude_blocks(contents),
        model_name=model_name,
        max_retries=max_retries,
        base_interval_sec=base_interval_sec,
        result_parsing_func=result_parsing_func,
        generation_configs=generation_configs,
        check_parsed_response_not_none=check_parsed_response_not_none,
    )


def call_claude_with_images(
    prompt: str,
    images: list[str],
    model_name: str,
    result_parsing_func: callable = parse_gemini_json_results,
    generation_configs: Optional[dict] = None,
    check_parsed_response_not_none: bool = True,
    max_retries: int = 5,
    base_interval_sec: int = 5,
):
    blocks = [{"type": "text", "text": prompt}]
    blocks.extend(image_block_from_path(p) for p in images)
    return call_claude_with_content(
        content_blocks=blocks,
        model_name=model_name,
        max_retries=max_retries,
        base_interval_sec=base_interval_sec,
        result_parsing_func=result_parsing_func,
        generation_configs=generation_configs,
        check_parsed_response_not_none=check_parsed_response_not_none,
    )


def call_claude_with_pdf(
    pdf_path: str,
    prompt: str,
    model_name: str,
    system_instruction: Optional[str] = None,
    result_parsing_func: callable = parse_gemini_json_results,
    generation_configs: Optional[dict] = None,
    check_parsed_response_not_none: bool = True,
    max_retries: int = 5,
    base_interval_sec: int = 5,
):
    configs = dict(generation_configs) if generation_configs else {}
    if system_instruction is not None:
        configs["system_instruction"] = system_instruction
    return call_claude_with_content(
        content_blocks=[pdf_block_from_path(pdf_path), {"type": "text", "text": prompt}],
        model_name=model_name,
        max_retries=max_retries,
        base_interval_sec=base_interval_sec,
        result_parsing_func=result_parsing_func,
        generation_configs=configs,
        check_parsed_response_not_none=check_parsed_response_not_none,
    )
