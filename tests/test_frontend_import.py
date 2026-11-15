"""Tests that frontend/app.py imports from the repo root.

app.py used to import frontend_utils before adding the repo root to
sys.path, so `import frontend.app` from the repo root failed with
ModuleNotFoundError even though the documented `streamlit run
frontend/app.py` launch worked. These tests check the import works from
the repo root, and that the documented launch path is unaffected.

Run from the repo root with the project venv:
  .venv/bin/python -m unittest discover -s tests -v
"""

import os
import subprocess
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def import_env():
    env = dict(os.environ)
    env["GEMINI_API_KEY"] = "fake-key-for-tests"
    env["OPENAI_API_KEY"] = "fake-key-for-tests"
    env.pop("VERTEX_AI_PROJECT", None)
    env.pop("VERTEX_AI_LOCATION", None)
    return env


class TestFrontendImport(unittest.TestCase):
    def test_import_from_repo_root(self):
        result = subprocess.run(
            [sys.executable, "-c", "import frontend.app; print('import ok')"],
            env=import_env(),
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("import ok", result.stdout)

    def test_import_from_frontend_dir_still_works(self):
        result = subprocess.run(
            [sys.executable, "-c", "import app; print('import ok')"],
            env=import_env(),
            capture_output=True,
            text=True,
            cwd=os.path.join(REPO_ROOT, "frontend"),
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("import ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
