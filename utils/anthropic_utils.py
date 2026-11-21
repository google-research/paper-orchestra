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

"""Anthropic (Claude) backend, with the same return contract as the OpenAI and Gemini backends."""

import base64
import mimetypes
import os
import threading
import time
from typing import Any, Callable, Optional

import anthropic
from dotenv import load_dotenv

from utils.openai_utils import parse_openai_json_results

dot_file = os.path.join(os.path.dirname(__file__), "../.env")
load_dotenv(dot_file)

DEFAULT_MAX_TOKENS = 64000
PDF_MAX_BYTES = 32 * 1024 * 1024  # request size limit of the Messages API
IMAGE_MEDIA_TYPES = ("image/jpeg", "image/png", "image/gif", "image/webp")
# Models whose safety classifiers can decline a request; for these the API can re-run the request on a
# fallback model inside the same call (https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback).
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = (
    "claude-fable-5-2",
    "claude-fable-5-1",
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-sonnet-5-5",
)
# Errors that a retry cannot fix: bad request, bad credentials, missing permission, unknown model.
NON_RETRYABLE_ERRORS = (
    anthropic.BadRequestError,
    anthropic.AuthenticationError,
    anthropic.PermissionDeniedError,
    anthropic.NotFoundError,
)

_anthropic_client = None
_anthropic_client_lock = threading.Lock()


class AnthropicRefusalError(RuntimeError):
    """The model declined the request (stop_reason == "refusal")."""


def is_anthropic_model(model_name: str) -> bool:
    return "claude" in model_name.lower()


def get_anthropic_client() -> anthropic.Anthropic:
    """Returns a shared Anthropic client, creating it on first use.

    The client is created lazily so that credentials are only required when a Claude model is actually
    called. The SDK resolves them itself (ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN or an `ant auth login` profile).
    """
    global _anthropic_client
    if _anthropic_client is None:
        with _anthropic_client_lock:
            if _anthropic_client is None:
                _anthropic_client = anthropic.Anthropic()
    return _anthropic_client


def get_anthropic_image_part_from_path(image_path: str) -> list[dict[str, Any]]:
    media_type = mimetypes.guess_type(image_path)[0]
    if media_type not in IMAGE_MEDIA_TYPES:
        raise ValueError(
            f"Unsupported image type {media_type!r} for {image_path}; expected one of {IMAGE_MEDIA_TYPES}."
        )
    with open(image_path, "rb") as image_file:
        data = base64.standard_b64encode(image_file.read()).decode("utf-8")
    return [{"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}]


def get_anthropic_pdf_part_from_path(pdf_path: str) -> list[dict[str, Any]]:
    size = os.path.getsize(pdf_path)
    if size > PDF_MAX_BYTES:
        raise ValueError(f"{pdf_path} has {size} bytes; the Messages API accepts PDFs up to {PDF_MAX_BYTES}.")
    with open(pdf_path, "rb") as pdf_file:
        data = base64.standard_b64encode(pdf_file.read()).decode("utf-8")
    return [{"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": data}}]


def build_anthropic_request(
    content: list[Any],
    model_name: str,
    generation_configs: Optional[dict] = None,
    system_prompt: Optional[str] = None,
) -> dict[str, Any]:
    """Keyword arguments of `client.beta.messages.stream` for one user turn.

    `generation_configs` accepts `max_tokens` and `effort`; other keys (e.g. the `temperature` that the callers
    pass to Gemini) are not parameters of current Claude models and are ignored.
    """
    configs = generation_configs or {}
    request = {
        "model": model_name,
        "max_tokens": configs.get("max_tokens", DEFAULT_MAX_TOKENS),
        "messages": [{"role": "user", "content": content}],
    }
    if system_prompt:
        request["system"] = system_prompt
    if configs.get("effort"):
        request["output_config"] = {"effort": configs["effort"]}
    if model_name in FALLBACK_MODELS:
        request["betas"] = [FALLBACK_BETA]
        request["fallbacks"] = "default"
    return request


def text_of_message(message: Any) -> str:
    """Text of a Messages API response. Raises if the model refused or the output was cut."""
    if message.stop_reason == "refusal":
        details = getattr(message, "stop_details", None)
        raise AnthropicRefusalError(
            f"The model declined the request (category={getattr(details, 'category', None)!r})."
        )
    if message.stop_reason == "max_tokens":
        raise ValueError("The response hit max_tokens before finishing; raise max_tokens in generation_configs.")
    return "".join(block.text for block in message.content if block.type == "text")


def call_anthropic_with_content(
    content: list[Any],
    model_name: str,
    max_retries: int = 5,
    base_interval_sec: int = 5,
    result_parsing_func: Callable = parse_openai_json_results,
    generation_configs: Optional[dict] = None,
    check_parsed_response_not_none: bool = True,
    system_prompt: Optional[str] = None,
    client: Optional[anthropic.Anthropic] = None,
) -> dict[str, Any]:
    """Calls a Claude model; returns {"raw_response", "parsed_response"} like the other backends.

    The SDK already retries rate limits, server errors and connection errors. The loop here covers what is
    left: a response that does not parse. `client` is injectable for tests.
    """
    client = client or get_anthropic_client()
    request = build_anthropic_request(content, model_name, generation_configs, system_prompt)

    for attempt in range(max_retries):
        try:
            # Streaming keeps long generations under the HTTP timeout.
            with client.beta.messages.stream(**request) as stream:
                message = stream.get_final_message()
            raw_response = text_of_message(message)
            parsed_response = result_parsing_func(raw_response)
            if check_parsed_response_not_none:
                assert (
                    parsed_response is not None
                ), f"Parsed response is None, Here is the raw response:\n{raw_response}"
            return {"raw_response": raw_response, "parsed_response": parsed_response}
        except (*NON_RETRYABLE_ERRORS, AnthropicRefusalError):
            raise
        except Exception as e:
            print(
                f"Warning: Anthropic API call (model={model_name}) failed on attempt {attempt + 1} of {max_retries}. Error: {e}",
            )
            if attempt + 1 == max_retries:
                print(f"Error: All {max_retries} retry attempts failed.")
                raise
            delay = base_interval_sec * (2 ** (attempt - 1)) if attempt > 0 else 0
            print(f"Retrying in {delay} seconds...")
            if delay > 0:
                time.sleep(delay)

    raise ValueError(f"max_retries must be at least 1, got {max_retries}")


def call_anthropic_with_text_prompt(
    prompt: str,
    model_name: str,
    result_parsing_func: Callable = parse_openai_json_results,
    generation_configs: Optional[dict] = None,
    check_parsed_response_not_none: bool = True,
    max_retries: int = 5,
    base_interval_sec: int = 5,
    system_prompt: Optional[str] = None,
    client: Optional[anthropic.Anthropic] = None,
) -> dict[str, Any]:
    return call_anthropic_with_content(
        content=[{"type": "text", "text": prompt}],
        model_name=model_name,
        result_parsing_func=result_parsing_func,
        generation_configs=generation_configs,
        check_parsed_response_not_none=check_parsed_response_not_none,
        max_retries=max_retries,
        base_interval_sec=base_interval_sec,
        system_prompt=system_prompt,
        client=client,
    )
