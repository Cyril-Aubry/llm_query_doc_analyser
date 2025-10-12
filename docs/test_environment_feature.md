# Test Environment Feature - Implementation Guide

**Date**: October 11, 2025  
**Feature**: Test flag for CLI commands  
**Purpose**: Safe separation between production and test data

---

## Overview

This feature introduces a `--test` flag for all CLI commands that creates complete separation between production and test environments. This allows safe testing of new features without risking production data corruption or file conflicts.

## Architecture

### Configuration Module (`core/config.py`)

The new configuration module provides centralized environment management:

- **`EnvironmentConfig` class**: Manages all environment-specific paths
- **Two modes**: `production` (default) and `test`
- **Global singleton**: `_config` instance accessed via `get_config()`
- **Helper functions**: `set_test_mode()`, `set_production_mode()`, `is_test_mode()`

### Path Separation

#### Production Paths (default)
```
data/
├── cache/
│   └── research_articles_management.db
├── pdfs/
├── docx/
└── markdown/
```

#### Test Paths (when --test flag is used)
```
test_data/
├── cache/
│   └── test_research_articles.db
├── pdfs/
├── docx/
└── markdown/
```

## Usage

### Basic Usage

Add the `--test` flag to any command to use test environment:

```powershell
# Import test data
uv run llm-query-doc-analyser --test import data/test_input.xlsx

# Enrich test records
uv run llm-query-doc-analyser --test enrich

# Filter test records
uv run llm-query-doc-analyser --test filter --query "machine learning" --query-id 1

# Download test PDFs
uv run llm-query-doc-analyser --test pdfs --query-id 1

# Retrieve test DOCX files
uv run llm-query-doc-analyser --test batch-docx-retrieve

# Convert test DOCX to markdown
uv run llm-query-doc-analyser --test batch-docx-to-markdown
```

### Combined with Other Flags

The `--test` flag works with all other CLI flags:

```powershell
# Verbose test mode
uv run llm-query-doc-analyser --test --verbose enrich

# Quiet test mode
uv run llm-query-doc-analyser --test --quiet pdfs --query-id 1

# Test mode with custom destination
uv run llm-query-doc-analyser --test pdfs --query-id 1 --dest test_data/custom_pdfs
```

## Safety Features

### 1. Complete Isolation

- **Separate database file**: Test data never touches production database
- **Separate directories**: All file operations use test directories
- **No cross-contamination**: Production and test are completely independent

### 2. Explicit Mode Selection

- **Default is production**: No accidental test mode usage
- **Must specify --test**: Intentional opt-in for test environment
- **Logged in output**: Environment mode shown in application startup logs

### 3. Clear Identification

- **Database file name**: `test_research_articles.db` (vs `research_articles_management.db`)
- **Root directory**: `test_data/` (vs `data/`)
- **Log output**: Shows `mode=test` in initialization logs

## Implementation Details

### Modified Files

1. **`core/config.py`** (NEW)
   - Environment configuration management
   - Path resolution for all data storage
   - Mode switching functionality

2. **`core/store.py`**
   - Updated to use `get_config().db_path` instead of hardcoded `DB_PATH`
   - All database operations now respect environment mode
   - Backward compatible: Legacy `DB_PATH` constant still exists

3. **`pdfs/download.py`**
   - Updated to use `get_config().docx_dir` and `get_config().markdown_dir`
   - All file operations now respect environment mode
   - Backward compatible: Legacy constants still exist

4. **`cli.py`**
   - Added `--test` flag to global callback
   - Calls `set_test_mode()` when flag is present
   - Shows environment info in startup logs
   - Updated all `DB_PATH` references to use `get_config().db_path`

### Code Pattern

**Before** (hardcoded path):
```python
DB_PATH = Path("data/cache/research_articles_management.db")
conn = sqlite3.connect(DB_PATH)
```

**After** (configurable path):
```python
def _get_db_path() -> Path:
    return get_config().db_path

db_path = _get_db_path()
conn = sqlite3.connect(db_path)
```

## Testing Workflow

### Typical Test Workflow

1. **Import test dataset**:
   ```powershell
   uv run llm-query-doc-analyser --test import test_data/sample_articles.xlsx
   ```

2. **Verify import**:
   Check that `test_data/cache/test_research_articles.db` was created

3. **Enrich test data**:
   ```powershell
   uv run llm-query-doc-analyser --test enrich
   ```

4. **Filter test data**:
   ```powershell
   uv run llm-query-doc-analyser --test filter --query "your test query"
   ```

5. **Download test PDFs**:
   ```powershell
   uv run llm-query-doc-analyser --test pdfs --query-id 1
   ```

6. **Verify files**:
   Check that files are in `test_data/pdfs/`, `test_data/docx/`, `test_data/markdown/`

7. **Clean up** (when done testing):
   ```powershell
   Remove-Item -Recurse -Force test_data
   ```

### Integration with pytest

The configuration module is designed to work seamlessly with pytest:

```python
import pytest
from llm_query_doc_analyser.core.config import set_test_mode, set_production_mode

@pytest.fixture(autouse=True)
def use_test_environment():
    """Automatically use test environment for all tests."""
    set_test_mode()
    yield
    set_production_mode()  # Clean up after test
```

## Verification Checklist

Before using test mode in production-like scenarios, verify:

- [ ] Test database is created in `test_data/cache/`
- [ ] Production database remains untouched in `data/cache/`
- [ ] PDF files go to `test_data/pdfs/` with --test
- [ ] DOCX files are searched in `test_data/docx/` with --test
- [ ] Markdown files go to `test_data/markdown/` with --test
- [ ] Application logs show `mode=test` when --test is used
- [ ] Application logs show `mode=production` when --test is NOT used

## Troubleshooting

### Issue: Test data appears in production directory

**Cause**: Forgot to use --test flag  
**Solution**: Always use --test flag for test operations

### Issue: Cannot find test database

**Cause**: Database not initialized with --test flag  
**Solution**: Run any command with --test flag to initialize (e.g., `import`)

### Issue: Test and production data mixed

**Cause**: Switched between modes without cleaning up  
**Solution**: 
1. Delete `test_data/` directory
2. Restart with consistent mode usage

### Issue: Paths not resolving correctly

**Cause**: Using old hardcoded paths in custom code  
**Solution**: Use `get_config()` methods:
- `get_config().db_path` for database
- `get_config().pdf_dir` for PDFs
- `get_config().docx_dir` for DOCX
- `get_config().markdown_dir` for Markdown

## Backward Compatibility

### Legacy Code Support

The implementation maintains backward compatibility:

1. **Legacy constants exist**: `DB_PATH`, `DOCX_DIR`, `MD_OUTPUT_DIR` still defined
2. **No breaking changes**: Existing code continues to work
3. **Migration path**: Code can be gradually updated to use `get_config()`

### External Tools

Tools that directly access data directories should be updated:

**Before**:
```python
from llm_query_doc_analyser.core.store import DB_PATH
```

**After**:
```python
from llm_query_doc_analyser.core.config import get_config
db_path = get_config().db_path
```

## Future Enhancements

Potential improvements for the test environment feature:

1. **Named test environments**: Support multiple test environments (e.g., `--test=integration`, `--test=staging`)
2. **Environment variable configuration**: Allow custom paths via environment variables
3. **Test data fixtures**: Built-in sample datasets for testing
4. **Snapshot comparisons**: Compare test results against known good snapshots
5. **Automatic cleanup**: Optional auto-deletion of test data after test completion

## API Reference

### Functions

#### `get_config() -> EnvironmentConfig`
Get the global configuration instance.

**Returns**: Current environment configuration object

**Example**:
```python
from llm_query_doc_analyser.core.config import get_config

config = get_config()
print(f"Database: {config.db_path}")
print(f"Mode: {config.mode}")
```

#### `set_test_mode() -> None`
Switch to test mode globally.

**Example**:
```python
from llm_query_doc_analyser.core.config import set_test_mode

set_test_mode()
# All subsequent operations use test paths
```

#### `set_production_mode() -> None`
Switch to production mode globally (default).

**Example**:
```python
from llm_query_doc_analyser.core.config import set_production_mode

set_production_mode()
# All subsequent operations use production paths
```

#### `is_test_mode() -> bool`
Check if currently in test mode.

**Returns**: True if in test mode, False otherwise

**Example**:
```python
from llm_query_doc_analyser.core.config import is_test_mode

if is_test_mode():
    print("Running in test mode - data is isolated")
else:
    print("Running in production mode")
```

### EnvironmentConfig Class

#### Properties

- **`mode`**: Current environment mode (`"production"` or `"test"`)
- **`db_path`**: Path to database file
- **`pdf_dir`**: Path to PDF storage directory
- **`docx_dir`**: Path to DOCX storage directory
- **`markdown_dir`**: Path to Markdown storage directory
- **`cache_dir`**: Path to HTTP cache directory

#### Methods

- **`set_mode(mode: Literal["production", "test"])`**: Change environment mode
- **`ensure_directories()`**: Create all necessary directories
- **`get_summary()`**: Get summary of current configuration as dict

## Best Practices

### 1. Always Use Test Mode for Experiments

Never experiment with production data. Always use --test:

```powershell
# ✓ Good: Testing new feature safely
uv run llm-query-doc-analyser --test import new_data.xlsx

# ✗ Bad: Testing with production data
uv run llm-query-doc-analyser import new_data.xlsx
```

### 2. Clean Up Test Data Regularly

Test data can accumulate. Clean up periodically:

```powershell
# Remove all test data
Remove-Item -Recurse -Force test_data

# Or selectively clean subdirectories
Remove-Item -Recurse -Force test_data/pdfs
```

### 3. Document Test Scenarios

Keep notes on what test data represents:

```
test_data/
├── sample_articles.xlsx          # 10 articles for basic testing
├── large_dataset.xlsx            # 1000 articles for performance testing
└── edge_cases.xlsx               # Articles with missing fields, etc.
```

### 4. Use Consistent Test Data

Maintain a set of test fixtures for reproducible testing:

```powershell
# Copy from fixtures
Copy-Item tests/data/fixtures/sample_articles.xlsx test_data/input.xlsx

# Import to test database
uv run llm-query-doc-analyser --test import test_data/input.xlsx
```

### 5. Verify Mode Before Bulk Operations

Always check mode before large operations:

```powershell
# Check the logs to see environment mode
uv run llm-query-doc-analyser --test --verbose enrich
# Look for: "environment=test" in logs
```

## Security Considerations

### Test Data Privacy

- **Sensitive data**: Use anonymized/synthetic data for testing
- **API keys**: Test mode still uses production API keys (consider separate test keys)
- **Credentials**: Never commit test data containing real credentials

### File Permissions

Test directories have same permissions as production:

```powershell
# Secure test data directory
icacls test_data /inheritance:r
icacls test_data /grant:r "$env:USERNAME:(OI)(CI)F"
```

## Performance

### Disk Space

Test mode uses additional disk space:

- **Database**: Separate copy of all records
- **Files**: Separate copies of PDFs, DOCX, markdown files
- **Cache**: Separate HTTP cache

**Estimate**: ~2x production data size when both environments active

### Speed

No performance difference between test and production modes - same code paths, just different directories.

---

## Questions or Issues?

For questions or issues with the test environment feature:

1. Check this documentation
2. Review application logs (look for `environment=test` or `mode=test`)
3. Verify file paths using `get_config().get_summary()`
4. Report issues with full log context

---

**Last Updated**: October 11, 2025  
**Version**: 1.0.0  
**Status**: Stable
