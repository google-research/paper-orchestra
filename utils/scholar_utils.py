"""Structured scholarly retrieval; models never invent the candidate bibliography."""

import datetime as dt
import difflib
import hashlib
import json
import os
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

_FIELDS = "paperId,title,authors,venue,year,abstract,citationCount,journal,publicationDate,url,externalIds"
_request_lock = threading.Lock()
_next_request = {}


class LiteratureSearchError(RuntimeError):
    pass


def cutoff_boundary(cutoff):
    if not cutoff:
        return None
    # YYYY-MM means strictly before the first day of that month, as promised
    # by the research-cutoff prompt. Unknown publication dates fail closed.
    return dt.date.fromisoformat(cutoff + "-01" if len(cutoff) == 7 else cutoff)


def is_paper_allowed(paper, cutoff):
    boundary = cutoff_boundary(cutoff)
    if boundary is None:
        return True
    publication = paper.get("publicationDate")
    if publication:
        try:
            return dt.date.fromisoformat(str(publication)[:10]) < boundary
        except ValueError:
            pass
    year = paper.get("year")
    return bool(year and int(year) < boundary.year)


def _get(url, params, provider, headers=None):
    # Bound API pressure across all literature worker threads.
    with _request_lock:
        delay = max(0, _next_request.get(provider, 0) - time.monotonic())
        if delay:
            time.sleep(delay)
        _next_request[provider] = time.monotonic() + (3.1 if provider == "arxiv" else 1.1)
    for attempt in range(3):
        response = requests.get(url, params=params, headers=headers, timeout=(10, 30))
        if response.status_code not in {429, 500, 502, 503, 504} or attempt == 2:
            response.raise_for_status()
            return response
        time.sleep(2 ** attempt)
    raise LiteratureSearchError("Unreachable retrieval state")


def _semantic_scholar(query, limit):
    key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    headers = {"X-API-KEY": key} if key else {}
    data = _get(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        {"query": query, "limit": limit, "fields": _FIELDS}, "semantic_scholar", headers,
    ).json()
    papers = data.get("data", [])
    for paper in papers:
        paper["source"] = "semantic_scholar"
    return papers


def _crossref(query, limit):
    items = _get("https://api.crossref.org/works", {
        "query.bibliographic": query, "rows": limit,
    }, "crossref").json().get("message", {}).get("items", [])
    papers = []
    for item in items:
        title = (item.get("title") or [""])[0]
        date_parts = []
        for key in ("published", "published-online", "published-print", "issued"):
            date_parts = (item.get(key) or {}).get("date-parts", [[]])[0]
            if date_parts:
                break
        # Never invent January 1 when metadata only supplies a year.
        publication = "-".join(f"{value:02d}" for value in date_parts) if len(date_parts) == 3 else None
        abstract = item.get("abstract") or ""
        if abstract:
            try:
                abstract = " ".join(ET.fromstring(abstract).itertext())
            except ET.ParseError:
                abstract = ""
        papers.append({
            "title": title, "year": date_parts[0] if date_parts else None,
            "publicationDate": publication,
            "authors": [{"name": " ".join(filter(None, [a.get("given"), a.get("family")]))} for a in item.get("author", [])],
            "abstract": abstract, "venue": (item.get("container-title") or [""])[0],
            "url": item.get("URL"), "externalIds": {"DOI": item.get("DOI")},
            "citationCount": item.get("is-referenced-by-count", 0), "source": "crossref",
        })
    return papers


def _arxiv(query, limit):
    # Quote the complete query; never pass model output as API query operators.
    safe_query = query.replace('"', ' ')
    response = _get("https://export.arxiv.org/api/query", {
        "search_query": 'all:"' + safe_query + '"', "max_results": limit,
    }, "arxiv")
    root = ET.fromstring(response.content)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    papers = []
    for entry in root.findall("a:entry", ns):
        publication = entry.findtext("a:published", "", ns)[:10]
        url = entry.findtext("a:id", "", ns)
        papers.append({
            "title": " ".join(entry.findtext("a:title", "", ns).split()),
            "year": int(publication[:4]) if publication else None,
            "publicationDate": publication or None,
            "authors": [{"name": a.findtext("a:name", "", ns)} for a in entry.findall("a:author", ns)],
            "abstract": " ".join(entry.findtext("a:summary", "", ns).split()),
            "venue": "arXiv", "url": url, "citationCount": 0,
            "externalIds": {"ArXiv": url.rsplit("/", 1)[-1]}, "source": "arxiv",
        })
    return papers


def search_papers(query, cutoff_date=None, limit=12, audit_dir=None):
    if not isinstance(query, str) or not query.strip() or len(query) > 500:
        raise ValueError("A scholarly query must be a nonempty string of at most 500 characters")
    cutoff_boundary(cutoff_date)  # Validate before making any request.
    papers, errors, seen = [], [], set()
    successful_providers = 0
    for provider in (_semantic_scholar, _crossref, _arxiv):
        try:
            retrieved = provider(query, limit)
            successful_providers += 1
        except (requests.RequestException, ValueError, ET.ParseError) as exc:
            errors.append({
                "provider": provider.__name__, "error_type": type(exc).__name__,
                "status_code": getattr(getattr(exc, "response", None), "status_code", None),
            })
            continue
        for paper in retrieved:
            title = paper.get("title") or ""
            norm = "".join(c for c in title.lower() if c.isalnum())
            if not norm or norm in seen or not is_paper_allowed(paper, cutoff_date):
                continue
            seen.add(norm)
            paper["retrieved_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
            papers.append(paper)
    record = {"query": query, "cutoff": cutoff_date, "papers": papers, "errors": errors}
    if audit_dir:
        path = Path(audit_dir)
        path.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(json.dumps([query, cutoff_date]).encode()).hexdigest()[:20]
        # Each query is independent; replace the complete audit atomically.
        temporary = path / f".{key}.{threading.get_ident()}.tmp"
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path / f"{key}.json")
    if not successful_providers:
        raise LiteratureSearchError("All scholarly providers failed; see retrieval audit")
    return papers


def s2_title_search(title_query, year_hint=None, cutoff_date=None):
    """Compatibility title lookup, now using real scholarly search providers."""
    candidates = search_papers(title_query, cutoff_date, limit=3)
    if year_hint:
        candidates = [p for p in candidates if p.get("year") == year_hint]
    ranked = sorted(candidates, key=lambda p: difflib.SequenceMatcher(
        None, title_query.casefold(), p["title"].casefold()).ratio(), reverse=True)
    if ranked and difflib.SequenceMatcher(None, title_query.casefold(), ranked[0]["title"].casefold()).ratio() >= 0.8:
        return ranked[0]
    return None
