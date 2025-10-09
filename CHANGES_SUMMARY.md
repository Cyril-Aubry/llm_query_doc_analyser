# API Best Practices and Abstract Retrieval Tracking - Changes Summary

## Overview
This update implements robust API calling patterns with proper retry logic, rate limiting, and error logging across all external API integrations. It also adds comprehensive tracking for why abstracts fail to be retrieved during enrichment.

## Key Changes

### 1. Enhanced HTTP Utility (`utils/http.py`)
- **Improved `get_with_retry()`**: Now uses tenacity's retry decorator with exponential backoff (2-60 seconds)
- **Smart retry logic**: Retries on 408, 429, 5xx status codes and network errors
- **Better error logging**: Comprehensive logging of all HTTP errors with response details
- **Connection pooling**: Added `httpx.Limits` to prevent overwhelming APIs
- **Rate limiting**: New `RateLimiter` class implementing token bucket algorithm
  - Configurable calls per second
  - Async-safe with lock mechanism
  - Automatic wait time calculation

### 2. Updated All API Clients
All API client modules now follow best practices:

#### arXiv (`enrich/arxiv.py`)
- Uses `get_with_retry()` with 15-second timeout
- Rate limited to 0.33 calls/sec (ArXiv recommendation: 1 call per 3 seconds)
- Comprehensive error handling for timeout, HTTP, and parsing errors
- Detailed logging at each step

#### Crossref (`enrich/crossref.py`)
- Uses `get_with_retry()` with proper retry logic
- Rate limited to 1 call/sec (polite rate)
- JSON parsing error handling
- Logs success/failure with relevant metadata

#### OpenAlex (`enrich/openalex.py`)
- Uses `get_with_retry()` with retry logic
- Rate limited to 5 calls/sec (no strict limit, but polite)
- Fixed abstract reconstruction from inverted index
- Better error handling for edge cases

#### EuropePMC (`enrich/europepmc.py`)
- Uses `get_with_retry()` with retry logic
- Rate limited to 2 calls/sec
- Comprehensive error logging
- Handles empty results gracefully

#### PubMed (`enrich/pubmed.py`)
- Uses `get_with_retry()` for both search and fetch
- Rate limited to 3 calls/sec (NCBI guideline without API key)
- Two-step process (search PMID, fetch abstract) with error handling at each step
- Better XML parsing with cleanup

#### Semantic Scholar (`enrich/semanticscholar.py`)
- Uses `get_with_retry()` with retry logic
- Rate limited to 5 calls/sec (with API key can be higher)
- Comprehensive error handling
- API key validation

#### Unpaywall (`enrich/unpaywall.py`)
- Updated to use `get_with_retry()`
- Rate limited to 5 calls/sec
- Already had good error handling, now enhanced

#### Preprint Providers (`enrich/preprint_providers.py`)
- Updated arXiv, bioRxiv/medRxiv, and Preprints.org fetchers
- All use `get_with_retry()` with proper error handling
- Rate limited to 2 calls/sec for preprint sources
- Comprehensive logging for each provider

### 3. Abstract Retrieval Failure Tracking

#### Database Schema (`core/models.py` & `core/store.py`)
- **New field**: `abstract_no_retrieval_reason` (TEXT)
  - Stores detailed reason why abstract was not retrieved
  - Example: "Crossref: No abstract field in response; OpenAlex: http_404; EuropePMC: no_doi"
  - NULL if abstract was successfully retrieved

#### Migration Support (`core/store.py`)
- Added `_apply_migrations()` function
- Automatically adds `abstract_no_retrieval_reason` column to existing databases
- Safe ALTER TABLE with error handling
- Logged migration process

#### Orchestrator Updates (`enrich/orchestrator.py`)
- **Rate limiters integrated**: Each API source has configured rate limiter
- **Failure reason compilation**: After enrichment, compiles all failure reasons into single field
- **Enhanced logging**: Warns when abstracts can't be retrieved with specific reasons
- **Report updates**: `format_enrichment_report()` now displays failure reason

### 4. Rate Limiting Configuration (`enrich/orchestrator.py`)
Global rate limiters for each API:
```python
RATE_LIMITERS = {
    "arxiv": RateLimiter(calls_per_second=0.33),      # ArXiv: 1 per 3 sec
    "crossref": RateLimiter(calls_per_second=1.0),     # Polite
    "openalex": RateLimiter(calls_per_second=5.0),     # Polite, no strict limit
    "europepmc": RateLimiter(calls_per_second=2.0),    # Polite
    "pubmed": RateLimiter(calls_per_second=3.0),       # NCBI guideline (no key)
    "s2": RateLimiter(calls_per_second=5.0),           # With API key
    "unpaywall": RateLimiter(calls_per_second=5.0),    # Polite
    "preprints": RateLimiter(calls_per_second=2.0),    # General preprints
}
```

## Benefits

### Reliability
- **Exponential backoff**: Automatically handles temporary API failures
- **Rate limiting**: Prevents hitting API rate limits
- **Connection pooling**: Efficient connection reuse

### Observability
- **Comprehensive logging**: Every API call is logged with URL, status, and errors
- **Failure tracking**: Database field shows exactly why abstracts couldn't be retrieved
- **Structured logs**: Easy to parse and analyze

### Performance
- **Connection reuse**: HTTP/2 support with connection pooling
- **Smart retries**: Only retries on recoverable errors
- **Configurable timeouts**: 15-second timeout for most APIs

### Compliance
- **Respects rate limits**: Follows each API's recommended rate limits
- **Polite user agents**: All requests identify the application
- **Proper error handling**: Doesn't spam APIs on permanent failures

## Testing Recommendations

1. **Test with many arXiv preprints**: Should now handle large batches without rate limit errors
2. **Check logs**: Verify structured logging captures all API interactions
3. **Database inspection**: Query `abstract_no_retrieval_reason` to see why abstracts failed
4. **Monitor retry behavior**: Check logs for retry attempts and backoff times
5. **Rate limiting validation**: Ensure no more than configured calls per second to each API

## Example Queries

Check records where abstracts couldn't be retrieved:
```sql
SELECT 
    doi_norm, 
    title, 
    abstract_no_retrieval_reason 
FROM research_articles 
WHERE abstract_text IS NULL 
    AND abstract_no_retrieval_reason IS NOT NULL;
```

Analyze common failure reasons:
```sql
SELECT 
    abstract_no_retrieval_reason, 
    COUNT(*) as count 
FROM research_articles 
WHERE abstract_text IS NULL 
GROUP BY abstract_no_retrieval_reason 
ORDER BY count DESC;
```

## Files Modified

1. `src/llm_query_doc_analyser/utils/http.py` - Enhanced retry and rate limiting
2. `src/llm_query_doc_analyser/core/models.py` - Added `abstract_no_retrieval_reason` field
3. `src/llm_query_doc_analyser/core/store.py` - Database schema and migration
4. `src/llm_query_doc_analyser/enrich/arxiv.py` - Updated with best practices
5. `src/llm_query_doc_analyser/enrich/crossref.py` - Updated with best practices
6. `src/llm_query_doc_analyser/enrich/openalex.py` - Updated with best practices
7. `src/llm_query_doc_analyser/enrich/europepmc.py` - Updated with best practices
8. `src/llm_query_doc_analyser/enrich/pubmed.py` - Updated with best practices
9. `src/llm_query_doc_analyser/enrich/semanticscholar.py` - Updated with best practices
10. `src/llm_query_doc_analyser/enrich/unpaywall.py` - Updated with best practices
11. `src/llm_query_doc_analyser/enrich/preprint_providers.py` - Updated all providers
12. `src/llm_query_doc_analyser/enrich/orchestrator.py` - Rate limiting and failure tracking

## No Breaking Changes

All changes are backward compatible:
- Existing code continues to work
- Database migration is automatic
- New field defaults to NULL for existing records
- Rate limiting is transparent to callers
