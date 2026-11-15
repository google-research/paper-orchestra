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

"""Tests for the optional OpenRouter free-model support.

Stdlib unittest only. The OpenRouter client is mocked, so no network
call happens and no real key is needed.
"""

import json
import os
import subprocess
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from google.genai import types as genai_types  # type: ignore

import utils.llm_backend_utils as backend
import utils.openrouter_utils as openrouter_utils
from utils.llm_backend_utils import (
    DEFAULT_FREE_MODEL,
    call_llm_with_contents,
    call_llm_with_text_prompt,
    resolve_model_provider,
    set_model_provider,
)

FREE_MODEL = DEFAULT_FREE_MODEL
KEY_VARS = (
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "VERTEX_AI_PROJECT",
    "VERTEX_AI_LOCATION",
    "OPENROUTER_API_KEY",
)


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content):
        self.message = FakeMessage(content)


class FakeResponse:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


class FakeCompletions:
    def __init__(self, client, content):
        self.client = client
        self.content = content

    def create(self, model, messages, **kwargs):
        self.client.calls.append(
            {"model": model, "messages": messages, "kwargs": kwargs}
        )
        return FakeResponse(self.content)


class FakeChat:
    def __init__(self, client, content):
        self.completions = FakeCompletions(client, content)


class FakeOpenAIClient:
    """Stands in for openai.OpenAI. Records calls, never touches network."""

    instances = []

    def __init__(self, api_key=None, base_url=None, **kwargs):
        self.api_key = api_key
        self.base_url = base_url
        self.calls = []
        self.chat = FakeChat(self, '{"key": "value"}')
        FakeOpenAIClient.instances.append(self)


class OpenRouterTestBase(unittest.TestCase):
    def setUp(self):
        self.saved_env = {key: os.environ.get(key) for key in KEY_VARS}
        for key in KEY_VARS:
            os.environ.pop(key, None)
        self.saved_provider = backend.get_model_provider()
        set_model_provider("auto")
        openrouter_utils._openrouter_client = None
        FakeOpenAIClient.instances = []

    def tearDown(self):
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        set_model_provider(self.saved_provider)
        openrouter_utils._openrouter_client = None

    def fake_openrouter(self):
        os.environ["OPENROUTER_API_KEY"] = "fake-openrouter-key"
        patcher = mock.patch.object(
            openrouter_utils, "OpenAI", FakeOpenAIClient
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        return patcher


class RoutingTests(OpenRouterTestBase):
    def test_free_model_name_routes_to_openrouter(self):
        self.fake_openrouter()
        result = call_llm_with_text_prompt(
            "Return a JSON object.", FREE_MODEL
        )
        self.assertEqual(result["parsed_response"], {"key": "value"})
        client = FakeOpenAIClient.instances[0]
        self.assertEqual(client.base_url, "https://openrouter.ai/api/v1")
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0]["model"], FREE_MODEL)

    def test_openrouter_call_needs_no_gemini_or_openai_key(self):
        self.fake_openrouter()
        result = call_llm_with_text_prompt(
            "Return a JSON object.", FREE_MODEL
        )
        self.assertIsNotNone(result["parsed_response"])
        self.assertNotIn("OPENAI_API_KEY", os.environ)
        self.assertNotIn("GEMINI_API_KEY", os.environ)

    def test_provider_flag_forces_openrouter_for_plain_name(self):
        self.fake_openrouter()
        set_model_provider("openrouter")
        result = call_llm_with_text_prompt(
            "Return a JSON object.", "some-plain-model-name"
        )
        self.assertEqual(result["parsed_response"], {"key": "value"})
        self.assertEqual(
            FakeOpenAIClient.instances[0].calls[0]["model"],
            "some-plain-model-name",
        )

    def test_gpt_name_still_routes_to_openai(self):
        fake_openai = types.ModuleType("utils.openai_utils")
        calls = []
        fake_openai.call_openai_models_with_text_prompt = (
            lambda prompt, model_name, **kwargs: calls.append(model_name)
            or {"raw_response": "{}", "parsed_response": {}}
        )
        fake_openai.parse_openai_json_results = lambda s: {}
        with mock.patch.dict(sys.modules, {"utils.openai_utils": fake_openai}):
            call_llm_with_text_prompt("hi", "gpt-4o")
        self.assertEqual(calls, ["gpt-4o"])
        self.assertEqual(FakeOpenAIClient.instances, [])

    def test_gemini_name_still_routes_to_gemini(self):
        fake_gemini = types.ModuleType("utils.gemini_utils")
        calls = []
        fake_gemini.call_gemini_with_text_prompt = (
            lambda prompt, model_name, **kwargs: calls.append(model_name)
            or {"raw_response": "{}", "parsed_response": {}}
        )
        fake_gemini.parse_gemini_json_results = lambda s: {}
        with mock.patch.dict(sys.modules, {"utils.gemini_utils": fake_gemini}):
            call_llm_with_text_prompt("hi", "gemini-3.1-pro-preview")
        self.assertEqual(calls, ["gemini-3.1-pro-preview"])
        self.assertEqual(FakeOpenAIClient.instances, [])

    def test_resolve_model_provider_defaults_unchanged(self):
        self.assertEqual(resolve_model_provider("gemini-3.1-pro-preview"), "gemini")
        self.assertEqual(resolve_model_provider("gpt-4o"), "openai")
        self.assertEqual(resolve_model_provider(FREE_MODEL), "openrouter")
        self.assertEqual(resolve_model_provider("gemini-3-flash-preview"), "gemini")
        self.assertEqual(
            resolve_model_provider("projects/my-proj/locations/us/models/gemini-3-pro"),
            "gemini",
        )

    def test_set_model_provider_rejects_unknown(self):
        with self.assertRaises(ValueError):
            set_model_provider("no-such-provider")


class ClientTests(OpenRouterTestBase):
    def test_missing_openrouter_key_raises_clear_error(self):
        with self.assertRaisesRegex(
            ValueError, "OPENROUTER_API_KEY must be set."
        ):
            openrouter_utils.call_openrouter_models_with_text_prompt(
                "hi", FREE_MODEL
            )

    def test_client_created_once_and_cached(self):
        self.fake_openrouter()
        call_llm_with_text_prompt("one", FREE_MODEL)
        call_llm_with_text_prompt("two", FREE_MODEL)
        self.assertEqual(len(FakeOpenAIClient.instances), 1)
        self.assertEqual(len(FakeOpenAIClient.instances[0].calls), 2)


class ContentsTests(OpenRouterTestBase):
    def test_contents_routed_to_openrouter(self):
        self.fake_openrouter()
        contents = [
            genai_types.Part.from_text(text="Write a section."),
            "plain string part",
            genai_types.Part.from_bytes(
                data=b"fake-image-bytes", mime_type="image/png"
            ),
        ]
        result = call_llm_with_contents(contents, FREE_MODEL)
        self.assertEqual(result["parsed_response"], {"key": "value"})
        sent = FakeOpenAIClient.instances[0].calls[0]["messages"][0]["content"]
        kinds = [part["type"] for part in sent]
        self.assertEqual(kinds, ["text", "text", "image_url"])
        self.assertIn("Write a section.", sent[0]["text"])

    def test_pdf_part_converted_to_text(self):
        self.fake_openrouter()
        import pymupdf

        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Hello PDF world")
        pdf_bytes = doc.tobytes()
        contents = [
            genai_types.Part.from_bytes(
                data=pdf_bytes, mime_type="application/pdf"
            ),
        ]
        result = call_llm_with_contents(contents, FREE_MODEL)
        self.assertEqual(result["parsed_response"], {"key": "value"})
        sent = FakeOpenAIClient.instances[0].calls[0]["messages"][0]["content"]
        self.assertEqual(len(sent), 1)
        self.assertIn("Hello PDF world", sent[0]["text"])


class ImportTests(unittest.TestCase):
    def _clean_env(self):
        env = dict(os.environ)
        for key in KEY_VARS:
            env.pop(key, None)
        return env

    def test_pipeline_imports_with_no_keys_set(self):
        repo = os.path.join(os.path.dirname(__file__), "..")
        for module in (
            "methods.paper_writer",
            "methods.paper_writer_with_plotting",
            "utils.llm_backend_utils",
            "methods.agents.outline_agent",
            "methods.agents.content_refinement_agent",
            "utils.paper_banana_utils",
        ):
            proc = subprocess.run(
                [sys.executable, "-c", f"import {module}"],
                cwd=repo,
                env=self._clean_env(),
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"import {module} failed: {proc.stderr.strip()[-300:]}",
            )

    def test_cli_help_lists_model_provider(self):
        repo = os.path.join(os.path.dirname(__file__), "..")
        proc = subprocess.run(
            [sys.executable, "paper_writing_cli.py", "--help"],
            cwd=repo,
            env=self._clean_env(),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--model_provider", proc.stdout)
        self.assertIn("openrouter", proc.stdout)

    def test_cli_rejects_unknown_provider(self):
        repo = os.path.join(os.path.dirname(__file__), "..")
        proc = subprocess.run(
            [
                sys.executable,
                "paper_writing_cli.py",
                "--model_provider",
                "no-such-provider",
                "--raw_materials_dir",
                "/tmp",
                "--latex_template_dir",
                "/tmp",
            ],
            cwd=repo,
            env=self._clean_env(),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
