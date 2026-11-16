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

import tempfile
import unittest
from unittest.mock import patch

from methods.agents.literature_review_agent import HybridLiteratureAgent


class UnicodeLiteratureTitlesTest(unittest.TestCase):
    @patch("methods.agents.literature_review_agent.s2_title_search")
    def test_distinct_non_latin_papers_are_retained(self, search):
        titles = ["图神经网络", "强化学习"]
        search.side_effect = [
            {"title": title, "year": 2023, "abstract": "Research abstract."}
            for title in titles
        ]
        with tempfile.TemporaryDirectory() as output:
            agent = HybridLiteratureAgent("", "", "", "", output)
            registry = {}
            for title in titles:
                agent._enrich_and_register_paper(
                    {"title": title, "year": 2023},
                    {"section": "Introduction"},
                    registry,
                    "2024-11",
                )
            self.assertEqual(search.call_count, 2)
            self.assertEqual([paper.title for paper in registry.values()], titles)

    def test_canonical_forms_have_the_same_key(self):
        with tempfile.TemporaryDirectory() as output:
            agent = HybridLiteratureAgent("", "", "", "", output)
            self.assertEqual(
                agent._normalize_title("ÉTUDE : graphes"),
                agent._normalize_title("e\u0301tude graphes"),
            )
