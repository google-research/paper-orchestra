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

import re
from datetime import date


def parse_research_cutoff(value: str) -> date:
    """Resolve a year, month, or date to an exclusive publication boundary."""
    missing_parts = {4: "-01-01", 7: "-01", 10: ""}
    if not re.fullmatch(r"[0-9]{4}(?:-[0-9]{2}){0,2}", value):
        raise ValueError("expected a valid YYYY, YYYY-MM, or YYYY-MM-DD date")
    try:
        return date.fromisoformat(value + missing_parts[len(value)])
    except ValueError:
        raise ValueError("expected a valid YYYY, YYYY-MM, or YYYY-MM-DD date") from None
