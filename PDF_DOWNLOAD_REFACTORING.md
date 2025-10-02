# PDF Download Refactoring Documentation

## Overview

The `pdfs` command has been completely refactored to work with filtering query results and properly store all PDF resolution and download information in the database.

## Database Schema Changes

### New Tables

#### 1. `pdf_resolutions` Table
Stores the PDF candidates resolved for each record.

```sql
CREATE TABLE pdf_resolutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL,
    filtering_query_id INTEGER,
    timestamp TEXT NOT NULL,
    candidates TEXT NOT NULL,  -- JSON array of candidate objects
    FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE,
    FOREIGN KEY (filtering_query_id) REFERENCES filtering_queries(id) ON DELETE SET NULL
);
```

**Fields:**
- `id`: Unique identifier for the resolution record
- `record_id`: Foreign key to the record being processed
- `filtering_query_id`: Optional link to the filtering query (NULL if not from filtering)
- `timestamp`: ISO 8601 timestamp of when resolution occurred
- `candidates`: JSON array containing all resolved PDF candidates with their metadata

**Example candidates JSON:**
```json
[
  {"url": "https://arxiv.org/pdf/2410.03289.pdf", "source": "arxiv"},
  {"url": "https://unpaywall.org/...", "source": "unpaywall", "license": "cc-by"},
  {"url": "https://europepmc.org/...", "source": "epmc"}
]
```

#### 2. `pdf_downloads` Table
Stores individual download attempts and their results.

```sql
CREATE TABLE pdf_downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL,
    filtering_query_id INTEGER,
    timestamp TEXT NOT NULL,
    url TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    pdf_local_path TEXT,
    sha1 TEXT,
    final_url TEXT,
    error_message TEXT,
    FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE,
    FOREIGN KEY (filtering_query_id) REFERENCES filtering_queries(id) ON DELETE SET NULL
);
```

**Fields:**
- `id`: Unique identifier for the download attempt
- `record_id`: Foreign key to the record
- `filtering_query_id`: Optional link to filtering query
- `timestamp`: ISO 8601 timestamp of download attempt
- `url`: URL that was attempted
- `source`: Source of the URL (arxiv, unpaywall, epmc, s2, crossref, etc.)
- `status`: Download status (see below)
- `pdf_local_path`: Local file path if successfully downloaded
- `sha1`: SHA1 hash of the PDF content
- `final_url`: Final URL after redirects
- `error_message`: Error message if failed

**Status Values:**
- `downloaded`: PDF successfully downloaded and saved
- `unavailable`: URL returned non-200 status or non-PDF content
- `too_large`: PDF exceeds MAX_PDF_SIZE (50 MB)
- `no_candidates`: No PDF candidates found for the record
- `error`: Exception occurred during download

### New Indexes

```sql
CREATE INDEX idx_pdf_resolutions_record_id ON pdf_resolutions(record_id);
CREATE INDEX idx_pdf_resolutions_filtering_query_id ON pdf_resolutions(filtering_query_id);
CREATE INDEX idx_pdf_downloads_record_id ON pdf_downloads(record_id);
CREATE INDEX idx_pdf_downloads_filtering_query_id ON pdf_downloads(filtering_query_id);
CREATE INDEX idx_pdf_downloads_status ON pdf_downloads(status);
```

## New Database Functions

### `get_matched_records_by_filtering_query(filtering_query_id: int) -> list[Record]`

Retrieves all matched records from a filtering query, excluding ERROR and WARNING records.

**Returns:** List of Record objects that:
- Have `match_result = 1`
- Don't have explanations starting with "ERROR:"
- Don't have explanations starting with "WARNING:"

### `insert_pdf_resolution(record_id, candidates, timestamp, filtering_query_id=None) -> int`

Stores PDF resolution candidates for a record.

**Args:**
- `record_id`: ID of the record
- `candidates`: List of candidate dictionaries
- `timestamp`: ISO format timestamp
- `filtering_query_id`: Optional filtering query ID

**Returns:** ID of inserted resolution record

### `insert_pdf_download(record_id, url, source, status, timestamp, ...) -> int`

Stores a PDF download attempt result.

**Args:**
- `record_id`: ID of the record
- `url`: URL attempted
- `source`: Source identifier
- `status`: Status string
- `timestamp`: ISO format timestamp
- `filtering_query_id`: Optional filtering query ID
- `pdf_local_path`: Local path if downloaded
- `sha1`: SHA1 hash if downloaded
- `final_url`: Final URL after redirects
- `error_message`: Error message if failed

**Returns:** ID of inserted download record

### `get_pdf_download_stats(filtering_query_id=None) -> dict`

Gets statistics on PDF download attempts.

**Args:**
- `filtering_query_id`: Optional filtering query ID to filter by

**Returns:** Dictionary with status counts, e.g.:
```python
{
    "downloaded": 45,
    "unavailable": 20,
    "too_large": 3,
    "error": 2,
    "no_candidates": 10
}
```

## Refactored CLI Command

### New Signature

```python
def pdfs(
    filtering_query_id: int = typer.Option(..., "--query-id", help="Filtering query ID"),
    dest: Path = typer.Option(Path("data/pdfs"), "--dest", "-d", help="Destination directory"),
    max_concurrent: int = typer.Option(5, help="Maximum concurrent downloads"),
)
```

### Usage Examples

#### Basic Usage
```bash
# Download PDFs for filtering query ID 1
uv run llm-query-doc-analyser pdfs --query-id 1
```

#### Custom Destination
```bash
# Download to custom directory
uv run llm-query-doc-analyser pdfs --query-id 1 --dest "outputs/pdfs"
```

#### Adjust Concurrency
```bash
# Download with higher concurrency
uv run llm-query-doc-analyser pdfs --query-id 1 --max-concurrent 10
```

### Command Flow

1. **Fetch Matched Records**
   - Queries database for matched records from the filtering query
   - Excludes ERROR and WARNING records
   - Shows count to user

2. **For Each Record:**
   - **Resolve PDF Candidates**
     - Calls `resolve_pdf_candidates(rec)`
     - Stores candidates in `pdf_resolutions` table
     - Candidates are ranked: repository > preprint > publisher OA
   
   - **Attempt Downloads**
     - Tries each candidate in order
     - Stores each attempt in `pdf_downloads` table
     - Stops on first successful download
     - Continues to next record if all attempts fail

3. **Display Statistics**
   - Queries `pdf_downloads` table for final stats
   - Shows breakdown by status

### Output Example

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

## Enhanced download.py

### Improvements

1. **Better Error Handling**
   - Catches specific exception types (TimeoutException, HTTPError)
   - Returns structured error information
   - Never raises exceptions to caller

2. **Enhanced Return Values**
   - Always returns dictionary with status
   - Includes error messages for debugging
   - Provides content-type information for non-PDF responses

3. **Validation**
   - Checks for missing URLs
   - Validates content-type headers
   - Checks content-length before downloading

### Return Dictionary Format

```python
# Success
{
    "status": "downloaded",
    "path": "/path/to/sha1.pdf",
    "sha1": "abc123...",
    "final_url": "https://final.url/after/redirects.pdf",
    "url": "https://original.url/file.pdf"
}

# Too Large
{
    "status": "too_large",
    "url": "https://example.com/huge.pdf",
    "size": 60000000
}

# Unavailable
{
    "status": "unavailable",
    "url": "https://example.com/missing.pdf",
    "error": "HTTP 404"
}

# Error
{
    "status": "error",
    "url": "https://example.com/broken.pdf",
    "error": "Request timeout"
}
```

## Query Examples

### Find All Successful Downloads for a Filtering Query

```sql
SELECT 
    r.doi_norm,
    r.title,
    pd.source,
    pd.pdf_local_path,
    pd.sha1
FROM pdf_downloads pd
JOIN records r ON pd.record_id = r.id
WHERE pd.filtering_query_id = 1
    AND pd.status = 'downloaded'
ORDER BY pd.timestamp;
```

### Get Resolution Candidates for a Record

```sql
SELECT 
    r.doi_norm,
    pr.candidates,
    pr.timestamp
FROM pdf_resolutions pr
JOIN records r ON pr.record_id = r.id
WHERE r.id = 5;
```

### Find Records with Download Failures

```sql
SELECT 
    r.doi_norm,
    r.title,
    pd.url,
    pd.source,
    pd.status,
    pd.error_message
FROM pdf_downloads pd
JOIN records r ON pd.record_id = r.id
WHERE pd.filtering_query_id = 1
    AND pd.status IN ('error', 'unavailable')
ORDER BY r.id;
```

### Download Success Rate by Source

```sql
SELECT 
    source,
    status,
    COUNT(*) as count
FROM pdf_downloads
WHERE filtering_query_id = 1
GROUP BY source, status
ORDER BY source, status;
```

### Records with No PDF Candidates

```sql
SELECT 
    r.doi_norm,
    r.title,
    r.arxiv_id,
    r.oa_status
FROM records r
JOIN pdf_downloads pd ON r.id = pd.record_id
WHERE pd.filtering_query_id = 1
    AND pd.status = 'no_candidates';
```

## Complete Workflow Example

### 1. Filter Records
```bash
uv run llm-query-doc-analyser filter \
    --query "model description for image semantic segmentation on 2D image data" \
    --exclude "3D volumetric data"
```

Output shows: `Filtering query ID: 1`

### 2. Download PDFs
```bash
uv run llm-query-doc-analyser pdfs --query-id 1
```

### 3. Query Results in Database
```python
import sqlite3
conn = sqlite3.connect("data/cache/records.db")

# Get summary
stats = conn.execute("""
    SELECT status, COUNT(*) 
    FROM pdf_downloads 
    WHERE filtering_query_id = 1 
    GROUP BY status
""").fetchall()

# Get successful downloads
downloads = conn.execute("""
    SELECT r.title, pd.source, pd.pdf_local_path
    FROM pdf_downloads pd
    JOIN records r ON pd.record_id = r.id
    WHERE pd.filtering_query_id = 1 
        AND pd.status = 'downloaded'
""").fetchall()
```

## Benefits of This Refactoring

1. **Complete Audit Trail**: Every resolution and download attempt is recorded
2. **Filtering Integration**: Direct connection to filtering query results
3. **Reproducibility**: Can re-download for same query or analyze failures
4. **Debugging**: Error messages stored for troubleshooting
5. **Analytics**: Can analyze success rates by source, identify problematic URLs
6. **Efficiency**: Concurrent downloads with configurable limits
7. **Data Integrity**: Foreign keys ensure referential integrity
8. **Flexibility**: Can query by filtering_query_id or record_id

## Migration Notes

- Old `pdfs` command required `--from` parameter with file path
- New `pdfs` command requires `--query-id` with filtering query ID
- Records table fields `pdf_status` and `pdf_local_path` are no longer directly updated
- All PDF information is now in dedicated tables
- Old workflow: file → pdfs command → file
- New workflow: filter command → pdfs command → database
