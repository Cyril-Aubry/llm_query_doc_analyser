import re
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from ..core.models import Record
from ..utils.http import get_with_retry
from ..utils.log import get_logger

log = get_logger(__name__)


async def fetch_crossref(rec: Record) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Fetch Crossref metadata and abstract by DOI.
    
    Uses retry logic with exponential backoff for handling API rate limits.
    """
    if not rec.doi_norm:
        log.debug("crossref_no_doi", record_id=rec.id)
        return {"abstract": None, "error": "no_doi"}, {}
    
    url = f"https://api.crossref.org/works/{rec.doi_norm}"
    headers = {"User-Agent": "llm_query_doc_analyser/1.0"}
    
    try:
        resp = await get_with_retry(url, headers=headers, timeout=15.0)
        
        if resp.status_code != 200:
            log.warning(
                "crossref_non_200",
                doi=rec.doi_norm,
                status=resp.status_code,
                url=url,
            )
            return {
                "abstract": None,
                "oa_pdf_url": None,
                "error": f"http_{resp.status_code}",
            }, {"status_code": resp.status_code, "url": url}
        
        try:
            data = resp.json()
        except Exception as je:
            log.error("crossref_json_parse_error", doi=rec.doi_norm, error=str(je))
            return {
                "abstract": None,
                "oa_pdf_url": None,
                "error": "json_parse_error",
            }, {"url": url, "error": str(je), "response_text": resp.text[:500]}
        
    except httpx.TimeoutException as e:
        log.error("crossref_timeout", doi=rec.doi_norm, url=url, error=str(e))
        return {
            "abstract": None,
            "oa_pdf_url": None,
            "error": "timeout",
        }, {"url": url, "error": str(e)}
    except httpx.HTTPError as e:
        log.error("crossref_http_error", doi=rec.doi_norm, url=url, error=str(e))
        return {
            "abstract": None,
            "oa_pdf_url": None,
            "error": f"http_error: {e}",
        }, {"url": url, "error": str(e)}
    except Exception as e:
        log.exception("crossref_unexpected_error", doi=rec.doi_norm, url=url)
        return {
            "abstract": None,
            "oa_pdf_url": None,
            "error": f"unexpected: {e}",
        }, {"url": url, "error": str(e)}
    
    # Parse abstract and links
    abstract = data.get("message", {}).get("abstract")
    if abstract:
        try:
            # Parse and clean XML-like abstract
            abstract = ET.fromstring(f"<root>{abstract}</root>").text
            if abstract:
                abstract = re.sub(r"\s+", " ", abstract).strip()
        except ET.ParseError:
            # Fallback: remove tags using regex
            abstract = re.sub(r"<[^>]+>", "", abstract)
            abstract = re.sub(r"\s+", " ", abstract).strip()
    
    links = data.get("message", {}).get("link", [])
    pdf_url = None
    for link in links:
        if link.get("content-type") == "application/pdf":
            pdf_url = link.get("URL")
            break
    
    log.info(
        "crossref_fetched",
        doi=rec.doi_norm,
        has_abstract=bool(abstract),
        has_pdf_url=bool(pdf_url),
    )
    
    return {
        "abstract": abstract,
        "oa_pdf_url": pdf_url,
    }, {
        "url": url,
        "status_code": resp.status_code,
        "message": data.get("message", {}),
    }
