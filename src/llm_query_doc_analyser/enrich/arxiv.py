import re
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from ..core.models import Record
from ..utils.http import get_with_retry
from ..utils.log import get_logger

log = get_logger(__name__)

ARXIV_ID_PATTERN = re.compile(r"arxiv:(\d{4}\.\d{4,5})(v\d+)?", re.IGNORECASE)


async def fetch_arxiv(rec: Record) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Fetch arXiv metadata and abstract by arXiv ID.
    
    Uses retry logic with exponential backoff for handling API rate limits.
    """
    arxiv_id = rec.arxiv_id
    # Fallback: try to extract from DOI if not set
    if not arxiv_id and rec.doi_norm:
        m = ARXIV_ID_PATTERN.match(rec.doi_norm)
        if m:
            arxiv_id = m.group(1)
    
    if not arxiv_id:
        log.debug("arxiv_no_id", doi=rec.doi_norm)
        return {"abstract": None, "error": "no_arxiv_id"}, {}
    
    url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
    headers = {"User-Agent": "llm_query_doc_analyser/1.0"}
    
    try:
        resp = await get_with_retry(url, headers=headers, timeout=15.0)
        
        if resp.status_code != 200:
            log.warning(
                "arxiv_non_200",
                arxiv_id=arxiv_id,
                status=resp.status_code,
                url=url,
            )
            return {
                "abstract": None,
                "error": f"http_{resp.status_code}",
            }, {"status_code": resp.status_code, "url": url}
        
        xml = resp.text
        
    except httpx.TimeoutException as e:
        log.error("arxiv_timeout", arxiv_id=arxiv_id, url=url, error=str(e))
        return {"abstract": None, "error": "timeout"}, {"url": url, "error": str(e)}
    except httpx.HTTPError as e:
        log.error("arxiv_http_error", arxiv_id=arxiv_id, url=url, error=str(e))
        return {"abstract": None, "error": f"http_error: {e}"}, {"url": url, "error": str(e)}
    except Exception as e:
        log.exception("arxiv_unexpected_error", arxiv_id=arxiv_id, url=url)
        return {"abstract": None, "error": f"unexpected: {e}"}, {"url": url, "error": str(e)}
    
    # Parse XML for abstract
    try:
        root = ET.fromstring(xml)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entry = root.find("atom:entry", ns)
        
        if entry is None:
            log.warning("arxiv_no_entry", arxiv_id=arxiv_id)
            return {
                "abstract": None,
                "error": "no_entry_in_xml",
            }, {"xml": xml, "url": url}
        
        summary_elem = entry.find("atom:summary", ns)
        abstract = summary_elem.text.strip() if summary_elem is not None and summary_elem.text else None
        title_elem = entry.find("atom:title", ns)
        title = title_elem.text.strip() if title_elem is not None and title_elem.text else None
        
        # Normalize abstract text
        if abstract:
            abstract = re.sub(r"\s+", " ", abstract.replace("\n", " ")).strip()
        
        provenance = {
            "xml": xml,
            "url": url,
            "status_code": resp.status_code,
            "arxiv_id": arxiv_id,
        }
        
        log.info(
            "arxiv_fetched",
            arxiv_id=arxiv_id,
            has_abstract=bool(abstract),
            has_title=bool(title),
        )
        
        return {"abstract": abstract, "title": title}, provenance
        
    except ET.ParseError as e:
        log.error("arxiv_xml_parse_error", arxiv_id=arxiv_id, error=str(e), xml_preview=xml[:500])
        return {
            "abstract": None,
            "error": f"xml_parse: {e}",
        }, {"xml": xml, "url": url, "error": f"xml_parse: {e}"}
    except Exception as e:
        log.exception("arxiv_parse_unexpected_error", arxiv_id=arxiv_id, xml_preview=xml[:500])
        return {
            "abstract": None,
            "error": f"parse_error: {e}",
        }, {"xml": xml, "url": url, "error": str(e)}
