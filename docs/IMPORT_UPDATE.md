# Import Command Update - Citation and Bibliographic Fields

## Overview
Updated the import command to support additional bibliographic and citation metadata fields from the input file.

## New Fields Added

### Required Input Columns
The import command now reads and stores the following columns from CSV/XLSX files:

1. **Title** (required) - Paper title
2. **Publication Date** - Publication date
3. **DOI** - Digital Object Identifier
4. **Total Citations** - Total number of citations (integer)
5. **Average per Year** - Average citations per year (float)
6. **Authors** - Author names (string)
7. **Source Title** - Journal/conference name (string)

### Database Schema Changes

Added four new columns to the `records` table:
```sql
total_citations INTEGER
citations_per_year REAL
authors TEXT
source_title TEXT
```

## Files Modified

### 1. `core/models.py`
- Added `total_citations: int | None` field
- Added `citations_per_year: float | None` field
- Added `authors: str | None` field
- Added `source_title: str | None` field

### 2. `core/store.py`
- Updated `CREATE_TABLE_SQL` with new columns
- Updated `insert_record()` to include new fields
- Updated `upsert_record()` UPDATE and INSERT statements to include new fields

### 3. `io_/load.py`
- Added helper functions: `to_int()`, `to_float()`, `to_str()`
- Updated `load_records()` to map new columns from input file
- Handles missing/null values gracefully

### 4. `migrations/add_citation_fields.py` (new)
- Migration script for existing databases
- Adds new columns if they don't exist
- Safe to run multiple times (idempotent)

## Usage

### Importing New Data
```powershell
uv run llm-query-doc-analyser import path/to/your/file.csv
```

Or for Excel:
```powershell
uv run llm-query-doc-analyser import path/to/your/file.xlsx
```

### Expected Input File Format (CSV/XLSX)

| Title | Publication Date | DOI | Total Citations | Average per Year | Authors | Source Title |
|-------|-----------------|-----|-----------------|------------------|---------|--------------|
| Example Paper | 2023-01-15 | 10.1234/example | 42 | 21.0 | Smith J, Doe J | Nature |
| Another Study | 2022-06-20 | 10.5678/study | 15 | 7.5 | Johnson A | Science |

### Migrating Existing Database

If you have an existing database, run the migration:

```powershell
cd src/llm_query_doc_analyser/migrations
python add_citation_fields.py
```

This will add the new columns without losing existing data.

## Backward Compatibility

- All new fields are optional (nullable)
- Existing code continues to work
- Missing columns in input files are handled gracefully (set to NULL)
- Old CSV/XLSX files without these columns can still be imported

## Data Type Handling

The load function includes robust type conversion:
- **Total Citations**: Converted to integer, NULL if invalid
- **Average per Year**: Converted to float, NULL if invalid
- **Authors**: Converted to string, NULL if missing
- **Source Title**: Converted to string, NULL if missing
- **Publication Date**: Supports datetime objects and strings

## Testing

To verify the changes work:

1. Create a test CSV with the new columns
2. Run the import command
3. Query the database to verify fields are populated:

```powershell
# Check database structure
sqlite3 data/cache/records.db "PRAGMA table_info(records);"

# View imported records
sqlite3 data/cache/records.db "SELECT title, total_citations, authors, source_title FROM records LIMIT 5;"
```

## Notes

- The citation metrics (Total Citations, Average per Year) can be used for ranking and filtering in future enhancements
- Author and Source Title fields enable bibliometric analysis
- All fields maintain NULL values for records where data is unavailable
