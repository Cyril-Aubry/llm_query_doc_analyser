# llm_query_doc_analyser

`llm_query_doc_analyser` is a production-ready command-line tool for scholarly literature analysis, enrichment, semantic filtering, and Open Access PDF management. Designed for researchers and engineers, it automates the process of loading, enriching, filtering, and exporting scholarly records with strict Open Access guardrails and full provenance tracking.

---
## Key Features

- **Input Processing:** Accepts Excel/CSV files, validates data, and ensures required fields.
- **Abstract Enrichment:** Integrates with public scholarly APIs, caches responses, and tracks provenance.
- **Semantic Filtering:** Supports advanced natural language queries and relevance scoring.
- **PDF Management:** Downloads only Open Access PDFs, manages links, and organizes files securely.
- **Export Functionality:** Outputs to CSV, XLSX, and Parquet with full metadata and provenance.

---
## Technical Requirements

- Python 3.11 (see `pyproject.toml` for version constraints)
- Follows PEP 8 and modern Python best practices
- Comprehensive error handling, type hints, and docstrings
- CLI help documentation
- Asyncio for concurrent API requests
- Structured logging with configurable levels
- Configuration via environment variables (`.env`)
- Example `.env.example` file included
- Unit tests with >= 80% coverage
- API rate limits and quotas documented

---
## Project Structure

```
llm_query_doc_analyser/
├─ pyproject.toml
├─ README.md
├─ .env.example
├─ data/
│  ├─ input/          # user CSV/XLSX
│  ├─ cache/          # HTTP/db cache
│  └─ pdfs/           # saved PDFs (aa/bb/<sha1>.pdf)
├─ outputs/           # exported tables & reports
├─ src/
│  └─ llm_query_doc_analyser/
│     ├─ __init__.py
│     ├─ cli.py
│     ├─ io_/load.py
│     ├─ io_/export.py
│     ├─ core/models.py
│     ├─ core/store.py
│     ├─ core/hashing.py
│     ├─ utils/http.py
│     ├─ utils/log.py
│     ├─ enrich/
│     │  ├─ crossref.py
│     │  ├─ unpaywall.py
│     │  ├─ openalex.py
│     │  ├─ semanticscholar.py     # optional if API key provided
│     │  ├─ europepmc.py
│     │  ├─ pubmed.py
│     │  └─ orchestrator.py
│     ├─ filter_rank/
│     │  ├─ rules.py
│     │  ├─ embed.py
│     │  ├─ rerank.py
│     │  └─ prompts.py
│     └─ pdfs/
│        ├─ resolve.py
│        └─ download.py
└─ tests/
	 ├─ test_load.py
	 ├─ test_enrich.py
	 ├─ test_filter.py
	 ├─ test_pdfs.py
	 └─ data/fixtures/*.json
```

---
## Guardrails & Scope

- No university credentials, proxy/VPN logic, or scraping of paywalled HTML
- Programmatic PDF fetches only from OA endpoints (HTTP 200, Content-Type: application/pdf, no cookies/auth)
- Strict API etiquette: rate-limit, backoff, cache, and include contact email in User-Agent
- Full provenance for all injected fields (source, URL, timestamp, raw JSON)

---
## Required Dependencies

- `pandas`, `openpyxl`: data processing
- `httpx[http2]`: async HTTP client
- `pydantic`: data validation
- `typer`: CLI interface
- `pytest`, `pytest-asyncio`, `pytest-cov`, `respx`: testing
- `structlog`: logging
- `python-dotenv`: configuration
- `tenacity`: retry logic
- `rapidfuzz`, `rank-bm25`, `sentence-transformers`, `faiss-cpu`: semantic filtering
- `pypdf`: PDF handling
- `openai`, `spacy`, `nltk`: LLM and NLP support

See `pyproject.toml` for the full list.

---
## Installation

```powershell
# Clone the repository
git clone <repo-url>
cd llm_query_doc_analyser

# Install dependencies (recommended: use a virtual environment)
# If using requirements.txt:
# pip install -r requirements.txt
# If using pyproject.toml and uv:
uv pip install
```

---
## Usage

```powershell
# Show CLI help
python -m llm_query_doc_analyser --help

# Example: Import, enrich, filter, download PDFs, and export
python -m llm_query_doc_analyser import data/input/records.xlsx
python -m llm_query_doc_analyser enrich
python -m llm_query_doc_analyser filter --query "image semantic segmentation on 2D image data only"
python -m llm_query_doc_analyser pdfs
python -m llm_query_doc_analyser export outputs/results.xlsx
```

---
## API Documentation

- See `src/llm_query_doc_analyser/` modules for details on each component.
- Each API client implements rate limiting and backoff; see code and API docs for quotas.
- HTTP and database cache stored in `data/cache/`.
- Comprehensive error handling and logging; see logs for details.

---

## Configuration

All configuration is managed via environment variables. Copy `.env.example` to `.env` and edit as needed:

```powershell
cp .env.example .env
# Then edit .env with your API keys and settings
```

Key variables:

- `UNPAYWALL_EMAIL`: Your email for Unpaywall API
- `S2_API_KEY`: (Optional) Semantic Scholar API key
- `OPENAI_API_KEY`: (Optional) For LLM-based filtering
- `OPENAI_MODEL`: (Optional) Model name (e.g., gpt-4)
- `LOG_LEVEL`: Logging verbosity

---

## Development Setup & Contribution Guidelines

1. Fork and clone the repository.
2. Install dependencies as above.
3. Use a virtual environment for isolation.
4. Follow PEP 8 and use type hints and docstrings.
5. Run linting and type checks:

```powershell
uv run ruff check src
uv run mypy src
```

6. Add or update tests in the `tests/` directory.
7. Ensure all tests pass before submitting a PR:

```powershell
uv run pytest
```

---

## Testing Instructions

Run all tests with:

```powershell
uv run pytest
```

Test coverage is expected to be >= 80%. Add tests for new features or bug fixes.

---

## Known Issues or Limitations

- No support for paywalled or non-OA PDF downloads
- No scraping or proxy logic
- API rate limits may restrict throughput
- Only tested on Python 3.11

---
## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
