import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils.pdf_utils import compile_latex


class CompileLatexTimeoutTest(unittest.TestCase):
    def test_timeout_discards_partial_pdf_even_when_it_is_the_requested_path(self):
        for timeout_at in (0, 1, 3):
            with self.subTest(timeout_at=timeout_at), tempfile.TemporaryDirectory() as directory:
                pdf_path = Path(directory, "template.pdf")
                pdf_path.write_bytes(b"stale output from earlier run")
                passes = []

                def run(command, **kwargs):
                    passes.append(command[0])
                    if command[0] == "pdflatex":
                        pdf_path.write_bytes(b"partial output from this run")
                    if len(passes) == timeout_at + 1:
                        raise subprocess.TimeoutExpired(command, kwargs["timeout"])
                    return subprocess.CompletedProcess(command, 0, "", "")

                with patch("utils.pdf_utils.subprocess.run", side_effect=run):
                    compile_latex(directory, pdf_path, timeout=1)

                self.assertFalse(pdf_path.exists())
                self.assertEqual(len(passes), timeout_at + 1)

    def test_success_keeps_output_at_requested_path(self):
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory, "template.pdf")

            def run(command, **kwargs):
                if command[0] == "pdflatex":
                    pdf_path.write_bytes(b"new output")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch("utils.pdf_utils.subprocess.run", side_effect=run) as process:
                compile_latex(directory, pdf_path)

            self.assertEqual(pdf_path.read_bytes(), b"new output")
            self.assertEqual(process.call_count, 4)


if __name__ == "__main__":
    unittest.main()
