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

import warnings
import os
import requests
import time
from typing import List, Dict, Union, Optional
from thefuzz import fuzz  # type: ignore
from datetime import date

from utils.research_cutoff import parse_research_cutoff

from dotenv import load_dotenv  # type: ignore

cur_dir = os.path.dirname(os.path.realpath(__file__))
load_dotenv(os.path.join(cur_dir, "../.env"))
S2_API_KEY = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
print(f"Using S2 API Key: {S2_API_KEY}")


# --- SEMANTIC SCHOLAR UTILS ---


def s2_title_search(
    title_query: str, year_hint: int = None, cutoff_date: str = None
) -> Optional[Dict]:
    headers = {"X-API-KEY": S2_API_KEY} if S2_API_KEY else {}

    cutoff = parse_research_cutoff(cutoff_date) if cutoff_date else None

    try:
        rsp = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            headers=headers,
            params={
                "query": title_query,
                "limit": 3,
                "fields": "title,authors,venue,year,abstract,citationCount,journal,publicationDate",
            },
            timeout=5,
        )
        if rsp.status_code != 200:
            return None
        results = rsp.json().get("data", [])
        if not results:
            return None

        best_match = None
        highest_ratio = 0

        for r in results:
            if not r.get("title"):
                continue
            if cutoff and not _is_before_cutoff(r, cutoff):
                continue

            ratio = fuzz.ratio(title_query.lower(), r["title"].lower())
            if year_hint and r.get("year") == year_hint:
                ratio += 10

            if ratio > highest_ratio:
                highest_ratio = ratio
                best_match = r

        if highest_ratio > 70:
            return best_match
        return None
    except Exception as e:
        print(f"      ⚠️ S2 Error for '{title_query}': {e}")
        return None


def _is_before_cutoff(paper: Dict, cutoff: date) -> bool:
    if paper.get("publicationDate"):
        try:
            return date.fromisoformat(paper["publicationDate"]) < cutoff
        except (ValueError, TypeError):
            pass

    year = paper.get("year")
    if year:
        # With year-only metadata, keep papers that could predate the cutoff.
        return (int(year), 1, 1) < (cutoff.year, cutoff.month, cutoff.day)
    return True
