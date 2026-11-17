"""Keep experimental evidence and claim limits available at every writing stage."""

import hashlib
import json
from pathlib import Path


def load_experiment_context(path):
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    claims = path.parent / "claims.md"
    if claims.is_file():
        text += (
            "\n\n--- AUTHOR-SUPPLIED CLAIM LIMITS (claims.md) ---\n"
            + claims.read_text(encoding="utf-8")
            + "\nThese limits constrain all summaries and revisions. Reviewer scores "
            "do not authorize stronger claims or changes to experimental numbers.\n"
        )
    return text


def write_materials_manifest(materials_dir, output_path):
    root = Path(materials_dir)
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            files[path.relative_to(root).as_posix()] = {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "bytes": path.stat().st_size,
            }
    Path(output_path).write_text(json.dumps(files, indent=2), encoding="utf-8")
    return files
