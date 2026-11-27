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
import random

from dotenv import load_dotenv  # type: ignore

cur_dir = os.path.dirname(os.path.realpath(__file__))
load_dotenv(os.path.join(cur_dir, "../.env"))
S2_API_KEY = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
print(f"Using S2 API Key: {S2_API_KEY}")


# --- SEMANTIC SCHOLAR UTILS ---


def _s2_only_title_search(
    title_query: str, year_hint: int = None, cutoff_date: str = None
) -> Optional[Dict]:
    headers = {"X-API-KEY": S2_API_KEY} if S2_API_KEY else {}

    def is_date_valid(p_date, p_year, cutoff_str):
        if not cutoff_str:
            return True
        try:
            c_year, c_month = map(int, cutoff_str.split("-"))
            cutoff_dt = datetime.datetime(c_year, c_month, 1)
            if p_date:
                try:
                    p_dt = datetime.datetime.strptime(p_date, "%Y-%m-%d")
                    return p_dt < cutoff_dt
                except ValueError:
                    pass
            if p_year:
                if p_year < c_year:
                    return True
                if p_year == c_year and c_month > 1:
                    return True
                return False
            return True
        except Exception:
            return True

    try:
        # Semantic Scholar often answers 429 (too many requests), especially without
        # an API key. Retry with exponential backoff instead of dropping the paper.
        rsp = None
        for attempt in range(6 if S2_API_KEY else 2):
            try:
                rsp = requests.get(
                    "https://api.semanticscholar.org/graph/v1/paper/search",
                    headers=headers,
                    params={
                        "query": title_query,
                        "limit": 3,
                        "fields": "title,authors,venue,year,abstract,citationCount,journal,publicationDate",
                    },
                    timeout=10,
                )
            except requests.exceptions.RequestException:
                rsp = None
            if rsp is not None and rsp.status_code not in (429, 500, 502, 503, 504):
                break
            time.sleep(min(2 ** attempt, 30) + random.uniform(0, 1))
        if rsp is None or rsp.status_code != 200:
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


# --- OPENALEX FALLBACK ---
# OpenAlex (https://openalex.org) is a free scholarly database that needs no API key.
# It is used when Semantic Scholar has no key (its shared pool is often rate-limited)
# or does not find the paper. Results are converted to the Semantic Scholar format
# that the rest of the pipeline expects.

OPENALEX_URL = "https://api.openalex.org/works"


def _openalex_abstract(inverted_index: Optional[Dict]) -> str:
    if not inverted_index:
        return ""
    positions = []
    for word, idxs in inverted_index.items():
        for i in idxs:
            positions.append((i, word))
    return " ".join(w for _, w in sorted(positions))


def _openalex_to_s2(work: Dict) -> Dict:
    source = ((work.get("primary_location") or {}).get("source") or {})
    biblio = work.get("biblio") or {}
    pages = None
    if biblio.get("first_page"):
        pages = biblio["first_page"]
        if biblio.get("last_page"):
            pages += "-" + biblio["last_page"]
    is_journal = source.get("type") == "journal"
    return {
        "title": work.get("title") or work.get("display_name") or "",
        "authors": [
            {"name": (a.get("author") or {}).get("display_name", "")}
            for a in work.get("authorships", [])
            if (a.get("author") or {}).get("display_name")
        ],
        "venue": source.get("display_name") or "",
        "year": work.get("publication_year"),
        "abstract": _openalex_abstract(work.get("abstract_inverted_index")),
        "citationCount": work.get("cited_by_count") or 0,
        "journal": (
            {
                "name": source.get("display_name"),
                "volume": biblio.get("volume"),
                "pages": pages,
            }
            if is_journal
            else None
        ),
        "publicationDate": work.get("publication_date"),
    }


def _openalex_title_search(
    title_query: str, year_hint: int = None, cutoff_date: str = None
) -> Optional[Dict]:
    params = {
        "search": title_query,
        "per-page": 5,
        "select": "title,display_name,authorships,primary_location,publication_year,"
        "publication_date,abstract_inverted_index,cited_by_count,biblio",
    }
    if cutoff_date:
        try:
            c_year, c_month = map(int, cutoff_date.split("-"))
            params["filter"] = f"to_publication_date:{c_year:04d}-{c_month:02d}-01"
        except ValueError:
            pass
    rsp = None
    for attempt in range(4):
        try:
            rsp = requests.get(OPENALEX_URL, params=params, timeout=15)
        except requests.exceptions.RequestException:
            rsp = None
        if rsp is not None and rsp.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(min(2 ** attempt, 15) + random.uniform(0, 1))
    if rsp is None or rsp.status_code != 200:
        return None

    best_match, highest_ratio = None, 0
    for work in rsp.json().get("results", []):
        title = work.get("title") or work.get("display_name")
        if not title:
            continue
        ratio = fuzz.ratio(title_query.lower(), title.lower())
        if year_hint and work.get("publication_year") == year_hint:
            ratio += 10
        if ratio > highest_ratio:
            highest_ratio, best_match = ratio, work
    if highest_ratio > 70:
        return _openalex_to_s2(best_match)
    return None


def s2_title_search(
    title_query: str, year_hint: int = None, cutoff_date: str = None
) -> Optional[Dict]:
    """Finds a paper by title. Returns Semantic Scholar-style metadata or None.

    With a Semantic Scholar API key, Semantic Scholar is tried first and OpenAlex
    is the fallback. Without a key, OpenAlex is tried first, because the keyless
    Semantic Scholar pool is frequently rate-limited.
    """
    searches = [_s2_only_title_search, _openalex_title_search]
    if not S2_API_KEY:
        searches.reverse()
    best = None
    for search in searches:
        try:
            result = search(title_query, year_hint, cutoff_date)
        except Exception as e:
            print(f"      ⚠️ Search error for '{title_query}': {e}")
            result = None
        if result and result.get("abstract"):
            return result
        best = best or result
    return best
