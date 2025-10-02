# Structlog Migration Summary

## Overview

The project has been migrated from Python's standard `logging` library to `structlog` for structured, machine-readable logging. This migration provides better observability, easier log analysis, and per-session log files.

## Changes Made

### 1. Enhanced `utils/log.py`

**New Features:**
- Per-session log files in `logs/` directory
- Configurable log levels via `LOG_LEVEL` environment variable
- JSON Lines (`.jsonl`) format for easy parsing
- Session-based log file naming: `session_YYYYMMDD_HHMMSS.jsonl`
- Structured processors for consistent log formatting

**Key Functions:**
- `setup_logging(session_id, log_level)`: Initialize structlog with file and console output
- `get_logger(name)`: Get a logger instance for a specific module

### 2. Updated `cli.py`

**Changes:**
- Added application callback to initialize logging at startup
- Added structured logging to all CLI commands:
  - `import_`: Logs import start/completion with record counts
  - `enrich`: Logs enrichment start/completion with sources
  - `filter`: Logs filtering operations, OpenAI API calls, and results
  - `pdfs`: Logs download operations with success/failure counts
  - `export`: Logs export operations with format and record counts

**Log Events:**
- `application_started`: When CLI starts
- `import_started` / `import_completed`: Data import operations
- `enrich_started` / `enrich_completed`: Enrichment operations
- `filter_started` / `filter_completed`: Filtering operations
- `pdf_download_started` / `pdf_download_completed`: PDF downloads
- `export_started` / `export_completed`: Data export operations

### 3. Updated `enrich/orchestrator.py`

**Changes:**
- Replaced `logging` with `structlog`
- Removed `logging.basicConfig()` call
- Added structured logging for enrichment operations

**Log Events:**
- `enrichment_started`: When enrichment begins for a record
- `fetched_arxiv`: After fetching from arXiv
- `fetched_semanticscholar`: After fetching from Semantic Scholar
- `enrichment_completed`: When enrichment finishes

### 4. Updated `io_/load.py`

**Changes:**
- Added structured logging for data loading operations

**Log Events:**
- `loading_records`: When starting to load records
- `missing_title_column`: Error when Title column is missing
- `records_loaded`: When records are successfully loaded

### 5. Updated `io_/export.py`

**Changes:**
- Added structured logging for export operations

**Log Events:**
- `exporting_records`: When starting export
- `unsupported_export_format`: Error for invalid format
- `export_completed`: When export finishes

### 6. Updated `core/store.py`

**Changes:**
- Added structured logging for database operations

**Log Events:**
- `initializing_database` / `database_initialized`: DB initialization
- `fetching_records_from_db` / `records_fetched`: Record retrieval
- `upserting_record`: Record upsert operations
- `inserting_new_record` / `record_inserted`: New record insertion
- `record_updated`: Existing record update

### 7. Configuration Files

**`.env.example`:**
- Added `LOG_LEVEL` configuration option (default: INFO)

**`.gitignore`:**
- Added `logs/` directory
- Added `*.log` and `*.jsonl` patterns

### 8. Documentation

**`logs/README.md`:**
- Created comprehensive documentation for log file format
- Included example queries for log analysis with `jq`
- Documented log entry structure and retention considerations

## Log File Structure

Each log entry is a JSON object with the following standard fields:

```json
{
  "event": "event_name",
  "timestamp": "2025-10-01T14:30:45.123456",
  "level": "info",
  "logger": "module.name",
  // Additional context-specific fields
}
```

## Usage

### Setting Log Level

In your `.env` file:

```bash
LOG_LEVEL=DEBUG  # Options: DEBUG, INFO, WARNING, ERROR, CRITICAL
```

### Viewing Logs

Logs are stored in the `logs/` directory with one file per session:

```bash
# View latest session log
tail -f logs/session_*.jsonl

# Pretty-print JSON logs
cat logs/session_20251001_143045.jsonl | jq .

# Filter specific events
cat logs/session_*.jsonl | jq 'select(.event == "enrichment_completed")'

# Count errors
cat logs/session_*.jsonl | jq 'select(.level == "error")' | wc -l
```

### Analyzing Logs Programmatically

```python
import json

# Read and parse log file
with open('logs/session_20251001_143045.jsonl') as f:
    for line in f:
        entry = json.loads(line)
        if entry['level'] == 'error':
            print(f"{entry['timestamp']}: {entry['event']}")
```

## Benefits

1. **Structured Data**: All logs are JSON objects, making them easy to parse and analyze
2. **Session Tracking**: Each CLI invocation gets its own log file for isolation
3. **Machine Readable**: Easy integration with log aggregation tools (ELK, Splunk, etc.)
4. **Contextual Information**: Each log entry includes relevant context (DOI, paths, counts)
5. **Debug Support**: Detailed debug logs available when LOG_LEVEL=DEBUG
6. **Performance**: Minimal overhead with async-friendly design

## Migration Checklist

- [x] Removed all `import logging` statements
- [x] Removed all `logging.basicConfig()` calls
- [x] Replaced all `logging.debug()`, `logging.info()`, etc. with structlog equivalents
- [x] Added per-session log files
- [x] Added LOG_LEVEL configuration
- [x] Updated .env.example
- [x] Updated .gitignore
- [x] Created logs/README.md
- [x] Added logging to all CLI commands
- [x] Added logging to core modules (store, load, export)
- [x] Added logging to enrichment orchestrator
- [x] Verified no lint errors
- [x] Created migration documentation

## Next Steps

Consider these optional enhancements:

1. **Log Rotation**: Implement automatic log rotation/cleanup
2. **Remote Logging**: Send logs to a centralized logging service
3. **Performance Metrics**: Add timing information to log entries
4. **Error Tracking**: Integrate with error tracking services (Sentry, Rollbar)
5. **Log Dashboard**: Create a simple web UI for viewing/searching logs
6. **Alerting**: Set up alerts for critical errors or anomalies

## Testing

To verify the logging implementation:

1. Run any CLI command and check that a log file is created in `logs/`
2. Set `LOG_LEVEL=DEBUG` and verify detailed logs are captured
3. Use `jq` to verify log entries are valid JSON
4. Check that session IDs are unique per invocation
5. Verify no standard logging imports remain in the codebase
