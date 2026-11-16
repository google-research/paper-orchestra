import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from methods.agents import content_refinement_agent as refinement


class PeerReviewFailureTest(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        source = self.directory / "draft.tex"
        source.write_text("Initial draft", encoding="utf-8")
        self.source = source
        self.agent = refinement.ContentRefinementAgent(
            experimental_log_path=source,
            citation_map_path=source,
            guidelines_path=source,
            max_reflections=1,
            work_dir=self.directory,
        )
        self.enterContext(
            patch.object(refinement, "compile_latex", side_effect=self.compile_draft)
        )
        self.enterContext(patch.object(refinement, "pdf_to_grid_images"))
        self.enterContext(patch.object(refinement, "load_paper", return_value="Text"))
        self.review_format = self.enterContext(
            patch.object(self.agent, "_get_formatting_review", return_value={})
        )
        self.revise = self.enterContext(
            patch.object(
                refinement,
                "call_gemini_with_contents",
                return_value={
                    "parsed_response": json.dumps(
                        {"latex": "Revised draft", "json": {}}
                    )
                },
            )
        )

    @staticmethod
    def compile_draft(directory, output, stem):
        Path(output).write_bytes(Path(directory, stem + ".tex").read_bytes())

    def test_missing_baseline_score_skips_content_refinement(self):
        with patch.object(refinement, "perform_review_agentreview", return_value={}):
            final_pdf = self.agent.run(self.source)

        self.revise.assert_not_called()
        self.review_format.assert_called_once()
        self.assertEqual(Path(final_pdf).read_bytes(), b"Initial draft")
        self.assertIsNone(self.agent.current_score)

    def test_nonfinite_candidate_score_cannot_replace_baseline(self):
        scores = [{"Overall": 5}, {"Overall": "NaN"}]
        with patch.object(
            refinement, "perform_review_agentreview", side_effect=scores
        ):
            final_pdf = self.agent.run(self.source)

        self.revise.assert_called_once()
        self.review_format.assert_called_once()
        self.assertEqual(Path(final_pdf).read_bytes(), b"Initial draft")
        self.assertEqual(self.agent.current_score, 5)

    def test_valid_improvement_can_replace_baseline(self):
        scores = [{"Overall": 5}, {"Overall": "6"}]
        with patch.object(
            refinement, "perform_review_agentreview", side_effect=scores
        ):
            final_pdf = self.agent.run(self.source)

        self.assertEqual(Path(final_pdf).read_bytes(), b"Revised draft")
        self.assertEqual(self.agent.current_score, 6)


if __name__ == "__main__":
    unittest.main()
