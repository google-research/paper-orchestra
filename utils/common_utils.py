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

import datetime
import json
import os
import os.path as osp
import re
from typing import Dict, Any


def parse_gemini_latex_results(response: str):
    """Extract LaTeX from a model response.

    Pure text processing, no API key needed. Kept here so modules that
    only need the parser do not have to import utils.gemini_utils,
    which requires a Gemini key at import time.
    """
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
    Pure text processing, no API key needed. Kept here for the same
    reason as parse_gemini_latex_results.
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


def create_log_folder(
    prefix: str = "",
    date_str: str = "",
    log_dir: str = "./logs/paper_writing",
):
    now = datetime.datetime.now()
    timestamp_str = now.strftime("%Y_%m_%d_%H_%M_%S")

    log_dir_name = f"log_{timestamp_str}"
    if prefix != "":
        log_dir_name = f"{prefix}_" + log_dir_name

    if date_str == "":
        date_str = now.strftime("%Y%m%d")
    log_path = os.path.join(log_dir, date_str, log_dir_name)

    os.makedirs(log_path, exist_ok=True)

    print(f"Generated Log Directory Name: **{log_dir_name}**")
    print(f"Full Log Path: **{log_path}**")

    return log_path


def load_md_file(md_file_path: str):
    if not osp.exists(md_file_path):
        print(
            f"Error! Markdown file not found at '{md_file_path}', use empty string..."
        )
        return None

    with open(md_file_path, "r") as f:
        prompt_content = f.read()

    return prompt_content
