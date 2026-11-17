import contextlib
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import anthropic
import httpx
import pymupdf

import paper_writing_cli
from utils import anthropic_utils as backend
from utils.materials import load_experiment_context, write_materials_manifest
from test_claude_backend import sse_response
from test_scholarly import sample


LATEX = r"""\documentclass{article}
\begin{document}
Synthetic research draft. This text exists only for an offline orchestration test.
No empirical conclusion or real experimental measurement is represented here.
\end{document}"""


def fake_compile(cwd, pdf_file, texfile_name="template", timeout=30):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Offline test PDF. " + "Synthetic test content. " * 12)
    doc.save(pdf_file)
    doc.close()


def create_materials(root):
    materials = root / "materials"
    template = root / "template"
    materials.mkdir()
    template.mkdir()
    (materials / "idea_sparse.md").write_text("Synthetic idea")
    (materials / "experimental_log.md").write_text("Synthetic results only; no real findings.")
    (materials / "claims.md").write_text("CLAIM_BOUNDARY_SENTINEL: Never claim profitability.")
    (template / "template.tex").write_text(LATEX)
    (template / "guidelines.md").write_text("Use a readable article layout.")
    return materials, template


class PipelineTests(unittest.TestCase):
    def test_full_pipeline_uses_claude_sdk_without_external_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            materials, template = create_materials(root)
            out = root / "out"
            outline = {"intro_related_work_plan": {"introduction_strategy": {"search_directions": ["verification"]}}, "section_plan": []}
            high = {"Overall": 8, "Confidence": 4, "Quality": 3, "Clarity": 3}
            low = dict(high, Overall=7)
            responses = [
                json.dumps(outline), json.dumps({"queries": ["verified paper"]}),
                json.dumps({"selected": [{"id": 0, "reason": "relevant"}]}),
                "```latex\n" + LATEX + "\n```", "```latex\n" + LATEX + "\n```",
                *[json.dumps(high)] * 4,
                '```json\n{"change": "offline test"}\n```\n```latex\n' + LATEX + '\n```',
                *[json.dumps(low)] * 4,
                json.dumps({"figure_and_tables": {}, "other_issues": []}),
            ]
            requests_seen = []
            def handler(request):
                requests_seen.append(json.loads(request.content))
                if not responses:
                    raise AssertionError("Unexpected extra model call")
                return sse_response(responses.pop(0))
            client = anthropic.Anthropic(api_key="test-not-real", base_url="https://claude.invalid", http_client=httpx.Client(transport=httpx.MockTransport(handler)), max_retries=0)
            paper = sample(externalIds={"DOI": "10.example/verified"})
            def retrieve(query, cutoff_date, audit_dir=None):
                Path(audit_dir).mkdir(parents=True, exist_ok=True)
                return [paper]
            with client, patch.object(backend, "_client", client), patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-not-real", "ANTHROPIC_TEMPERATURE": ""}), patch("requests.get", side_effect=AssertionError("Live requests are forbidden in offline tests")), patch("paper_writing_cli.shutil.which", return_value="/test/bin/tool"), patch("methods.agents.literature_review_agent.search_papers", retrieve), patch("methods.agents.content_refinement_agent.compile_latex", fake_compile), contextlib.redirect_stdout(io.StringIO()):
                code = paper_writing_cli.main([
                    "--raw_materials_dir", str(materials), "--latex_template_dir", str(template),
                    "--output_dir", str(out), "--research_cutoff", "2025-01",
                ])
            self.assertEqual(code, 0, (out / "run.log").read_text())
            self.assertEqual(responses, [])
            self.assertEqual(len(requests_seen), 15)
            self.assertTrue(all(r["model"].startswith("claude-") for r in requests_seen))
            self.assertIn("CLAIM_BOUNDARY_SENTINEL", json.dumps(requests_seen[0]))
            self.assertIn("CLAIM_BOUNDARY_SENTINEL", json.dumps(requests_seen[4]))
            self.assertTrue((out / "final_paper.pdf").is_file())
            self.assertTrue((out / "final_paper.tex").is_file())
            self.assertIn("human review required", (out / "RUN_REPORT.md").read_text())
            self.assertEqual(len((out / "usage.jsonl").read_text().splitlines()), 15)
            self.assertNotIn("test-not-real", (out / "usage.jsonl").read_text())
            registry = json.loads((out / "literature_agent_output" / "citation_map.json").read_text())
            self.assertEqual(next(iter(registry.values()))["doi"], "10.example/verified")

    def test_existing_outputs_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            materials, template = create_materials(root)
            out = root / "out"
            out.mkdir()
            (out / "keep.txt").write_text("keep")
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}), patch("paper_writing_cli.shutil.which", return_value="tool"), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    paper_writing_cli.main(["--raw_materials_dir", str(materials), "--latex_template_dir", str(template), "--output_dir", str(out)])
            self.assertEqual((out / "keep.txt").read_text(), "keep")

    def test_disabled_plotting_fails_before_credentials_or_network(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            paper_writing_cli.main(["--raw_materials_dir", "unused", "--latex_template_dir", "unused", "--use_plotting", "true"])

    def test_pipeline_failure_returns_nonzero_and_writes_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            materials, template = create_materials(root)
            out = root / "out"
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}), patch("paper_writing_cli.shutil.which", return_value="tool"), patch("methods.paper_writer.write_single_paper", return_value=False), contextlib.redirect_stdout(io.StringIO()):
                code = paper_writing_cli.main(["--raw_materials_dir", str(materials), "--latex_template_dir", str(template), "--output_dir", str(out)])
            self.assertEqual(code, 1)
            self.assertIn("failed", (out / "RUN_REPORT.md").read_text())

    def test_missing_tex_tool_fails_before_paid_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            materials, template = create_materials(root)
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}), patch("paper_writing_cli.shutil.which", return_value=None), contextlib.redirect_stderr(io.StringIO()), patch.object(backend, "get_anthropic_client") as get_client:
                with self.assertRaises(SystemExit):
                    paper_writing_cli.main(["--raw_materials_dir", str(materials), "--latex_template_dir", str(template)])
                get_client.assert_not_called()

    def test_claim_limits_and_input_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            materials, _ = create_materials(root)
            self.assertIn("CLAIM_BOUNDARY_SENTINEL", load_experiment_context(materials / "experimental_log.md"))
            manifest = write_materials_manifest(materials, root / "manifest.json")
            self.assertEqual(manifest["claims.md"]["sha256"], hashlib.sha256((materials / "claims.md").read_bytes()).hexdigest())

    def test_all_public_core_modules_import_without_google_or_openai(self):
        for name in ["methods.paper_writer", "methods.paper_writer_with_plotting", "autoraters.agent_review", "autoraters.citation_f1", "autoraters.lit_review_quality", "autoraters.sxs_lit_review_quality", "autoraters.sxs_paper_quality", "utils.content_parsing_utils"]:
            importlib.import_module(name)
        import sys
        self.assertNotIn("google.genai", sys.modules)
        self.assertNotIn("openai", sys.modules)


if __name__ == "__main__":
    unittest.main()
