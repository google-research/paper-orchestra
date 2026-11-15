"""Tests that the pipeline death signal works on systems without prctl.

frontend/app.py asks the OS to kill the pipeline process if the Streamlit
server dies, using libc prctl, which only exists on Linux. On macOS the
old preexec_fn raised AttributeError and the run failed to start. These
tests check that the guarded helper skips the call on a libc without
prctl and still calls it on Linux.

Run from the repo root with the project venv:
  .venv/bin/python -m unittest discover -s tests -v
"""

import os
import signal
import sys
import unittest
from unittest import mock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_frontend_app():
    os.environ.setdefault("GEMINI_API_KEY", "fake-key-for-tests")
    os.environ.setdefault("OPENAI_API_KEY", "fake-key-for-tests")
    os.environ.pop("VERTEX_AI_PROJECT", None)
    os.environ.pop("VERTEX_AI_LOCATION", None)
    sys.path.insert(0, os.path.join(REPO_ROOT, "frontend"))
    sys.path.insert(0, REPO_ROOT)
    import frontend.app as app_module

    return app_module


class TestParentDeathSignal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = load_frontend_app()

    def test_no_crash_without_prctl(self):
        class FakeLibc:
            pass  # no prctl attribute, like macOS libc

        with mock.patch.object(self.app.ctypes, "CDLL", return_value=FakeLibc()):
            self.app._set_parent_death_signal()

    def test_prctl_called_on_linux_libc(self):
        mock_libc = mock.Mock()
        with mock.patch.object(self.app.ctypes, "CDLL", return_value=mock_libc):
            self.app._set_parent_death_signal()
        mock_libc.prctl.assert_called_once_with(1, signal.SIGKILL)


if __name__ == "__main__":
    unittest.main()
