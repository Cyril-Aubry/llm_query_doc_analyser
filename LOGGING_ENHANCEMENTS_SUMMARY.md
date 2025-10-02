# Logging Enhancements Summary

## What Changed

### 1. Console Output Control
Added global CLI flags to control console logging behavior:

- `--quiet` / `-q`: Suppress console log output (logs still written to file)
- `--verbose` / `-v`: Enable DEBUG-level logging

### 2. Updated Functions

#### `utils/log.py`
```python
def setup_logging(
    session_id: str | None = None,
    log_level: str = "INFO",
    console_output: bool = True  # NEW PARAMETER
) -> Path:
```

#### `cli.py`
```python
@app.callback()
def callback(
    quiet: bool = typer.Option(False, "--quiet", "-q", ...),  # NEW
    verbose: bool = typer.Option(False, "--verbose", "-v", ...),  # NEW
):
```

## Usage Examples

### Default (unchanged)
```bash
llm-query-doc-analyser filter --query "test"
# Console: ✅ INFO logs + user output
# File:    ✅ INFO logs
```

### Quiet Mode
```bash
llm-query-doc-analyser --quiet filter --query "test"
# Console: ❌ No logs, only user output (typer.echo)
# File:    ✅ INFO logs
```

### Verbose Mode
```bash
llm-query-doc-analyser --verbose filter --query "test"
# Console: ✅ DEBUG logs + user output
# File:    ✅ DEBUG logs
```

### Quiet + Verbose
```bash
llm-query-doc-analyser --quiet --verbose filter --query "test"
# Console: ❌ No logs, only user output
# File:    ✅ DEBUG logs (useful for detailed troubleshooting without console clutter)
```

## Key Features

1. **Always Log to File**: Logs are always written to `logs/session_*.jsonl` regardless of console settings
2. **User Output Preserved**: `typer.echo()` output (like filtering results) is always shown
3. **Backward Compatible**: Default behavior unchanged (console + file logging)
4. **Flexible**: Choose verbosity and output destination independently

## Benefits

- **Automation**: Clean output for scripts and CI/CD pipelines
- **Debugging**: Full detailed logs always available in files
- **User Choice**: Different modes for different contexts
- **Performance**: Slightly faster when console output disabled

## Log File Location
All logs always written to:
```
logs/session_YYYYMMDD_HHMMSS.jsonl
```

## Documentation
- Full guide: `CONSOLE_LOGGING_CONTROL.md`
- Filtering changes: `FILTERING_DATABASE_REFACTOR.md`
