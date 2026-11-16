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

import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

from utils.scholar_utils import s2_title_search


class ResearchCutoffTest(unittest.TestCase):
    @patch("utils.scholar_utils.requests.get")
    def test_cutoff_filters_results_before_ranking(self, get):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = {
            "data": [
                {"title": "Graph Networks", "publicationDate": "2024-11-15", "year": 2024},
                {"title": "Graph Network", "publicationDate": "2024-11-14", "year": 2024},
            ]
        }
        self.assertEqual(
            s2_title_search("Graph Networks", cutoff_date="2024-11-15")["title"],
            "Graph Network",
        )
        self.assertIsNone(s2_title_search("Graph Networks", cutoff_date="2024-11"))
        self.assertIsNone(s2_title_search("Graph Networks", cutoff_date="2024"))

    @patch("utils.scholar_utils.requests.get")
    def test_year_only_metadata_can_predate_cutoff(self, get):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = {"data": [{"title": "Graph Networks", "year": 2024}]}
        self.assertIsNotNone(s2_title_search("Graph Networks", cutoff_date="2024-11"))
        self.assertIsNone(s2_title_search("Graph Networks", cutoff_date="2024-01"))

    def test_invalid_cutoff_is_reported_before_input_io(self):
        result = subprocess.run(
            [
                sys.executable, "paper_writing_cli.py",
                "--raw_materials_dir", "nonexistent-materials",
                "--latex_template_dir", "nonexistent-template",
                "--research_cutoff", "2024-02-30",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--research_cutoff: expected a valid", result.stderr)
