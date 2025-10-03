# Quick Reference - New Import Fields

## CSV/XLSX Column Mapping

| Input Column Name    | Database Field        | Type   | Required |
|---------------------|-----------------------|--------|----------|
| Title               | title                 | TEXT   | ✓ YES    |
| Publication Date    | pub_date             | TEXT   | Optional |
| DOI                 | doi_norm             | TEXT   | Optional |
| Total Citations     | total_citations      | INTEGER| Optional |
| Average per Year    | citations_per_year   | REAL   | Optional |
| Authors             | authors              | TEXT   | Optional |
| Source Title        | source_title         | TEXT   | Optional |

## Quick Commands

### Import CSV with new fields:
```powershell
uv run llm-query-doc-analyser import path/to/file.csv
```

### Migrate existing database:
```powershell
python src/llm_query_doc_analyser/migrations/add_citation_fields.py
```

### Check database schema:
```powershell
sqlite3 data/cache/records.db "PRAGMA table_info(records);"
```

### View imported citation data:
```powershell
sqlite3 data/cache/records.db "SELECT title, total_citations, authors FROM records WHERE total_citations > 0 LIMIT 5;"
```

## Files Modified

1. ✅ `core/models.py` - Added 4 fields to Record
2. ✅ `core/store.py` - Updated schema + all SQL operations
3. ✅ `io_/load.py` - Added column mapping + type converters
4. ✅ `io_/export.py` - Added new fields to export
5. ✅ `migrations/add_citation_fields.py` - NEW migration script
6. ✅ `docs/sample_import.csv` - NEW sample data

## Data Types

- **total_citations**: Integer (NULL if missing/invalid)
- **citations_per_year**: Float (NULL if missing/invalid)
- **authors**: String (NULL if missing)
- **source_title**: String (NULL if missing)

All fields are optional and nullable for backward compatibility.
