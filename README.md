
# llm_query_doc_analyser

`llm_query_doc_analyser` is a production-ready command-line tool for scholarly literature analysis, enrichment, semantic filtering, and Open Access PDF management. Designed for researchers and engineers, it automates the process of loading, enriching, filtering, and exporting scholarly records with strict Open Access guardrails and full provenance tracking.

## Core Functionality

### 1. Input Processing
- Accepts Excel/CSV files containing scholarly records
- Required fields: `title`
- Optional fields: `DOI`, `publication date`
- Validates input format and data integrity

### 2. Abstract Enrichment
- Utilizes public scholarly APIs (Crossref, Unpaywall, OpenAlex, EuropePMC, PubMed)
- Implements rate limiting and exponential backoff
- Caches API responses locally
- Includes API attribution (email in User-Agent)
- Stores provenance metadata (source, URL, timestamp, raw response)

### 3. Semantic Filtering
- Natural language query processing for advanced filtering
- Supports user-defined criteria (e.g., "image semantic segmentation on 2D image data only")
- Calculates and stores relevance scores
- Documents filtering logic and thresholds

### 4. PDF Management
- Downloads PDFs only from Open Access sources returning:
	- HTTP 200 status
	- Content-Type: application/pdf
	- No authentication required
- Generates clean links for non-downloadable papers:
	- Publisher DOI landing page
	- Repository landing page
- Stores PDFs using SHA1-based directory structure

### 5. Export Functionality
- Supports CSV, XLSX, and Parquet formats
- Includes enriched metadata, relevance scores, and filtering rationale
- Exports PDF paths or access links
- Maintains data provenance throughout

## Technical Requirements
- Follows PEP 8 and modern Python best practices
- Comprehensive error handling
- Type hints and docstrings throughout
- CLI help documentation
- Asyncio for concurrent API requests
- Structured logging with configurable levels
- Configuration via environment variables (`.env`)
- Example `.env.example` file included
- Unit tests with >= 80% coverage
- API rate limits and quotas documented

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

## Guardrails & Scope
- No university credentials, proxy/VPN logic, or scraping of paywalled HTML
- Programmatic PDF fetches only from OA endpoints (HTTP 200, Content-Type: application/pdf, no cookies/auth)
- Strict API etiquette: rate-limit, backoff, cache, and include contact email in User-Agent
- Full provenance for all injected fields (source, URL, timestamp, raw JSON)

## Required Dependencies
- `pandas`: data processing
- `httpx`: async HTTP client
- `pydantic`: data validation
- `click`: CLI interface
- `pytest`: testing
- `loguru`: logging
- `python-dotenv`: configuration

## Installation

```sh
# Clone the repository
git clone <repo-url>
cd llm_query_doc_analyser

# Install dependencies (recommended: use a virtual environment)
pip install -r requirements.txt
# or, if using pyproject.toml/uv
uv pip install
```

## Usage

```sh
# Show CLI help
python -m llm_query_doc_analyser --help

# Example: Import, enrich, filter, download PDFs, and export
python -m llm_query_doc_analyser import data/input/records.xlsx
python -m llm_query_doc_analyser enrich
python -m llm_query_doc_analyser filter --query "image semantic segmentation on 2D image data only"
python -m llm_query_doc_analyser pdfs
python -m llm_query_doc_analyser export outputs/results.xlsx
```

## Documentation

- **API Reference**: See `src/llm_query_doc_analyser/` modules for details
- **Rate Limits**: Each API client implements rate limiting and backoff; see code and API docs for quotas
- **Cache Configuration**: HTTP and database cache stored in `data/cache/`
- **Error Handling**: Comprehensive error handling and logging; see logs for details
- **Contributing**: PRs and issues welcome! Please add tests and follow code style guidelines

## License

MIT License. See [LICENSE](LICENSE) for details.
