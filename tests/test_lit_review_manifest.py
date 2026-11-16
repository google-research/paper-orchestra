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
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from autoraters import lit_review_quality


class LiteratureReviewManifestTest(TestCase):
    def test_ratings_use_a_sibling_file_without_overwriting_the_manifest(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pdf = root / "paper.pdf"
            pdf.touch()
            manifest_data = [{"paper_id": "sample", "pdf_path": str(pdf)}]
            original = json.dumps(manifest_data)
            for parent_name, manifest_name in [
                ("normal", "papers.json"),
                ("experiment.json", "papers.json"),
                ("normal", "papers.JSON"),
                ("normal", "papers"),
            ]:
                with self.subTest(parent=parent_name, manifest=manifest_name):
                    parent = root / parent_name
                    parent.mkdir(exist_ok=True)
                    manifest = parent / manifest_name
                    manifest.write_text(original, encoding="utf-8")
                    with patch.object(
                        lit_review_quality, "rate_single_paper",
                        return_value={"overall_score": 80},
                    ):
                        lit_review_quality.perform_batch_rating_json(str(manifest))
                    self.assertEqual(manifest.read_text(encoding="utf-8"), original)
                    output = parent / "papers_lit_review_quality_ratings.json"
                    ratings = json.loads(output.read_text(encoding="utf-8"))
                    self.assertEqual(ratings["sample"]["pdf_path"], str(pdf))
                    self.assertEqual(ratings["overall_metrics"]["overall_score"], 80)
                    output.unlink()
