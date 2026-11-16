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


class SharedCitationsTest(unittest.TestCase):
    @patch("methods.agents.literature_review_agent.s2_title_search")
    def test_one_bibliography_entry_is_available_in_each_discovering_section(self, search):
        search.return_value = {
            "title": "Graph Networks", "authors": [{"name": "A. Smith"}],
            "year": 2023, "abstract": "Graph experiments.",
        }
        with tempfile.TemporaryDirectory() as output:
            agent = HybridLiteratureAgent("", "", "", "", output)
            registry = {}
            for title, section in [
                ("Graph Networks", "Introduction"),
                ("Graph Networks", "Related Work: Graphs"),
                ("Graph Networks Workshop Version", "Methods - Models"),
                ("Graph Networks", "Related Work: Graphs"),
            ]:
                agent._enrich_and_register_paper(
                    {"title": title, "year": 2023}, {"section": section}, registry, "2024-11"
                )
            self.assertEqual(len(registry), 1)
            self.assertEqual(search.call_count, 2)
            plan = {
                "intro_related_work_plan": {
                    "introduction_strategy": {},
                    "related_work_strategy": {"subsections": [{"subsection_title": "Graphs"}]},
                },
                "section_plan": [{
                    "section_title": "Methods",
                    "subsections": [{"subsection_title": "Models"}],
                }],
            }
            agent._inject_citations_into_outline(plan, registry)
            intro = plan["intro_related_work_plan"]["introduction_strategy"]
            related = plan["intro_related_work_plan"]["related_work_strategy"]["subsections"][0]
            methods = plan["section_plan"][0]["subsections"][0]
            for section in (intro, related, methods):
                self.assertEqual(section["citation_candidates"], ["Smith2023GraphNetworks"])
            bibtex = agent._generate_bibtex(list(registry.values()))
            self.assertEqual(bibtex.count("@inproceedings"), 1)
