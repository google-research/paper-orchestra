"""Tests that the CLI validates --latex_template_dir up front.

A missing template directory used to start the pipeline and fail three
times inside write_single_paper before giving up, while a missing raw
materials directory already failed fast with a clear error. These tests
check that both missing directories now fail fast, before any work starts.

Run from the repo root with the project venv:
  .venv/bin/python -m unittest discover -s tests -v
"""

import os
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_cli(raw_dir, template_dir):
    return subprocess.run(
        [
            sys.executable,
            "paper_writing_cli.py",
            "--raw_materials_dir",
            raw_dir,
            "--latex_template_dir",
            template_dir,
            "--output_dir",
            os.path.join(tempfile.gettempdir(), "po_cli_test_out"),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


class TestCliValidatesDirectories(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raw_dir = os.path.join(self._tmp.name, "raw")
        os.makedirs(self.raw_dir)
        for name in ("idea_sparse.md", "experimental_log.md"):
            with open(os.path.join(self.raw_dir, name), "w") as f:
                f.write("# test\n")

    def test_missing_template_dir_fails_fast(self):
        result = run_cli(self.raw_dir, os.path.join(self._tmp.name, "NOPE"))
        self.assertEqual(result.returncode, 1)
        combined = result.stdout + result.stderr
        self.assertIn("does not exist", combined)
        self.assertIn("LaTeX template directory", combined)
        self.assertNotIn("Try 1/3", combined)

    def test_missing_raw_dir_still_fails_fast(self):
        result = run_cli(
            os.path.join(self._tmp.name, "NOPE"),
            os.path.join(REPO_ROOT, "templates", "cvpr2025"),
        )
        self.assertEqual(result.returncode, 1)
        combined = result.stdout + result.stderr
        self.assertIn("does not exist", combined)
        self.assertIn("Raw materials directory", combined)


if __name__ == "__main__":
    unittest.main()
