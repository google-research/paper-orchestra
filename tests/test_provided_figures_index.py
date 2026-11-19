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
import os
from pathlib import Path
import tempfile
import unittest

from utils.common_utils import index_provided_figures


class IndexProvidedFiguresTest(unittest.TestCase):
    def _figures_dir(self, tmp: str, names) -> Path:
        figures = Path(tmp) / "figures"
        figures.mkdir()
        for name in names:
            (figures / name).write_bytes(b"fixture")
        return figures

    def test_writes_sorted_names_for_image_files_without_caption(self):
        with tempfile.TemporaryDirectory() as tmp:
            figures = self._figures_dir(
                tmp, ["fig2_brechas.pdf", "fig1_panel.png", "notes.txt", "data.csv"]
            )
            written = index_provided_figures(str(figures))
            self.assertEqual(written, str(figures / "info.json"))
            info = json.loads((figures / "info.json").read_text(encoding="utf-8"))
            self.assertEqual(
                info, [{"name": "fig1_panel.png"}, {"name": "fig2_brechas.pdf"}]
            )
            for entry in info:
                self.assertNotIn("caption", entry)

    def test_keeps_existing_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            figures = self._figures_dir(tmp, ["fig1.png"])
            existing = [{"name": "kept.jpg", "caption": "from the plotting pipeline"}]
            (figures / "info.json").write_text(json.dumps(existing), encoding="utf-8")
            self.assertEqual(index_provided_figures(str(figures)), "")
            info = json.loads((figures / "info.json").read_text(encoding="utf-8"))
            self.assertEqual(info, existing)

    def test_no_op_without_figures_or_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = self._figures_dir(tmp, ["notes.txt"])
            self.assertEqual(index_provided_figures(str(empty)), "")
            self.assertFalse(os.path.exists(empty / "info.json"))
            self.assertEqual(
                index_provided_figures(os.path.join(tmp, "missing")), ""
            )


if __name__ == "__main__":
    unittest.main()
