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
import tempfile
import unittest
from unittest.mock import patch

from methods.agents import section_writing_agent
from methods.agents.section_writing_agent import SectionWritingAgent


class SectionWritingFiguresTest(unittest.TestCase):
    def _run_agent(self, figure_names, files_on_disk):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            figures_dir = root / "figures"
            figures_dir.mkdir()
            for name in files_on_disk:
                (figures_dir / name).write_bytes(b"x")
            info_path = figures_dir / "info.json"
            info_path.write_text(
                json.dumps([{"name": n, "caption": "c"} for n in figure_names])
            )
            for name in (
                "outline.json",
                "template.tex",
                "idea.md",
                "log.md",
                "guidelines.md",
                "citation_map.json",
            ):
                (root / name).write_text("{}")

            agent = SectionWritingAgent(
                outline_path=str(root / "outline.json"),
                template_path=str(root / "template.tex"),
                idea_path=str(root / "idea.md"),
                experimental_log_path=str(root / "log.md"),
                citation_map_path=str(root / "citation_map.json"),
                figures_info_path=str(info_path),
                guidelines_path=str(root / "guidelines.md"),
            )
            with patch.object(
                section_writing_agent,
                "call_llm_with_images",
                return_value={"parsed_response": "latex"},
            ) as call:
                agent.run(str(root / "out.tex"))
            kwargs = call.call_args.kwargs
            images = sorted(Path(p).name for p in kwargs["images"])
            return images, kwargs["prompt"]

    def test_jpeg_and_uppercase_extensions_are_kept(self):
        names = ["teaser.jpeg", "Results.PNG", "plot.JPG", "overview.png"]
        images, prompt = self._run_agent(names, names)

        self.assertEqual(images, sorted(names))
        for name in names:
            self.assertIn(f"Filename: {name}\n", prompt)
        self.assertNotIn(".jpeg.png", prompt)
        self.assertNotIn(".PNG.png", prompt)

    def test_pdf_figures_are_listed_but_not_sent_as_images(self):
        names = ["diagram.pdf", "Chart.PDF"]
        images, prompt = self._run_agent(names, names)

        self.assertEqual(images, [])
        self.assertIn("Filename: diagram.pdf\n", prompt)
        self.assertIn("Filename: Chart.PDF\n", prompt)

    def test_names_without_extension_still_default_to_png(self):
        images, prompt = self._run_agent(["fig1"], ["fig1.png"])

        self.assertEqual(images, ["fig1.png"])
        self.assertIn("Filename: fig1.png\n", prompt)


if __name__ == "__main__":
    unittest.main()
