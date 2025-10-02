import httpx
from typing import Tuple, Any
from ..core.models import Record
import os

async def fetch_unpaywall(rec: Record) -> Tuple[dict, Any]:
    """Fetch OA status and PDF info from Unpaywall."""
    email = os.getenv("UNPAYWALL_EMAIL")
    if not rec.doi_norm or not email:
        return {}, {}
    url = f"https://api.unpaywall.org/v2/{rec.doi_norm}?email={email}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers={"User-Agent": f"llm_query_doc_analyser/1.0 (mailto:{email})"})
            data = resp.json() if resp.status_code == 200 else {}
    except httpx.TimeoutException:
        return {"is_oa": None, "oa_status": None, "license": None, "oa_pdf_url": None, "error": "timeout"}, {}
    except Exception as e:
        return {"is_oa": None, "oa_status": None, "license": None, "oa_pdf_url": None, "error": str(e)}, {}
    best = data.get("best_oa_location") or {}
    is_oa = data.get("is_oa")
    oa_status = data.get("oa_status")
    license = best.get("license") if best else None
    oa_pdf_url = best.get("url_for_pdf") if best else None
    return {"is_oa": is_oa, "oa_status": oa_status, "license": license, "oa_pdf_url": oa_pdf_url}, data
