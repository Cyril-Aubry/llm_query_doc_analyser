# Console Logging Control

## Overview
The CLI now supports optional console logging output while always maintaining detailed logs in files. This is useful for automated scripts, CI/CD pipelines, or when you want cleaner terminal output.

## Usage

### Global Flags
These flags are available for all commands and must be specified **before** the command name:

#### `--quiet` / `-q`
Suppress console log output. Logs are still written to the session log file in `logs/`.

```bash
# Quiet mode - no console logs
llm-query-doc-analyser --quiet filter --query "your query"
llm-query-doc-analyser -q import data.csv
```

#### `--verbose` / `-v`
Enable verbose (DEBUG level) logging for detailed troubleshooting.

```bash
# Verbose mode - DEBUG level logs
llm-query-doc-analyser --verbose filter --query "your query"
llm-query-doc-analyser -v enrich
```

### Combining Flags
Flags can be combined (though `--quiet` and `--verbose` are mutually exclusive in effect):

```bash
# This will enable DEBUG level but suppress console output
llm-query-doc-analyser --quiet --verbose filter --query "test"
```

## Examples

### 1. Normal Operation (Default)
Console and file logging enabled:
```bash
llm-query-doc-analyser filter --query "medical imaging" --exclude "3D data"
```

**Output:**
```
2025-10-01 12:30:15 [info     ] application_started            session_id=20251001_123015 log_file=logs/session_20251001_123015.jsonl
2025-10-01 12:30:15 [info     ] filter_started                 query=medical imaging exclude=3D data
2025-10-01 12:30:15 [info     ] openai_client_configured       model=gpt-4
...
Filtering completed:
  Total records processed: 79
  Matched records: 25
  Failed records: 0
  Filtering query ID: 1

Results stored in database: data\cache\records.db
```

### 2. Quiet Mode
Only user-facing output (typer.echo), no logs:
```bash
llm-query-doc-analyser --quiet filter --query "medical imaging" --exclude "3D data"
```

**Output:**
```
Filtering completed:
  Total records processed: 79
  Matched records: 25
  Failed records: 0
  Filtering query ID: 1

Results stored in database: data\cache\records.db
```

**Note:** All detailed logs are still written to `logs/session_20251001_123015.jsonl`

### 3. Verbose Mode
Detailed DEBUG-level console logging:
```bash
llm-query-doc-analyser --verbose filter --query "medical imaging"
```

**Output:**
```
2025-10-01 12:30:15 [info     ] application_started            session_id=20251001_123015
2025-10-01 12:30:15 [debug    ] fetching_records_from_db       path=data\cache\records.db
2025-10-01 12:30:15 [debug    ] llm_query_started             doi=arxiv:2403.06759 title=Average Calibration Error...
2025-10-01 12:30:16 [debug    ] llm_response_received         doi=arxiv:2403.06759 response_content={"match": true...
...
```

### 4. Quiet Mode in Scripts
Perfect for automated workflows:
```bash
# Bash/PowerShell script
llm-query-doc-analyser --quiet import data.csv
llm-query-doc-analyser --quiet enrich
llm-query-doc-analyser --quiet filter --query "relevant papers" --export results.csv

echo "Pipeline complete. Check logs/session_*.jsonl for details."
```

### 5. CI/CD Integration
```yaml
# GitHub Actions example
- name: Filter papers
  run: |
    llm-query-doc-analyser --quiet filter \
      --query "machine learning papers" \
      --exclude "survey papers" \
      --export outputs/filtered.csv
    
    # Upload only the results, logs are artifacts
    echo "Filtered papers exported"
```

## Log File Location
Regardless of console output settings, all logs are always written to:
```
logs/session_YYYYMMDD_HHMMSS.jsonl
```

Example: `logs/session_20251001_123015.jsonl`

## Technical Implementation

### Log Setup
The `setup_logging()` function now accepts a `console_output` parameter:

```python
def setup_logging(
    session_id: str | None = None,
    log_level: str = "INFO",
    console_output: bool = True
) -> Path:
    """
    Configure structured logging to file (JSONL) and optionally to console.
    """
```

### CLI Callback
The global callback processes logging flags before any command:

```python
@app.callback()
def callback(
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress console log output"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose (DEBUG) logging"),
):
    """Initialize application with structured logging."""
    log_level = "DEBUG" if verbose else os.getenv("LOG_LEVEL", "INFO")
    console_output = not quiet
    setup_logging(session_id=session_id, log_level=log_level, console_output=console_output)
```

## Use Cases

### 1. **Development & Debugging**
Use default or verbose mode for full visibility:
```bash
llm-query-doc-analyser --verbose filter --query "test"
```

### 2. **Production Scripts**
Use quiet mode for cleaner output, rely on log files for troubleshooting:
```bash
llm-query-doc-analyser --quiet filter --query "papers" --export results.csv
```

### 3. **Scheduled Jobs**
Cron jobs or Task Scheduler with quiet mode:
```bash
# Linux cron
0 2 * * * /usr/local/bin/llm-query-doc-analyser --quiet enrich >> /var/log/llm-enrich.log 2>&1

# Windows Task Scheduler
llm-query-doc-analyser.exe --quiet filter --query "daily papers"
```

### 4. **CI/CD Pipelines**
Clean pipeline output while preserving detailed logs as artifacts:
```yaml
- run: llm-query-doc-analyser --quiet filter --query "test"
- uses: actions/upload-artifact@v3
  with:
    name: session-logs
    path: logs/
```

### 5. **Interactive Analysis**
Keep console logs for immediate feedback:
```bash
llm-query-doc-analyser filter --query "interactive exploration"
# See live progress and results
```

## Logging Behavior Matrix

| Mode | Console Output | File Output | Log Level | Use Case |
|------|----------------|-------------|-----------|----------|
| Default | ✅ INFO | ✅ INFO | INFO | Normal operation |
| `--quiet` | ❌ None | ✅ INFO | INFO | Scripts, automation |
| `--verbose` | ✅ DEBUG | ✅ DEBUG | DEBUG | Troubleshooting |
| `--quiet --verbose` | ❌ None | ✅ DEBUG | DEBUG | Detailed logs, clean output |
| `LOG_LEVEL=DEBUG` (env) | ✅ DEBUG | ✅ DEBUG | DEBUG | Development |

## Environment Variables

The `LOG_LEVEL` environment variable is still respected:
```bash
# .env file or shell
export LOG_LEVEL=DEBUG

# Then run normally
llm-query-doc-analyser filter --query "test"
```

Priority: `--verbose` flag > `LOG_LEVEL` env var > default (INFO)

## Log File Contents

All session logs contain the same detailed information regardless of console output:
- Timestamps (ISO 8601)
- Log levels
- Logger names
- Event names and context
- Full error tracebacks
- API request/response details
- Database operations
- Processing statistics

Example log entry:
```json
{
  "session_id": "20251001_123015",
  "log_file": "logs/session_20251001_123015.jsonl",
  "event": "filter_started",
  "query": "medical imaging",
  "exclude": "3D data",
  "max_concurrent": 10,
  "level": "info",
  "logger": "llm_query_doc_analyser.cli",
  "timestamp": "2025-10-01T12:30:15.123456Z"
}
```

## Best Practices

1. **Development**: Use default or `--verbose` for immediate feedback
2. **Production**: Use `--quiet` for cleaner output, parse log files as needed
3. **Debugging**: Always check log files in `logs/` directory for full details
4. **Automation**: Use `--quiet` and capture only user-facing output (typer.echo)
5. **Monitoring**: Parse JSONL log files for metrics, errors, and analytics

## Benefits

1. **Cleaner Automation**: Scripts produce only essential output
2. **Flexible Debugging**: Toggle verbosity without code changes
3. **Complete Audit Trail**: File logs always contain full details
4. **CI/CD Friendly**: Clean pipeline output, logs as artifacts
5. **User Choice**: Different modes for different contexts
6. **Backward Compatible**: Default behavior unchanged (console + file logging)

## Migration Notes

### For Existing Users
No changes required. Default behavior is unchanged:
- Console logging: ✅ Enabled (as before)
- File logging: ✅ Enabled (as before)

### For Automation Scripts
Optionally add `--quiet` flag for cleaner output:
```bash
# Before
llm-query-doc-analyser filter --query "test" 2>/dev/null

# After (cleaner)
llm-query-doc-analyser --quiet filter --query "test"
```

## Troubleshooting

### No Logs Appearing
- Check `logs/` directory for session log files
- File logs are always created regardless of `--quiet` flag
- Session ID is printed in first log entry

### Too Verbose
```bash
# Use quiet mode
llm-query-doc-analyser --quiet <command>

# Or set environment variable
export LOG_LEVEL=WARNING
```

### Need More Detail
```bash
# Use verbose mode
llm-query-doc-analyser --verbose <command>

# Or check log files
cat logs/session_20251001_123015.jsonl | jq
```
