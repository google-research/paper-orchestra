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
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest


FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"


class RefinementSelectionTest(unittest.TestCase):
    def render_run(self, content_worklog, format_worklog):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            workdir = run / "content_refinement_workdir"
            workdir.mkdir()
            (workdir / "final_refined_paper.pdf").touch()
            if content_worklog is not None:
                (workdir / "content_refinement_worklog.json").write_text(
                    json.dumps(content_worklog), encoding="utf-8"
                )
            (workdir / "format_refinement_worklog.json").write_text(
                json.dumps(format_worklog), encoding="utf-8"
            )

            app = AppTest.from_file(str(FRONTEND_DIR / "app.py"))
            app.session_state["hide_inputs"] = True
            app.session_state["run_directory"] = str(run)
            with (
                patch.object(sys, "path", [str(FRONTEND_DIR), *sys.path]),
                patch.dict(sys.modules, {
                    "methods.paper_writer": SimpleNamespace(write_single_paper=Mock()),
                    "utils.pdf_utils": SimpleNamespace(pdf_to_grid_images=Mock()),
                }),
            ):
                app.run()

        self.assertFalse(app.exception)
        return "\n".join(element.value for element in app.info)

    def test_latest_accepted_rounds_are_selected(self):
        messages = self.render_run(
            {
                "v1": {"round": 1, "outcome": "ACCEPTED_SCORE_INCREASE"},
                "v2": {"round": 2, "outcome": "ACCEPTED_NEUTRAL_IMPROVEMENT"},
                "v3": {"round": 3, "outcome": "REJECTED_DEGRADATION"},
            },
            {
                "v1": {"outcome": "ACCEPTED_COMPILE_SUCCESS"},
                "v2": {"outcome": "REJECTED_COMPILE_FAILURE"},
            },
        )

        self.assertIn("Content Refinement V2", messages)
        self.assertIn("Format Refinement V1", messages)
        self.assertNotIn("Format Refinement V2", messages)

    def test_rejected_format_round_falls_back_to_initial_without_content_log(self):
        messages = self.render_run(
            None, {"v1": {"outcome": "REJECTED_COMPILE_FAILURE"}}
        )

        self.assertIn("Content Refinement V0 (Initial)", messages)
        self.assertIn("Format Refinement V0 (Initial)", messages)
        self.assertNotIn("Format Refinement V1", messages)
