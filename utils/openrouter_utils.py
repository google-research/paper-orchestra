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

"""OpenRouter backend.

When enabled (see `is_openrouter_enabled`), every Gemini and OpenAI call in the
codebase is transparently routed through OpenRouter's OpenAI-compatible API, so
a single OPENROUTER_API_KEY is enough to run the whole pipeline.

Gemini-style `contents` (strings / google.genai `types.Part` objects with text,
image or PDF bytes) are converted into OpenAI-style message content parts, the
Gemini Google Search tool is mapped to OpenRouter's `web` plugin, and image
generation uses OpenRouter's `modalities=["image", "text"]` output.
"""

import base64
import os
import threading
import time
from typing import Any, Callable, Optional

from dotenv import load_dotenv  # type: ignore
from openai import OpenAI, BadRequestError  # type: ignore

dot_file = os.path.join(os.path.dirname(__file__), "../.env")
load_dotenv(dot_file)

OPENROUTER_BASE_URL = os.environ.get(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
)

_openrouter_client = None
_openrouter_client_lock = threading.Lock()


def is_openrouter_enabled() -> bool:
    """OpenRouter is used when LLM_PROVIDER=openrouter, or when
    OPENROUTER_API_KEY is set and LLM_PROVIDER is not explicitly "native"."""
    provider = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if provider == "openrouter":
        return True
    if provider == "native":
        return False
    return bool(os.environ.get("OPENROUTER_API_KEY"))


def get_openrouter_client() -> OpenAI:
    global _openrouter_client
    if _openrouter_client is None:
        with _openrouter_client_lock:
            if _openrouter_client is None:
                api_key = os.environ.get("OPENROUTER_API_KEY")
                if not api_key:
                    raise ValueError(
                        "OPENROUTER_API_KEY must be set to use the OpenRouter backend."
                    )
                print("Using OpenRouter configuration.")
                _openrouter_client = OpenAI(
                    api_key=api_key,
                    base_url=OPENROUTER_BASE_URL,
                    default_headers={"X-Title": "PaperOrchestra"},
                )
    return _openrouter_client


def to_openrouter_model(model_name: str) -> str:
    """Maps bare model names (e.g. "gemini-3.1-pro-preview", "gpt-5") to
    OpenRouter slugs ("google/...", "openai/..."). Names that already contain a
    "/" are treated as OpenRouter slugs and passed through unchanged."""
    if "/" in model_name:
        return model_name
    lower = model_name.lower()
    if lower.startswith(("gemini", "gemma")):
        return f"google/{model_name}"
    if lower.startswith(("gpt", "o1", "o3", "o4", "chatgpt")):
        return f"openai/{model_name}"
    if lower.startswith("claude"):
        return f"anthropic/{model_name}"
    return model_name


# ---------------------------------------------------------------------------
# Content conversion (google.genai -> OpenAI chat format)
# ---------------------------------------------------------------------------


def _bytes_part(data: bytes, mime_type: str) -> dict:
    b64 = base64.b64encode(data).decode("utf-8")
    data_url = f"data:{mime_type};base64,{b64}"
    if mime_type == "application/pdf":
        return {
            "type": "file",
            "file": {"filename": "document.pdf", "file_data": data_url},
        }
    if mime_type.startswith("image/"):
        return {"type": "image_url", "image_url": {"url": data_url}}
    raise ValueError(f"Unsupported inline data mime type for OpenRouter: {mime_type}")


def gemini_contents_to_openai(contents: Any) -> list[dict]:
    """Converts Gemini `contents` (str, Part, Content, or a list of them) into a
    list of OpenAI-style content parts."""
    if contents is None:
        return []
    if isinstance(contents, (list, tuple)):
        parts: list[dict] = []
        for item in contents:
            parts.extend(gemini_contents_to_openai(item))
        return parts
    if isinstance(contents, str):
        return [{"type": "text", "text": contents}]
    if isinstance(contents, dict) and "type" in contents:
        return [contents]  # already OpenAI-style

    # google.genai types.Content
    if getattr(contents, "parts", None) is not None:
        return gemini_contents_to_openai(contents.parts)

    # google.genai types.Part
    text = getattr(contents, "text", None)
    if text is not None:
        return [{"type": "text", "text": text}]
    inline_data = getattr(contents, "inline_data", None)
    if inline_data is not None and inline_data.data is not None:
        return [_bytes_part(inline_data.data, inline_data.mime_type or "image/png")]

    raise ValueError(f"Unsupported content for OpenRouter: {type(contents)!r}")


def _merge_text_parts(parts: list[dict]) -> list[dict]:
    """Joins consecutive text parts to keep requests compact."""
    merged: list[dict] = []
    for p in parts:
        if p.get("type") == "text" and merged and merged[-1].get("type") == "text":
            merged[-1] = {"type": "text", "text": merged[-1]["text"] + "\n\n" + p["text"]}
        else:
            merged.append(dict(p))
    return merged


def _has_google_search(tools: Any) -> bool:
    for tool in tools or []:
        if getattr(tool, "google_search", None) is not None:
            return True
        if isinstance(tool, dict) and "google_search" in tool:
            return True
    return False


def _translate_generation_configs(generation_configs: Optional[dict]):
    """Returns (system_prompt, request_kwargs, extra_body)."""
    configs = dict(generation_configs or {})
    system_prompt = configs.pop("system_instruction", None)
    kwargs: dict = {}
    extra_body: dict = {}

    if "temperature" in configs:
        kwargs["temperature"] = configs.pop("temperature")
    if "top_p" in configs:
        kwargs["top_p"] = configs.pop("top_p")
    if "max_output_tokens" in configs:
        kwargs["max_tokens"] = configs.pop("max_output_tokens")
    if "max_tokens" in configs:
        kwargs["max_tokens"] = configs.pop("max_tokens")
    if "seed" in configs:
        kwargs["seed"] = configs.pop("seed")
    if "stop_sequences" in configs:
        kwargs["stop"] = configs.pop("stop_sequences")
    if "tools" in configs:
        tools = configs.pop("tools")
        if _has_google_search(tools):
            extra_body["plugins"] = [{"id": "web"}]

    if configs:
        print(
            f"Warning: OpenRouter backend ignoring unsupported generation configs: {sorted(configs)}"
        )
    return system_prompt, kwargs, extra_body


# ---------------------------------------------------------------------------
# Calls
# ---------------------------------------------------------------------------


def call_openrouter_with_content(
    content: list[dict],
    model_name: str,
    result_parsing_func: Callable,
    generation_configs: Optional[dict] = None,
    check_parsed_response_not_none: bool = True,
    max_retries: int = 5,
    base_interval_sec: int = 5,
    system_prompt: Optional[str] = None,
) -> dict:
    client = get_openrouter_client()
    or_model = to_openrouter_model(model_name)
    cfg_system, kwargs, extra_body = _translate_generation_configs(generation_configs)
    system_prompt = system_prompt or cfg_system

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": _merge_text_parts(content)})

    raw_response = None
    parsed_response = None
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=or_model,
                messages=messages,
                extra_body=extra_body or None,
                **kwargs,
            )
            if not response.choices:
                raise ValueError(f"Empty response from OpenRouter: {response}")
            raw_response = response.choices[0].message.content
            if raw_response is None:
                raise ValueError("OpenRouter returned no text content")
            parsed_response = result_parsing_func(raw_response)

            if check_parsed_response_not_none:
                assert (
                    parsed_response is not None
                ), f"Parsed response is None, Here is the raw response:\n{raw_response}"

            return {"raw_response": raw_response, "parsed_response": parsed_response}

        except BadRequestError as e:
            print(f"Error: OpenRouter rejected the request (model={or_model}): {e}")
            raise
        except Exception as e:
            print(
                f"Warning: OpenRouter API call (model={or_model}) failed on attempt {attempt + 1} of {max_retries}. Error: {e}"
            )
            if attempt + 1 == max_retries:
                print(f"Error: All {max_retries} retry attempts failed.")
                raise

            delay = base_interval_sec * (2 ** (attempt - 1)) if attempt > 0 else 0
            print(f"Retrying in {delay} seconds...")
            if delay > 0:
                time.sleep(delay)

    return {"raw_response": raw_response, "parsed_response": parsed_response}


def call_openrouter_with_gemini_contents(
    contents: Any,
    model_name: str,
    result_parsing_func: Callable,
    generation_configs: Optional[dict] = None,
    check_parsed_response_not_none: bool = True,
    max_retries: int = 5,
    base_interval_sec: int = 5,
) -> dict:
    return call_openrouter_with_content(
        content=gemini_contents_to_openai(contents),
        model_name=model_name,
        result_parsing_func=result_parsing_func,
        generation_configs=generation_configs,
        check_parsed_response_not_none=check_parsed_response_not_none,
        max_retries=max_retries,
        base_interval_sec=base_interval_sec,
    )


def generate_image_with_openrouter(
    model_name: str,
    prompt: str,
    aspect_ratio: str = "16:9",
    generation_configs: Optional[dict] = None,
    max_retries: int = 5,
    base_interval_sec: int = 5,
    save_path: Optional[str] = None,
) -> Optional[str]:
    """Generates an image via OpenRouter and returns it base64-encoded."""
    client = get_openrouter_client()
    or_model = to_openrouter_model(model_name)
    configs = dict(generation_configs or {})
    system_prompt = configs.pop("system_instruction", None)
    temperature = configs.pop("temperature", 0.7)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=or_model,
                messages=messages,
                temperature=temperature,
                extra_body={
                    "modalities": ["image", "text"],
                    "image_config": {"aspect_ratio": aspect_ratio},
                },
            )
            message = response.choices[0].message.model_dump()
            for image in message.get("images") or []:
                url = (image.get("image_url") or {}).get("url", "")
                if not url.startswith("data:"):
                    continue
                img_base64 = url.split(",", 1)[1]

                if save_path:
                    try:
                        os.makedirs(os.path.dirname(save_path), exist_ok=True)
                        with open(save_path, "wb") as fh:
                            fh.write(base64.b64decode(img_base64))
                        print(f"Image for prompt '{prompt}' saved to {save_path}")
                    except Exception as e:
                        print(f"Warning: Failed to save image to {save_path}: {e}")
                return img_base64
            raise ValueError("OpenRouter response contained no image")
        except Exception as e:
            print(f"Warning: OpenRouter image generation (model={or_model}) failed: {e}")
            if attempt + 1 == max_retries:
                print(
                    f"Error: All {max_retries} retry attempts failed for image generation."
                )
                break
            delay = base_interval_sec * (2 ** (attempt - 1)) if attempt > 0 else 0
            print(f"Retrying in {delay} seconds...")
            if delay > 0:
                time.sleep(delay)

    return None
