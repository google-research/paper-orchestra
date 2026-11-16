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

import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
import zipfile

import streamlit as st
from streamlit.testing.v1 import AppTest


FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"


class LatexArchiveTest(unittest.TestCase):
    def test_archive_contains_final_manuscript_and_relative_support_files(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            source = run / "latex_writeup"
            (source / "figures").mkdir(parents=True)
            (source / "template.tex").write_text("template")
            (source / "raw_draft_paper.tex").write_text("draft")
            (source / "main.tex").write_text("older manuscript")
            (source / "references.bib").write_text("example references")
            (source / "figures" / "plot.png").write_bytes(b"example figure")
            refinement = run / "content_refinement_workdir"
            refinement.mkdir()
            (refinement / "final_refined_paper.tex").write_text("final manuscript")
            (refinement / "initial_draft.pdf").write_bytes(b"intermediate PDF")

            app = AppTest.from_file(str(FRONTEND_DIR / "app.py"))
            app.session_state["hide_inputs"] = True
            app.session_state["run_directory"] = str(run)
            with (
                patch.object(sys, "path", [str(FRONTEND_DIR), *sys.path]),
                patch.dict(sys.modules, {
                    "methods.paper_writer": SimpleNamespace(write_single_paper=Mock()),
                    "utils.pdf_utils": SimpleNamespace(pdf_to_grid_images=Mock()),
                }),
                patch.object(st, "download_button") as download,
            ):
                app.run()

            self.assertFalse(app.exception)
            payload, = (
                call.kwargs["data"]
                for call in download.call_args_list
                if call.kwargs["key"] == "download_final_latex_tab"
            )
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                self.assertCountEqual(
                    archive.namelist(),
                    ["main.tex", "references.bib", "figures/plot.png"],
                )
                self.assertEqual(archive.read("main.tex"), b"final manuscript")
                self.assertEqual(archive.read("references.bib"), b"example references")
                self.assertEqual(archive.read("figures/plot.png"), b"example figure")
            self.assertEqual((source / "main.tex").read_text(), "older manuscript")
