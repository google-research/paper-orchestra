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
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest


FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"


class GeneratedFiguresTest(unittest.TestCase):
    def test_unsaved_figures_do_not_break_gallery_or_hide_successful_figure(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            (run / "figures").mkdir()
            shutil.copyfile(
                FRONTEND_DIR / "examples" / "cvpr_example_figure.png",
                run / "figures" / "rendered.png",
            )
            (run / "plotting_results.json").write_text(
                json.dumps([
                    {"title": "Unsaved diagram"},
                    {"title": "Missing file", "image_path": "figures/missing.png"},
                    {
                        "title": "Rendered diagram",
                        "image_path": "figures/rendered.png",
                        "caption": "Published caption",
                    },
                ]),
                encoding="utf-8",
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
        self.assertEqual(len(app.get("image")), 1)
        self.assertEqual(app.get("image")[0].proto.imgs[0].caption, "Published caption")
        self.assertEqual(
            [caption.value for caption in app.caption],
            ["No image is available for this figure."] * 2,
        )
