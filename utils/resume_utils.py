# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Lets `paper_writing_cli.py --resume` skip stages
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
