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

import contextlib
import io
import os
from pathlib import Path
import runpy
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

CLI_PATH = Path(__file__).resolve().parents[1] / "paper_writing_cli.py"


class CliOutputDirTest(unittest.TestCase):
    def _run_cli(self, cwd, materials, output_dir=None):
        writer = ModuleType("methods.paper_writer")
        writer.write_single_paper = Mock(return_value=True)
        argv = [
            str(CLI_PATH),
            "--raw_materials_dir",
            str(materials),
            "--latex_template_dir",
            str(cwd),
        ]
        if output_dir is not None:
            argv += ["--output_dir", str(output_dir)]
        previous_cwd = os.getcwd()
        os.chdir(cwd)
        try:
            with (
                patch.dict(sys.modules, {"methods.paper_writer": writer}),
                patch.object(sys, "argv", argv),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                try:
                    runpy.run_path(str(CLI_PATH), run_name="__main__")
                except SystemExit as error:
                    return error.code, writer.write_single_paper
                except Exception as error:  # e.g. shutil.Error from copytree
                    return error, writer.write_single_paper
                return 0, writer.write_single_paper
        finally:
            os.chdir(previous_cwd)

    def test_default_output_dir_inside_materials_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            materials = Path(directory) / "materials"
            materials.mkdir()
            (materials / "idea_sparse.md").write_text("idea")

            status, writer = self._run_cli(cwd=materials, materials=".")

            self.assertEqual(status, 1)
            writer.assert_not_called()
            self.assertEqual(
                sorted(p.name for p in materials.iterdir()), ["idea_sparse.md"]
            )

    def test_output_dir_outside_materials_still_copies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            materials = root / "materials"
            materials.mkdir()
            (materials / "idea_sparse.md").write_text("idea")

            status, writer = self._run_cli(
                cwd=root, materials=materials, output_dir=root / "out"
            )

            writer.assert_called_once()
            self.assertTrue(
                (root / "out" / "raw_materials" / "idea_sparse.md").exists()
            )

    def test_materials_already_in_output_dir_is_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            materials = root / "out" / "raw_materials"
            materials.mkdir(parents=True)
            (materials / "idea_sparse.md").write_text("idea")

            status, writer = self._run_cli(
                cwd=root, materials=materials, output_dir=root / "out"
            )

            writer.assert_called_once()


if __name__ == "__main__":
    unittest.main()
