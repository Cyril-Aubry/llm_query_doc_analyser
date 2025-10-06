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
- **Install:** Use `uv pip install` (preferred) or `pip install -r requirements.txt`.
- **Run CLI:**
  - `python -m llm_query_doc_analyser --help`
  - Example pipeline:
    - `python -m llm_query_doc_analyser import data/input/records.xlsx`
    - `python -m llm_query_doc_analyser enrich`
    - `python -m llm_query_doc_analyser filter --query "..."`
    - `python -m llm_query_doc_analyser pdfs`
    - `python -m llm_query_doc_analyser export outputs/results.xlsx`
- **Lint/Type Check:**
  - `uv run ruff check src`
  - `uv run mypy src`
- **Test:**
  - `uv run pytest`

## Integration Points
- **APIs:** Crossref, Unpaywall, OpenAlex, EuropePMC, PubMed, Semantic Scholar (optional), OpenAI (optional)
- **Dependencies:** See `pyproject.toml` for full list. Key: `pandas`, `httpx[http2]`, `pydantic`, `typer`, `structlog`, `tenacity`, `rapidfuzz`, `rank-bm25`, `sentence-transformers`, `faiss-cpu`, `pypdf`, `openai`, `spacy`, `nltk`.

## Examples & References
- **Input/Output:** See `data/input/`, `outputs/`, and `io_/` modules.
- **Enrichment:** See `enrich/orchestrator.py` for API orchestration logic.
- **Filtering:** See `filter_rank/` and `enrich/embed.py` for semantic filtering patterns.
- **PDF Handling:** See `pdfs/` for OA PDF resolution and download logic.

---

If any section is unclear or missing, please provide feedback for further refinement.
