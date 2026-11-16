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
from pathlib import Path
import runpy
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import Mock, patch


CLI_PATH = Path(__file__).resolve().parents[1] / "paper_writing_cli.py"


class CliWriterExitTest(unittest.TestCase):
    def test_entry_point_propagates_both_writer_results(self):
        for plotting in (False, True):
            module_name = (
                "methods.paper_writer_with_plotting" if plotting
                else "methods.paper_writer"
            )
            for succeeded in (False, True):
                with self.subTest(plotting=plotting, succeeded=succeeded):
                    writer = ModuleType(module_name)
                    writer.write_single_paper = Mock(return_value=succeeded)
                    stderr = io.StringIO()
                    with tempfile.TemporaryDirectory() as directory:
                        root = Path(directory)
                        source = root / "materials"
                        source.mkdir()
                        command = [
                            str(CLI_PATH), "--raw_materials_dir", str(source),
                            "--latex_template_dir", str(root),
                            "--output_dir", str(root / "output"),
                            "--use_plotting", str(plotting),
                        ]
                        with (
                            patch.dict(sys.modules, {module_name: writer}),
                            patch.object(sys, "argv", command),
                            contextlib.redirect_stdout(io.StringIO()),
                            contextlib.redirect_stderr(stderr),
                        ):
                            try:
                                runpy.run_path(str(CLI_PATH), run_name="__main__")
                            except SystemExit as error:
                                status = error.code
                            else:
                                status = 0

                    writer.write_single_paper.assert_called_once()
                    self.assertEqual(status, 0 if succeeded else 1)
                    if not succeeded:
                        self.assertIn("Paper generation failed", stderr.getvalue())
