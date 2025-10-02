# Filter and Ranking Package

This package provides filtering and ranking utilities for scholarly literature analysis.

## Overview

The `filter_rank` package has been refactored to use **LLM-based filtering** as the primary method for evaluating scientific papers against inclusion/exclusion criteria. This approach provides more accurate and flexible filtering compared to traditional rule-based or embedding-based methods.

## Current Implementation

### LLM-Based Filtering (`prompts.py`)

The main filtering method uses OpenAI's API with asynchronous parallelized calls for efficiency.

**Key Features:**
- ✅ Async/await pattern for non-blocking API calls
- ✅ Concurrent request limiting with semaphores
- ✅ Automatic retry logic with exponential backoff (using tenacity)
- ✅ Structured logging for debugging and monitoring
- ✅ JSON-based response parsing with fallback handling
- ✅ Provenance tracking for filter decisions

**Main Functions:**

1. `filter_records_with_llm(records, query, exclude, api_key, model_name, max_concurrent=10)`
   - Filters a list of records using OpenAI's LLM
   - Returns only records that match the inclusion criteria
   - Processes records concurrently with rate limiting

2. `query_llm_for_record(client, rec, query, exclude, model_name)`
   - Queries the LLM for a single record
   - Returns (record, is_match, explanation) tuple
   - Includes retry logic for transient failures

3. `build_filter_prompt(query, exclude, title, abstract)`
   - Constructs system and user prompts for the LLM
   - Formats criteria and article content appropriately

**Usage Example:**

```python
from filter_rank import filter_records_with_llm

filtered = await filter_records_with_llm(
    records=records,
    query="image semantic segmentation on 2D data",
    exclude="3D volumetric data",
    api_key="sk-...",
    model_name="gpt-4",
    max_concurrent=10,
)
```

## Deprecated Modules

The following modules are kept for backward compatibility but are no longer actively used:

### `rules.py` (DEPRECATED)
- Rule-based regex filtering
- Uses hardcoded patterns for inclusion/exclusion
- Less flexible than LLM-based approach

### `embed.py` (DEPRECATED)
- Embedding-based semantic similarity
- Uses Sentence Transformers for vector embeddings
- Requires local model loading (slower startup)

### `rerank.py` (DEPRECATED)
- Combines multiple scores (rule, embedding, LLM)
- No longer needed with pure LLM-based filtering

## Performance Considerations

### Concurrency Settings

The `max_concurrent` parameter controls how many API requests run in parallel:

- **Default: 10** - Good balance for most use cases
- **Low (1-5)**: Use if rate limits are a concern
- **High (20-50)**: Use for faster processing if your API tier supports it

### Rate Limiting

The implementation includes:
- Semaphore-based concurrency control
- Automatic retry with exponential backoff
- Structured logging for monitoring API usage

### Cost Optimization

To minimize API costs:
- Filter records by abstract availability first
- Use a lower-cost model for initial screening (e.g., `gpt-3.5-turbo`)
- Set `max_completion_tokens=500` to limit response length
- Cache results to avoid re-filtering the same records

## Error Handling

The implementation handles various error scenarios:

1. **Network Errors**: Automatic retry with exponential backoff
2. **Rate Limits**: Semaphore prevents exceeding concurrent request limits
3. **Invalid JSON**: Fallback parsing with text analysis
4. **API Errors**: Logged with full context for debugging

## Logging

All operations are logged using structured logging:

- `llm_query_started`: When a record is queued for filtering
- `llm_response_received`: Raw API response with content preview
- `llm_response_parsed`: Parsed match decision and explanation
- `llm_response_parse_failed`: JSON parsing failures with fallback
- `llm_query_failed`: Unrecoverable errors for specific records
- `llm_filtering_started` / `llm_filtering_completed`: Batch processing lifecycle

Set `LOG_LEVEL=DEBUG` in your `.env` file to see detailed logs.

## Configuration

Required environment variables:

```bash
OPENAI_API_KEY=sk-...          # Your OpenAI API key
OPENAI_MODEL=gpt-4             # Model to use (gpt-4, gpt-3.5-turbo, etc.)
LOG_LEVEL=INFO                 # Logging level
```

## Migration Guide

If you were using the old rule-based or embedding-based filtering:

### Before (Old Approach)
```python
from filter_rank.rules import rule_filter
from filter_rank.embed import similarity
from filter_rank.rerank import rerank

# Complex multi-step filtering
keep, rule_score, reasons = rule_filter(text)
embed_score = similarity(query, [text])[0]
final_score = rerank(rule_score, embed_score)
```

### After (New Approach)
```python
from filter_rank import filter_records_with_llm

# Single async call handles everything
filtered = await filter_records_with_llm(
    records=records,
    query=query,
    exclude=exclude,
    api_key=api_key,
    model_name=model_name,
)
```

## Testing

To test the filtering implementation:

```python
import asyncio
from filter_rank import filter_records_with_llm
from core.models import Record

# Create test record
rec = Record(
    title="Semantic Segmentation of Medical Images",
    abstract_text="This paper presents a 2D image segmentation method...",
    doi_norm="10.1234/test",
)

# Run filtering
filtered = asyncio.run(filter_records_with_llm(
    records=[rec],
    query="image semantic segmentation on 2D data",
    exclude="3D volumetric",
    api_key="sk-...",
    model_name="gpt-3.5-turbo",
    max_concurrent=1,
))

print(f"Matched: {len(filtered)} records")
```

## Future Enhancements

Potential improvements for future versions:

1. **Caching**: Cache LLM responses to avoid re-filtering
2. **Batch Processing**: Send multiple records in a single API call
3. **Cost Tracking**: Monitor and report API usage costs
4. **Model Selection**: Auto-select model based on complexity
5. **Confidence Scores**: Return match confidence/probability
6. **Multi-Model Voting**: Combine results from multiple models

## Support

For issues or questions:
- Check logs in `logs/session_*.jsonl`
- Review OpenAI API status at https://status.openai.com
- Consult OpenAI rate limits documentation
- Enable DEBUG logging for detailed troubleshooting
