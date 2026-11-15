"""Tests for routing writer steps through the router (issue #7).

Before this fix the outline, literature review synthesis and content
refinement agents called call_gemini_with_contents directly, so a writer
model name such as gpt-5 was sent to the Gemini API and failed without a
Gemini key. These tests check that the writing steps now go through
call_llm_with_contents in utils/llm_backend_utils.py, that a gpt model
reaches the OpenAI backend, that a Gemini model still reaches Gemini with
the contents unchanged, and that the literature search step still uses
Gemini by design (it needs Google Search grounding).

All LLM backends are mocked. No network calls, no real API keys.

Run from the repo root with the project venv:
  .venv/bin/python -m unittest discover -s tests -v
"""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.genai import types  # type: ignore

import utils.llm_backend_utils as router
import methods.agents.outline_agent as outline_mod
import methods.agents.literature_review_agent as lit_mod
import methods.agents.content_refinement_agent as refine_mod


def canned_openai(*args, **kwargs):
    return {"raw_response": "{}", "parsed_response": {"outline": "ok"}}


def gemini_must_not_run(*args, **kwargs):
    raise AssertionError("Gemini backend must not be called for a gpt model")


def canned_gemini(*args, **kwargs):
    return {"raw_response": "{}", "parsed_response": {"outline": "ok"}}


def openai_must_not_run(*args, **kwargs):
    raise AssertionError("OpenAI backend must not be called for a Gemini model")


def make_pdf_bytes(text="Hello PDF"):
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    return doc.tobytes()


def temp_text_file(directory, name, content="test content"):
    path = os.path.join(directory, name)
    with open(path, "w") as f:
        f.write(content)
    return path


class TestCallLlmWithContentsRouter(unittest.TestCase):
    def test_gpt_model_routes_to_openai(self):
        with mock.patch.object(
            router, "call_openai_models_with_content"
        ) as openai_mock, mock.patch.object(
            router, "call_gemini_with_contents", gemini_must_not_run
        ):
            openai_mock.return_value = canned_openai()
            parts = [
                types.Part.from_text(text="system prompt"),
                types.Part.from_text(text="user text"),
            ]
            result = router.call_llm_with_contents(
                contents=parts,
                model_name="gpt-5",
                generation_configs={"system_instruction": "be helpful"},
            )
            self.assertEqual(result["parsed_response"], {"outline": "ok"})
            openai_mock.assert_called_once()
            sent = openai_mock.call_args.kwargs["content"]
            self.assertEqual(
                sent,
                [
                    {"type": "text", "text": "system prompt"},
                    {"type": "text", "text": "user text"},
                ],
            )
            self.assertEqual(
                openai_mock.call_args.kwargs["system_prompt"], "be helpful"
            )

    def test_temperature_is_dropped_for_openai(self):
        with mock.patch.object(
            router, "call_openai_models_with_content"
        ) as openai_mock, mock.patch.object(
            router, "call_gemini_with_contents", gemini_must_not_run
        ):
            openai_mock.return_value = canned_openai()
            router.call_llm_with_contents(
                contents=["hello"],
                model_name="gpt-5",
                generation_configs={"temperature": 0.9},
            )
            configs = openai_mock.call_args.kwargs["generation_configs"]
            self.assertNotIn("temperature", configs)

    def test_gemini_model_passes_contents_through(self):
        parts = [types.Part.from_text(text="hello")]
        with mock.patch.object(
            router, "call_gemini_with_contents"
        ) as gemini_mock, mock.patch.object(
            router, "call_openai_models_with_content", openai_must_not_run
        ):
            gemini_mock.return_value = canned_gemini()
            router.call_llm_with_contents(
                contents=parts, model_name="gemini-3.1-pro-preview"
            )
            gemini_mock.assert_called_once()
            self.assertIs(gemini_mock.call_args.kwargs["contents"], parts)

    def test_plain_string_contents_route_to_openai(self):
        with mock.patch.object(
            router, "call_openai_models_with_content"
        ) as openai_mock, mock.patch.object(
            router, "call_gemini_with_contents", gemini_must_not_run
        ):
            openai_mock.return_value = canned_openai()
            router.call_llm_with_contents(
                contents=["first", "second"], model_name="gpt-5"
            )
            sent = openai_mock.call_args.kwargs["content"]
            self.assertEqual(
                sent,
                [
                    {"type": "text", "text": "first"},
                    {"type": "text", "text": "second"},
                ],
            )

    def test_pdf_bytes_part_becomes_text_for_openai(self):
        pdf_part = types.Part.from_bytes(
            data=make_pdf_bytes("Hello PDF"), mime_type="application/pdf"
        )
        with mock.patch.object(
            router, "call_openai_models_with_content"
        ) as openai_mock, mock.patch.object(
            router, "call_gemini_with_contents", gemini_must_not_run
        ):
            openai_mock.return_value = canned_openai()
            router.call_llm_with_contents(
                contents=[pdf_part, types.Part.from_text(text="review this")],
                model_name="gpt-5",
            )
            sent = openai_mock.call_args.kwargs["content"]
            self.assertEqual(len(sent), 2)
            self.assertIn("Hello PDF", sent[0]["text"])
            self.assertEqual(sent[1], {"type": "text", "text": "review this"})

    def test_image_bytes_part_becomes_image_url_for_openai(self):
        image_part = types.Part.from_bytes(
            data=b"\x89PNG fake image bytes", mime_type="image/png"
        )
        with mock.patch.object(
            router, "call_openai_models_with_content"
        ) as openai_mock, mock.patch.object(
            router, "call_gemini_with_contents", gemini_must_not_run
        ):
            openai_mock.return_value = canned_openai()
            router.call_llm_with_contents(
                contents=[image_part], model_name="gpt-5"
            )
            sent = openai_mock.call_args.kwargs["content"]
            self.assertEqual(sent[0]["type"], "image_url")
            self.assertTrue(
                sent[0]["image_url"]["url"].startswith("data:image/png;base64,")
            )

    def test_unsupported_inline_type_raises(self):
        audio_part = types.Part.from_bytes(
            data=b"fake audio", mime_type="audio/mp3"
        )
        with self.assertRaises(ValueError):
            router.call_llm_with_contents(
                contents=[audio_part], model_name="gpt-5"
            )


class TestOutlineAgentRouting(unittest.TestCase):
    def test_gpt_writer_routes_to_openai(self):
        with tempfile.TemporaryDirectory() as tmp:
            idea = temp_text_file(tmp, "idea.md")
            log = temp_text_file(tmp, "log.md")
            template = temp_text_file(tmp, "template.tex")
            guidelines = temp_text_file(tmp, "guidelines.md")
            out_path = os.path.join(tmp, "outline.json")
            with mock.patch.object(
                router, "call_openai_models_with_content", canned_openai
            ), mock.patch.object(
                router, "call_gemini_with_contents", gemini_must_not_run
            ):
                agent = outline_mod.OutlineAgent(model_name="gpt-5")
                result = agent.run(
                    idea, log, template, guidelines, output_filepath=out_path
                )
            self.assertEqual(result, {"outline": "ok"})
            with open(out_path) as f:
                self.assertEqual(json.load(f), {"outline": "ok"})

    def test_gemini_writer_still_uses_gemini(self):
        with tempfile.TemporaryDirectory() as tmp:
            idea = temp_text_file(tmp, "idea.md")
            log = temp_text_file(tmp, "log.md")
            template = temp_text_file(tmp, "template.tex")
            guidelines = temp_text_file(tmp, "guidelines.md")
            with mock.patch.object(
                router, "call_gemini_with_contents"
            ) as gemini_mock, mock.patch.object(
                router, "call_openai_models_with_content", openai_must_not_run
            ):
                gemini_mock.return_value = canned_gemini()
                agent = outline_mod.OutlineAgent(
                    model_name="gemini-3.1-pro-preview"
                )
                result = agent.run(idea, log, template, guidelines)
            self.assertEqual(result, {"outline": "ok"})
            gemini_mock.assert_called_once()
            contents = gemini_mock.call_args.kwargs["contents"]
            self.assertEqual(len(contents), 5)
            self.assertTrue(all(isinstance(p, types.Part) for p in contents))


class TestLiteratureReviewRouting(unittest.TestCase):
    def _make_agent(self, tmp, model_name):
        idea = temp_text_file(tmp, "idea.md")
        log = temp_text_file(tmp, "log.md")
        template = temp_text_file(tmp, "template.tex")
        guidelines = temp_text_file(tmp, "guidelines.md")
        return lit_mod.HybridLiteratureAgent(
            idea, log, template, guidelines, os.path.join(tmp, "out"),
            model_name=model_name,
        )

    def test_synthesis_with_gpt_routes_to_openai(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = self._make_agent(tmp, "gpt-5")
            with mock.patch.object(
                router, "call_openai_models_with_content", canned_openai
            ), mock.patch.object(
                router, "call_gemini_with_contents", gemini_must_not_run
            ):
                result = agent._synthesize_content({}, [], "2024-10")
            self.assertEqual(result, {"outline": "ok"})

    def test_search_still_uses_gemini_with_gpt_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = self._make_agent(tmp, "gpt-5")
            task = {"search_type": "broad", "focus": "test topic", "context": ""}
            outline = {"intro_related_work_plan": {"introduction_strategy": {}}}
            with mock.patch.object(
                lit_mod, "call_gemini_with_contents"
            ) as gemini_mock:
                gemini_mock.return_value = {
                    "parsed_response": {"candidates": []}
                }
                result = agent._discover_candidates(task, outline, "2024-10")
            self.assertEqual(result, [])
            gemini_mock.assert_called_once()
            self.assertEqual(
                gemini_mock.call_args.kwargs["model_name"],
                "gemini-3-flash-preview",
            )


class TestContentRefinementRouting(unittest.TestCase):
    def _make_agent(self, tmp, model_name):
        return refine_mod.ContentRefinementAgent(
            experimental_log_path=os.path.join(tmp, "log.md"),
            citation_map_path=os.path.join(tmp, "citations.json"),
            guidelines_path=os.path.join(tmp, "guidelines.md"),
            model_name=model_name,
            work_dir=os.path.join(tmp, "work"),
        )

    def test_formatting_review_with_gpt_routes_to_openai(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = self._make_agent(tmp, "gpt-5")
            fake_images = [os.path.join(tmp, "page1.png")]
            with mock.patch.object(
                refine_mod, "pdf_to_grid_images", return_value=fake_images
            ), mock.patch.object(
                refine_mod, "call_llm_with_images"
            ) as routed_mock:
                routed_mock.return_value = {
                    "parsed_response": {"figure_and_tables": {}}
                }
                review = agent._get_formatting_review(
                    os.path.join(tmp, "paper.pdf"), "v1"
                )
            self.assertEqual(review, {"figure_and_tables": {}})
            routed_mock.assert_called_once()
            self.assertEqual(
                routed_mock.call_args.kwargs["model_name"], "gpt-5"
            )
            self.assertEqual(
                routed_mock.call_args.kwargs["images"], fake_images
            )

    def test_formatting_review_with_gemini_still_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = self._make_agent(tmp, "gemini-3.1-pro-preview")
            fake_images = [os.path.join(tmp, "page1.png")]
            with mock.patch.object(
                refine_mod, "pdf_to_grid_images", return_value=fake_images
            ), mock.patch.object(
                router, "call_gemini_with_images"
            ) as gemini_mock, mock.patch.object(
                router, "call_openai_models_with_content", openai_must_not_run
            ):
                gemini_mock.return_value = {
                    "parsed_response": {"figure_and_tables": {}}
                }
                review = agent._get_formatting_review(
                    os.path.join(tmp, "paper.pdf"), "v1"
                )
            self.assertEqual(review, {"figure_and_tables": {}})
            gemini_mock.assert_called_once()
            self.assertEqual(
                gemini_mock.call_args.kwargs["model_name"],
                "gemini-3.1-pro-preview",
            )


if __name__ == "__main__":
    unittest.main()
