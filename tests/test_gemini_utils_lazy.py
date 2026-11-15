"""Tests for lazy Gemini client creation.

The Gemini client used to be created at import time, so any run without a
Gemini key or Vertex config crashed before doing any work, even when only
OpenAI models were selected. These tests check that importing works without
the key, that a Gemini call without the key still fails with a clear error,
and that a call with the key set reaches the client.

Run from the repo root with the project venv:
  .venv/bin/python -m unittest discover -s tests -v
"""

import os
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import utils.gemini_utils as gemini_utils


def openai_only_env():
    env = dict(os.environ)
    env.pop("GEMINI_API_KEY", None)
    env.pop("VERTEX_AI_PROJECT", None)
    env.pop("VERTEX_AI_LOCATION", None)
    env["OPENAI_API_KEY"] = "fake-openai-key-for-tests"
    return env


class TestImportWithoutGeminiKey(unittest.TestCase):
    def test_import_gemini_utils_without_key(self):
        code = "import utils.gemini_utils; print('import ok')"
        result = subprocess.run(
            [sys.executable, "-c", code],
            env=openai_only_env(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("import ok", result.stdout)

    def test_import_paper_writer_without_key(self):
        code = (
            "import methods.paper_writer;"
            "import methods.paper_writer_with_plotting;"
            "print('import ok')"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            env=openai_only_env(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("import ok", result.stdout)

    def test_cli_help_without_key(self):
        result = subprocess.run(
            [sys.executable, "paper_writing_cli.py", "--help"],
            env=openai_only_env(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("usage", result.stdout.lower())


class TestLazyClient(unittest.TestCase):
    def setUp(self):
        self._saved_env = {
            key: os.environ.pop(key, None)
            for key in ("GEMINI_API_KEY", "VERTEX_AI_PROJECT", "VERTEX_AI_LOCATION")
        }
        self._saved_client = gemini_utils.genai_client
        gemini_utils.genai_client = None

    def tearDown(self):
        gemini_utils.genai_client = self._saved_client
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_call_without_key_raises_value_error(self):
        with self.assertRaisesRegex(
            ValueError, "GEMINI_API_KEY must be set."
        ):
            gemini_utils.call_gemini_with_text_prompt(
                "hello", "gemini-3.1-pro-preview", max_retries=1, base_interval_sec=0
            )

    def test_call_without_key_fails_fast(self):
        import time

        start = time.monotonic()
        with self.assertRaises(ValueError):
            gemini_utils.call_gemini_with_text_prompt(
                "hello", "gemini-3.1-pro-preview", max_retries=5, base_interval_sec=5
            )
        self.assertLess(time.monotonic() - start, 5)

    def test_client_created_with_key_and_cached(self):
        os.environ["GEMINI_API_KEY"] = "fake-key"
        with mock.patch.object(gemini_utils.genai, "Client") as mock_client_cls:
            first = gemini_utils.get_genai_client()
            second = gemini_utils.get_genai_client()
        mock_client_cls.assert_called_once_with(api_key="fake-key")
        self.assertIs(first, second)

    def test_vertex_config_preferred_when_set(self):
        os.environ["VERTEX_AI_PROJECT"] = "fake-project"
        os.environ["VERTEX_AI_LOCATION"] = "fake-location"
        with mock.patch.object(gemini_utils.genai, "Client") as mock_client_cls:
            gemini_utils.get_genai_client()
        mock_client_cls.assert_called_once_with(
            vertexai=True, project="fake-project", location="fake-location"
        )

    def test_call_with_key_reaches_mocked_client(self):
        os.environ["GEMINI_API_KEY"] = "fake-key"
        mock_response = mock.Mock()
        mock_response.text = '```json\n{"ok": true}\n```'
        mock_client = mock.Mock()
        mock_client.models.generate_content.return_value = mock_response
        with mock.patch.object(gemini_utils.genai, "Client", return_value=mock_client):
            result = gemini_utils.call_gemini_with_text_prompt(
                "hello", "gemini-3.1-pro-preview", max_retries=1, base_interval_sec=0
            )
        self.assertEqual(result["parsed_response"], {"ok": True})
        mock_client.models.generate_content.assert_called_once()


if __name__ == "__main__":
    unittest.main()
