"""
Score reranking utilities (DEPRECATED).

This module is deprecated in favor of LLM-based filtering in prompts.py.
It is kept for backward compatibility and reference purposes only.
"""


def rerank(
    rule_score: float | None, embed_score: float | None, llm_score: float | None = None
) -> float:
    """Combine scores: 0.5*embed + 0.3*rule + 0.2*llm (omit LLM if absent)."""
    if embed_score is None:
        embed_score = 0.0
    if rule_score is None:
        rule_score = 0.0
    if llm_score is not None:
        relevance = 0.5 * embed_score + 0.3 * rule_score + 0.2 * llm_score
    else:
        relevance = 0.5 * embed_score + 0.3 * rule_score
    return relevance
