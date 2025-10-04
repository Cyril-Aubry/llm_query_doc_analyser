"""
LLM-based filtering using OpenAI API with async parallelized calls.
"""

import asyncio
import json
from collections.abc import Callable
from typing import Any

from openai import AsyncOpenAI
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..core.models import Record
from ..utils.log import get_logger

log = get_logger(__name__)


def build_filter_prompt(query: str, exclude: str, title: str, abstract: str) -> dict[str, Any]:
    """
    Build the system and user prompts for LLM-based filtering.
    
    Args:
        query: Inclusive criteria query string
        exclude: Exclusive criteria string
        title: Article title
        abstract: Article abstract text
    
    Returns:
        Dictionary with 'system' and 'user' prompt messages
    """
    system_prompt = """You are an assistant that evaluates scientific papers for inclusion in a research corpus. 
Your task is to decide if a given article (title + abstract) is RELEVANT or NOT RELEVANT based on two criteria:
1. Inclusive criteria: conditions that the paper must satisfy to be considered relevant.
2. Exclusive criteria: conditions that disqualify a paper, even if the inclusive criteria are met.

Output ONLY a valid JSON object in this exact format:
{
  "match": true or false,
  "explanation": "a brief one-sentence justification for the decision"
}

Keep the explanation short and factual. Do not include any additional commentary or text outside of this JSON format."""

    text = f"{title}\n{abstract or ''}"
    
    user_prompt = f"""Inclusive criteria: {query}
Exclusive criteria: {exclude}

For the article below, answer ONLY with a JSON object with two fields:
  - match: true or false (boolean)
  - explanation: a short 1-2 sentence justification (string)

Do NOT include any additional text.

Article:
{text}"""
    
    return {
        "system": system_prompt,
        "user": user_prompt,
    }


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((Exception,)),
)
async def query_llm_for_record(
    client: AsyncOpenAI,
    rec: Record,
    query: str,
    exclude: str,
    model_name: str,
) -> tuple[Record, bool, str]:
    """
    Query OpenAI LLM to determine if a record matches the filter criteria.
    
    Args:
        client: AsyncOpenAI client instance
        rec: Record to evaluate
        query: Inclusive criteria query string
        exclude: Exclusive criteria string
        model_name: OpenAI model name to use
    
    Returns:
        Tuple of (record, is_match, explanation)
    """
    log.debug("llm_query_started", doi=rec.doi_norm, title=rec.title[:100])
    
    # Build prompts
    prompts = build_filter_prompt(query, exclude, rec.title, rec.abstract_text or "")
    
    try:
        # Make async API call
        # Some models (e.g., gpt-5-nano) do not support setting temperature; only include if allowed
        create_kwargs = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": prompts["system"]},
                {"role": "user", "content": prompts["user"]},
            ],
            "max_completion_tokens": 5000,
        }
        # Only set temperature if model is not gpt-5-nano (or other known restricted models)
        if not model_name.lower().startswith("gpt-5-nano"):
            create_kwargs["temperature"] = 0.0
        response = await client.chat.completions.create(**create_kwargs)
        
        # Extract content
        content = response.choices[0].message.content
        
        log.debug(
            "llm_response_received",
            doi=rec.doi_norm,
            response_content=content[:500],
            content_length=len(content),
        )
        
        # Parse JSON response
        is_match = False
        explanation = ""
        
        try:
            parsed = json.loads(content)
            is_match = bool(parsed.get("match"))
            explanation = str(parsed.get("explanation", "")).strip()
            
            log.debug(
                "llm_response_parsed",
                doi=rec.doi_norm,
                match=is_match,
                explanation=explanation[:200],
            )
        except json.JSONDecodeError as e:
            # Fallback: loose textual check
            txt = content.strip().lower()
            is_match = "true" in txt and "match" in txt
            explanation = content[:200].strip() if content else ""
            
            log.warning(
                "llm_response_parse_failed",
                doi=rec.doi_norm,
                error=str(e),
                fallback_used=True,
                raw_content=content[:200],
            )
        
        # Check for missing or empty explanation for ANY match result (True or False)
        if not explanation:
            explanation = f"WARNING: LLM returned match={is_match} without explanation"
            log.warning(
                "llm_response_missing_explanation",
                doi=rec.doi_norm,
                match=is_match,
            )
        
        return rec, is_match, explanation
        
    except Exception as e:
        log.error(
            "llm_query_failed",
            doi=rec.doi_norm,
            error=str(e),
            error_type=type(e).__name__,
        )
        # Return error information instead of raising
        error_explanation = f"ERROR: {type(e).__name__}: {e!s}"
        return rec, False, error_explanation


async def filter_records_with_llm(
    records: list[Record],
    query: str,
    exclude: str,
    api_key: str,
    model_name: str,
    max_concurrent: int = 10,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[tuple[int, bool, str]]:
    """
    Filter records using OpenAI LLM with async parallelized calls.
    
    Args:
        records: List of records to filter
        query: Inclusive criteria query string
        exclude: Exclusive criteria string
        api_key: OpenAI API key
        model_name: OpenAI model name to use
        max_concurrent: Maximum number of concurrent API calls
        progress_callback: Optional callback function to report progress (completed_count, total_count)
    
    Returns:
        List of tuples (record_id, match_result, explanation). 
        Failed records will have match_result=False and explanation starting with "ERROR:"
    """
    log.info("llm_filtering_started", total_records=len(records), max_concurrent=max_concurrent)
    
    # Initialize async OpenAI client
    client = AsyncOpenAI(api_key=api_key)
    
    # Create semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(max_concurrent)
    
    # Progress tracking
    completed = 0
    
    async def process_with_semaphore(rec: Record) -> tuple[int, bool, str]:
        nonlocal completed
        async with semaphore:
            try:
                result = await query_llm_for_record(client, rec, query, exclude, model_name)
                _, is_match, explanation = result
                # Return record ID instead of full record
                return (rec.id, is_match, explanation)
            except Exception as e:
                # This should rarely happen now since query_llm_for_record handles errors
                log.error("record_processing_failed_unexpectedly", doi=rec.doi_norm, error=str(e))
                error_explanation = f"ERROR: Unexpected processing failure: {type(e).__name__}: {e!s}"
                return (rec.id, False, error_explanation)
            finally:
                completed += 1
                if progress_callback:
                    progress_callback(completed, len(records))
    
    # Process all records concurrently with rate limiting
    tasks = [process_with_semaphore(rec) for rec in records]
    results = await asyncio.gather(*tasks)
    
    # Count statistics
    matched_count = sum(1 for r in results if r[1])  # Count where match_result=True
    failed_count = sum(1 for r in results if r[2].startswith("ERROR:"))  # Count where explanation starts with ERROR:
    
    log.info(
        "llm_filtering_completed",
        total_records=len(records),
        matched_count=matched_count,
        failed_count=failed_count,
    )
    
    return results
