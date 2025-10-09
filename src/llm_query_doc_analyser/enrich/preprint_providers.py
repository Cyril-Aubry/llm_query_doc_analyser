"""
Fetch metadata from preprint providers (arXiv, bioRxiv, medRxiv, etc.).
"""

import re
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from ..core.models import Record
from ..utils.http import get_client
from ..utils.log import get_logger

log = get_logger(__name__)


async def fetch_preprint_metadata(
    rec: Record, preprint_source: str
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """
    Fetch metadata from the detected preprint provider.

    Args:
        rec: The Record instance to enrich
        preprint_source: The detected preprint source (e.g., 'arxiv', 'biorxiv', 'medrxiv')

    Returns:
        A tuple of (parsed_data, raw_response). Both are None if fetch fails.
        parsed_data contains fields like 'abstract', 'title', 'authors', 'published_doi', etc.
        raw_response contains the full API response with provenance metadata.
    """
    log.debug(
        "fetching_preprint_metadata",
        record_id=rec.id,
        doi=rec.doi_norm,
        preprint_source=preprint_source,
    )

    if preprint_source == "arxiv":
        return await _fetch_arxiv_metadata(rec)
    elif preprint_source in ("biorxiv", "medrxiv"):
        return await _fetch_biorxiv_medrxiv_metadata(rec, preprint_source)
    elif preprint_source == "preprints":
        return await _fetch_preprints_org_metadata(rec)
    else:
        log.warning(
            "unsupported_preprint_source",
            preprint_source=preprint_source,
            doi=rec.doi_norm,
        )
        return None, None


async def _fetch_arxiv_metadata(
    rec: Record,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """
    Fetch metadata from arXiv API using arXiv ID or DOI.

    API docs: https://info.arxiv.org/help/api/index.html
    """
    # Extract arXiv ID from DOI or existing field
    arxiv_id = rec.arxiv_id
    if not arxiv_id and rec.doi_norm:
        arxiv_doi_pattern = re.compile(r"arxiv[:\.](\d{4}\.\d{4,5})(v\d+)?", re.IGNORECASE)
        match = arxiv_doi_pattern.search(rec.doi_norm)
        if match:
            arxiv_id = match.group(1)

    if not arxiv_id:
        log.debug("no_arxiv_id", doi=rec.doi_norm)
        return None, None

    url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"

    try:
        async with get_client() as client:
            resp = await client.get(url, timeout=10.0)
            resp.raise_for_status()

            # Parse XML response
            root = ET.fromstring(resp.text)

            # Namespace for arXiv API
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            entry = root.find("atom:entry", ns)

            if entry is None:
                log.warning("arxiv_no_entry", arxiv_id=arxiv_id)
                return None, None

            # Extract fields
            abstract = entry.findtext("atom:summary", namespaces=ns, default="").strip()
            title = entry.findtext("atom:title", namespaces=ns, default="").strip()
            published = entry.findtext("atom:published", namespaces=ns)
            doi_link = entry.find("atom:link[@title='doi']", ns)
            published_doi = doi_link.get("href") if doi_link is not None else None
            
            # Extract journal reference if available
            journal_ref = entry.findtext("arxiv:journal_ref", namespaces={**ns, "arxiv": "http://arxiv.org/schemas/atom"})

            parsed = {
                "abstract": abstract if abstract else None,
                "title": title if title else None,
                "published_date": published,
                "published_doi": published_doi,
                "published_journal": journal_ref,
                "published_url": published_doi if published_doi else None,
                "arxiv_id": arxiv_id,
            }

            raw_response = {
                "source": "arxiv",
                "url": url,
                "timestamp": resp.headers.get("date"),
                "status_code": resp.status_code,
                "raw_xml": resp.text,
            }

            log.info(
                "arxiv_metadata_fetched",
                arxiv_id=arxiv_id,
                has_abstract=bool(abstract),
                has_published_doi=bool(published_doi),
            )

            return parsed, raw_response

    except (httpx.HTTPError, ET.ParseError) as e:
        log.error("arxiv_fetch_failed", arxiv_id=arxiv_id, error=str(e))
        return None, None


async def _fetch_biorxiv_medrxiv_metadata(
    rec: Record, preprint_source: str
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """
    Fetch metadata from bioRxiv/medRxiv API using DOI.

    API docs: https://api.biorxiv.org/
    """
    if not rec.doi_norm:
        log.debug("no_doi_for_biorxiv_medrxiv", record_id=rec.id)
        return None, None

    # Clean DOI for API query
    doi_clean = rec.doi_norm.replace("https://doi.org/", "").replace("http://doi.org/", "")

    # Construct API URL
    base_url = "https://api.biorxiv.org/details"
    url = f"{base_url}/{preprint_source}/{doi_clean}"

    try:
        async with get_client() as client:
            resp = await client.get(url, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()

            # API returns a collection
            if not data.get("collection") or len(data["collection"]) == 0:
                log.warning(
                    "biorxiv_medrxiv_no_results",
                    doi=doi_clean,
                    preprint_source=preprint_source,
                )
                return None, None

            item = data["collection"][0]

            # Extract fields
            published_doi = item.get("published")
            parsed = {
                "abstract": item.get("abstract"),
                "title": item.get("title"),
                "published_date": item.get("date"),
                "published_doi": published_doi,  # DOI of peer-reviewed version if exists
                "published_journal": item.get("published_journal") or item.get("journal"),
                "published_url": f"https://doi.org/{published_doi}" if published_doi else None,
                "version": item.get("version"),
            }

            raw_response = {
                "source": preprint_source,
                "url": url,
                "timestamp": resp.headers.get("date"),
                "status_code": resp.status_code,
                "raw_json": data,
            }

            log.info(
                "biorxiv_medrxiv_metadata_fetched",
                doi=doi_clean,
                preprint_source=preprint_source,
                has_abstract=bool(parsed.get("abstract")),
                has_published_doi=bool(parsed.get("published")),
            )

            return parsed, raw_response

    except (httpx.HTTPError, ValueError) as e:
        log.error(
            "biorxiv_medrxiv_fetch_failed",
            doi=doi_clean,
            preprint_source=preprint_source,
            error=str(e),
        )
        return None, None


async def _fetch_preprints_org_metadata(
    rec: Record,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """
    Fetch metadata from PrePrints.org API using DOI.
    
    API docs: https://www.preprints.org/api
    """
    if not rec.doi_norm:
        log.debug("no_doi_for_preprints_org", record_id=rec.id)
        return None, None
    
    # Clean DOI for API query
    doi_clean = rec.doi_norm.replace("https://doi.org/", "").replace("http://doi.org/", "")
    
    # Construct API URL - PrePrints.org uses their own API endpoint
    url = f"https://www.preprints.org/api/manuscript/doi/{doi_clean}"
    
    try:
        async with get_client() as client:
            resp = await client.get(url, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            
            # Check if we got valid data
            if not data or not isinstance(data, dict):
                log.warning(
                    "preprints_org_no_results",
                    doi=doi_clean,
                )
                return None, None
            
            # Extract fields from PrePrints.org response
            # The API structure may vary, adjust based on actual API response
            published_doi = data.get("published_doi") or data.get("peer_reviewed_doi")
            parsed = {
                "abstract": data.get("abstract"),
                "title": data.get("title"),
                "published_date": data.get("published_date") or data.get("date_published"),
                "published_doi": published_doi,
                "published_journal": data.get("published_journal") or data.get("journal_name"),
                "published_url": f"https://doi.org/{published_doi}" if published_doi else None,
                "published_fulltext_url": data.get("published_url") or data.get("fulltext_url"),
                "version": data.get("version"),
            }
            
            raw_response = {
                "source": "preprints",
                "url": url,
                "timestamp": resp.headers.get("date"),
                "status_code": resp.status_code,
                "raw_json": data,
            }
            
            log.info(
                "preprints_org_metadata_fetched",
                doi=doi_clean,
                has_abstract=bool(parsed.get("abstract")),
                has_published_doi=bool(parsed.get("published_doi")),
            )
            
            return parsed, raw_response
            
    except (httpx.HTTPError, ValueError) as e:
        log.error(
            "preprints_org_fetch_failed",
            doi=doi_clean,
            error=str(e),
        )
        return None, None
