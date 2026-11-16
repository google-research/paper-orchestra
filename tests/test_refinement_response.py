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
import unittest
from unittest.mock import Mock, patch

from utils.gemini_utils import (
    call_gemini_with_contents,
    parse_gemini_json_latex_response,
)


class RefinementResponseTest(unittest.TestCase):
    @patch("utils.gemini_utils.get_genai_client")
    def test_retries_until_response_contains_latex(self, get_client):
        generate = get_client.return_value.models.generate_content
        generate.side_effect = [
            Mock(text='```json\n{"changes": []}\n```'),
            Mock(text="```latex\n   \n```"),
            Mock(text="\n```latex\n\\section{Results}\n```"),
        ]
        result = call_gemini_with_contents(
            contents=["Revise this paper"],
            model_name="gemini-test",
            max_retries=3,
            base_interval_sec=0,
            result_parsing_func=parse_gemini_json_latex_response,
        )
        self.assertEqual(generate.call_count, 3)
        self.assertEqual(
            json.loads(result["parsed_response"]),
            {"json": None, "latex": "\\section{Results}"},
        )

    def test_keeps_worklog_with_latex(self):
        response = '```json\n{"changes": ["revise"]}\n```\n```latex\nText\n```'
        self.assertEqual(
            json.loads(parse_gemini_json_latex_response(response)),
            {"json": {"changes": ["revise"]}, "latex": "Text"},
        )
