"""Tests for lazy OpenAI client creation (issue #5).

The OpenAI client used to be created at import time, so any run without
OPENAI_API_KEY crashed before doing any work, even when only Gemini models
were selected. These tests check that importing works without the key, that
an OpenAI call without the key still fails with a clear error, and that a
call with the key set reaches the client.

Run from the repo root with the project venv:
  .venv/bin/python -m unittest discover -s tests -v
"""

import os
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import utils.openai_utils as openai_utils


def gemini_only_env():
    env = dict(os.environ)
    env.pop("OPENAI_API_KEY", None)
    env["GEMINI_API_KEY"] = "fake-gemini-key-for-tests"
    env.pop("VERTEX_AI_PROJECT", None)
    env.pop("VERTEX_AI_LOCATION", None)
    return env


class TestImportWithoutOpenAIKey(unittest.TestCase):
    def test_import_openai_utils_without_key(self):
        code = "import utils.openai_utils; print('import ok')"
        result = subprocess.run(
            [sys.executable, "-c", code],
            env=gemini_only_env(),
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
            env=gemini_only_env(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("import ok", result.stdout)

    def test_cli_help_without_key(self):
        result = subprocess.run(
            [sys.executable, "paper_writing_cli.py", "--help"],
            env=gemini_only_env(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("usage", result.stdout.lower())


class TestLazyClient(unittest.TestCase):
    def setUp(self):
        self._saved_key = os.environ.pop("OPENAI_API_KEY", None)
        self._saved_client = openai_utils.openai_client
        openai_utils.openai_client = None

    def tearDown(self):
        openai_utils.openai_client = self._saved_client
        if self._saved_key is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = self._saved_key

    def test_call_without_key_raises_value_error(self):
        with self.assertRaisesRegex(ValueError, "OPENAI_API_KEY must be set."):
            openai_utils.call_openai_models_with_text_prompt(
                "hello", "gpt-4o", max_retries=1, base_interval_sec=0
            )

    def test_call_without_key_fails_fast(self):
        import time

        start = time.monotonic()
        with self.assertRaises(ValueError):
            openai_utils.call_openai_models_with_text_prompt(
                "hello", "gpt-4o", max_retries=5, base_interval_sec=5
            )
        self.assertLess(time.monotonic() - start, 5)

    def test_client_created_with_key_and_cached(self):
        os.environ["OPENAI_API_KEY"] = "fake-openai-key"
        fake_client = mock.MagicMock()
        with mock.patch.object(openai_utils, "OpenAI", return_value=fake_client) as mock_openai:
            first = openai_utils.get_openai_client()
            second = openai_utils.get_openai_client()
        self.assertIs(first, fake_client)
        self.assertIs(second, fake_client)
        mock_openai.assert_called_once_with(api_key="fake-openai-key")

    def test_call_with_key_uses_client(self):
        os.environ["OPENAI_API_KEY"] = "fake-openai-key"
        fake_response = mock.MagicMock()
        fake_response.choices = [mock.MagicMock()]
        fake_response.choices[0].message.content = '{"answer": 42}'
        fake_client = mock.MagicMock()
        fake_client.chat.completions.create.return_value = fake_response
        with mock.patch.object(openai_utils, "OpenAI", return_value=fake_client):
            result = openai_utils.call_openai_models_with_text_prompt(
                "hello", "gpt-4o"
            )
        self.assertEqual(result["parsed_response"], {"answer": 42})
        fake_client.chat.completions.create.assert_called_once()
        call_kwargs = fake_client.chat.completions.create.call_args
        self.assertEqual(call_kwargs.kwargs["model"], "gpt-4o")


if __name__ == "__main__":
    unittest.main()
