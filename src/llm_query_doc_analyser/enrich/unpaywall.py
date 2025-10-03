import os
from typing import Any

import httpx

from ..core.models import Record
from ..utils.log import get_logger

log = get_logger(__name__)


async def fetch_unpaywall(rec: Record) -> tuple[dict, Any]:
    """Fetch OA status and PDF info from Unpaywall."""
    email = os.getenv("UNPAYWALL_EMAIL")
    if not rec.doi_norm or not email:
        log.debug("unpaywall_skipped", doi=rec.doi_norm, email_present=bool(email))
        return {}, {}

    url = f"https://api.unpaywall.org/v2/{rec.doi_norm}?email={email}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                url, headers={"User-Agent": f"llm_query_doc_analyser/1.0 (mailto:{email})"}
            )

            if resp.status_code != 200:
                log.warning(
                    "unpaywall_non_200",
                    doi=rec.doi_norm,
                    status=resp.status_code,
                    url=url,
                )
                data = {}
            else:
                try:
                    data = resp.json()
                except Exception as je:
                    log.error(
                        "unpaywall_json_error",
                        doi=rec.doi_norm,
                        status=resp.status_code,
                        url=url,
                        error=str(je),
                    )
                    data = {}

            # Log successful fetch summary
            if data:
                log.debug(
                    "unpaywall_fetched",
                    doi=rec.doi_norm,
                    is_oa=data.get("is_oa"),
                    oa_status=data.get("oa_status"),
                )

    except httpx.TimeoutException as te:
        log.error("unpaywall_timeout", doi=rec.doi_norm, url=url, error=str(te))
        return {
            "is_oa": None,
            "oa_status": None,
            "license": None,
            "oa_pdf_url": None,
            "error": "timeout",
        }, {}
    except httpx.HTTPError as he:
        log.error("unpaywall_http_error", doi=rec.doi_norm, url=url, error=str(he))
        return {
            "is_oa": None,
            "oa_status": None,
            "license": None,
            "oa_pdf_url": None,
            "error": str(he),
        }, {}
    except Exception as e:
        log.exception("unpaywall_error", doi=rec.doi_norm, url=url)
        return {
            "is_oa": None,
            "oa_status": None,
            "license": None,
            "oa_pdf_url": None,
            "error": str(e),
        }, {}

    best = data.get("best_oa_location") or {}
    is_oa = data.get("is_oa")
    oa_status = data.get("oa_status")
    license = best.get("license") if best else None
    oa_pdf_url = best.get("url_for_pdf") if best else None
    return {"is_oa": is_oa, "oa_status": oa_status, "license": license, "oa_pdf_url": oa_pdf_url}, data
