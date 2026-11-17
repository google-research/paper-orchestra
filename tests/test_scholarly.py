import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import requests
from utils import scholar_utils as scholar
from methods.agents.literature_review_agent import HybridLiteratureAgent


def sample(title="Verified Paper", year=2024, **extra):
    return {"title": title, "year": year, "publicationDate": f"{year}-04-01", "abstract": "Verified abstract", "authors": [{"name": "Ada Author"}], "venue": "Test Conference", "url": "https://example.org/paper", "source": "test", **extra}


def none(*args, **kwargs):
    return []


class ScholarlyTests(unittest.TestCase):
    def test_cutoff_is_exclusive(self):
        self.assertTrue(scholar.is_paper_allowed(sample(publicationDate="2025-10-31"), "2025-11"))
        self.assertFalse(scholar.is_paper_allowed(sample(publicationDate="2025-11-01"), "2025-11"))

    def test_unknown_date_fails_closed(self):
        self.assertFalse(scholar.is_paper_allowed({"title": "Unknown"}, "2025-11"))
        self.assertFalse(scholar.is_paper_allowed({"year": 2025}, "2025-11"))
        self.assertTrue(scholar.is_paper_allowed({"year": 2024}, "2025-11"))

    def test_invalid_cutoff_fails_before_retrieval(self):
        with patch.object(scholar, "_get") as get:
            with self.assertRaises(ValueError):
                scholar.search_papers("query", "invalid")
            get.assert_not_called()

    def test_deduplication_and_audit(self):
        def first(*args):
            return [sample(), sample("Too New", year=2026)]
        def second(*args):
            return [sample()]
        with tempfile.TemporaryDirectory() as tmp, patch.object(scholar, "_semantic_scholar", first), patch.object(scholar, "_crossref", second), patch.object(scholar, "_arxiv", none):
            results = scholar.search_papers("test query", "2025-01", audit_dir=tmp)
            self.assertEqual(len(results), 1)
            self.assertIn("retrieved_at", results[0])
            records = list(Path(tmp).glob("*.json"))
            self.assertEqual(len(records), 1)
            self.assertEqual(json.loads(records[0].read_text())["query"], "test query")

    def test_provider_failure_is_audited(self):
        def unavailable(*args):
            raise requests.ConnectionError("simulated")
        with tempfile.TemporaryDirectory() as tmp, patch.object(scholar, "_semantic_scholar", unavailable), patch.object(scholar, "_crossref", none), patch.object(scholar, "_arxiv", none):
            self.assertEqual(scholar.search_papers("test", "2025-01", audit_dir=tmp), [])
            record = json.loads(next(Path(tmp).glob("*.json")).read_text())
            self.assertEqual(record["errors"][0]["error_type"], "ConnectionError")

    def test_total_provider_failure_is_not_silenced(self):
        def unavailable(*args):
            raise requests.ConnectionError("simulated")
        with patch.object(scholar, "_semantic_scholar", unavailable), patch.object(scholar, "_crossref", unavailable), patch.object(scholar, "_arxiv", unavailable):
            with self.assertRaises(scholar.LiteratureSearchError):
                scholar.search_papers("test", "2025-01")

    def test_crossref_year_does_not_invent_a_day(self):
        class Response:
            def json(self):
                return {"message": {"items": [{"title": ["Paper"], "published": {"date-parts": [[2024]]}, "DOI": "10.example/test"}]}}
        with patch.object(scholar, "_get", return_value=Response()):
            paper = scholar._crossref("test", 3)[0]
        self.assertEqual(paper["year"], 2024)
        self.assertIsNone(paper["publicationDate"])
        self.assertEqual(paper["externalIds"]["DOI"], "10.example/test")

    def test_arxiv_atom_metadata(self):
        class Response:
            content = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>https://arxiv.org/abs/2401.00001</id><title>Real Paper</title><published>2024-01-02T00:00:00Z</published><summary>An abstract</summary><author><name>Ada Author</name></author></entry></feed>'
        with patch.object(scholar, "_get", return_value=Response()):
            paper = scholar._arxiv("test", 3)[0]
        self.assertEqual(paper["title"], "Real Paper")
        self.assertEqual(paper["year"], 2024)
        self.assertEqual(paper["authors"], [{"name": "Ada Author"}])

    def test_rate_limit_retry_is_bounded(self):
        calls = []
        class Response:
            status_code = 429
            def raise_for_status(self):
                raise requests.HTTPError("simulated rate limit")
        def get(*args, **kwargs):
            calls.append(1)
            return Response()
        with patch.object(scholar.requests, "get", get), patch.object(scholar.time, "sleep"):
            with self.assertRaises(requests.HTTPError):
                scholar._get("https://example.invalid", {}, "test")
        self.assertEqual(len(calls), 3)

    def make_agent(self, root):
        for filename in ("idea.md", "experimental_log.md", "template.tex", "guidelines.md"):
            (root / filename).write_text("test")
        return HybridLiteratureAgent(str(root / "idea.md"), str(root / "experimental_log.md"), str(root / "template.tex"), str(root / "guidelines.md"), str(root / "output"))

    def test_model_cannot_add_an_unretrieved_paper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agent = self.make_agent(root)
            responses = [{"parsed_response": {"queries": ["test"]}}, {"parsed_response": {"selected": [{"id": 999, "reason": "invented"}]}}]
            with patch("methods.agents.literature_review_agent.call_llm_with_contents", side_effect=responses), patch("methods.agents.literature_review_agent.search_papers", return_value=[sample()]):
                with self.assertRaisesRegex(ValueError, "outside"):
                    agent._discover_candidates({"section": "Related Work", "focus": "test"}, {}, "2025-01")

    def test_full_abstract_and_provenance_survive_registration(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = self.make_agent(Path(tmp))
            registry = {}
            paper = sample(abstract="a" * 2000, externalIds={"DOI": "10.example/paper"})
            agent._enrich_and_register_paper({"title": paper["title"], "year": paper["year"], "source_data": paper}, {"section": "Introduction"}, registry, "2025-01")
            data = next(iter(registry.values()))
            self.assertEqual(len(data.abstract), 2000)
            self.assertEqual(data.evidence_level, "abstract_only")
            self.assertIn("10.example/paper", agent._generate_bibtex([data]))
            self.assertEqual(agent._generate_citation_map([data])[data.citation_key]["url"], paper["url"])


if __name__ == "__main__":
    unittest.main()
