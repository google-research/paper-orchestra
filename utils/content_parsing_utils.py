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

from .gemini_utils import call_gemini_with_text_prompt

extract_title_prompt_template = """You are an expert bibliographic parser. Extract the full research paper title from the messy citation text below.

## Rules:
1. Return ONLY the title text. No authors, years, venues, or labels.
2. HANDLING HYPHENS (Important):
    - ONLY remove a hyphen if it clearly splits a single word due to a line break (e.g., "Net- work" -> "Network").
    - PRESERVE hyphens in compound words (e.g., keep "Text-to-Image", "Zero-shot").
3. FIX MERGED WORDS (Important):
    - If spaces are missing between words (common in PDF extraction), split them.
    - Examples: Change "Imagesearch" to "Image search", "Transformerbased" to "Transformer-based" or "Transformer based".
    
Input Citation:
```
{citation_text}
```

Title:"""


def extract_paper_title_from_citation(citation_text: str):
    instruction = extract_title_prompt_template.format(citation_text=citation_text)
    response_dict = call_gemini_with_text_prompt(
        prompt=instruction,
        model_name="gemini-3-flash-preview",
        check_parsed_response_not_none=False,
    )
    return response_dict["raw_response"].strip()
