#!/usr/bin/env bash
set -euo pipefail
# Usage: bash paper_writing_cli.sh /path/to/materials /path/to/new_output [template]
python paper_writing_cli.py \
  --raw_materials_dir "${1:?provide the materials directory}" \
  --output_dir "${2:?provide a new output directory}" \
  --latex_template_dir "${3:-templates/iclr2025}" \
  --use_plotting false
