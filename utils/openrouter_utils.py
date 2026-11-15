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

from typing import Any
import re
import json
import time
import os
import base64

from openai import OpenAI  # type: ignore
from dotenv import load_dotenv  # type: ignore

dot_file = os.path.join(os.path.dirname(__file__), "../.env")
load_dotenv(dot_file)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

_openrouter_client = None


def get_openrouter_client():
    """Return the shared OpenRouter client, creating it on first use.

    The client is created lazily so that importing this module never
    requires OPENROUTER_API_KEY. The key is only required when an
    OpenRouter model is actually called.
    """
    global _openrouter_client
    if _openrouter_client is None:
        openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        if not openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY must be set.")
        _openrouter_client = OpenAI(
            api_key=openrouter_api_key, base_url=OPENROUTER_BASE_URL
        )
    return _openrouter_client


def _parse_json_text(response: str):
    """Small local JSON extractor, used only when the OpenAI helper
    cannot be imported (for example when OPENAI_API_KEY is unset and
    utils.openai_utils refuses to import). It covers the common cases:
    fenced ```json blocks, a bare object or array, and the same cleanup
    retries as the OpenAI helper.
    """
    if not response or not isinstance(response, str):
        return None

    json_pattern = r"```json(.*?)```"
    matches = re.findall(json_pattern, response, re.DOTALL)

    if not matches:
        json_pattern = r"(\{.*\}|\[.*\])"
        matches = re.findall(json_pattern, response, re.DOTALL)

    for json_string in matches:
        json_string = json_string.strip()
        try:
            return json.loads(json_string)
        except json.JSONDecodeError:
            try:
                json_string_clean = re.sub(r"[\x00-\x1F\x7F]", "", json_string)
                json_string_clean = re.sub(r",\s*([\]}])", r"\1", json_string_clean)
                json_string_clean = re.sub(
                    r'\\(?![\\"/bfnrtu])', r"\\\\", json_string_clean
                )
                return json.loads(json_string_clean)
            except json.JSONDecodeError:
                continue

    return None


def parse_openrouter_json_results(response: str):
    """Parse JSON from a model response.

    Reuses the OpenAI helper when it can be imported, and falls back to
    the local extractor otherwise, so OpenRouter calls keep working on a
    setup with no OpenAI key at all.
    """
    try:
        from utils.openai_utils import parse_openai_json_results

        return parse_openai_json_results(response)
    except (ImportError, ValueError):
        return _parse_json_text(response)


def call_openrouter_models_with_content(
    content: list[Any],
    model_name: str,
    max_retries: int = 5,
    base_interval_sec: int = 5,
    result_parsing_func: callable = parse_openrouter_json_results,
    generation_configs: dict = {},
    check_parsed_response_not_none: bool = True,
    system_prompt: str = None,
):
    client = get_openrouter_client()

    raw_response = None
    parsed_response = None

    for attempt in range(max_retries):
        try:
            messages = []
            if system_prompt:
                role = "developer" if model_name.startswith(("o1", "o3")) else "system"
                messages.append({"role": role, "content": system_prompt})

            messages.append({"role": "user", "content": content})

            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                **generation_configs,
            )
            raw_response = response.choices[0].message.content
            parsed_response = result_parsing_func(raw_response)

            if check_parsed_response_not_none:
                assert (
                    parsed_response is not None
                ), f"Parsed response is None, Here is the raw response:\n{raw_response}"

            return {
                "raw_response": raw_response,
                "parsed_response": parsed_response,
            }

        except Exception as e:
            print(
                f"Warning: OpenRouter API call (model={model_name}) failed on attempt {attempt + 1} of {max_retries}. Error: {e}",
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


def call_openrouter_models_with_text_prompt(
    prompt: str,
    model_name: str,
    result_parsing_func: callable = parse_openrouter_json_results,
    generation_configs: dict = {},
    check_parsed_response_not_none: bool = True,
    max_retries: int = 5,
    base_interval_sec: int = 5,
    system_prompt: str = None,
):
    return call_openrouter_models_with_content(
        content=[{"type": "text", "text": prompt}],
        model_name=model_name,
        result_parsing_func=result_parsing_func,
        generation_configs=generation_configs,
        check_parsed_response_not_none=check_parsed_response_not_none,
        max_retries=max_retries,
        base_interval_sec=base_interval_sec,
        system_prompt=system_prompt,
    )


def get_openrouter_image_part_from_path(image_path: str):
    with open(image_path, "rb") as image_file:
        base64_image = base64.b64encode(image_file.read()).decode("utf-8")

    image_content = [
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{base64_image}",
            },
        }
    ]
    return image_content
