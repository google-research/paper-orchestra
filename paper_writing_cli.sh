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

MY_ENV=paper_orchestra
PAPER_ID="cvpr2025_0b62029e18" # Switch this to the paper id you want to write

PYTHONUNBUFFERED=1 nohup conda run --no-capture-output -n $MY_ENV python paper_writing_cli.py \
--raw_materials_dir datasets/cvpr2025/papers/${PAPER_ID}/raw_materials \
--latex_template_dir templates/cvpr2025 \
--output_dir ./paper_output_${PAPER_ID} \
--use_plotting true \
> ./paper_writing_${PAPER_ID}.log 2>&1 &


