# PDF Download HTTP Improvements

## Changes Made

### 1. Updated `utils/http.py`
**Fix:**
- ✅ Added `follow_redirects=True` to `get_with_retry()` client creation
- ✅ Handles 301/302 redirects from arXiv, medRxiv, and other sources

### 2. Updated `pdfs/download.py`
**Improvements:**
- ✅ Uses `get_with_retry()` from `utils/http.py` for automatic retry logic
- ✅ Structured logging with `structlog` throughout
- ✅ Source-aware header configuration via `_get_pdf_headers()`
- ✅ Maintains bioRxiv/medRxiv specific headers (Referer, Cache-Control)
- ✅ Maintains preprints.org specific headers (manuscript page referrer)
- ✅ Proper error handling with detailed logging

**Header Strategy:**
```python
def _get_pdf_headers(url: str, source: str | None = None) -> dict[str, str]:
    # Base headers for all sources
    base_headers = {"User-Agent": "...", "Accept": "application/pdf,*/*;q=0.8"}
    
    # bioRxiv/medRxiv: Google referer + cache control
    if source in ("biorxiv", "medrxiv"):
        base_headers.update({"Referer": "https://www.google.com/", ...})
    
    # preprints.org: manuscript page as referer
    elif source == "preprints":
        base_headers["Referer"] = url.split("/download")[0]
```

### 3. Updated `cli.py` (pdfs command)
**Improvements:**
- ✅ Added `RateLimiter` (2 calls/sec) to be polite to servers
- ✅ Rate limiting applied before each PDF download attempt
- ✅ Works with concurrent downloads via semaphore + rate limiter

**Pattern:**
```python
pdf_rate_limiter = RateLimiter(calls_per_second=2.0)

async def download_record_pdf(rec: Record):
    for cand in candidates:
        await pdf_rate_limiter.acquire()  # Rate limit
        result = await download_pdf(cand, dest)  # Retry logic inside
```

## Benefits

1. **Reliability**: Automatic retries on transient failures (5xx, timeouts)
2. **Politeness**: Rate limiting prevents overwhelming servers
3. **Observability**: Structured logging for debugging
4. **Consistency**: Same HTTP patterns as enrichment commands
5. **Source-specific**: Preserves working headers for bioRxiv, preprints.org, etc.

## Testing

✅ All 30 tests pass  
✅ PDF download functionality verified  
✅ No breaking changes

## Redirect Handling (arXiv, medRxiv)

**Issue**: HTTP 301 redirects from arXiv URLs like `https://arxiv.org/pdf/2410.03289.pdf`

**Fix**: Added `follow_redirects=True` to the temporary client in `get_with_retry()`:
```python
client = httpx.AsyncClient(http2=True, timeout=timeout, follow_redirects=True)
```

This ensures all HTTP redirects (301, 302) are followed automatically during PDF downloads.

## Files Modified

- `src/llm_query_doc_analyser/utils/http.py` - Added redirect following to `get_with_retry()`
- `src/llm_query_doc_analyser/pdfs/download.py` - Main HTTP improvements
- `src/llm_query_doc_analyser/cli.py` - Added rate limiting to pdfs command
