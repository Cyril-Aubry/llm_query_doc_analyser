from typing import Any

import httpx

from ..core.models import Record


async def fetch_openalex(rec: Record) -> tuple[dict, Any]:
    """Fetch OpenAlex metadata and abstract by DOI."""
    if not rec.doi_norm:
        return {}, {}
    url = f"https://api.openalex.org/works/doi:{rec.doi_norm}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers={"User-Agent": "llm_query_doc_analyser/1.0"})
            data = resp.json() if resp.status_code == 200 else {}
    except httpx.TimeoutException:
        return {"abstract": None, "error": "timeout"}, {}
    except Exception as e:
        return {"abstract": None, "error": str(e)}, {}
    # Parse abstract_inverted_index
    idx = data.get("abstract_inverted_index")
    abstract = None
    if idx and isinstance(idx, dict) and idx:
        try:
            words = [None] * (max([max(v) for v in idx.values()]) + 1)
            for word, positions in idx.items():
                for pos in positions:
                    words[pos] = word
            abstract = " ".join(words)
        except Exception:
            abstract = None
    return {"abstract": abstract}, data
