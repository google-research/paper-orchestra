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

import base64
import json
from typing import Optional, Callable, Dict, Any

from google.genai import types

from utils.pdf_utils import load_paper

# Provider selection. "auto" keeps the historical behavior: the provider
# is picked from the model name. Set explicitly with set_model_provider(),
# for example from the --model_provider CLI flag. This is strictly
# optional: with "auto" and the default model names, routing is exactly
# the same as before this change.
MODEL_PROVIDERS = ("auto", "gemini", "openai", "openrouter")

_MODEL_PROVIDER = "auto"

# Example free model for OpenRouter. This is only a documented example,
# never a default: the default models stay the Gemini ones.
DEFAULT_FREE_MODEL = "google/gemma-4-26b-a4b-it:free"


def set_model_provider(provider: str) -> None:
    """Set the process-wide model provider override.

    Use "auto" to go back to picking the provider from the model name.
    """
    if provider not in MODEL_PROVIDERS:
        raise ValueError(
            f"Unknown model provider: {provider}. "
            f"Expected one of {MODEL_PROVIDERS}."
        )
    global _MODEL_PROVIDER
    _MODEL_PROVIDER = provider


def get_model_provider() -> str:
    """Return the current process-wide model provider override."""
    return _MODEL_PROVIDER


def resolve_model_provider(
    model_name: str, model_provider: Optional[str] = None
) -> str:
    """Pick the provider for a model name.

    An explicit provider always wins. In "auto" mode, a model name with
    a slash (OpenRouter ids look like vendor/model) routes to OpenRouter,
    a gpt/o1/o3 name routes to OpenAI, and anything else routes to
    Gemini, exactly as before. A Vertex AI resource path
    (projects/.../models/...) always stays on Gemini.
    """
    provider = model_provider or _MODEL_PROVIDER or "auto"
    if provider != "auto":
        return provider

    name = model_name or ""
    if name.startswith("projects/"):
        return "gemini"
    if "/" in name:
        return "openrouter"
    lowered = name.lower()
    if "gpt" in lowered or "o1" in lowered or "o3" in lowered:
        return "openai"
    return "gemini"


def identity_parse(response: str):
    return response


def get_llm_parser(
    model_name: str,
    return_json: bool = True,
    model_provider: Optional[str] = None,
) -> Callable:
    if not return_json:
        return identity_parse

    provider = resolve_model_provider(model_name, model_provider)
    if provider == "openrouter":
        from utils.openrouter_utils import parse_openrouter_json_results

        return parse_openrouter_json_results
    if provider == "openai":
        from utils.openai_utils import parse_openai_json_results

        return parse_openai_json_results
    from utils.gemini_utils import parse_gemini_json_results

    return parse_gemini_json_results


def _split_openai_configs(generation_configs: Dict[str, Any]):
    """Split Gemini-style configs into an OpenAI-style pair.

    Returns (configs_for_openai, system_prompt). The system instruction
    becomes a system prompt and temperature is dropped, matching the
    existing OpenAI path.
    """
    configs_for_openai = dict(generation_configs) if generation_configs else {}
    system_prompt = None
    if "system_instruction" in configs_for_openai:
        system_prompt = configs_for_openai.pop("system_instruction")
    if "temperature" in configs_for_openai:
        configs_for_openai.pop("temperature")
    return configs_for_openai, system_prompt


def _parts_to_openai_content(contents) -> list:
    """Convert Gemini-style contents to OpenAI chat content parts.

    Accepts plain strings, dicts that already look like OpenAI content
    parts, and google.genai types.Part objects (text, image bytes, and
    PDF bytes, whose text is extracted). Anything else raises a clear
    error instead of being sent silently.
    """
    if contents is None:
        return []
    if isinstance(contents, (str, dict)) or hasattr(contents, "text"):
        contents = [contents]

    openai_content = []
    for part in contents:
        if isinstance(part, str):
            openai_content.append({"type": "text", "text": part})
            continue
        if isinstance(part, dict):
            openai_content.append(part)
            continue
        text = getattr(part, "text", None)
        if text is not None:
            openai_content.append({"type": "text", "text": text})
            continue
        inline_data = getattr(part, "inline_data", None)
        if inline_data is not None:
            mime_type = getattr(inline_data, "mime_type", "") or ""
            data = getattr(inline_data, "data", b"")
            if mime_type == "application/pdf":
                import pymupdf

                doc = pymupdf.open(stream=data, filetype="pdf")
                pdf_text = "\n".join(page.get_text() for page in doc)
                openai_content.append({"type": "text", "text": pdf_text})
                continue
            encoded = base64.b64encode(data).decode("utf-8")
            openai_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                }
            )
            continue
        raise ValueError(
            f"Cannot convert content part of type {type(part)} to OpenAI format."
        )
    return openai_content


def call_llm_with_text_prompt(
    prompt: str,
    model_name: str,
    generation_configs: Optional[Dict[str, Any]] = None,
    check_parsed_response_not_none: bool = True,
    return_json: bool = True,
    result_parsing_func: Optional[Callable] = None,
    model_provider: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Unified function to call Gemini, OpenAI, or OpenRouter models based
    on the model name or the provider override.
    """
    parser = (
        result_parsing_func
        if result_parsing_func is not None
        else get_llm_parser(model_name, return_json, model_provider)
    )

    if generation_configs is None:
        generation_configs = {}

    provider = resolve_model_provider(model_name, model_provider)

    if provider == "openrouter":
        from utils.openrouter_utils import call_openrouter_models_with_text_prompt

        configs_for_openrouter, system_prompt = _split_openai_configs(
            generation_configs
        )
        response_dict = call_openrouter_models_with_text_prompt(
            prompt=prompt,
            model_name=model_name,
            generation_configs=configs_for_openrouter,
            result_parsing_func=parser,
            check_parsed_response_not_none=check_parsed_response_not_none,
            system_prompt=system_prompt,
        )
        return response_dict

    if provider == "openai":
        from utils.openai_utils import call_openai_models_with_text_prompt

        configs_for_openai, system_prompt = _split_openai_configs(generation_configs)
        response_dict = call_openai_models_with_text_prompt(
            prompt=prompt,
            model_name=model_name,
            generation_configs=configs_for_openai,
            result_parsing_func=parser,
            check_parsed_response_not_none=check_parsed_response_not_none,
            system_prompt=system_prompt,
        )
        return response_dict

    from utils.gemini_utils import call_gemini_with_text_prompt

    response_dict = call_gemini_with_text_prompt(
        prompt=prompt,
        model_name=model_name,
        generation_configs=generation_configs,
        result_parsing_func=parser,
        check_parsed_response_not_none=check_parsed_response_not_none,
    )
    return response_dict


def call_llm_with_images(
    prompt: str,
    images: list[str],
    model_name: str,
    generation_configs: Optional[Dict[str, Any]] = None,
    check_parsed_response_not_none: bool = True,
    return_json: bool = True,
    result_parsing_func: Optional[Callable] = None,
    model_provider: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Unified function to call Gemini, OpenAI, or OpenRouter models with
    images based on the model name or the provider override.
    """
    parser = (
        result_parsing_func
        if result_parsing_func is not None
        else get_llm_parser(model_name, return_json, model_provider)
    )

    if generation_configs is None:
        generation_configs = {}

    provider = resolve_model_provider(model_name, model_provider)

    if provider == "openrouter":
        from utils.openrouter_utils import (
            call_openrouter_models_with_content,
            get_openrouter_image_part_from_path,
        )

        configs_for_openrouter, system_prompt = _split_openai_configs(
            generation_configs
        )
        content = [{"type": "text", "text": prompt}]
        for image_path in images:
            content.extend(get_openrouter_image_part_from_path(image_path))

        response_dict = call_openrouter_models_with_content(
            content=content,
            model_name=model_name,
            generation_configs=configs_for_openrouter,
            result_parsing_func=parser,
            check_parsed_response_not_none=check_parsed_response_not_none,
            system_prompt=system_prompt,
        )
        return response_dict

    if provider == "openai":
        from utils.openai_utils import (
            call_openai_models_with_content,
            get_openai_image_part_from_path,
        )

        # Copy to avoid side-effects on caller's dictionary
        configs_for_openai, system_prompt = _split_openai_configs(generation_configs)

        content = [{"type": "text", "text": prompt}]
        for image_path in images:
            content.extend(get_openai_image_part_from_path(image_path))

        response_dict = call_openai_models_with_content(
            content=content,
            model_name=model_name,
            generation_configs=configs_for_openai,
            result_parsing_func=parser,
            check_parsed_response_not_none=check_parsed_response_not_none,
            system_prompt=system_prompt,
        )
        return response_dict

    from utils.gemini_utils import call_gemini_with_images

    response_dict = call_gemini_with_images(
        prompt=prompt,
        images=images,
        model_name=model_name,
        generation_configs=generation_configs,
        result_parsing_func=parser,
        check_parsed_response_not_none=check_parsed_response_not_none,
    )
    return response_dict


def call_llm_with_contents(
    contents,
    model_name: str,
    max_retries: int = 5,
    base_interval_sec: int = 5,
    result_parsing_func: Optional[Callable] = None,
    generation_configs: Optional[Dict[str, Any]] = None,
    check_parsed_response_not_none: bool = True,
    model_provider: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Unified function to call Gemini, OpenAI, or OpenRouter models with
    Gemini-style contents (plain strings or google.genai types.Part
    objects). The Gemini path passes contents through unchanged. The
    OpenAI and OpenRouter paths convert text parts, image parts, and PDF
    parts to OpenAI chat content.
    """
    parser = (
        result_parsing_func
        if result_parsing_func is not None
        else get_llm_parser(model_name, True, model_provider)
    )

    if generation_configs is None:
        generation_configs = {}

    provider = resolve_model_provider(model_name, model_provider)

    if provider == "openrouter":
        from utils.openrouter_utils import call_openrouter_models_with_content

        configs_for_openrouter, system_prompt = _split_openai_configs(
            generation_configs
        )
        response_dict = call_openrouter_models_with_content(
            content=_parts_to_openai_content(contents),
            model_name=model_name,
            generation_configs=configs_for_openrouter,
            result_parsing_func=parser,
            check_parsed_response_not_none=check_parsed_response_not_none,
            system_prompt=system_prompt,
            max_retries=max_retries,
            base_interval_sec=base_interval_sec,
        )
        return response_dict

    if provider == "openai":
        from utils.openai_utils import call_openai_models_with_content

        configs_for_openai, system_prompt = _split_openai_configs(generation_configs)
        response_dict = call_openai_models_with_content(
            content=_parts_to_openai_content(contents),
            model_name=model_name,
            generation_configs=configs_for_openai,
            result_parsing_func=parser,
            check_parsed_response_not_none=check_parsed_response_not_none,
            system_prompt=system_prompt,
            max_retries=max_retries,
            base_interval_sec=base_interval_sec,
        )
        return response_dict

    from utils.gemini_utils import call_gemini_with_contents

    response_dict = call_gemini_with_contents(
        contents=contents,
        model_name=model_name,
        result_parsing_func=parser,
        generation_configs=generation_configs,
        check_parsed_response_not_none=check_parsed_response_not_none,
        max_retries=max_retries,
        base_interval_sec=base_interval_sec,
    )
    return response_dict


def call_llm_with_pdf(
    pdf_path: str,
    prompt: str,
    model_name: str,
    system_instruction: Optional[str] = None,
    temperature: float = 0.7,
    check_parsed_response_not_none: bool = True,
    return_json: bool = True,
    result_parsing_func: Optional[Callable] = None,
    model_provider: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Unified function to evaluate a PDF.
    Passes raw PDF bytes to Gemini, and extracted text to OpenAI or
    OpenRouter.
    """
    parser = (
        result_parsing_func
        if result_parsing_func is not None
        else get_llm_parser(model_name, return_json, model_provider)
    )

    provider = resolve_model_provider(model_name, model_provider)

    if provider == "openrouter":
        from utils.openrouter_utils import call_openrouter_models_with_text_prompt

        paper_text = load_paper(pdf_path, min_size=100)
        full_prompt = f"Paper Content:\n{paper_text}\n\nTask:\n{prompt}"

        generation_configs = {}
        response_dict = call_openrouter_models_with_text_prompt(
            prompt=full_prompt,
            model_name=model_name,
            generation_configs=generation_configs,
            result_parsing_func=parser,
            check_parsed_response_not_none=check_parsed_response_not_none,
            system_prompt=system_instruction,
        )
        return response_dict

    if provider == "openai":
        from utils.openai_utils import call_openai_models_with_text_prompt

        paper_text = load_paper(pdf_path, min_size=100)
        full_prompt = f"Paper Content:\n{paper_text}\n\nTask:\n{prompt}"

        generation_configs = {}
        response_dict = call_openai_models_with_text_prompt(
            prompt=full_prompt,
            model_name=model_name,
            generation_configs=generation_configs,
            result_parsing_func=parser,
            check_parsed_response_not_none=check_parsed_response_not_none,
            system_prompt=system_instruction,
        )
        return response_dict

    from utils.gemini_utils import call_gemini_with_contents

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    contents = [
        types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
        types.Part.from_text(text=prompt),
    ]

    generation_configs = {"temperature": temperature}
    if system_instruction is not None:
        generation_configs["system_instruction"] = system_instruction

    response_dict = call_gemini_with_contents(
        contents=contents,
        model_name=model_name,
        generation_configs=generation_configs,
        result_parsing_func=parser,
        check_parsed_response_not_none=check_parsed_response_not_none,
    )
    return response_dict
