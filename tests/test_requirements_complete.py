"""Tests that requirements.txt declares every direct dependency.

autoraters/citation_f1.py imported joblib, utils/scholar_utils.py and
autoraters/citation_f1.py import requests, and utils/pdf_utils.py and
autoraters/agent_review.py import numpy, but none of the three were listed
in requirements.txt. They only worked when another package happened to pull
them in, and joblib was not pulled in at all, so the citation autorater
crashed on import. This test scans the repo for third-party imports and
fails if any of them is missing from requirements.txt.

Run from the repo root with the project venv:
  .venv/bin/python -m unittest discover -s tests -v
"""

import ast
import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Top-level module name -> distribution name in requirements.txt.
DIST_MAP = {
    "cv2": "opencv-python",
    "dotenv": "python-dotenv",
    "google": "google-genai",
    "joblib": "joblib",
    "json_repair": "json_repair",
    "matplotlib": "matplotlib",
    "numpy": "numpy",
    "openai": "openai",
    "pydantic": "pydantic",
    "pymupdf": "PyMuPDF",
    "pymupdf4llm": "pymupdf4llm",
    "pypdf": "pypdf",
    "requests": "requests",
    "rich": "rich",
    "streamlit": "streamlit",
    "thefuzz": "thefuzz",
    "tqdm": "tqdm",
}

LOCAL_TOP_LEVELS = {"utils", "methods", "autoraters", "frontend_utils"}


def declared_distributions():
    req_path = os.path.join(REPO_ROOT, "requirements.txt")
    declared = set()
    with open(req_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                declared.add(line.split("==")[0].split(">=")[0].strip().lower())
    return declared


def imported_third_party_modules():
    found = set()
    stdlib = sys.stdlib_module_names
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [
            d for d in dirnames if d not in (".venv", ".git", "__pycache__", "tests")
        ]
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            path = os.path.join(dirpath, filename)
            with open(path) as f:
                tree = ast.parse(f.read(), filename=path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        found.add(alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    if node.module:
                        found.add(node.module.split(".")[0])
    return {
        mod for mod in found if mod not in stdlib and mod not in LOCAL_TOP_LEVELS
    }


class TestRequirementsComplete(unittest.TestCase):
    def test_every_direct_dependency_is_declared(self):
        declared = declared_distributions()
        imported = imported_third_party_modules()
        missing = sorted(
            mod for mod in imported if DIST_MAP.get(mod, mod).lower() not in declared
        )
        self.assertEqual(missing, [], msg=f"Missing from requirements.txt: {missing}")

    def test_known_direct_dependencies_present(self):
        declared = declared_distributions()
        for dist in ("joblib", "requests", "numpy"):
            self.assertIn(dist, declared)


if __name__ == "__main__":
    unittest.main()
