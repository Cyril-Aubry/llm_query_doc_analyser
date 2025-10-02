import re
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from ..core.models import Record


async def fetch_crossref(rec: Record) -> tuple[dict, Any]:
    """Fetch Crossref metadata and abstract by DOI."""
    if not rec.doi_norm:
        return {}, {}
    url = f"https://api.crossref.org/works/{rec.doi_norm}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers={"User-Agent": "llm_query_doc_analyser/1.0"})
            data = resp.json() if resp.status_code == 200 else {}
    except httpx.TimeoutException:
        return {"abstract": None, "oa_pdf_url": None, "error": "timeout"}, {}
    except Exception as e:
        return {"abstract": None, "oa_pdf_url": None, "error": str(e)}, {}
    # Parse abstract and links
    abstract = data.get("message", {}).get("abstract")
    if abstract:
        try:
            # Parse and clean XML-like abstract
            abstract = ET.fromstring(f"<root>{abstract}</root>").text
            abstract = re.sub(r'\s+', ' ', abstract).strip()
        except ET.ParseError:
            abstract = re.sub(r'<[^>]+>', '', abstract)  # Fallback: remove tags
            abstract = re.sub(r'\s+', ' ', abstract).strip()

    links = data.get("message", {}).get("link", [])
    pdf_url = None
    for link in links:
        if link.get("content-type") == "application/pdf":
            pdf_url = link.get("URL")
            break
    return {"abstract": abstract, "oa_pdf_url": pdf_url}, data
