# PDF Command Refactoring Summary

## Changes Made

### 1. Database Schema (`core/store.py`)

#### New Tables Added

**`pdf_resolutions`**
- Stores PDF candidates resolved for each record
- Links to filtering queries
- Contains JSON array of all candidates with their metadata

**`pdf_downloads`**
- Stores individual download attempts
- Tracks status, errors, and successful downloads
- Links downloads to filtering queries

#### New Indexes
- 6 new indexes for efficient querying by record_id, filtering_query_id, and status

### 2. New Database Functions (`core/store.py`)

1. **`get_matched_records_by_filtering_query(filtering_query_id) -> list[Record]`**
   - Fetches matched records from a filtering query
   - Excludes ERROR and WARNING records
   - Returns full Record objects

2. **`insert_pdf_resolution(record_id, candidates, timestamp, filtering_query_id=None) -> int`**
   - Stores resolved PDF candidates
   - Saves all candidate URLs and metadata as JSON

3. **`insert_pdf_download(record_id, url, source, status, timestamp, ...) -> int`**
   - Records each download attempt
   - Captures success, failure, or error details

4. **`get_pdf_download_stats(filtering_query_id=None) -> dict`**
   - Aggregates download statistics by status
   - Can filter by filtering_query_id

### 3. Enhanced Download Logic (`pdfs/download.py`)

**Improvements:**
- Comprehensive error handling (timeout, HTTP errors, general exceptions)
- Structured return values with detailed error messages
- Content-type validation
- Size checking before download
- Never raises exceptions (always returns status dictionary)

**New Return Fields:**
- `status`: downloaded, unavailable, too_large, error
- `error`: Error message if failed
- `size`: File size for too_large status
- `final_url`: URL after redirects

### 4. Refactored CLI Command (`cli.py`)

**Old Signature:**
```python
def pdfs(from_: Path | None = None, dest: Path = Path("data/pdfs"))
```

**New Signature:**
```python
def pdfs(
    filtering_query_id: int = typer.Option(..., "--query-id"),
    dest: Path = typer.Option(Path("data/pdfs"), "--dest", "-d"),
    max_concurrent: int = typer.Option(5),
)
```

**Key Changes:**
- Now requires filtering_query_id instead of file path
- Fetches matched records directly from database
- Stores all resolution and download data in database
- Async concurrent processing with configurable limit
- Progress and detailed statistics output

### 5. Complete Workflow Integration

**Before:**
```bash
# Old workflow (file-based)
llm-query-doc-analyser filter ... --export filtered.parquet
llm-query-doc-analyser pdfs --from filtered.parquet
```

**After:**
```bash
# New workflow (database-based)
llm-query-doc-analyser filter ... 
# Output: Filtering query ID: 1

llm-query-doc-analyser pdfs --query-id 1
# All results stored in database
```

## Benefits

### 1. Complete Audit Trail
- Every PDF resolution saved
- Every download attempt recorded
- Full error messages for debugging

### 2. Data Integrity
- Foreign key constraints
- Referential integrity with filtering queries
- Cascade deletes for cleanup

### 3. Analytics Capabilities
```sql
-- Success rate by source
SELECT source, status, COUNT(*) 
FROM pdf_downloads 
GROUP BY source, status;

-- Records with no candidates
SELECT r.* FROM records r
JOIN pdf_downloads pd ON r.id = pd.record_id
WHERE pd.status = 'no_candidates';

-- Failed downloads to retry
SELECT * FROM pdf_downloads 
WHERE status IN ('error', 'unavailable')
ORDER BY record_id;
```

### 4. Reproducibility
- Can re-run downloads for same filtering query
- Can analyze which sources work best
- Can identify problematic records

### 5. Performance
- Concurrent downloads (configurable)
- Indexed queries for fast lookups
- Batch processing of records

## Usage Examples

### Basic Usage
```bash
uv run llm-query-doc-analyser pdfs --query-id 1
```

### Custom Destination
```bash
uv run llm-query-doc-analyser pdfs --query-id 1 --dest "outputs/pdfs"
```

### Higher Concurrency
```bash
uv run llm-query-doc-analyser pdfs --query-id 1 --max-concurrent 10
```

## Output Example

```
Fetching matched records from filtering query 1...
Found 79 matched records to process.
Destination: data/pdfs

Resolving PDF candidates and downloading...

PDF Download Results:
  Total records processed: 79
  Successfully downloaded: 45
  No candidates found: 10
  Unavailable: 20
  Too large: 3
  Errors: 1

PDFs saved to: data/pdfs
Results stored in database: data\cache\records.db
```

## Migration Checklist

- [x] Created pdf_resolutions table
- [x] Created pdf_downloads table
- [x] Added indexes for performance
- [x] Implemented get_matched_records_by_filtering_query
- [x] Implemented insert_pdf_resolution
- [x] Implemented insert_pdf_download
- [x] Implemented get_pdf_download_stats
- [x] Enhanced download.py error handling
- [x] Refactored pdfs CLI command
- [x] Integrated with filtering query workflow
- [x] Added comprehensive documentation

## Files Modified

1. `src/llm_query_doc_analyser/core/store.py`
   - Added 2 new table schemas
   - Added 6 new indexes
   - Added 4 new database functions
   - Updated init_db() to create new tables

2. `src/llm_query_doc_analyser/cli.py`
   - Updated imports
   - Completely refactored pdfs() command
   - Added filtering_query_id parameter
   - Implemented concurrent processing
   - Enhanced output with statistics

3. `src/llm_query_doc_analyser/pdfs/download.py`
   - Enhanced error handling
   - Improved return value structure
   - Added validation checks
   - Better exception handling

## Next Steps

Users can now:
1. Run filter command to get matched records
2. Use the filtering_query_id to download PDFs
3. Query the database for detailed analytics
4. Re-run downloads for failed attempts
5. Analyze success rates by source
