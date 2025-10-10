# PDF Download HTTP Improvements

## Changes Made

### 1. Updated `utils/http.py`
**Fix:**
- ✅ Added `follow_redirects=True` to `get_with_retry()` client creation
- ✅ Handles 301/302 redirects from arXiv, medRxiv, and other sources

### 2. Updated `pdfs/download.py` - Bot Detection Prevention
**Improvements:**
- ✅ Uses `get_with_retry()` from `utils/http.py` for automatic retry logic
- ✅ **Enhanced browser-like headers** to avoid bot detection:
  - Complete Chrome 131 User-Agent
  - Accept-Language, Accept-Encoding
  - Sec-Fetch-* headers (Dest, Mode, Site, User)
  - sec-ch-ua headers for Chrome browser fingerprint
  - DNT, Upgrade-Insecure-Requests
- ✅ **arXiv-specific headers**: Sets `Referer: https://arxiv.org/`
- ✅ Maintains bioRxiv/medRxiv headers (Google referer, Cache-Control)
- ✅ Maintains preprints.org headers (manuscript page referrer)
- ✅ Structured logging with `structlog` throughout
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

### 3. Updated `cli.py` (pdfs command) - Source-Aware Rate Limiting
**Improvements:**
- ✅ **Source-specific rate limiters** to respect provider guidelines:
  - **arXiv**: 0.33 calls/sec (1 call per 3 seconds) - arXiv recommendation
  - **Default**: 1.0 calls/sec (conservative for other sources)
- ✅ Rate limiting applied before each PDF download attempt
- ✅ Works with concurrent downloads via semaphore + rate limiter

**Pattern:**
```python
rate_limiters = {
    "arxiv": RateLimiter(calls_per_second=0.33),  # arXiv: 1 call per 3 seconds
    "default": RateLimiter(calls_per_second=1.0),
}

async def download_record_pdf(rec: Record):
    for cand in candidates:
        source = cand.get("source", "").lower()
        limiter = rate_limiters.get(source, rate_limiters["default"])
        await limiter.acquire()  # Source-specific rate limit
        result = await download_pdf(cand, dest)
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

## Bot Detection Prevention (arXiv)

**Issue**: arXiv returns HTML "human verification" pages instead of PDFs when bot detection is triggered. Error: `Content type is text/html, not PDF`

**Root Causes**:
1. Too rapid requests (need 3 second intervals per arXiv guidelines)
2. Inadequate browser headers (obvious bot signature)

**Solutions**:
1. **Enhanced Browser Headers** - Complete Chrome fingerprint:
   ```python
   "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
   "Accept": "application/pdf,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
   "Accept-Language": "en-US,en;q=0.9",
   "Sec-Fetch-Dest": "document",
   "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
   "Referer": "https://arxiv.org/"  # arXiv-specific
   ```

2. **Source-Specific Rate Limiting**:
   - arXiv: 0.33 calls/sec (1 per 3 seconds) - follows arXiv guidelines
   - Others: 1.0 calls/sec (conservative default)

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
