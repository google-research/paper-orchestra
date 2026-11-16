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

from autoraters import sxs_lit_review_quality, sxs_paper_quality


class SideBySideCheckpointScopeTest(TestCase):
    def test_summary_uses_only_current_pairs_and_reuses_matching_checkpoints(self):
        for module, run_batch, rate_name, prefix in [
            (
                sxs_lit_review_quality,
                sxs_lit_review_quality.perform_sxs_lit_review_batch,
                "rate_sxs_lit_review",
                "sxs_lit_review",
            ),
            (
                sxs_paper_quality,
                sxs_paper_quality.perform_sxs_paper_quality_batch,
                "rate_sxs_paper_quality",
                "sxs_paper_quality",
            ),
        ]:
            with self.subTest(module=module.__name__), TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                first, second, output = (root / name for name in ("a", "b", "output"))
                output.mkdir()
                for directory in (first, second):
                    for paper_id in ("matching", "changed", "failed"):
                        paper = directory / paper_id / "current.pdf"
                        paper.parent.mkdir(parents=True)
                        paper.touch()

                def cached_rating(paper_id, name):
                    return {
                        "paper_1_path": str(first / paper_id / name),
                        "paper_2_path": str(second / paper_id / name),
                        "category_5pt": "loss",
                        "category_3pt": "loss",
                    }

                previous_ratings = {
                    "matching": cached_rating("matching", "current.pdf"),
                    "changed": cached_rating("changed", "old.pdf"),
                    "failed": cached_rating("failed", "old.pdf"),
                    "removed": cached_rating("removed", "current.pdf"),
                }
                filename = output / f"{prefix}_enhanced_gemini-test_a_vs_b_unknown.json"
                filename.write_text(json.dumps(previous_ratings), encoding="utf-8")

                def rate(paper_1, paper_2, *, model_name):
                    if Path(paper_1).parent.name == "failed":
                        return {}
                    winner = "paper_1" if Path(paper_1).parts[-3] == "a" else "paper_2"
                    return {"winner": winner}

                with patch.object(module, rate_name, side_effect=rate) as rate_call:
                    with patch.object(module, "load_paper", side_effect=lambda path, **_: path):
                        run_batch(
                            str(first), str(second), "current.pdf", "current.pdf",
                            "a", "b", str(output), "gemini-test",
                        )

                results = json.loads(filename.read_text(encoding="utf-8"))
                self.assertEqual(rate_call.call_count, 4)
                self.assertEqual(results["matching"], previous_ratings["matching"])
                self.assertEqual(results["removed"], previous_ratings["removed"])
                self.assertEqual(results["failed"], previous_ratings["failed"])
                self.assertEqual(results["changed"]["category_3pt"], "win")
                summary = results["_summary_stats"]
                self.assertEqual(summary["total_valid_evals"], 2)
                self.assertEqual(summary["three_point"]["wins"], 1)
                self.assertEqual(summary["three_point"]["losses"], 1)
