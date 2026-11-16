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
import datetime

from dotenv import load_dotenv  # type: ignore

cur_dir = os.path.dirname(os.path.realpath(__file__))
load_dotenv(os.path.join(cur_dir, "../.env"))
S2_API_KEY = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
print(f"S2 API key configured: {bool(S2_API_KEY)}")


# --- SEMANTIC SCHOLAR UTILS ---

S2_MAX_RETRIES = 4
S2_RETRY_STATUS = {429, 500, 502, 503, 504}


def is_before_cutoff(publication_date, year, cutoff_str: str) -> bool:
    """
    Returns True if a paper is known (or, with missing data, presumed) to be
    published strictly before the first day of the cutoff month.

    cutoff_str is "YYYY" or "YYYY-MM" (a day part is ignored).
    A paper with only a year equal to the cutoff year is rejected, because it
    may have been published after the cutoff.
    """
    if not cutoff_str:
        return True
    try:
        c_parts = [int(x) for x in str(cutoff_str).split("-")]
    except ValueError:
        return True
    c_year = c_parts[0]
    c_month = c_parts[1] if len(c_parts) > 1 else 1

    p_year, p_month = None, None
    if publication_date:
        try:
            p_parts = [int(x) for x in str(publication_date).split("-")]
            p_year = p_parts[0]
            p_month = p_parts[1] if len(p_parts) > 1 else None
        except ValueError:
            pass
    if p_year is None and year:
        try:
            p_year = int(year)
        except (TypeError, ValueError):
            p_year = None

    if p_year is None:
        return True
    if p_year != c_year:
        return p_year < c_year
    if p_month is None:
        # Same year, unknown month: it may post-date the cutoff, so reject it
        # to avoid leaking future literature.
        return False
    return p_month < c_month


def _s2_get_with_retry(url: str, headers: Dict, params: Dict, timeout: int = 10):
    """GET with exponential backoff on rate limiting / transient server errors."""
    rsp = None
    for attempt in range(S2_MAX_RETRIES):
        rsp = requests.get(url, headers=headers, params=params, timeout=timeout)
        if rsp.status_code not in S2_RETRY_STATUS:
            return rsp
        retry_after = rsp.headers.get("Retry-After")
        try:
            delay = float(retry_after) if retry_after else 2 ** (attempt + 1)
        except ValueError:
            delay = 2 ** (attempt + 1)
        time.sleep(min(delay, 30))
    return rsp


def s2_title_search(
    title_query: str, year_hint: int = None, cutoff_date: str = None
) -> Optional[Dict]:
    headers = {"X-API-KEY": S2_API_KEY} if S2_API_KEY else {}

    def is_date_valid(p_date, p_year, cutoff_str):
        return is_before_cutoff(p_date, p_year, cutoff_str)

    try:
        rsp = _s2_get_with_retry(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            headers=headers,
            params={
                "query": title_query,
                "limit": 3,
                "fields": "title,authors,venue,year,abstract,citationCount,journal,publicationDate",
            },
        )
        if rsp.status_code != 200:
            print(
                f"      ⚠️ S2 search for '{title_query}' failed with HTTP {rsp.status_code}"
            )
            return None
        results = rsp.json().get("data", [])
        if not results:
            return None

        best_match = None
        highest_ratio = 0

        for r in results:
            if not r.get("title"):
                continue
            if not is_date_valid(r.get("publicationDate"), r.get("year"), cutoff_date):
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
