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

import re
import json
from typing import Dict, Any

from google import genai
from google.genai import types  # type: ignore
import time
import os
import mimetypes
import base64
import threading

import dotenv

dot_file = os.path.join(os.path.dirname(__file__), "../.env")
dotenv.load_dotenv(dot_file)

_genai_client = None
_genai_client_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Local addition (not upstream): spend guard.
# Set PAPER_BUDGET_USD in .env to stop the whole process once the estimated
# Gemini spend passes that amount. Unset or 0 = no limit (usage is still logged).
# Prices are USD per 1M tokens for gemini-3.1-pro-preview (paid tier), read from
# the Gemini pricing page on 2026-11-17; override with the env vars below.
# ---------------------------------------------------------------------------
_spend_lock = threading.Lock()
_spend = {"usd": 0.0, "in": 0, "out": 0, "calls": 0, "searches": 0}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        return default


def _budget_usd() -> float:
    return _env_float("PAPER_BUDGET_USD", 0.0)


def _stop_if_over_budget():
    budget = _budget_usd()
    if budget > 0 and _spend["usd"] >= budget:
        print(
            f"\n🛑 BUDGET STOP: estimated spend ${_spend['usd']:.3f} reached the "
            f"limit ${budget:.2f} after {_spend['calls']} calls "
            f"({_spend['in']:,} input / {_spend['out']:,} output tokens, "
            f"{_spend['searches']} searches). Exiting.",
            flush=True,
        )
        os._exit(3)


def _record_usage(response):
    usage = getattr(response, "usage_metadata", None)
    n_in = (getattr(usage, "prompt_token_count", 0) or 0) + (
        getattr(usage, "tool_use_prompt_token_count", 0) or 0
    )
    n_out = (getattr(usage, "candidates_token_count", 0) or 0) + (
        getattr(usage, "thoughts_token_count", 0) or 0
    )
    n_search = 0
    for cand in getattr(response, "candidates", None) or []:
        meta = getattr(cand, "grounding_metadata", None)
        n_search += len(getattr(meta, "web_search_queries", None) or [])

    long_prompt = n_in > 200_000
    price_in = _env_float("PAPER_PRICE_IN_PER_M", 4.0 if long_prompt else 2.0)
    price_out = _env_float("PAPER_PRICE_OUT_PER_M", 18.0 if long_prompt else 12.0)
    price_search = _env_float("PAPER_PRICE_PER_SEARCH", 0.0)
    cost = n_in / 1e6 * price_in + n_out / 1e6 * price_out + n_search * price_search

    with _spend_lock:
        _spend["usd"] += cost
        _spend["in"] += n_in
        _spend["out"] += n_out
        _spend["calls"] += 1
        _spend["searches"] += n_search
        budget = _budget_usd()
        limit = f" / ${budget:.2f}" if budget > 0 else ""
        print(
            f"💰 call {_spend['calls']}: +${cost:.4f} "
            f"({n_in:,} in, {n_out:,} out, {n_search} searches) "
            f"| total ${_spend['usd']:.3f}{limit}",
            flush=True,
        )
        _stop_if_over_budget()


def _install_spend_guard(client):
    original = client.models.generate_content

    def guarded(*args, **kwargs):
        with _spend_lock:
            _stop_if_over_budget()
        response = original(*args, **kwargs)
        try:
            _record_usage(response)
        except Exception as exc:  # never let accounting break a call
            print(f"Warning: spend accounting failed: {exc}")
        return response

    client.models.generate_content = guarded
    return client


def get_genai_client() -> genai.Client:
    """Returns a shared Gemini client, creating it on first use.

    The client is created lazily so that Gemini credentials are only required
    when a Gemini model is actually called (e.g. OpenAI-only setups don't need
    them). Vertex AI takes precedence over GEMINI_API_KEY when both are set.
    """
    global _genai_client
    if _genai_client is None:
        with _genai_client_lock:
            if _genai_client is None:
                vertex_ai_project = os.getenv("VERTEX_AI_PROJECT")
                vertex_ai_location = os.getenv("VERTEX_AI_LOCATION")
                gemini_api_key = os.getenv("GEMINI_API_KEY")

                if vertex_ai_project and vertex_ai_location:
                    print(
                        f"Using Vertex AI configuration. Project: {vertex_ai_project}, Location: {vertex_ai_location}"
                    )
                    _genai_client = genai.Client(
                        vertexai=True,
                        project=vertex_ai_project,
                        location=vertex_ai_location,
                    )
                elif gemini_api_key:
                    print("Using Gemini API Key configuration.")
                    # Local addition: this SDK version defaults to API version v1,
                    # where preview models (the defaults here) are not served.
                    _genai_client = genai.Client(
                        api_key=gemini_api_key,
                        http_options=types.HttpOptions(
                            api_version=os.getenv("GEMINI_API_VERSION", "v1beta")
                        ),
                    )
                else:
                    raise ValueError(
                        "Either VERTEX_AI_PROJECT/VERTEX_AI_LOCATION or GEMINI_API_KEY"
                        " must be set to use Gemini models."
                    )
                _install_spend_guard(_genai_client)
    return _genai_client


def parse_gemini_json_results(response: str):
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
            parsed_json = json.loads(json_string)
            return parsed_json
        except json.JSONDecodeError:
            try:
                json_string_clean = re.sub(r"[\x00-\x1F\x7F]", "", json_string)
                json_string_clean = re.sub(r",\s*([\]}])", r"\1", json_string_clean)
                json_string_clean = re.sub(
                    r'\\(?![\\"/bfnrtu])', r"\\\\", json_string_clean
                )

                parsed_json = json.loads(json_string_clean)
                return parsed_json
            except json.JSONDecodeError:
                continue

    try:
        start_idx = response.find("{")
        end_idx = response.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_string = response[start_idx : end_idx + 1]
            json_string_clean = re.sub(r"[\x00-\x1F\x7F]", "", json_string)
            json_string_clean = re.sub(r",\s*([\]}])", r"\1", json_string_clean)
            json_string_clean = re.sub(
                r'\\(?![\\"/bfnrtu])', r"\\\\", json_string_clean
            )
            return json.loads(json_string_clean)
    except Exception:
        pass

    return None  # No valid JSON found


def parse_gemini_latex_results(response: str):
    match = re.search(r"```latex\s*(.*?)\s*```", response.strip(), re.DOTALL)
    if match:
        latex_string = match.group(1)
    else:
        latex_string = response
    return latex_string


def parse_gemini_json_latex_response(response_text: str) -> Dict[str, Any]:
    """
    Extracts the JSON worklog and the LaTeX code from the LLM response.
    Expected format:
      ... arbitrary text ...
      ```json
      { ... }
      ```
      ... arbitrary text ...
      ```latex
      ...
      ```
    """
    result = {"json": None, "latex": None}

    json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
    if json_match:
        try:
            result["json"] = json.loads(json_match.group(1))
        except json.JSONDecodeError:
            print(" >> Error: Failed to parse JSON worklog from response.")
            result["json"] = {"error": "Invalid JSON format returned"}

    latex_match = re.search(r"```latex\s*(.*?)\s*```", response_text, re.DOTALL)
    if latex_match:
        result["latex"] = latex_match.group(1)
    else:
        print(" >> Warning: No ```latex``` block found.")

    return json.dumps(result)


def call_gemini_with_contents(
    contents: types.Content,
    model_name: str,
    max_retries: int = 5,
    base_interval_sec: int = 5,
    result_parsing_func: callable = parse_gemini_json_results,
    generation_configs: dict = {},
    check_parsed_response_not_none: bool = True,
):
    """
    Calls the Gemini API (text-only) with retry logic and exponential backoff.
    """

    raw_response = None
    parsed_response = None

    # Local addition: route to Claude Code / Codex when PAPER_LLM_BACKEND is set.
    from utils.cli_backend import call_cli, cli_backend

    use_cli = bool(cli_backend())
    genai_client = None if use_cli else get_genai_client()
    for attempt in range(max_retries):
        try:
            if use_cli:
                raw_response = call_cli(contents, generation_configs)
                if not raw_response:
                    raise ValueError("Empty response from the CLI backend")
                parsed_response = result_parsing_func(raw_response)
                if check_parsed_response_not_none:
                    assert (
                        parsed_response is not None
                    ), f"Parsed response is None, Here is the raw response:\n{raw_response}"
                return {
                    "raw_response": raw_response,
                    "parsed_response": parsed_response,
                }

            response = genai_client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(**generation_configs),
            )

            if not response or not hasattr(response, "text") or response.text is None:
                raise ValueError("Incomplete response from Gemini API or empty text")

            raw_response = response.text
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
            error_msg = str(e)
            if type(e).__name__ == "CliFatalError":
                print(
                    f"\n🛑 CLI backend stopped (not retrying): {error_msg}\n"
                    "   Finished stages are kept. Run the same command again with --resume.",
                    flush=True,
                )
                os._exit(4)
            print(
                f"Warning: Gemini API call failed on attempt {attempt + 1} of {max_retries}. Error: {error_msg}",
            )

            if (
                "maximum number of tokens allowed" in error_msg.lower()
                or "400 bad request" in error_msg.lower()
                or "code: 400" in error_msg.lower()
                or "400 invalid_argument" in error_msg.lower()
            ):
                print("Detected input token count exceed. Not retrying.")
                raise e

            if attempt + 1 == max_retries:
                print(f"Error: All {max_retries} retry attempts failed.")
                raise e

            delay = base_interval_sec * (2 ** (attempt - 1)) if attempt > 0 else 0
            print(f"Retrying in {delay} seconds...")
            if delay > 0:
                time.sleep(delay)

    print("Error: Exited retry loop unexpectedly.")
    return {"raw_response": raw_response, "parsed_response": parsed_response}


def call_gemini_with_text_prompt(
    prompt: str,
    model_name: str,
    result_parsing_func: callable = parse_gemini_json_results,
    generation_configs: dict = {},
    check_parsed_response_not_none: bool = True,
    max_retries: int = 5,
    base_interval_sec: int = 5,
):
    contents = [types.Part(text=prompt)]
    return call_gemini_with_contents(
        contents=contents,
        model_name=model_name,
        result_parsing_func=result_parsing_func,
        generation_configs=generation_configs,
        check_parsed_response_not_none=check_parsed_response_not_none,
        max_retries=max_retries,
        base_interval_sec=base_interval_sec,
    )


def call_gemini_with_images(
    prompt: str,
    images: list[str],
    model_name: str,
    result_parsing_func: callable = parse_gemini_json_results,
    generation_configs: dict = {},
    check_parsed_response_not_none: bool = True,
    max_retries: int = 5,
    base_interval_sec: int = 5,
):
    llm_contents = [
        types.Part.from_text(text=prompt),
    ]
    for image_path in images:
        with open(image_path, "rb") as f:
            img_bytes = f.read()
        llm_contents.append(
            types.Part.from_bytes(data=img_bytes, mime_type="image/png")
        )

    response_dict = call_gemini_with_contents(
        contents=llm_contents,
        model_name=model_name,
        generation_configs=generation_configs,
        result_parsing_func=result_parsing_func,
        check_parsed_response_not_none=check_parsed_response_not_none,
        max_retries=max_retries,
        base_interval_sec=base_interval_sec,
    )
    return response_dict


def generate_image_with_gemini(
    model_name: str,
    prompt: str,
    aspect_ratio: str = "16:9",
    generation_configs: dict = None,
    max_retries: int = 5,
    base_interval_sec: int = 5,
    save_path: str = None,
) -> str:
    """
    Directly calls Gemini for image generation and returns base64.
    """
    if generation_configs is None:
        generation_configs = {}

    genai_client = get_genai_client()
    for attempt in range(max_retries):
        try:
            config_args = {
                "temperature": 0.7,
                "candidate_count": 1,
                "response_modalities": ["IMAGE"],
                "image_config": types.ImageConfig(
                    aspect_ratio=aspect_ratio, image_size="1k"
                ),
            }
            config_args.update(generation_configs)

            response = genai_client.models.generate_content(
                model=model_name,
                contents=[types.Part.from_text(text=prompt)],
                config=types.GenerateContentConfig(**config_args),
            )
            if hasattr(response, "candidates") and response.candidates:
                if (
                    len(response.candidates) > 0
                    and response.candidates[0].content
                    and response.candidates[0].content.parts
                ):
                    for part in response.candidates[0].content.parts:
                        if part.inline_data:
                            img_base64 = base64.b64encode(part.inline_data.data).decode(
                                "utf-8"
                            )

                            if save_path:
                                try:
                                    os.makedirs(
                                        os.path.dirname(save_path), exist_ok=True
                                    )
                                    with open(save_path, "wb") as fh:
                                        fh.write(base64.b64decode(img_base64))
                                    print(
                                        f"Image for prompt '{prompt}' saved to {save_path}"
                                    )
                                except Exception as e:
                                    print(
                                        f"Warning: Failed to save image to {save_path}: {e}"
                                    )

                            return img_base64
        except Exception as e:
            print(f"Warning: Gemini API image generation failed {e}.")
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
