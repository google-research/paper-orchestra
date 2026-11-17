# Local addition (not upstream): lets `paper_writing_cli.py --resume` skip stages
# whose outputs already exist in the output folder, so a run stopped by a usage
# limit (or Ctrl+C) continues where it stopped instead of starting over.
import os

LIT_OUTPUTS = ("outline_v1.json", "updated_template.tex", "references.bib", "citation_map.json")


def stage_done(resume: bool, name: str, *paths: str) -> bool:
    """True (and say so) when resuming and every output file of a stage exists."""
    if resume and paths and all(os.path.exists(p) and os.path.getsize(p) > 0 for p in paths):
        print(f"⏭️  Resume: skipping {name} (output already exists)", flush=True)
        return True
    return False
