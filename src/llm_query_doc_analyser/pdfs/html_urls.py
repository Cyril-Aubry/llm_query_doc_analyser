"""Construct full-text HTML URLs from DOIs for preprint sources."""

import re

from ..core.models import Record
from ..utils.log import get_logger

log = get_logger(__name__)


def extract_arxiv_id_from_doi(doi: str) -> str | None:
    """Extract arXiv ID from DOI like 10.48550/arXiv.2408.06784."""
    arxiv_doi_pattern = re.compile(r"arxiv[:\.](\d{4}\.\d{4,5})(v\d+)?", re.IGNORECASE)
    match = arxiv_doi_pattern.search(doi)
    if match:
        arxiv_id = match.group(1)
        version = match.group(2) or ""
        return f"{arxiv_id}{version}"
    return None


def extract_preprints_id_version_from_doi(doi: str) -> tuple[str, str] | None:
    """
    Extract manuscript ID and version from preprints.org DOI.
    Example: 10.20944/preprints202311.1954.v2 -> (202311.1954, v2)
    """
    pattern = re.compile(r"10\.20944/preprints(\d+\.\d+)\.(v\d+)", re.IGNORECASE)
    match = pattern.search(doi)
    if match:
        manuscript_id = match.group(1)
        version = match.group(2)
        return manuscript_id, version
    return None


def build_fulltext_html_url(record: Record) -> str | None:
    """
    Build full-text HTML URL for preprint sources based on DOI.

    Args:
        record: Record with preprint_source and doi_norm

    Returns:
        Full-text HTML URL or None if not applicable

    Examples:
        - arxiv: https://arxiv.org/html/2408.06784v1
        - biorxiv: https://www.biorxiv.org/content/10.1101/859496v2.full
        - medrxiv: https://www.medrxiv.org/content/10.1101/2024.07.28.24311154v1.full-text
        - preprints: https://www.preprints.org/manuscript/202311.1954/v2
    """
    if not record.is_preprint or not record.doi_norm or not record.preprint_source:
        log.debug(
            "cannot_build_html_url",
            record_id=record.id,
            is_preprint=record.is_preprint,
            has_doi=bool(record.doi_norm),
            has_source=bool(record.preprint_source),
        )
        return None

    doi = record.doi_norm
    source = record.preprint_source.lower()

    try:
        if source == "arxiv":
            arxiv_id = extract_arxiv_id_from_doi(doi)
            if not arxiv_id:
                log.warning("arxiv_id_extraction_failed", doi=doi)
                return None
            url = f"https://arxiv.org/html/{arxiv_id}"
            log.debug("arxiv_html_url_built", doi=doi, arxiv_id=arxiv_id, url=url)
            return url

        elif source == "biorxiv":
            # DOI format: 10.1101/859496
            # URL format: https://www.biorxiv.org/content/10.1101/859496v2.full
            url = f"https://www.biorxiv.org/content/{doi}.full"
            log.debug("biorxiv_html_url_built", doi=doi, url=url)
            return url

        elif source == "medrxiv":
            # DOI format: 10.1101/2024.07.28.24311154
            # URL format: https://www.medrxiv.org/content/10.1101/2024.07.28.24311154v1.full-text
            url = f"https://www.medrxiv.org/content/{doi}.full-text"
            log.debug("medrxiv_html_url_built", doi=doi, url=url)
            return url

        elif source == "preprints":
            # DOI format: 10.20944/preprints202311.1954.v2
            # URL format: https://www.preprints.org/manuscript/202311.1954/v2
            result = extract_preprints_id_version_from_doi(doi)
            if not result:
                log.warning("preprints_id_extraction_failed", doi=doi)
                return None
            manuscript_id, version = result
            url = f"https://www.preprints.org/manuscript/{manuscript_id}/{version}"
            log.debug("preprints_html_url_built", doi=doi, manuscript_id=manuscript_id, version=version, url=url)
            return url

        else:
            log.warning("unsupported_preprint_source_for_html", source=source, doi=doi)
            return None

    except Exception as e:
        log.error("html_url_construction_error", doi=doi, source=source, error=str(e))
        return None
