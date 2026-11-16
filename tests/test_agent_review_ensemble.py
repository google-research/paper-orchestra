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


from unittest import TestCase
from unittest.mock import patch

from autoraters import agent_review


class AgentReviewEnsembleTest(TestCase):
    def test_malformed_review_is_excluded_from_meta_review_and_scores(self):
        parsed = [[], {"Overall": 5}, {"Overall": 9}]
        responses = [{"parsed_response": review} for review in parsed]
        responses.append({"parsed_response": {"Summary": "Meta-review"}})
        with patch.object(
            agent_review, "call_gemini_with_text_prompt", side_effect=responses
        ) as call:
            review = agent_review.perform_review_agentreview("paper", "gemini-test")

        self.assertEqual(review, {"Summary": "Meta-review", "Overall": 7})
        meta_prompt = call.call_args.kwargs["prompt"]
        self.assertIn("Review 1/2:", meta_prompt)
        self.assertIn("Review 2/2:", meta_prompt)
        self.assertNotIn("Review 3/", meta_prompt)

    def test_malformed_meta_review_falls_back_to_first_valid_review(self):
        first = {"Summary": "First review", "Overall": 5}
        responses = [{"parsed_response": value} for value in [first, {"Overall": 9}, []]]
        with patch.object(
            agent_review, "call_gemini_with_text_prompt", side_effect=responses
        ):
            review = agent_review.perform_review_agentreview(
                "paper", "gemini-test", num_review_ensemble=2
            )

        self.assertEqual(review, {"Summary": "First review", "Overall": 7})
        self.assertEqual(first["Overall"], 5)

    def test_all_malformed_reviews_fail_before_meta_review(self):
        with patch.object(
            agent_review,
            "call_gemini_with_text_prompt",
            return_value={"parsed_response": []},
        ) as call:
            with self.assertRaisesRegex(ValueError, "No valid reviewer responses"):
                agent_review.perform_review_agentreview(
                    "paper", "gemini-test", num_review_ensemble=2
                )

        self.assertEqual(call.call_count, 2)
