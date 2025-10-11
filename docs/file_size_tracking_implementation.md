# File Size Tracking Implementation

**Date:** 2025-01-11  
**Status:** Completed  
**Author:** GitHub Copilot

## Summary

Updated the database schema and application logic to track file sizes (in bytes) for all file artifacts: PDF downloads, DOCX conversions, and Markdown variants. This enables future analysis of storage requirements, file size distributions, and optimization decisions.

---

## Database Schema Changes

### 1. PDF Downloads Table (`pdf_downloads`)

**Added Column:**
- `file_size_bytes INTEGER` - Size of the downloaded PDF file in bytes

**Purpose:** Track the actual size of successfully downloaded PDF files for storage planning and analysis.

**Location:** `src/llm_query_doc_analyser/core/store.py:100-112`

### 2. DOCX Versions Table (`docx_versions`)

**Added Column:**
- `file_size_bytes INTEGER` - Size of the DOCX file in bytes

**Purpose:** Track DOCX file sizes for storage management and conversion planning.

**Location:** `src/llm_query_doc_analyser/core/store.py:114-122`

### 3. Markdown Versions Table (`markdown_versions`)

**Added Column:**
- `file_size_bytes INTEGER` - Size of the Markdown file in bytes

**Purpose:** Track markdown file sizes separately for both variants (with and without images) to understand storage impact of different conversion options.

**Location:** `src/llm_query_doc_analyser/core/store.py:124-135`

---

## Migration Logic

### Database Migration Function

**Function:** `_migrate_add_file_size_columns()`  
**Location:** `src/llm_query_doc_analyser/core/store.py:267-295`

**Behavior:**
- Automatically adds `file_size_bytes` columns to existing tables if they don't exist
- Uses SQLite's `PRAGMA table_info()` to check for column existence before migration
- Executed automatically during `init_db()` to ensure backward compatibility
- Idempotent: safe to run multiple times

**Migration Steps:**
1. Checks `pdf_downloads` table for `file_size_bytes` column
2. Checks `docx_versions` table for `file_size_bytes` column
3. Checks `markdown_versions` table for `file_size_bytes` column
4. Adds missing columns via `ALTER TABLE` statements
5. Logs all migration activities

---

## Updated Functions

### 1. PDF Download Logic

#### Function: `record_pdf_download_attempt()`
**Location:** `src/llm_query_doc_analyser/core/store.py:1038-1137`

**Changes:**
- Added `file_size_bytes: int | None = None` parameter
- Updated INSERT statement to include `file_size_bytes` column
- Updated UPDATE statement to include `file_size_bytes` column
- Enhanced logging to include file size information

**Usage Pattern:**
```python
record_pdf_download_attempt(
    record_id=123,
    url="https://...",
    source="unpaywall",
    status="downloaded",
    download_attempt_datetime="2025-01-11T...",
    pdf_local_path="/path/to/file.pdf",
    sha1="abc123...",
    final_url="https://...",
    file_size_bytes=1048576,  # NEW: File size in bytes
    error_message=None,
)
```

#### Function: `download_pdf()`
**Location:** `src/llm_query_doc_analyser/pdfs/download.py:85-127`

**Changes:**
- After writing PDF to disk, calculates actual file size using `pdf_path.stat().st_size`
- Returns `file_size_bytes` in the result dictionary
- Uses actual file size (not Content-Length header) for accuracy

**Specific Logic:**
```python
# Download and save
sha1 = sha1_bytes(resp.content)
pdf_path = dest_dir / f"{sha1}.pdf"
pdf_path.write_bytes(resp.content)

# Get actual file size from written file for accuracy
file_size_bytes = pdf_path.stat().st_size

log.info("pdf_downloaded", url=url, sha1=sha1, size=file_size_bytes, source=source)
return {
    "status": "downloaded",
    "path": str(pdf_path),
    "sha1": sha1,
    "final_url": str(resp.url),
    "url": url,
    "file_size_bytes": file_size_bytes,  # NEW
}
```

#### CLI Integration
**Location:** `src/llm_query_doc_analyser/cli.py:675-715`

**Changes:**
- Updated both successful and non-successful download recording to pass `file_size_bytes`
- Extracts `file_size_bytes` from download result dictionary
- Logs file size information for monitoring

---

### 2. DOCX Retrieval Logic

#### Function: `insert_docx_version()`
**Location:** `src/llm_query_doc_analyser/core/store.py:1140-1175`

**Changes:**
- Added `file_size_bytes: int | None = None` parameter
- Updated INSERT statement to include `file_size_bytes` column
- Enhanced docstring with parameter documentation
- Added structured logging for file size

**Usage Pattern:**
```python
insert_docx_version(
    record_id=123,
    docx_local_path="/path/to/file.docx",
    retrieved_attempt_datetime="2025-01-11T...",
    file_size_bytes=2097152,  # NEW: File size in bytes
    error_message=None,
)
```

#### Helper Function: `_retrieve_docx_for_record()`
**Location:** `src/llm_query_doc_analyser/cli.py:832-867`

**Changes:**
- Calculates file size using `docx_found.stat().st_size` when DOCX is found
- Passes `file_size_bytes` to `insert_docx_version()`
- Sets `file_size_bytes=None` when DOCX is not found
- Logs file size in success messages

**Specific Logic:**
```python
if docx_found:
    # Calculate file size
    file_size_bytes = docx_found.stat().st_size
    
    docx_id = insert_docx_version(
        record_id=record_id,
        docx_local_path=str(docx_found),
        retrieved_attempt_datetime=now,
        file_size_bytes=file_size_bytes,  # NEW
        error_message=None,
    )
    log.info("docx_retrieve_success", ..., file_size_bytes=file_size_bytes)
```

---

### 3. Markdown Conversion Logic

#### Function: `insert_markdown_version()`
**Location:** `src/llm_query_doc_analyser/core/store.py:1178-1213`

**Changes:**
- Added `file_size_bytes: int | None = None` parameter
- Updated INSERT statement to include `file_size_bytes` column
- Enhanced docstring with parameter documentation
- Added structured logging for file size and variant

**Usage Pattern:**
```python
insert_markdown_version(
    record_id=123,
    docx_version_id=456,
    variant="no_images",
    md_local_path="/path/to/file-no images.md",
    created_datetime="2025-01-11T...",
    file_size_bytes=524288,  # NEW: File size in bytes
    error_message=None,
)
```

#### Helper Function: `_convert_docx_to_markdown_for_record()`
**Location:** `src/llm_query_doc_analyser/cli.py:1042-1101`

**Changes:**
- Calculates file size for **both** markdown variants (no_images and with_images)
- Uses `Path.stat().st_size` to get actual file size after conversion
- Handles file existence checking before accessing size
- Passes `file_size_bytes` to `insert_markdown_version()` for both variants
- Sets `file_size_bytes=None` on conversion failure
- Logs file size for both successful conversions

**Specific Logic (no_images variant):**
```python
if conv.get("md_no_images"):
    md_path_str = conv.get("md_no_images")
    md_path = Path(md_path_str) if md_path_str else None
    file_size_bytes = md_path.stat().st_size if md_path and md_path.exists() else None
    
    insert_markdown_version(
        record_id=record_id,
        docx_version_id=docx_version_id,
        variant="no_images",
        md_local_path=md_path_str,
        created_datetime=now,
        file_size_bytes=file_size_bytes,  # NEW
    )
    log.info("markdown_no_images_created", ..., file_size_bytes=file_size_bytes)
```

**Same logic applies to with_images variant**

---

## Data Flow Summary

### PDF Download Flow
1. `download_pdf()` downloads PDF and calculates file size from written file
2. Returns file size in result dictionary
3. CLI `pdfs` command extracts file size from result
4. CLI calls `record_pdf_download_attempt()` with `file_size_bytes`
5. Database stores file size in `pdf_downloads.file_size_bytes`

### DOCX Retrieval Flow
1. CLI `docx_retrieve` command finds DOCX file
2. `_retrieve_docx_for_record()` calculates file size using `stat().st_size`
3. Calls `insert_docx_version()` with `file_size_bytes`
4. Database stores file size in `docx_versions.file_size_bytes`

### Markdown Conversion Flow
1. CLI `docx_to_markdown` command converts DOCX to markdown
2. `_convert_docx_to_markdown_for_record()` creates both variants
3. For each successful variant, calculates file size using `stat().st_size`
4. Calls `insert_markdown_version()` twice (once per variant) with respective `file_size_bytes`
5. Database stores sizes in `markdown_versions.file_size_bytes` (one row per variant)

---

## Benefits

### 1. Storage Planning
- Track actual disk usage for each file type
- Identify large files that may need optimization
- Forecast storage requirements based on growth trends

### 2. Performance Analysis
- Correlate file sizes with download/conversion times
- Identify bottlenecks in processing pipelines
- Optimize for different file size ranges

### 3. Quality Assessment
- Detect unusually small/large files that may indicate issues
- Compare file sizes across different sources
- Validate conversion quality (e.g., markdown size vs source DOCX)

### 4. Cost Optimization
- Calculate storage costs based on actual file sizes
- Identify redundant or unnecessary files
- Prioritize which articles to process based on file size constraints

### 5. Reporting & Analytics
- Generate statistics on file size distributions
- Track trends over time
- Compare efficiency of different PDF sources

---

## Testing Recommendations

### 1. Database Migration Testing
```python
# Test on existing database without file_size_bytes columns
init_db()  # Should add columns automatically

# Verify columns exist
with get_conn() as conn:
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(pdf_downloads)")
    columns = [col[1] for col in cur.fetchall()]
    assert "file_size_bytes" in columns
```

### 2. PDF Download Testing
```python
# Test file size tracking
result = await download_pdf(candidate, dest_dir)
assert "file_size_bytes" in result
assert result["file_size_bytes"] > 0
```

### 3. DOCX Retrieval Testing
```python
# Test DOCX file size tracking
result = _retrieve_docx_for_record(record_id, pdf_path)
assert result["success"] == True
# Verify file size was stored in database
```

### 4. Markdown Conversion Testing
```python
# Test markdown file size tracking
result = _convert_docx_to_markdown_for_record(record_id, docx_path)
assert result["no_images_success"] == True
assert result["with_images_success"] == True
# Verify both file sizes were stored in database
```

---

## Future Enhancements

### 1. Size-based Filtering
- Add CLI options to filter by file size ranges
- Skip processing files above/below certain thresholds

### 2. Compression Analysis
- Track compression ratios (PDF → DOCX → Markdown)
- Identify opportunities for storage optimization

### 3. Size Statistics Commands
- Add CLI command to show file size statistics
- Generate reports on storage usage by source, date, etc.

### 4. Backfill Utility
- Create utility to backfill file sizes for existing records
- Scan existing files and update database with sizes

### 5. Alerts & Monitoring
- Set up alerts for unusually large/small files
- Monitor storage growth rate

---

## Breaking Changes

**None.** All changes are backward compatible:
- New columns allow NULL values
- Migration runs automatically
- Existing code continues to work without passing file sizes
- Old records will have `file_size_bytes = NULL`

---

## Files Modified

1. `src/llm_query_doc_analyser/core/store.py` - Database schema and functions
2. `src/llm_query_doc_analyser/pdfs/download.py` - PDF download logic
3. `src/llm_query_doc_analyser/cli.py` - CLI integration for all file types

---

## Rollback Plan

If needed, the changes can be rolled back safely:

1. Old code will continue to work (columns allow NULL)
2. To remove columns (if desired):
```sql
-- SQLite doesn't support DROP COLUMN directly
-- Would need to recreate tables without the column
-- Not recommended unless absolutely necessary
```

3. Better approach: Keep columns, they don't harm existing functionality

---

## Questions or Issues?

Contact: Project maintainers  
Documentation: This file + inline code comments + docstrings
