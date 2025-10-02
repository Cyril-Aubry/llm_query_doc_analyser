# Explanation Tracking Logic

## Overview
This document comprehensively describes the logic for tracking and handling explanation strings in the filter command, ensuring all edge cases are properly recorded.

## Complete Logic Flow

### 1. LLM Query Processing (`query_llm_for_record`)

#### Case 1: Successful JSON Parsing
```python
# LLM returns valid JSON
parsed = json.loads(content)
is_match = bool(parsed.get("match"))
explanation = str(parsed.get("explanation", "")).strip()
```

**Sub-cases:**
- ✅ **Has explanation**: Normal flow - returns `(record, is_match, explanation)`
- ⚠️ **Missing explanation**: Caught by empty check → returns `(record, is_match, "WARNING: LLM returned match={is_match} without explanation")`

#### Case 2: JSON Parsing Failure
```python
except json.JSONDecodeError:
    # Fallback: heuristic match detection
    is_match = "true" in txt and "match" in txt
    explanation = content[:200].strip() if content else ""
```

**Sub-cases:**
- ⚠️ **Has content**: Uses truncated content as explanation (might still be invalid JSON)
- ⚠️ **Empty content**: Caught by empty check → returns `(record, is_match, "WARNING: LLM returned match={is_match} without explanation")`

#### Case 3: Exception During API Call
```python
except Exception as e:
    error_explanation = f"ERROR: {type(e).__name__}: {e!s}"
    return rec, False, error_explanation
```

**Examples:**
- ❌ `"ERROR: APIError: Rate limit exceeded"`
- ❌ `"ERROR: Timeout: Request timed out"`
- ❌ `"ERROR: AuthenticationError: Invalid API key"`

### 2. Result Processing (`process_with_semaphore`)

All results return `tuple[int, bool, str]` (never `None`):

```python
try:
    result = await query_llm_for_record(...)
    _, is_match, explanation = result
    return (rec.id, is_match, explanation)
except Exception as e:
    # Unexpected fallback (shouldn't normally happen)
    error_explanation = f"ERROR: Unexpected processing failure: {type(e).__name__}: {e!s}"
    return (rec.id, False, error_explanation)
```

### 3. CLI Statistics Calculation

#### Matched Count
```python
if match_result and not explanation.startswith("ERROR:"):
    matched_count += 1
```

**Logic**: Only count as "matched" if:
- ✅ `match_result = True`
- ✅ No ERROR prefix (valid API response)
- ⚠️ May include WARNING records (flag for review but still matched)

#### Failed Count
```python
if explanation.startswith("ERROR:"):
    failed_count += 1
```

**Logic**: Count as "failed" if:
- ❌ Explanation starts with "ERROR:"
- Always means `match_result = False` (safe default)

#### Warning Count
```python
if explanation.startswith("WARNING:"):
    warning_count += 1
```

**Logic**: Count as "warning" if:
- ⚠️ Explanation starts with "WARNING:"
- Can have `match_result = True` or `False`
- Indicates suspicious result (missing explanation, parse failure)

### 4. Export Logic

```python
if match_result and not explanation.startswith("ERROR:") and not explanation.startswith("WARNING:"):
    matched_records.append(rec)
```

**Export Criteria** (ALL must be true):
- ✅ `match_result = True`
- ✅ No ERROR prefix (no API failures)
- ✅ No WARNING prefix (has valid explanation)

**Excluded from Export:**
- ❌ ERROR records (always excluded - API/processing failures)
- ⚠️ WARNING records (excluded - suspicious matches without proper explanation)
- ❌ `match_result = False` (doesn't match criteria)

## All Possible Explanation States

| Explanation Content | match_result | Matched Count | Failed Count | Warning Count | Exported | Use Case |
|---------------------|--------------|---------------|--------------|---------------|----------|----------|
| Valid explanation text | True | ✅ +1 | - | - | ✅ Yes | Normal positive match |
| Valid explanation text | False | - | - | - | ❌ No | Normal negative match |
| "WARNING: LLM returned match=True without explanation" | True | ✅ +1 | - | ⚠️ +1 | ❌ No | LLM matched but didn't explain why |
| "WARNING: LLM returned match=False without explanation" | False | - | - | ⚠️ +1 | ❌ No | LLM rejected but didn't explain why |
| "ERROR: APIError: Rate limit exceeded" | False | - | ❌ +1 | - | ❌ No | API failure |
| "ERROR: Timeout: Request timed out" | False | - | ❌ +1 | - | ❌ No | Network timeout |
| Empty string (before check) | True/False | - | - | ⚠️ +1 | ❌ No | Impossible - caught and replaced with WARNING |

## Database Storage

**ALL records are stored** in `records_filterings` table:
```sql
INSERT INTO records_filterings (record_id, filtering_query_id, match_result, explanation, timestamp)
VALUES (?, ?, ?, ?, ?)
```

This includes:
- ✅ Successful matches with explanations
- ❌ Successful non-matches with explanations
- ⚠️ Matches/non-matches without explanations (WARNING)
- ❌ Failed API calls (ERROR)

## Query Examples

### Find all suspicious matches (matched but no valid explanation)
```sql
SELECT * FROM records_filterings 
WHERE match_result = 1 
  AND explanation LIKE 'WARNING:%';
```

### Find all processing failures
```sql
SELECT * FROM records_filterings 
WHERE explanation LIKE 'ERROR:%';
```

### Find clean, validated matches
```sql
SELECT * FROM records_filterings 
WHERE match_result = 1 
  AND explanation NOT LIKE 'ERROR:%'
  AND explanation NOT LIKE 'WARNING:%';
```

### Statistics for a filtering session
```sql
SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN match_result = 1 AND explanation NOT LIKE 'ERROR:%' THEN 1 ELSE 0 END) as matched,
    SUM(CASE WHEN explanation LIKE 'ERROR:%' THEN 1 ELSE 0 END) as failed,
    SUM(CASE WHEN explanation LIKE 'WARNING:%' THEN 1 ELSE 0 END) as warnings
FROM records_filterings
WHERE filtering_query_id = ?;
```

## Output Examples

### Example 1: All Successful
```
Filtering completed:
  Total records processed: 79
  Matched records: 10
  Failed records (errors): 0
  Filtering query ID: 1
```

### Example 2: With Warnings
```
Filtering completed:
  Total records processed: 79
  Matched records: 8
  Failed records (errors): 0
  Warning records (missing explanation): 2
  Filtering query ID: 1
```

### Example 3: With Errors
```
Filtering completed:
  Total records processed: 79
  Matched records: 8
  Failed records (errors): 3
  Warning records (missing explanation): 2
  Filtering query ID: 1
```

## Benefits of This Design

1. **No Data Loss**: Every record is processed and stored, even failures
2. **Complete Audit Trail**: Database contains full history with error details
3. **Safe Defaults**: All errors → `match_result = False`
4. **Quality Control**: Warnings flag suspicious results for manual review
5. **Clean Exports**: Only validated matches with proper explanations
6. **Debuggability**: Error messages help troubleshoot API issues
7. **Reproducibility**: Filtering query parameters stored with results

## Troubleshooting

### High Warning Count
- **Cause**: LLM returning matches without explanations
- **Check**: Review prompt engineering - ensure JSON format is requested
- **Query**: `SELECT * FROM records_filterings WHERE explanation LIKE 'WARNING:%' LIMIT 10`

### High Failed Count  
- **Cause**: API errors (rate limits, timeouts, authentication)
- **Check**: Review error messages in explanation field
- **Query**: `SELECT DISTINCT explanation FROM records_filterings WHERE explanation LIKE 'ERROR:%'`

### Low Match Count
- **Cause**: Overly strict filtering or poor LLM performance
- **Check**: Review non-matched records with explanations
- **Query**: `SELECT * FROM records_filterings WHERE match_result = 0 AND explanation NOT LIKE 'ERROR:%' AND explanation NOT LIKE 'WARNING:%' LIMIT 10`
