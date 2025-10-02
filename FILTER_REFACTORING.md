# Filter Command Refactoring Summary

## Overview

The `filter` command has been completely refactored to use asynchronous parallelized OpenAI API calls for improved efficiency and performance. This migration replaces the synchronous, sequential processing with a modern async architecture.

## Changes Made

### 1. New Async LLM Filter Module (`filter_rank/prompts.py`)

**Complete rewrite** of the prompts.py module to include:

#### Core Functions

1. **`build_filter_prompt(query, exclude, title, abstract)`**
   - Constructs system and user prompts for LLM evaluation
   - Formats criteria and article content appropriately
   - Returns structured prompt dictionary

2. **`query_llm_for_record(client, rec, query, exclude, model_name)`**
   - Async function to query OpenAI API for a single record
   - Uses `AsyncOpenAI` client for non-blocking calls
   - Includes retry logic with exponential backoff (tenacity)
   - Returns `(record, is_match, explanation)` tuple
   - Comprehensive error handling and logging

3. **`filter_records_with_llm(records, query, exclude, api_key, model_name, max_concurrent=10)`**
   - Main entry point for async batch filtering
   - Processes multiple records concurrently
   - Uses semaphore for rate limiting
   - Returns list of filtered records with provenance

#### Key Features

- ✅ **Async/Await Pattern**: Non-blocking API calls
- ✅ **Concurrent Processing**: Process multiple records simultaneously
- ✅ **Rate Limiting**: Semaphore-based concurrency control
- ✅ **Retry Logic**: Automatic retry with exponential backoff
- ✅ **Structured Logging**: Comprehensive debug/info/warning logs
- ✅ **Error Recovery**: Graceful handling of individual failures
- ✅ **JSON Parsing**: Robust parsing with fallback handling

### 2. Refactored CLI Filter Command (`cli.py`)

**Before (Synchronous):**
```python
for rec in records:
    # Sequential API calls - SLOW
    response = client.chat.completions.create(...)
    # Process response
    if is_match:
        filtered_records.append(rec)
```

**After (Asynchronous):**
```python
from .filter_rank.prompts import filter_records_with_llm

# Single async call handles all records with parallelization
filtered_records = asyncio.run(
    filter_records_with_llm(
        records=records,
        query=query,
        exclude=exclude,
        api_key=openai_api_key,
        model_name=model_name,
        max_concurrent=max_concurrent,
    )
)
```

**Changes:**
- Removed synchronous for-loop processing
- Removed `OpenAI` import (now uses `AsyncOpenAI` in prompts.py)
- Removed unused `json` import
- Added `max_concurrent` CLI option for tuning performance
- Delegated all LLM logic to `filter_rank.prompts` module
- Simplified error handling (handled in filter module)

### 3. Updated filter_rank Package Structure

#### New `__init__.py`
- Proper package initialization
- Exports main functions: `filter_records_with_llm`, `query_llm_for_record`, `build_filter_prompt`
- Documents deprecated modules

#### Deprecated Modules (marked but kept for compatibility)
- `rules.py` - Rule-based regex filtering
- `embed.py` - Embedding-based similarity
- `rerank.py` - Score combination utilities

These are marked as deprecated in docstrings but retained for backward compatibility.

#### New Documentation
- `filter_rank/README.md` - Comprehensive package documentation
  - Usage examples
  - Performance tuning guide
  - Migration guide
  - Error handling reference
  - Configuration details

### 4. CLI Enhancements

**New Option:**
```bash
--max-concurrent INTEGER    Maximum concurrent API calls (default: 10)
```

**Usage:**
```bash
# Use default concurrency (10)
llm-query-doc-analyser filter --query "..." --exclude "..."

# Increase concurrency for faster processing
llm-query-doc-analyser filter --query "..." --exclude "..." --max-concurrent 20

# Reduce concurrency to respect rate limits
llm-query-doc-analyser filter --query "..." --exclude "..." --max-concurrent 5
```

## Performance Improvements

### Before (Sequential)
- **1 record** = ~2 seconds (API latency)
- **100 records** = ~200 seconds (3.3 minutes)
- **1000 records** = ~2000 seconds (33 minutes)

### After (Parallel with max_concurrent=10)
- **1 record** = ~2 seconds (same latency)
- **100 records** = ~20 seconds (10x speedup)
- **1000 records** = ~200 seconds (10x speedup)

**Speedup Factor:** Up to **10x faster** with default settings, scalable based on `max_concurrent` value.

## Technical Architecture

### Async Flow

```
CLI filter command
    ↓
filter_records_with_llm()
    ↓
Create AsyncOpenAI client
    ↓
Create semaphore (max_concurrent)
    ↓
asyncio.gather() - Process all records
    ↓ ↓ ↓ ↓ ↓ (concurrent)
query_llm_for_record() × N records
    ↓
Parse responses + update provenance
    ↓
Return filtered records
```

### Error Handling Strategy

1. **Network/API Errors**: Retry with exponential backoff (tenacity)
2. **Individual Failures**: Log and continue processing other records
3. **JSON Parse Failures**: Fallback to text-based parsing
4. **Rate Limits**: Semaphore prevents exceeding limits
5. **Validation Errors**: Early validation before API calls

## Dependencies

### Required (already in project)
- `asyncio` (stdlib)
- `openai>=2.0.0` (AsyncOpenAI client)
- `tenacity` (retry logic)
- `structlog` (logging)

### No New Dependencies Added
All required packages were already in the project dependencies.

## Logging Enhancements

New structured log events:

- `llm_query_started`: Record queued for filtering
- `llm_response_received`: Raw API response
- `llm_response_parsed`: Successfully parsed result
- `llm_response_parse_failed`: JSON parsing failure with fallback
- `llm_query_failed`: Unrecoverable error for a record
- `llm_filtering_started`: Batch filtering initiated
- `llm_filtering_completed`: Batch filtering finished with stats

All logs include relevant context (DOI, title, error details, etc.).

## Backward Compatibility

### Breaking Changes
None - the CLI interface remains the same with one optional addition.

### Additions
- `--max-concurrent` option (default: 10, maintains similar behavior)

### Deprecations
- Rule-based filtering (rules.py)
- Embedding-based filtering (embed.py)
- Score reranking (rerank.py)

These modules are kept but marked as deprecated.

## Testing Recommendations

### Unit Tests
```python
import asyncio
from filter_rank import filter_records_with_llm, query_llm_for_record

# Test single record filtering
async def test_single_record():
    result = await query_llm_for_record(
        client, rec, query, exclude, model_name
    )
    assert result[0] == rec
    assert isinstance(result[1], bool)
    assert isinstance(result[2], str)

# Test batch filtering
async def test_batch_filtering():
    filtered = await filter_records_with_llm(
        records, query, exclude, api_key, model_name
    )
    assert len(filtered) <= len(records)
```

### Integration Tests
```bash
# Test with small dataset
llm-query-doc-analyser filter \
    --query "test query" \
    --exclude "test exclude" \
    --max-concurrent 2 \
    --export outputs/test.csv

# Test with various concurrency levels
for n in 1 5 10 20; do
    time llm-query-doc-analyser filter \
        --max-concurrent $n \
        --export outputs/test_$n.csv
done
```

## Migration Checklist

- [x] Implement async LLM filter in `filter_rank/prompts.py`
- [x] Add retry logic with tenacity
- [x] Add semaphore-based rate limiting
- [x] Add comprehensive logging
- [x] Refactor CLI `filter` command to use async implementation
- [x] Remove synchronous API calls from CLI
- [x] Add `max_concurrent` CLI option
- [x] Clean up unused imports (json, OpenAI)
- [x] Mark deprecated modules (rules, embed, rerank)
- [x] Update `filter_rank/__init__.py`
- [x] Create `filter_rank/README.md` documentation
- [x] Verify no lint errors
- [x] Create migration summary document

## Performance Tuning Guide

### Optimal Concurrency Settings

**For Different Tiers:**
- **Free Tier**: `--max-concurrent 3` (3 RPM limit)
- **Tier 1**: `--max-concurrent 10` (default, ~500 RPM)
- **Tier 2**: `--max-concurrent 20` (~5000 RPM)
- **Tier 3+**: `--max-concurrent 50` (higher limits)

**General Guidelines:**
- Start with default (10)
- Monitor API rate limit errors in logs
- Increase gradually if no errors
- Decrease if rate limit errors occur

### Cost Optimization

1. **Pre-filter records**: Only process records with abstracts
2. **Use cheaper models**: Try `gpt-3.5-turbo` for initial screening
3. **Reduce token usage**: Set `max_completion_tokens=500`
4. **Batch processing**: Process records in smaller batches if needed

## Future Enhancements

Potential improvements for next iteration:

1. **Response Caching**: Cache LLM responses to avoid re-filtering
2. **Batch API Calls**: Use OpenAI batch endpoint when available
3. **Progressive Filtering**: Multi-stage filtering (cheap → expensive)
4. **Cost Tracking**: Real-time API usage monitoring
5. **Result Confidence**: Include confidence scores in responses
6. **Model Auto-Selection**: Choose model based on query complexity

## Support & Troubleshooting

### Common Issues

**Rate Limit Errors:**
- Reduce `--max-concurrent` value
- Check OpenAI dashboard for current limits
- Enable DEBUG logging to see retry behavior

**Slow Performance:**
- Increase `--max-concurrent` if under rate limits
- Check network latency
- Verify API key tier supports higher concurrency

**Parse Errors:**
- Review logs for `llm_response_parse_failed` events
- Check if model is returning valid JSON
- Fallback parsing will attempt text-based matching

### Debug Commands

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG

# Run with minimal concurrency
llm-query-doc-analyser filter \
    --query "..." \
    --max-concurrent 1 \
    --export outputs/debug.csv

# Check logs
cat logs/session_*.jsonl | jq 'select(.level == "error")'
```

## Conclusion

This refactoring provides significant performance improvements while maintaining backward compatibility. The async architecture enables efficient parallel processing of records, reducing total filtering time by up to 10x. The modular design in the `filter_rank` package makes it easy to extend and maintain.
