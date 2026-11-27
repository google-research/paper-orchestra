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

# Writes an APA 7 criminology / social-science manuscript.
# Point RAW_MATERIALS_DIR at your own folder containing idea_sparse.md and experimental_log.md.

MY_ENV=paper_orchestra
RAW_MATERIALS_DIR="examples/criminology_example/raw_materials"
OUTPUT_DIR="./paper_output_criminology"

PYTHONUNBUFFERED=1 nohup conda run --no-capture-output -n $MY_ENV python paper_writing_cli.py \
--raw_materials_dir ${RAW_MATERIALS_DIR} \
--latex_template_dir templates/apa7_criminology \
--domain social_science \
--output_dir ${OUTPUT_DIR} \
--use_plotting true \
> ./paper_writing_criminology.log 2>&1 &
