# Testing Guide for PDF Download Refactoring

## Prerequisites

1. Ensure database is initialized:
```bash
uv run python -c "from llm_query_doc_analyser.core.store import init_db; init_db()"
```

2. Have some records in the database (from import/enrich commands)

3. Have OpenAI API key and model configured in `.env`

## Test Workflow

### Step 1: Import Records

```bash
uv run llm-query-doc-analyser import_ path/to/records.csv
```

Expected output:
```
Imported X records from path/to/records.csv
```

### Step 2: Filter Records

```bash
uv run llm-query-doc-analyser filter \
    --query "model description for image semantic segmentation on 2D image data" \
    --exclude "3D volumetric data"
```

Expected output:
```
Filtering X records with query: '...'
Progress: 100% (X/X)

Filtering completed:
  Total records processed: X
  Matched records: Y
  Failed records (errors): 0
  Filtering query ID: 1

Results stored in database: data\cache\records.db
```

**Note the Filtering query ID** - you'll need this for the next step.

### Step 3: Download PDFs

```bash
uv run llm-query-doc-analyser pdfs --query-id 1
```

Expected output:
```
Fetching matched records from filtering query 1...
Found Y matched records to process.
Destination: data/pdfs

Resolving PDF candidates and downloading...

PDF Download Results:
  Total records processed: Y
  Successfully downloaded: A
  No candidates found: B
  Unavailable: C
  Too large: D
  Errors: E

PDFs saved to: data/pdfs
Results stored in database: data\cache\records.db
```

### Step 4: Verify Database

```bash
uv run python -c "
from llm_query_doc_analyser.core.store import get_pdf_download_stats
stats = get_pdf_download_stats(filtering_query_id=1)
print('Download Statistics:', stats)
"
```

## Verification Queries

### Check PDF Resolutions Table

```python
import sqlite3
conn = sqlite3.connect("data/cache/records.db")

# Count resolutions
count = conn.execute("""
    SELECT COUNT(*) FROM pdf_resolutions
    WHERE filtering_query_id = 1
""").fetchone()[0]
print(f"PDF resolutions stored: {count}")

# Sample resolution
sample = conn.execute("""
    SELECT r.doi_norm, pr.candidates
    FROM pdf_resolutions pr
    JOIN records r ON pr.record_id = r.id
    WHERE pr.filtering_query_id = 1
    LIMIT 1
""").fetchone()
print(f"Sample resolution: {sample}")
```

### Check PDF Downloads Table

```python
# Count downloads by status
stats = conn.execute("""
    SELECT status, COUNT(*) as count
    FROM pdf_downloads
    WHERE filtering_query_id = 1
    GROUP BY status
""").fetchall()
print("Download stats by status:")
for status, count in stats:
    print(f"  {status}: {count}")

# Sample successful download
success = conn.execute("""
    SELECT r.doi_norm, pd.source, pd.pdf_local_path, pd.sha1
    FROM pdf_downloads pd
    JOIN records r ON pd.record_id = r.id
    WHERE pd.filtering_query_id = 1 
        AND pd.status = 'downloaded'
    LIMIT 1
""").fetchone()
print(f"Sample download: {success}")
```

### Check Downloaded Files

```python
from pathlib import Path

pdf_dir = Path("data/pdfs")
if pdf_dir.exists():
    pdf_files = list(pdf_dir.rglob("*.pdf"))
    print(f"Total PDF files: {len(pdf_files)}")
    if pdf_files:
        print(f"Sample file: {pdf_files[0]}")
        print(f"File size: {pdf_files[0].stat().st_size / 1024:.2f} KB")
```

## Test Edge Cases

### Test 1: No Matched Records

```bash
# Create a filtering query that matches nothing
uv run llm-query-doc-analyser filter \
    --query "xyzabc nonexistent topic 12345"

# Try to download (should handle gracefully)
uv run llm-query-doc-analyser pdfs --query-id 2
```

Expected: "No matched records found for this filtering query."

### Test 2: Custom Destination

```bash
uv run llm-query-doc-analyser pdfs \
    --query-id 1 \
    --dest "outputs/my_pdfs"
```

Verify files are in `outputs/my_pdfs/` directory.

### Test 3: High Concurrency

```bash
uv run llm-query-doc-analyser pdfs \
    --query-id 1 \
    --max-concurrent 10
```

Should complete faster with more concurrent downloads.

### Test 4: Invalid Query ID

```bash
uv run llm-query-doc-analyser pdfs --query-id 99999
```

Expected: Empty result or error message.

## Analytics Queries

### Success Rate by Source

```sql
SELECT 
    source,
    status,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY source), 2) as percentage
FROM pdf_downloads
WHERE filtering_query_id = 1
GROUP BY source, status
ORDER BY source, count DESC;
```

### Records Without PDFs

```sql
SELECT 
    r.id,
    r.doi_norm,
    r.title,
    r.arxiv_id,
    r.oa_status
FROM records r
JOIN records_filterings rf ON r.id = rf.record_id
LEFT JOIN pdf_downloads pd ON r.id = pd.record_id AND pd.status = 'downloaded'
WHERE rf.filtering_query_id = 1
    AND rf.match_result = 1
    AND pd.id IS NULL;
```

### Download Errors Analysis

```sql
SELECT 
    pd.source,
    pd.error_message,
    COUNT(*) as count
FROM pdf_downloads pd
WHERE pd.filtering_query_id = 1
    AND pd.status = 'error'
GROUP BY pd.source, pd.error_message
ORDER BY count DESC;
```

### PDF Resolution Candidates Distribution

```sql
SELECT 
    r.doi_norm,
    json_array_length(pr.candidates) as candidate_count,
    pr.candidates
FROM pdf_resolutions pr
JOIN records r ON pr.record_id = r.id
WHERE pr.filtering_query_id = 1
ORDER BY candidate_count DESC
LIMIT 10;
```

## Performance Testing

### Time Different Concurrency Levels

```bash
# Test with max_concurrent=1
time uv run llm-query-doc-analyser pdfs --query-id 1 --max-concurrent 1

# Test with max_concurrent=5 (default)
time uv run llm-query-doc-analyser pdfs --query-id 1 --max-concurrent 5

# Test with max_concurrent=10
time uv run llm-query-doc-analyser pdfs --query-id 1 --max-concurrent 10
```

Compare times to find optimal concurrency for your system.

## Troubleshooting

### Issue: "No matched records found"

**Check:**
1. Verify filtering query ID exists:
```sql
SELECT * FROM filtering_queries WHERE id = 1;
```

2. Verify there are matched records:
```sql
SELECT COUNT(*) FROM records_filterings 
WHERE filtering_query_id = 1 
    AND match_result = 1
    AND explanation NOT LIKE 'ERROR:%'
    AND explanation NOT LIKE 'WARNING:%';
```

### Issue: All downloads fail with "unavailable"

**Check:**
1. Network connectivity
2. URL accessibility (test in browser)
3. Check error messages in database:
```sql
SELECT url, error_message FROM pdf_downloads 
WHERE filtering_query_id = 1 AND status = 'unavailable'
LIMIT 5;
```

### Issue: "Too large" errors

**Check:**
1. MAX_PDF_SIZE setting in `pdfs/download.py` (default 50 MB)
2. Consider increasing if needed:
```python
MAX_PDF_SIZE = 100 * 1024 * 1024  # 100 MB
```

### Issue: Database locked errors

**Solution:**
Close any other connections to the database or use WAL mode:
```python
import sqlite3
conn = sqlite3.connect("data/cache/records.db")
conn.execute("PRAGMA journal_mode=WAL")
```

## Clean Up

### Remove PDF Downloads for a Query

```sql
DELETE FROM pdf_downloads WHERE filtering_query_id = 1;
DELETE FROM pdf_resolutions WHERE filtering_query_id = 1;
```

### Remove All PDFs

```bash
rm -rf data/pdfs/*
```

### Reset All PDF Data

```sql
DELETE FROM pdf_downloads;
DELETE FROM pdf_resolutions;
```

## Expected File Structure

After successful execution:

```
data/
├── cache/
│   └── records.db          # Database with all tables
└── pdfs/
    ├── ab/
    │   └── cd/
    │       └── abcd123...pdf
    ├── de/
    │   └── f0/
    │       └── def0456...pdf
    └── ...
```

Each PDF is stored with SHA1-based directory structure for distribution.

## Success Criteria

✅ Filter command completes and returns filtering_query_id
✅ PDFs command fetches matched records
✅ PDF resolutions are stored in database
✅ Download attempts are recorded in database
✅ Successfully downloaded PDFs exist in destination directory
✅ Statistics match database counts
✅ No unhandled exceptions
✅ Foreign key relationships maintained
✅ Indexes created for performance

## Regression Testing

To ensure no breaking changes:

1. Test filter command still works independently
2. Test export functionality still works
3. Test database queries still work
4. Verify no impact on existing records table
5. Check filtering_queries and records_filterings tables unchanged
