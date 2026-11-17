# Claude migration

Base: upstream `d9bae997e793a015ed38bb1605be9eb58c00284f`.

This fork changes the writing pipeline, not any frozen Recap experimental code or results.

## Model boundary

All supported writers, reviewers and PDF/image readers use `utils/llm_backend_utils.py`, backed by Anthropic Messages streaming in `utils/anthropic_utils.py`. Non-Claude model IDs fail before network access. The client is lazy, honors `ANTHROPIC_BASE_URL` and standard proxy environment variables, and never prints credentials.

Provider-independent JSON, LaTeX and mixed worklog/LaTeX parsing lives in `utils/response_parsing.py`. Existing agents retain the `raw_response` / `parsed_response` contract. Invalid or truncated output is a failure; no silent repair or extra generation is performed by the adapter. Existing higher-level optional evaluators may retain their own retry loops.

Legacy per-agent temperature defaults are omitted at the API boundary because Claude model families differ in permitted sampling parameters. Only the explicit `ANTHROPIC_TEMPERATURE` override is forwarded. Unsupported generation configuration raises rather than being silently discarded. No thinking mode or prompt caching is enabled by this adapter.

Model-generated code execution and image generation are removed. The old plotting entry point raises an actionable error. PDF pages are rendered locally using PyMuPDF/Pillow for Claude layout inspection.

## Literature boundary

The original Gemini + Google Search discovery is replaced by Claude query generation, real Semantic Scholar/Crossref/arXiv retrieval, and Claude selection by candidate index. New papers cannot enter through a model-generated title. Sources and selection decisions are saved; missing or failed sources do not become fabricated citations. Exact publication cutoffs are enforced locally, unknown same-year dates fail closed, and the full retrieved abstract is retained.

These changes alter retrieval coverage relative to upstream. This fork does not claim to reproduce upstream benchmark quality. Abstract and metadata retrieval do not verify every claim made in a paper; original full texts still require review.

## Evidence boundary

`claims.md`, when present beside the experimental log, is supplied to outline, literature synthesis, section writing, content revision and scientific review. The run hashes original materials and keeps an explicit human-review-required status. These are traceability measures, not deterministic truth guarantees. Existing numerical and conclusion checks remain the author's responsibility.

The CLI preflights credentials and TeX executables, refuses nonempty output directories, logs progress to `run.log`, and writes `RUN_REPORT.md` even after an execution failure. It no longer retries the entire paid pipeline automatically. Usage lives in each output directory and is separate from research-experiment ledgers. Interrupted streaming requests may need reconciliation with the provider bill. No hard budget cap is claimed.

## Validation boundary

Tests exercise the real Anthropic SDK against an in-memory HTTP transport; no live model requests are used. The end-to-end orchestration test mocks scholarly retrieval and TeX compilation while retaining agent control flow, PDF processing, response parsing and usage logging. A browser session and a live API/real TeX production run are separate checks, not implied by these tests.
