import re
from typing import Any

import httpx

from ..core.models import Record

ARXIV_ID_PATTERN = re.compile(r"arxiv:(\d{4}\.\d{4,5})(v\d+)?", re.IGNORECASE)

async def fetch_arxiv(rec: Record) -> tuple[dict, Any]:
    """Fetch arXiv metadata and abstract by arXiv ID."""
    arxiv_id = rec.arxiv_id
    # Fallback: try to extract from DOI if not set
    if not arxiv_id and rec.doi_norm:
        m = ARXIV_ID_PATTERN.match(rec.doi_norm)
        if m:
            arxiv_id = m.group(1)
    if not arxiv_id:
        return {}, {}
    url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers={"User-Agent": "llm_query_doc_analyser/1.0"})
            xml = resp.text if resp.status_code == 200 else ""
    except httpx.TimeoutException:
        return {"abstract": None, "error": "timeout"}, {}
    except Exception as e:
        return {"abstract": None, "error": str(e)}, {}
    # Parse XML for abstract
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        entry = root.find('atom:entry', ns)
        abstract = entry.find('atom:summary', ns).text.strip() if entry is not None else None
        title = entry.find('atom:title', ns).text.strip() if entry is not None else None
        # Normalize abstract text
        if abstract:
            abstract = re.sub(r'\s+', ' ', abstract.replace('\n', ' ')).strip()
        provenance = {"xml": xml}
        return {"abstract": abstract, "title": title}, provenance
    except Exception as e:
        provenance = {"xml": xml, "error": f"xml_parse: {e}"}
        return {"abstract": None, "error": f"xml_parse: {e}"}, provenance
