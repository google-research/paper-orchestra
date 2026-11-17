# Claude migration validation — 2026-11-17

## Result

**36 offline tests passed** in 2.465 seconds.

- Python: `3.10.13`.
- Anthropic SDK: `0.125.0`; HTTPX: `0.28.1`.
- Pydantic: `2.14.3`; PyMuPDF: `1.28.2`; Pillow: `12.3.0`.
- Paid model requests: **0**. Test SDK requests use in-memory HTTP transport and dummy credentials.
- All production Python files parsed; no production imports of Google GenAI, Gemini helpers or OpenAI helpers remain.
- `git diff --check` passed.

## Covered

Text, JPEG, PDF and mixed JSON/LaTeX responses; stream termination and request IDs; rejection of truncated/invalid responses; immutable input configuration; usage and optional cost accounting; invalid price preflight; model restrictions; real SDK request construction and authentication error propagation.

Scholarly candidate filtering, exclusive date cutoffs, unknown dates, provider retries/failure records, duplicate papers, Crossref/Atom normalization, unabridged abstracts, DOI/URL preservation and rejection of paper IDs absent from actual retrieval.

A full simulated run executed outline generation, scholarly selection, literature synthesis, section writing, ensemble review, content revision, rollback, PDF screenshot processing, formatting review, final output and Markdown reporting. It made 15 mocked SDK requests. Tests also verify claim-limit context, input hashes, nonzero failure exits and preservation of existing outputs.

## Public retrieval smoke test

A separate read-only public API lookup for `Attention Is All You Need` (exclusive cutoff `2025-01`) returned one candidate through **Crossref**. Semantic Scholar returned HTTP **429** without an API key; arXiv timed out on this network. These failures were recorded rather than represented as successful retrieval. A `PaperOrchestra` lookup returned no candidates under the same partial source availability.

This establishes partial live connectivity, not comprehensive literature coverage. Rate limits and network availability remain operational limitations.

## Not established

No live Claude generation, production manuscript, real TeX compilation, browser session, upstream benchmark reproduction or scientific truth certification was performed. The pipeline integration test uses a simulated compiler; real PDF reading and screenshot generation run locally. GitHub CI for Python 3.11 is configured separately and its result is not included in the local pass count.

## Offline test transcript

```text
test_auth_failure_is_not_retried (test_claude_backend.MockClaude) ... ok
test_empty_input_is_rejected (test_claude_backend.MockClaude) ... ok
test_input_configuration_is_unchanged (test_claude_backend.MockClaude) ... ok
test_invalid_json_is_not_retried (test_claude_backend.MockClaude) ... ok
test_invalid_prices_fail_before_a_paid_call (test_claude_backend.MockClaude) ... ok
test_jpeg_media_type_is_preserved (test_claude_backend.MockClaude) ... ok
test_pdf_document_encoding (test_claude_backend.MockClaude) ... ok
test_raw_latex_response (test_claude_backend.MockClaude) ... ok
test_raw_mode (test_claude_backend.MockClaude) ... ok
test_text_sdk_contract (test_claude_backend.MockClaude) ... ok
test_truncation_is_rejected_and_billed (test_claude_backend.MockClaude) ... ok
test_unknown_generation_option_is_rejected (test_claude_backend.MockClaude) ... ok
test_unsupported_model_is_rejected_before_request (test_claude_backend.MockClaude) ... ok
test_fenced_json (test_claude_backend.Parsers) ... ok
test_json_array (test_claude_backend.Parsers) ... ok
test_json_does_not_repair_invalid_scientific_text (test_claude_backend.Parsers) ... ok
test_missing_refinement_latex_is_rejected (test_claude_backend.Parsers) ... ok
test_mixed_refinement_output (test_claude_backend.Parsers) ... ok
test_all_public_core_modules_import_without_google_or_openai (test_pipeline.PipelineTests) ... ok
test_claim_limits_and_input_hashes (test_pipeline.PipelineTests) ... ok
test_disabled_plotting_fails_before_credentials_or_network (test_pipeline.PipelineTests) ... ok
test_existing_outputs_are_never_overwritten (test_pipeline.PipelineTests) ... ok
test_full_pipeline_uses_claude_sdk_without_external_network (test_pipeline.PipelineTests) ... ok
test_missing_tex_tool_fails_before_paid_calls (test_pipeline.PipelineTests) ... ok
test_pipeline_failure_returns_nonzero_and_writes_report (test_pipeline.PipelineTests) ... ok
test_arxiv_atom_metadata (test_scholarly.ScholarlyTests) ... ok
test_crossref_year_does_not_invent_a_day (test_scholarly.ScholarlyTests) ... ok
test_cutoff_is_exclusive (test_scholarly.ScholarlyTests) ... ok
test_deduplication_and_audit (test_scholarly.ScholarlyTests) ... ok
test_full_abstract_and_provenance_survive_registration (test_scholarly.ScholarlyTests) ... ok
test_invalid_cutoff_fails_before_retrieval (test_scholarly.ScholarlyTests) ... ok
test_model_cannot_add_an_unretrieved_paper (test_scholarly.ScholarlyTests) ... ok
test_provider_failure_is_audited (test_scholarly.ScholarlyTests) ... ok
test_rate_limit_retry_is_bounded (test_scholarly.ScholarlyTests) ... ok
test_total_provider_failure_is_not_silenced (test_scholarly.ScholarlyTests) ... ok
test_unknown_date_fails_closed (test_scholarly.ScholarlyTests) ... ok

----------------------------------------------------------------------
Ran 36 tests in 2.465s

OK
Loaded S2 API Key for this project: None
      -> 📚 Added enriched paper: Verified Paper
```
