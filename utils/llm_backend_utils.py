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

import json
from typing import Optional, Callable, Dict, Any

from google.genai import types

from utils.gemini_utils import (
    call_gemini_with_text_prompt,
    parse_gemini_json_results,
    call_gemini_with_contents,
    call_gemini_with_images,
)
from utils.openai_utils import (
    call_openai_models_with_text_prompt,
    call_openai_models_with_content,
    parse_openai_json_results,
    get_openai_image_part_from_path,
)
from utils.pdf_utils import load_paper


def identity_parse(response: str):
    return response


def get_llm_parser(model_name: str, return_json: bool = True) -> Callable:
    if not return_json:
        return identity_parse

    if (
        "gpt" in model_name.lower()
        or "o1" in model_name.lower()
        or "o3" in model_name.lower()
    ):
        return parse_openai_json_results
    else:
        return parse_gemini_json_results


def call_llm_with_text_prompt(
    prompt: str,
    model_name: str,
    generation_configs: Optional[Dict[str, Any]] = None,
    check_parsed_response_not_none: bool = True,
    return_json: bool = True,
    result_parsing_func: Optional[Callable] = None,
) -> Dict[str, Any]:
    """
    Unified function to call either Gemini or OpenAI models based on the model_name.
    """
    parser = (
        result_parsing_func
        if result_parsing_func is not None
        else get_llm_parser(model_name, return_json)
    )

    if generation_configs is None:
        generation_configs = {}

    if (
        "gpt" in model_name.lower()
        or "o1" in model_name.lower()
        or "o3" in model_name.lower()
    ):
        system_prompt = None
        configs_for_openai = dict(generation_configs) if generation_configs else {}
        if "system_instruction" in configs_for_openai:
            system_prompt = configs_for_openai.pop("system_instruction")
        if "temperature" in configs_for_openai:
            configs_for_openai.pop("temperature")

        response_dict = call_openai_models_with_text_prompt(
            prompt=prompt,
            model_name=model_name,
            generation_configs=configs_for_openai,
            result_parsing_func=parser,
            check_parsed_response_not_none=check_parsed_response_not_none,
            system_prompt=system_prompt,
        )
        return response_dict
    else:
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
) -> Dict[str, Any]:
    """
    Unified function to call either Gemini or OpenAI models with images based on the model_name.
    """
    parser = (
        result_parsing_func
        if result_parsing_func is not None
        else get_llm_parser(model_name, return_json)
    )

    if generation_configs is None:
        generation_configs = {}

    if (
        "gpt" in model_name.lower()
        or "o1" in model_name.lower()
        or "o3" in model_name.lower()
    ):
        system_prompt = None
        # Copy to avoid side-effects on caller's dictionary
        configs_for_openai = dict(generation_configs) if generation_configs else {}
        if "system_instruction" in configs_for_openai:
            system_prompt = configs_for_openai.pop("system_instruction")
        if "temperature" in configs_for_openai:
            configs_for_openai.pop("temperature")

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
    else:
        response_dict = call_gemini_with_images(
            prompt=prompt,
            images=images,
            model_name=model_name,
            generation_configs=generation_configs,
            result_parsing_func=parser,
            check_parsed_response_not_none=check_parsed_response_not_none,
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
) -> Dict[str, Any]:
    """
    Unified function to evaluate a PDF.
    Passes raw PDF bytes to Gemini, and extracted text to OpenAI.
    """
    parser = (
        result_parsing_func
        if result_parsing_func is not None
        else get_llm_parser(model_name, return_json)
    )

    if (
        "gpt" in model_name.lower()
        or "o1" in model_name.lower()
        or "o3" in model_name.lower()
    ):
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
    else:
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
