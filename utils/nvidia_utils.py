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

from typing import Any, Callable, Dict, List, Optional
from collections import deque
import re
import json
import time
import os
import threading
import random
import base64

from openai import OpenAI  # type: ignore
from dotenv import load_dotenv  # type: ignore

dot_file = os.path.join(os.path.dirname(__file__), "../.env")
load_dotenv(dot_file)

_nvidia_client = None
_nvidia_client_lock = threading.Lock()

# Default NVIDIA NIM Hosted API URL
DEFAULT_NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


class NvidiaRateLimiter:
    """Thread-safe rate limiter and in-flight concurrency controller for NVIDIA NIM API calls.
    - Limits in-flight concurrency to max_concurrency (default: 1 request in-flight at a time)
      to avoid upstream 429 concurrency rejections on huge models like nemotron-3-ultra-550b.
    - Limits overall request rate to max_requests per period_seconds (default: 30 RPM).
    - Enforces a minimum cooldown interval after the previous request finishes before starting the next.
    - Provides context manager support: `with _rate_limiter:`
    """

    def __init__(
        self,
        max_requests: int = 30,
        period_seconds: float = 60.0,
        min_cooldown_seconds: float = 2.0,
        max_concurrency: int = 1,
    ):
        self.max_requests = max_requests
        self.period_seconds = period_seconds
        self.min_cooldown_seconds = min_cooldown_seconds
        self.max_concurrency = max_concurrency
        self.semaphore = threading.Semaphore(max_concurrency)
        self.lock = threading.Lock()
        self.timestamps: deque = deque()
        self.last_finish_time: float = 0.0

    def acquire(self):
        """Blocks until an in-flight slot is available and rate limits are satisfied."""
        self.semaphore.acquire()

        while True:
            with self.lock:
                now = time.time()
                # Purge timestamps older than the sliding window
                while self.timestamps and (now - self.timestamps[0]) >= self.period_seconds:
                    self.timestamps.popleft()

                # Check RPM window (max 30 requests in the last 60 seconds)
                rpm_sleep = 0.0
                if len(self.timestamps) >= self.max_requests:
                    oldest = self.timestamps[0]
                    rpm_sleep = max(0.0, (oldest + self.period_seconds) - now + 0.1)

                # Check minimum cooldown since previous request finished
                cooldown_sleep = 0.0
                if self.min_cooldown_seconds > 0.0:
                    cooldown_sleep = max(
                        0.0, (self.last_finish_time + self.min_cooldown_seconds) - now
                    )

                wait_time = max(rpm_sleep, cooldown_sleep)

                if wait_time <= 0.005:
                    self.timestamps.append(time.time())
                    return

            if wait_time > 0.5:
                print(
                    f"[NVIDIA Rate Limiter] Guard: holding slot for {wait_time:.2f}s "
                    f"({len(self.timestamps)} requests in last {self.period_seconds}s, cooldown {cooldown_sleep:.2f}s)..."
                )
            time.sleep(min(wait_time, 1.0))

    def release(self):
        """Releases the in-flight slot and updates the last finish timestamp."""
        with self.lock:
            self.last_finish_time = time.time()
        self.semaphore.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


_rate_limiter = NvidiaRateLimiter(
    max_requests=int(os.environ.get("NVIDIA_RPM_CAP", 30)),
    period_seconds=60.0,
    min_cooldown_seconds=float(os.environ.get("NVIDIA_MIN_INTERVAL_SEC", 2.0)),
    max_concurrency=int(os.environ.get("NVIDIA_MAX_CONCURRENCY", 1)),
)

# Recognized NVIDIA NIM model prefixes and identifiers
KNOWN_NVIDIA_PREFIXES = (
    "nvidia/",
    "meta/",
    "mistralai/",
    "deepseek-ai/",
    "qwen/",
    "microsoft/",
    "nim/",
    "nim:",
)


def is_nvidia_model(model_name: str) -> bool:
    """Checks if a model should be routed to NVIDIA NIM."""
    if not model_name or not isinstance(model_name, str):
        return False
    name = model_name.strip().lower()

    # Explicit NIM prefixes
    if any(name.startswith(p) for p in KNOWN_NVIDIA_PREFIXES):
        return True

    # Known NIM family keywords
    if "nemotron" in name:
        return True

    # If user explicitly set an NVIDIA key and model is not OpenAI or Gemini
    has_nvidia_key = bool(
        os.environ.get("NVIDIA_API_KEY") or os.environ.get("NVIDIA_NIM_API_KEY")
    )
    is_gemini = "gemini" in name
    is_openai = "gpt" in name or "o1" in name or "o3" in name
    if has_nvidia_key and not is_gemini and not is_openai:
        # If model format has a slash (vendor/model) or llama/mistral/deepseek
        if "/" in name or any(k in name for k in ("llama", "mistral", "deepseek", "qwen")):
            return True

    return False


def normalize_nvidia_model_name(model_name: str) -> str:
    """Strips routing prefixes such as 'nim/' or 'nim:'."""
    if not model_name:
        return model_name
    name = model_name.strip()
    if name.lower().startswith("nim/"):
        return name[4:]
    if name.lower().startswith("nim:"):
        return name[4:]
    return name


def get_nvidia_client(force_reload: bool = False) -> OpenAI:
    """Returns a shared OpenAI client configured for NVIDIA NIM."""
    global _nvidia_client
    if _nvidia_client is None or force_reload:
        with _nvidia_client_lock:
            if _nvidia_client is None or force_reload:
                # Reload .env to ensure fresh API key
                dot_file = os.path.join(os.path.dirname(__file__), "../.env")
                load_dotenv(dot_file, override=True)
                api_key = os.environ.get("NVIDIA_API_KEY") or os.environ.get(
                    "NVIDIA_NIM_API_KEY"
                )
                if not api_key:
                    raise ValueError(
                        "NVIDIA_API_KEY (or NVIDIA_NIM_API_KEY) must be set to use NVIDIA NIM models. "
                        "Please add NVIDIA_API_KEY to your .env file or environment variables."
                    )
                base_url = os.environ.get("NVIDIA_BASE_URL", DEFAULT_NVIDIA_BASE_URL)
                _nvidia_client = OpenAI(base_url=base_url, api_key=api_key)
    return _nvidia_client


def parse_nvidia_json_results(response: str):
    """Parses JSON from model responses, extracting from markdown blocks if present."""
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

    try:
        start_idx = response.find("[")
        end_idx = response.rfind("]")
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

    return None


def call_nvidia_models_with_content(
    content: List[Any],
    model_name: str,
    max_retries: int = 5,
    base_interval_sec: int = 5,
    result_parsing_func: Callable = parse_nvidia_json_results,
    generation_configs: Optional[Dict[str, Any]] = None,
    check_parsed_response_not_none: bool = True,
    system_prompt: Optional[str] = None,
) -> Dict[str, Any]:
    """Calls NVIDIA NIM models with multimodal or text content."""
    raw_response = None
    parsed_response = None
    client = get_nvidia_client()
    normalized_model = normalize_nvidia_model_name(model_name)

    if generation_configs is None:
        configs = {}
    else:
        configs = dict(generation_configs)

    # Filter out Gemini-specific config parameters
    configs.pop("system_instruction", None)
    configs.pop("tools", None)
    configs.pop("candidate_count", None)

    for attempt in range(max_retries):
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})

            messages.append({"role": "user", "content": content})

            # Enforce single-flight concurrency lock and RPM cap across all threads
            with _rate_limiter:
                response = client.chat.completions.create(
                    model=normalized_model,
                    messages=messages,
                    **configs,
                )

            raw_response = response.choices[0].message.content
            if not raw_response:
                msg = response.choices[0].message
                if hasattr(msg, "reasoning_content") and msg.reasoning_content:
                    raw_response = msg.reasoning_content
            if raw_response is None:
                raw_response = ""

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
            err_msg = str(e)
            print(
                f"Warning: NVIDIA NIM API call (model={normalized_model}) failed on attempt {attempt + 1} of {max_retries}. Error: {err_msg}"
            )

            if attempt + 1 == max_retries:
                print(f"Error: All {max_retries} retry attempts failed.")
                raise e

            if "429" in err_msg or "rate limit" in err_msg.lower():
                jitter = random.uniform(2.0, 5.0)
                delay = (10.0 * (1.5 ** attempt)) + jitter
                print(
                    f"[NVIDIA Rate Limiter] 429 rate limit detected; backing off for {delay:.2f}s (attempt {attempt + 1})..."
                )
            else:
                delay = base_interval_sec * (2 ** (attempt - 1)) if attempt > 0 else 2
                delay += random.uniform(1.0, 3.0)
                print(f"Retrying in {delay:.2f} seconds...")
            time.sleep(delay)

    return {
        "raw_response": raw_response,
        "parsed_response": parsed_response,
    }


def call_nvidia_models_with_text_prompt(
    prompt: str,
    model_name: str,
    result_parsing_func: Callable = parse_nvidia_json_results,
    generation_configs: Optional[Dict[str, Any]] = None,
    check_parsed_response_not_none: bool = True,
    max_retries: int = 5,
    base_interval_sec: int = 5,
    system_prompt: Optional[str] = None,
) -> Dict[str, Any]:
    """Convenience wrapper for text-only prompts to NVIDIA NIM."""
    return call_nvidia_models_with_content(
        content=[{"type": "text", "text": prompt}],
        model_name=model_name,
        result_parsing_func=result_parsing_func,
        generation_configs=generation_configs,
        check_parsed_response_not_none=check_parsed_response_not_none,
        max_retries=max_retries,
        base_interval_sec=base_interval_sec,
        system_prompt=system_prompt,
    )
