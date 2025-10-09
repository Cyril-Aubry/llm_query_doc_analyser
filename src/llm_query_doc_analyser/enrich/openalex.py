from typing import Any

import httpx

from ..core.models import Record
from ..utils.http import get_with_retry
from ..utils.log import get_logger

log = get_logger(__name__)


async def fetch_openalex(rec: Record) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Fetch OpenAlex metadata and abstract by DOI.
    
    Uses retry logic with exponential backoff for handling API rate limits.
    """
    if not rec.doi_norm:
        log.debug("openalex_no_doi", record_id=rec.id)
        return {"abstract": None, "error": "no_doi"}, {}
    
    url = f"https://api.openalex.org/works/doi:{rec.doi_norm}"
    headers = {"User-Agent": "llm_query_doc_analyser/1.0"}
    
    try:
        resp = await get_with_retry(url, headers=headers, timeout=15.0)
        
        if resp.status_code != 200:
            log.warning(
                "openalex_non_200",
                doi=rec.doi_norm,
                status=resp.status_code,
                url=url,
            )
            return {
                "abstract": None,
                "error": f"http_{resp.status_code}",
            }, {"status_code": resp.status_code, "url": url}
        
        try:
            data = resp.json()
        except Exception as je:
            log.error("openalex_json_parse_error", doi=rec.doi_norm, error=str(je))
            return {
                "abstract": None,
                "error": "json_parse_error",
            }, {"url": url, "error": str(je), "response_text": resp.text[:500]}
        
    except httpx.TimeoutException as e:
        log.error("openalex_timeout", doi=rec.doi_norm, url=url, error=str(e))
        return {"abstract": None, "error": "timeout"}, {"url": url, "error": str(e)}
    except httpx.HTTPError as e:
        log.error("openalex_http_error", doi=rec.doi_norm, url=url, error=str(e))
        return {"abstract": None, "error": f"http_error: {e}"}, {"url": url, "error": str(e)}
    except Exception as e:
        log.exception("openalex_unexpected_error", doi=rec.doi_norm, url=url)
        return {"abstract": None, "error": f"unexpected: {e}"}, {"url": url, "error": str(e)}
    
    # Parse abstract_inverted_index
    idx = data.get("abstract_inverted_index")
    abstract = None
    
    if idx and isinstance(idx, dict) and idx:
        try:
            max_pos = max(max(v) for v in idx.values() if v)
            words: list[str | None] = [None] * (max_pos + 1)
            for word, positions in idx.items():
                for pos in positions:
                    words[pos] = word
            abstract = " ".join(w for w in words if w is not None)
        except (ValueError, TypeError) as e:
            log.warning(
                "openalex_abstract_parse_error",
                doi=rec.doi_norm,
                error=str(e),
            )
            abstract = None
    
    log.info(
        "openalex_fetched",
        doi=rec.doi_norm,
        has_abstract=bool(abstract),
    )
    
    return {"abstract": abstract}, {
        "url": url,
        "status_code": resp.status_code,
        "data": data,
    }
