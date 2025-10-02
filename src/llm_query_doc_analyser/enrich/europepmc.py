from typing import Any

import httpx

from ..core.models import Record


async def fetch_europepmc(rec: Record) -> tuple[dict, Any]:
    """Fetch Europe PMC abstract and full text URLs by DOI/PMID/PMCID."""
    if not rec.doi_norm:
        return {}, {}
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:{rec.doi_norm}&format=json"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers={"User-Agent": "llm_query_doc_analyser/1.0"})
            data = resp.json() if resp.status_code == 200 else {}
    except httpx.TimeoutException:
        return {"abstract": None, "fulltext": [], "error": "timeout"}, {}
    except Exception as e:
        return {"abstract": None, "fulltext": [], "error": str(e)}, {}
    results = data.get("resultList", {}).get("result", [])
    if not results:
        return {"abstract": None, "fulltext": []}, data
    result = results[0]
    abstract = result.get("abstractText")
    fulltext = result.get("fullTextUrlList", {}).get("fullTextUrl", [])
    return {"abstract": abstract, "fulltext": fulltext}, data
