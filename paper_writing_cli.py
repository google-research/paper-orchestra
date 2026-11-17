# Copyright 2026 Google LLC
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy at https://www.apache.org/licenses/LICENSE-2.0
"""Claude-only manuscript pipeline; logs and review status are saved to files."""

import argparse
import contextlib
import datetime
import json
import os
from pathlib import Path
import shutil
import sys
import traceback

from utils.llm_backend_utils import DEFAULT_MODEL, validate_model
from utils.materials import write_materials_manifest
from utils.scholar_utils import cutoff_boundary


class Tee:
    def __init__(self, file, console):
        self.file, self.console = file, console

    def write(self, text):
        self.file.write(text)
        self.console.write(text)
        self.flush()

    def flush(self):
        self.file.flush()
        self.console.flush()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Write a LaTeX draft using Claude and verified scholarly retrieval")
    parser.add_argument("--raw_materials_dir", required=True)
    parser.add_argument("--latex_template_dir", required=True)
    parser.add_argument("--output_dir")
    parser.add_argument("--idea_filename", default="idea_sparse.md")
    parser.add_argument("--experimental_log_filename", default="experimental_log.md")
    parser.add_argument("--writer_model_name", default=DEFAULT_MODEL)
    parser.add_argument("--reflection_model_name", default=DEFAULT_MODEL)
    parser.add_argument("--research_cutoff", help="Exclusive publication cutoff: YYYY-MM or YYYY-MM-DD")
    parser.add_argument("--use_plotting", type=lambda x: str(x).lower() in {"true", "1", "yes"}, default=False)
    # Preserve old command-line compatibility but reject automatic generation.
    parser.add_argument("--plotting_model_name", default=DEFAULT_MODEL, help=argparse.SUPPRESS)
    parser.add_argument("--image_model_name", default="disabled", help=argparse.SUPPRESS)
    parser.add_argument("--plotting_max_critic_rounds", type=int, default=3, help=argparse.SUPPRESS)
    parser.add_argument("--stream_logs", action="store_true", help="Also stream progress for the optional frontend")
    args = parser.parse_args(argv)
    if args.use_plotting:
        parser.error("Automatic plotting is disabled in this Claude fork; provide figures and use --use_plotting false")
    args.research_cutoff = args.research_cutoff or datetime.datetime.now().strftime("%Y-%m")
    try:
        validate_model(args.writer_model_name)
        validate_model(args.reflection_model_name)
        cutoff_boundary(args.research_cutoff)
    except ValueError as exc:
        parser.error(str(exc))
    materials = Path(args.raw_materials_dir).resolve()
    template = Path(args.latex_template_dir).resolve()
    for path in (materials / args.idea_filename, materials / args.experimental_log_filename,
                 template / "template.tex", template / "guidelines.md"):
        if not path.is_file():
            parser.error(f"Required material is missing: {path}")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        parser.error("Set ANTHROPIC_API_KEY in your environment or private .env")
    for executable in ("pdflatex", "bibtex"):
        if not shutil.which(executable):
            parser.error(f"Install {executable} before starting paid model calls")
    base = Path(args.output_dir or datetime.datetime.now().strftime("paper_output_%Y%m%d_%H%M%S")).resolve()
    if base == materials or materials in base.parents:
        parser.error("The output directory must be outside the input materials directory")
    if base.exists() and (not base.is_dir() or any(base.iterdir())):
        parser.error("Use a new or empty output directory; existing drafts will not be overwritten")
    base.mkdir(parents=True, exist_ok=True)
    shutil.copytree(materials, base / "raw_materials", dirs_exist_ok=True)
    write_materials_manifest(base / "raw_materials", base / "materials_manifest.json")
    # Always use this run's separate usage ledger, never an experiment ledger.
    (base / "usage.jsonl").touch()
    old_usage_log = os.environ.get("PAPER_ORCHESTRA_USAGE_LOG")
    os.environ["PAPER_ORCHESTRA_USAGE_LOG"] = str(base / "usage.jsonl")
    config = vars(args).copy()
    config["review_status"] = "human_review_required"
    (base / "run_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    success = False
    error_type = None
    try:
        with (base / "run.log").open("w", encoding="utf-8") as log:
            stdout = Tee(log, sys.stdout) if args.stream_logs else log
            stderr = Tee(log, sys.stderr) if args.stream_logs else log
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                try:
                    from methods.paper_writer import write_single_paper
                    success = bool(write_single_paper(
                        base_dir=str(base), latex_template_dir=str(template),
                        idea_filename=args.idea_filename,
                        experimental_log_filename=args.experimental_log_filename,
                        writer_model_name=args.writer_model_name,
                        reflection_model_name=args.reflection_model_name,
                        research_cutoff=args.research_cutoff,
                    )) and (base / "final_paper.pdf").is_file()
                except Exception as exc:
                    error_type = type(exc).__name__
                    traceback.print_exc()
    finally:
        if old_usage_log is None:
            os.environ.pop("PAPER_ORCHESTRA_USAGE_LOG", None)
        else:
            os.environ["PAPER_ORCHESTRA_USAGE_LOG"] = old_usage_log
    source = base / "content_refinement_workdir" / "final_refined_paper.tex"
    if success and source.is_file():
        shutil.copy(source, base / "final_paper.tex")
    report = (
        "# Claude manuscript run\n\n"
        + f"- Pipeline status: {'completed' if success else 'failed'}\n"
        + "- Scientific review status: **human review required**\n"
        + f"- Writer: `{args.writer_model_name}`\n"
        + f"- Reviewer: `{args.reflection_model_name}`\n"
        + f"- Literature cutoff (exclusive): `{args.research_cutoff}`\n"
        + "- [Input hashes](materials_manifest.json) · [Execution log](run.log) · [API usage](usage.jsonl)\n"
        + ("- [PDF draft](final_paper.pdf) · [LaTeX source](final_paper.tex)\n" if success else "")
        + (f"- Error type: `{error_type}`\n" if error_type else "")
        + "\nBefore publication, reconcile every reported number with original result files, "
          "check claim limits in `raw_materials/claims.md`, and verify substantive citations "
          "against the original papers. Model review scores do not certify scientific correctness.\n"
    )
    (base / "RUN_REPORT.md").write_text(report, encoding="utf-8")
    print(f"{'Completed' if success else 'Failed'}; report: {base / 'RUN_REPORT.md'}")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
