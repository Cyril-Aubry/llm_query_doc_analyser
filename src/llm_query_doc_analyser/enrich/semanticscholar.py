from typing import Any

import httpx

from ..core.models import Record


async def fetch_semanticscholar(rec: Record, api_key: str) -> tuple[dict, Any]:
    """Fetch Semantic Scholar metadata and abstract by DOI (if API key provided)."""
    if not rec.doi_norm or not api_key:
        return {}, {}
    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{rec.doi_norm}?fields=title,abstract,externalIds,openAccessPdf"
    headers = {"x-api-key": api_key, "User-Agent": "llm_query_doc_analyser/1.0"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            data = resp.json() if resp.status_code == 200 else {}
    except httpx.TimeoutException:
        return {"abstract": None, "open_access_pdf": None, "error": "timeout"}, {}
    except Exception as e:
        return {"abstract": None, "open_access_pdf": None, "error": str(e)}, {}
    abstract = data.get("abstract")
    open_access_pdf = None
    if data.get("openAccessPdf") and isinstance(data["openAccessPdf"], dict):
        open_access_pdf = data["openAccessPdf"].get("url")
    return {"abstract": abstract, "open_access_pdf": open_access_pdf}, data
