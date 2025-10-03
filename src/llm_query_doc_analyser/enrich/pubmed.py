from typing import Any

import httpx

from ..core.models import Record


async def fetch_pubmed(rec: Record) -> tuple[dict, Any]:
    """Fetch PubMed abstract by DOI using E-utilities."""
    if not rec.doi_norm:
        return {}, {}
    # Step 1: Get PMID from DOI
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={rec.doi_norm}[AID]&retmode=json"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            data = resp.json() if resp.status_code == 200 else {}
            idlist = data.get("esearchresult", {}).get("idlist", [])
            if not idlist:
                return {"abstract": None}, data
            pmid = idlist[0]
            # Step 2: Fetch abstract
            url2 = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={pmid}&retmode=xml"
            resp2 = await client.get(url2)
            xml = resp2.text if resp2.status_code == 200 else ""
            # Parse XML for abstract (simple, not robust)
            import re
            m = re.search(r"<AbstractText.*?>(.*?)</AbstractText>", xml, re.DOTALL)
            abstract = m.group(1) if m else None
            return {"abstract": abstract}, {"pmid": pmid, "xml": xml}
    except httpx.TimeoutException:
        return {"abstract": None, "error": "timeout"}, {}
    except Exception as e:
        return {"abstract": None, "error": str(e)}, {}
