from typing import Any

import httpx

from ..core.models import Record
from ..utils.http import get_with_retry
from ..utils.log import get_logger

log = get_logger(__name__)


async def fetch_semanticscholar(rec: Record, api_key: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Fetch Semantic Scholar metadata and abstract by DOI (if API key provided).
    
    Uses retry logic with exponential backoff for handling API rate limits.
    """
    if not rec.doi_norm:
        log.debug("semanticscholar_no_doi", record_id=rec.id)
        return {"abstract": None, "error": "no_doi"}, {}
    
    if not api_key:
        log.debug("semanticscholar_no_api_key", doi=rec.doi_norm)
        return {"abstract": None, "error": "no_api_key"}, {}
    
    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{rec.doi_norm}?fields=title,abstract,externalIds,openAccessPdf"
    headers = {
        "x-api-key": api_key,
        "User-Agent": "llm_query_doc_analyser/1.0",
    }
    
    try:
        resp = await get_with_retry(url, headers=headers, timeout=15.0)
        
        if resp.status_code != 200:
            log.warning(
                "semanticscholar_non_200",
                doi=rec.doi_norm,
                status=resp.status_code,
                url=url,
            )
            return {
                "abstract": None,
                "open_access_pdf": None,
                "error": f"http_{resp.status_code}",
            }, {"status_code": resp.status_code, "url": url}
        
        try:
            data = resp.json()
        except Exception as je:
            log.error("semanticscholar_json_parse_error", doi=rec.doi_norm, error=str(je))
            return {
                "abstract": None,
                "open_access_pdf": None,
                "error": "json_parse_error",
            }, {"url": url, "error": str(je), "response_text": resp.text[:500]}
        
    except httpx.TimeoutException as e:
        log.error("semanticscholar_timeout", doi=rec.doi_norm, url=url, error=str(e))
        return {
            "abstract": None,
            "open_access_pdf": None,
            "error": "timeout",
        }, {"url": url, "error": str(e)}
    except httpx.HTTPError as e:
        log.error("semanticscholar_http_error", doi=rec.doi_norm, url=url, error=str(e))
        return {
            "abstract": None,
            "open_access_pdf": None,
            "error": f"http_error: {e}",
        }, {"url": url, "error": str(e)}
    except Exception as e:
        log.exception("semanticscholar_unexpected_error", doi=rec.doi_norm, url=url)
        return {
            "abstract": None,
            "open_access_pdf": None,
            "error": f"unexpected: {e}",
        }, {"url": url, "error": str(e)}
    
    abstract = data.get("abstract")
    open_access_pdf = None
    if data.get("openAccessPdf") and isinstance(data["openAccessPdf"], dict):
        open_access_pdf = data["openAccessPdf"].get("url")
    
    log.info(
        "semanticscholar_fetched",
        doi=rec.doi_norm,
        has_abstract=bool(abstract),
        has_pdf=bool(open_access_pdf),
    )
    
    return {"abstract": abstract, "open_access_pdf": open_access_pdf}, {
        "url": url,
        "status_code": resp.status_code,
        "data": data,
    }
