# Copilot Instructions for `llm_query_doc_analyser`

## Project Overview
- **Purpose:** Automates scholarly literature analysis, enrichment, semantic filtering, and Open Access PDF management for researchers and engineers.
- **Architecture:**
  - **CLI-first**: All workflows are driven by a Typer-based CLI (`src/llm_query_doc_analyser/cli.py`).
  - **Modular Components:**
    - **Input/Output:** `io_/load.py`, `io_/export.py`
    - **Enrichment:** `enrich/` (API clients, orchestrator)
    - **Filtering/Semantics:** `filter_rank/`, `enrich/embed.py`, `enrich/rerank.py`
    - **PDF Handling:** `pdfs/resolve.py`, `pdfs/download.py`
    - **Core Models/Store:** `core/models.py`, `core/store.py`, `core/hashing.py`
    - **Utilities:** `utils/http.py`, `utils/log.py`
  - **Data Flow:** Input (CSV/XLSX) → Enrich (APIs) → Filter (semantic) → Download PDFs → Export (CSV/XLSX/Parquet)

## Key Conventions & Patterns
- **Strict Open Access Guardrails:**
  - Only fetch PDFs from OA endpoints (no scraping, proxies, or paywalled content).
  - All enrichment fields must include provenance (source, URL, timestamp, raw JSON).
- **Async & Caching:**
  - All API calls are async (via `httpx`), with rate limiting, retries (`tenacity`), and caching (`data/cache/`).
- **Logging:**
  - Use `structlog` for structured logs. Log level is set via `LOG_LEVEL` env var.
- **Configuration:**
  - All config via environment variables. Copy `.env.example` to `.env` and edit as needed.
- **Testing:**
  - Tests in `tests/` (pytest, pytest-asyncio, respx for HTTP mocks). Coverage >= 80% expected.
- **Type Hints & Docstrings:**
  - All new code must use type hints and docstrings (PEP 8/PEP 484).

## Developer Workflows
- **Install & Setup:** Use `uv` for all environment and dependency management. Example:
  - Install dependencies: `uv sync`
- `uv run llm_query_doc_analyser --help`
- Example pipeline:
  - `uv run llm_query_doc_analyser import data/input/records.xlsx`
  - `uv run llm_query_doc_analyser enrich`
  - `uv run llm_query_doc_analyser filter --query "..."`
  - `uv run llm_query_doc_analyser pdfs`
  - `uv run llm_query_doc_analyser export outputs/results.xlsx`
- **Lint/Type Check:**
  - `uv run ruff check src`
  - `uv run mypy src`
- **Test:**
  - `uv run pytest`

## Integration Points
- **APIs:** Crossref, Unpaywall, OpenAlex, EuropePMC, PubMed, Semantic Scholar (optional), OpenAI
- **Dependencies:** See `pyproject.toml` for full list. Key: `pandas`, `httpx[http2]`, `pydantic`, `typer`, `structlog`, `tenacity`, `rapidfuzz`, `rank-bm25`, `sentence-transformers`, `faiss-cpu`, `pypdf`, `openai`, `spacy`, `nltk`.

## Examples & References
- **Input/Output:** See `data/input/`, `outputs/`, and `io_/` modules.
- **Enrichment:** See `enrich/orchestrator.py` for API orchestration logic.
- **Filtering:** See `filter_rank/`.
- **PDF Handling:** See `pdfs/` for OA PDF resolution and download logic.

## Implementation Summaries & Notes

- Purpose: When changes are implemented, the model should offer to record a concise implementation summary and explanation in a markdown file, but must not generate or output such notes automatically.
- Interaction pattern:
  - After completing any non-trivial implementation, modification, or update, prompt the user with a single question: "Would you like a markdown summary recorded for this change? (yes/no)". Do not create the summary unless the user answers "yes".
  - If the user answers "yes", ask follow-up questions to confirm:
    - Target path or filename (suggest defaults: `docs/IMPLEMENTATION_NOTES.md`, `docs/CHANGELOG.md`, or `docs/implementation/YYYY-MM-DD.md`).
    - Whether to append to the chosen file or create a new file.
    - Whether any sensitive or private information should be omitted.
- Format & required fields: When the user requests a summary, produce a markdown entry using the following minimum structure:
  - Title: short descriptive heading
  - Date: ISO 8601 timestamp
  - Author: (ask or infer from environment; allow user override)
  - Scope: high-level scope (e.g., "enrich/orchestrator: add async retries")
  - Summary: 2–5 sentence description of what was implemented or changed
  - Files changed: bullet list of paths
  - Rationale: brief explanation why the change was made
  - Notes: any migration steps, breaking changes, or follow-ups
  - Provenance: any relevant issue/PR numbers and links
- Style and constraints:
  - Keep entries concise and focused on actionable implementation details.
  - Do not include raw secrets, credentials, or sensitive data in summaries.
  - Use markdown headings and bullet lists; ensure plain-text compatibility.
- Confirmation prior to writing:
  - After generating the draft summary, present it to the user and ask for confirmation before writing to disk.
  - Allow user edits (inline or via a simple re-prompt) before the final write.
- Automation guard:
  - Under no circumstances should the model auto-commit, auto-push, or auto-save summaries without explicit user consent and confirmation of file path and write mode.
---

If any section is unclear or missing, please provide feedback for further refinement.
