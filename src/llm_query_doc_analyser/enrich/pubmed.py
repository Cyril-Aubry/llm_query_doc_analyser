import re
from typing import Any

import httpx

from ..core.models import Record
from ..utils.http import get_with_retry
from ..utils.log import get_logger

log = get_logger(__name__)


async def fetch_pubmed(rec: Record) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Fetch PubMed abstract by DOI using E-utilities.
    
    Uses retry logic with exponential backoff for handling API rate limits.
    """
    if not rec.doi_norm:
        log.debug("pubmed_no_doi", record_id=rec.id)
        return {"abstract": None, "error": "no_doi"}, {}
    
    # Step 1: Get PMID from DOI
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={rec.doi_norm}[AID]&retmode=json"
    headers = {"User-Agent": "llm_query_doc_analyser/1.0"}
    
    try:
        resp = await get_with_retry(url, headers=headers, timeout=15.0)
        
        if resp.status_code != 200:
            log.warning(
                "pubmed_search_non_200",
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
            log.error("pubmed_json_parse_error", doi=rec.doi_norm, error=str(je))
            return {
                "abstract": None,
                "error": "json_parse_error",
            }, {"url": url, "error": str(je), "response_text": resp.text[:500]}
        
        idlist = data.get("esearchresult", {}).get("idlist", [])
        if not idlist:
            log.debug("pubmed_no_pmid", doi=rec.doi_norm)
            return {"abstract": None, "error": "no_pmid_found"}, {
                "url": url,
                "status_code": resp.status_code,
                "data": data,
            }
        
        pmid = idlist[0]
        
        # Step 2: Fetch abstract
        url2 = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={pmid}&retmode=xml"
        resp2 = await get_with_retry(url2, headers=headers, timeout=15.0)
        
        if resp2.status_code != 200:
            log.warning(
                "pubmed_fetch_non_200",
                doi=rec.doi_norm,
                pmid=pmid,
                status=resp2.status_code,
                url=url2,
            )
            return {
                "abstract": None,
                "error": f"http_{resp2.status_code}_on_fetch",
            }, {"pmid": pmid, "status_code": resp2.status_code, "url": url2}
        
        xml = resp2.text
        
        # Parse XML for abstract (simple regex-based extraction)
        m = re.search(r"<AbstractText.*?>(.*?)</AbstractText>", xml, re.DOTALL)
        abstract = m.group(1) if m else None
        
        # Clean up abstract
        if abstract:
            abstract = re.sub(r"<[^>]+>", "", abstract)  # Remove any remaining tags
            abstract = re.sub(r"\s+", " ", abstract).strip()
        
        log.info(
            "pubmed_fetched",
            doi=rec.doi_norm,
            pmid=pmid,
            has_abstract=bool(abstract),
        )
        
        return {"abstract": abstract, "pmid": pmid}, {
            "pmid": pmid,
            "xml": xml,
            "search_url": url,
            "fetch_url": url2,
            "status_code": resp2.status_code,
        }
        
    except httpx.TimeoutException as e:
        log.error("pubmed_timeout", doi=rec.doi_norm, url=url, error=str(e))
        return {"abstract": None, "error": "timeout"}, {"url": url, "error": str(e)}
    except httpx.HTTPError as e:
        log.error("pubmed_http_error", doi=rec.doi_norm, url=url, error=str(e))
        return {"abstract": None, "error": f"http_error: {e}"}, {"url": url, "error": str(e)}
    except Exception as e:
        log.exception("pubmed_unexpected_error", doi=rec.doi_norm, url=url)
        return {"abstract": None, "error": f"unexpected: {e}"}, {"url": url, "error": str(e)}
