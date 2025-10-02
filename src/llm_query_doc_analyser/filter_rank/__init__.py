"""
Filter and ranking utilities for scholarly literature analysis.

This package provides tools for filtering and ranking academic records using various methods:
- LLM-based filtering with async parallelized OpenAI API calls
- Embedding-based semantic similarity (deprecated - use LLM filtering instead)
- Rule-based regex filtering (deprecated - use LLM filtering instead)
- Score reranking utilities (deprecated - use LLM filtering instead)

The primary filtering method is now LLM-based filtering using OpenAI's API,
which provides more accurate and flexible filtering compared to rule-based or
embedding-based methods.
"""

from .prompts import build_filter_prompt, filter_records_with_llm, query_llm_for_record

__all__ = [
    "build_filter_prompt",
    "filter_records_with_llm",
    "query_llm_for_record",
]
