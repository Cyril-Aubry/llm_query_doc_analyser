# Filtering Database Refactoring

## Overview
Refactored the filter command to store filtering results in the database instead of only exporting to files. This enables tracking of filtering queries, their parameters, and individual record filtering results over time.

## Database Schema Changes

### New Tables

#### 1. `filtering_queries`
Stores metadata about each filtering session.

```sql
CREATE TABLE IF NOT EXISTS filtering_queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    query TEXT NOT NULL,
    exclude_criteria TEXT,
    llm_model TEXT NOT NULL,
    max_concurrent INTEGER,
    total_records INTEGER,
    matched_count INTEGER,
    failed_count INTEGER
);
```

**Fields:**
- `id`: Unique identifier for the filtering query
- `timestamp`: ISO 8601 timestamp when the filtering was initiated
- `query`: The inclusive criteria query string
- `exclude_criteria`: The exclusive criteria string
- `llm_model`: The OpenAI model used (e.g., "gpt-4", "gpt-5-nano")
- `max_concurrent`: Maximum number of concurrent API calls
- `total_records`: Total number of records processed
- `matched_count`: Number of records that matched the criteria
- `failed_count`: Number of records that failed processing

#### 2. `records_filterings`
Stores individual filtering results for each record in a filtering session.

```sql
CREATE TABLE IF NOT EXISTS records_filterings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL,
    filtering_query_id INTEGER NOT NULL,
    match_result INTEGER NOT NULL,
    explanation TEXT,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE,
    FOREIGN KEY (filtering_query_id) REFERENCES filtering_queries(id) ON DELETE CASCADE
);
```

**Fields:**
- `id`: Unique identifier for the filtering result
- `record_id`: Foreign key to the `records` table
- `filtering_query_id`: Foreign key to the `filtering_queries` table
- `match_result`: Boolean (0/1) indicating if the record matched
- `explanation`: LLM's explanation for the match/non-match decision
- `timestamp`: ISO 8601 timestamp of the filtering

### Indexes
Added indexes for efficient querying:
- `idx_records_filterings_record_id` on `records_filterings(record_id)`
- `idx_records_filterings_filtering_query_id` on `records_filterings(filtering_query_id)`
- `idx_filtering_queries_timestamp` on `filtering_queries(timestamp)`

## New Functions in `core/store.py`

### `create_filtering_query()`
Creates a new filtering query record at the start of a filtering session.

```python
def create_filtering_query(
    timestamp: str,
    query: str,
    exclude_criteria: str,
    llm_model: str,
    max_concurrent: int,
) -> int
```

**Returns:** The ID of the created filtering query record.

### `update_filtering_query_stats()`
Updates statistics for a filtering query after processing is complete.

```python
def update_filtering_query_stats(
    filtering_query_id: int,
    total_records: int,
    matched_count: int,
    failed_count: int,
)
```

### `insert_filtering_result()`
Inserts a single filtering result for a record.

```python
def insert_filtering_result(
    record_id: int,
    filtering_query_id: int,
    match_result: bool,
    explanation: str,
    timestamp: str,
)
```

### `batch_insert_filtering_results()`
Batch inserts filtering results for efficiency (used by the filter command).

```python
def batch_insert_filtering_results(
    results: list[tuple[int, int, bool, str, str]],
)
```

**Parameters:** List of tuples (record_id, filtering_query_id, match_result, explanation, timestamp)

### `get_filtering_results()`
Retrieves all filtering results for a given filtering query.

```python
def get_filtering_results(filtering_query_id: int) -> list[dict]
```

**Returns:** List of dictionaries containing filtering results with record details.

### `get_record_id_by_doi()`
Helper function to get record ID by normalized DOI.

```python
def get_record_id_by_doi(doi_norm: str) -> int | None
```

## Changes to `cli.py`

### Updated `filter` Command
The filter command now:
1. Creates a filtering query record at the start
2. Processes records and collects results
3. Batch inserts all filtering results into the database
4. Updates filtering query statistics
5. Optionally exports matched records to a file (using `--export` flag)

**New Signature:**
```python
@app.command()
def filter(
    query: str = typer.Option(..., "--query", "-q", help="Query string for filtering records"),
    exclude: str = "",
    max_concurrent: int = typer.Option(10, help="Maximum concurrent API calls"),
    export_path: Path | None = typer.Option(None, "--export", "-e", help="Optional export path for filtered records"),
):
```

**Key Changes:**
- `export` parameter renamed to `export_path` and made optional
- Results are always stored in the database
- Export to file is now optional (only when `--export` is provided)
- Displays filtering statistics and filtering query ID in the output

## Changes to `filter_rank/prompts.py`

### Updated `filter_records_with_llm()`
Modified to return filtering results instead of filtered records.

**New Signature:**
```python
async def filter_records_with_llm(
    records: list[Record],
    query: str,
    exclude: str,
    api_key: str,
    model_name: str,
    max_concurrent: int = 10,
    filtering_query_id: int | None = None,
    timestamp: str | None = None,
) -> list[tuple[int, bool, str] | None]:
```

**Returns:** List of tuples (record_id, match_result, explanation) or None for failed records.

**Key Changes:**
- Returns record IDs instead of full Record objects
- Returns match results and explanations for database storage
- Added optional `filtering_query_id` and `timestamp` parameters for future use

## Usage Examples

### 1. Basic Filtering (Results to Database Only)
```bash
uv run llm-query-doc-analyser filter \
  --query "model description for image semantic segmentation on 2D image data only" \
  --exclude "3D volumetric data"
```

**Output:**
```
Filtering completed:
  Total records processed: 79
  Matched records: 15
  Failed records: 0
  Filtering query ID: 1

Results stored in database: data\cache\records.db
```

### 2. Filtering with Export
```bash
uv run llm-query-doc-analyser filter \
  --query "deep learning for medical imaging" \
  --exclude "non-medical applications" \
  --export outputs/filtered.csv
```

**Output:**
```
Filtering completed:
  Total records processed: 79
  Matched records: 25
  Failed records: 0
  Filtering query ID: 2

Results stored in database: data\cache\records.db
  Exported 25 matched records to: outputs/filtered.csv
```

## Querying Filtering Results

### Get All Filtering Queries
```sql
SELECT * FROM filtering_queries ORDER BY timestamp DESC;
```

### Get Results for a Specific Filtering Query
```sql
SELECT 
    r.doi_norm,
    r.title,
    rf.match_result,
    rf.explanation,
    rf.timestamp
FROM records_filterings rf
JOIN records r ON rf.record_id = r.id
WHERE rf.filtering_query_id = 1
ORDER BY rf.match_result DESC, r.title;
```

### Get Filtering History for a Specific Record
```sql
SELECT 
    fq.timestamp,
    fq.query,
    fq.llm_model,
    rf.match_result,
    rf.explanation
FROM records_filterings rf
JOIN filtering_queries fq ON rf.filtering_query_id = fq.id
JOIN records r ON rf.record_id = r.id
WHERE r.doi_norm = 'arxiv:2403.06759'
ORDER BY fq.timestamp DESC;
```

### Get Match Statistics by Query
```sql
SELECT 
    id,
    timestamp,
    query,
    llm_model,
    total_records,
    matched_count,
    failed_count,
    ROUND(100.0 * matched_count / total_records, 2) as match_percentage
FROM filtering_queries
ORDER BY timestamp DESC;
```

## Database Transactions and Best Practices

### Transaction Safety
All database operations use context managers (`with get_conn() as conn`) to ensure:
- Automatic commit on success
- Automatic rollback on error
- Proper connection cleanup

### Batch Operations
The implementation uses batch inserts for filtering results to:
- Minimize database I/O
- Improve performance for large datasets
- Ensure atomicity of filtering session results

### Foreign Key Constraints
- `ON DELETE CASCADE` ensures referential integrity
- Deleting a filtering query automatically deletes its results
- Deleting a record automatically deletes its filtering results

## Migration Guide

### For Existing Users
1. Run `init_db()` to create new tables (handled automatically on first use)
2. Update any scripts that relied on `filter` always exporting to a file
3. Use `--export` flag if you want to continue exporting to files

### Database Schema Evolution
The new tables are created with `IF NOT EXISTS`, so:
- Safe to run on existing databases
- No data migration required
- Existing `records` table is unchanged

## Benefits

1. **Audit Trail**: Complete history of all filtering operations
2. **Reproducibility**: Can track which records matched which queries
3. **Comparison**: Can compare results across different queries or models
4. **Analysis**: Can analyze LLM explanations and match patterns
5. **Efficiency**: No need to re-process records to query filtering results
6. **Flexibility**: Can still export to files when needed

## Future Enhancements

Potential improvements for future versions:
1. Add `filtering_query` parameter to specify model temperature, max_tokens, etc.
2. Create views for common queries (e.g., most matched records, query comparison)
3. Add CLI command to query filtering history
4. Export filtering results directly from database with filtering query context
5. Track API costs and response times per filtering session
6. Support re-running filtering queries with different parameters
