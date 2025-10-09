from typing import Any

import httpx

from ..core.models import Record
from ..utils.http import get_with_retry
from ..utils.log import get_logger

log = get_logger(__name__)


async def fetch_europepmc(rec: Record) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Fetch Europe PMC abstract and full text URLs by DOI.
    
    Uses retry logic with exponential backoff for handling API rate limits.
    """
    if not rec.doi_norm:
        log.debug("europepmc_no_doi", record_id=rec.id)
        return {"abstract": None, "fulltext": [], "error": "no_doi"}, {}
    
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:{rec.doi_norm}&format=json"
    headers = {"User-Agent": "llm_query_doc_analyser/1.0"}
    
    try:
        resp = await get_with_retry(url, headers=headers, timeout=15.0)
        
        if resp.status_code != 200:
            log.warning(
                "europepmc_non_200",
                doi=rec.doi_norm,
                status=resp.status_code,
                url=url,
            )
            return {
                "abstract": None,
                "fulltext": [],
                "error": f"http_{resp.status_code}",
            }, {"status_code": resp.status_code, "url": url}
        
        try:
            data = resp.json()
        except Exception as je:
            log.error("europepmc_json_parse_error", doi=rec.doi_norm, error=str(je))
            return {
                "abstract": None,
                "fulltext": [],
                "error": "json_parse_error",
            }, {"url": url, "error": str(je), "response_text": resp.text[:500]}
        
    except httpx.TimeoutException as e:
        log.error("europepmc_timeout", doi=rec.doi_norm, url=url, error=str(e))
        return {
            "abstract": None,
            "fulltext": [],
            "error": "timeout",
        }, {"url": url, "error": str(e)}
    except httpx.HTTPError as e:
        log.error("europepmc_http_error", doi=rec.doi_norm, url=url, error=str(e))
        return {
            "abstract": None,
            "fulltext": [],
            "error": f"http_error: {e}",
        }, {"url": url, "error": str(e)}
    except Exception as e:
        log.exception("europepmc_unexpected_error", doi=rec.doi_norm, url=url)
        return {
            "abstract": None,
            "fulltext": [],
            "error": f"unexpected: {e}",
        }, {"url": url, "error": str(e)}
    
    results = data.get("resultList", {}).get("result", [])
    if not results:
        log.debug("europepmc_no_results", doi=rec.doi_norm)
        return {"abstract": None, "fulltext": []}, {
            "url": url,
            "status_code": resp.status_code,
            "data": data,
        }
    
    result = results[0]
    abstract = result.get("abstractText")
    fulltext = result.get("fullTextUrlList", {}).get("fullTextUrl", [])
    
    log.info(
        "europepmc_fetched",
        doi=rec.doi_norm,
        has_abstract=bool(abstract),
        fulltext_count=len(fulltext) if fulltext else 0,
    )
    
    return {"abstract": abstract, "fulltext": fulltext}, {
        "url": url,
        "status_code": resp.status_code,
        "data": data,
    }
