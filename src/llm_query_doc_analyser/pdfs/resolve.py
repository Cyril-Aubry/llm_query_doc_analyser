import re
from typing import Any

from ..core.models import Record


def extract_preprints_id_version(doi: str) -> tuple[str, str] | None:
    """
    Extract id and version from DOIs like "10.20944/preprints202501.0123.v1".
    Returns ("202501.0123", "v1") or None if no match.
    """

    m = re.search(r"preprints(?P<id>\d+\.\d+)\.(?P<version>v\d+)", doi, flags=re.IGNORECASE)
    if not m:
        return None
    return m.group("id"), m.group("version")


def _preprint_pdf_url(record: Record) -> str | None:
    """
    If the record is a preprint from a known preprint source and has a DOI,
    return the direct PDF download URL when possible.
    Falls back to DOI resolver if source not recognized.
    """
    if not (record.is_preprint and record.doi_norm and record.preprint_source):
        return None

    doi = record.doi_norm
    source = record.preprint_source.lower()

    if source == "biorxiv":
        return f"https://www.biorxiv.org/content/{doi}.full.pdf"

    if source == "medrxiv":
        return f"https://www.medrxiv.org/content/{doi}.full.pdf"

    if source == "preprints":
        # DOIs like 10.20944/preprints202501.0123.v1
        preprint_id, version = extract_preprints_id_version(doi)
        return f"https://www.preprints.org/manuscript/{preprint_id}/{version}/download"

    if source == "arxiv":
        # DOIs like 10.48550/arXiv.2401.12345 -> extract ID after last dot
        # arxiv_id = doi.split("arxiv.", 1)[-1]
        print(f"https://arxiv.org/pdf/{doi.replace('10.48550/arXiv.', '').lower()}.pdf")
        return f"https://arxiv.org/pdf/{doi.replace('10.48550/arXiv.', '').lower()}.pdf"

    # fallback
    return f"https://doi.org/{doi}"


def resolve_pdf_candidates(rec: Record) -> list[dict[str, Any]]:
    """Collect and rank candidate OA PDF URLs from all sources."""
    candidates = []
    # Unpaywall
    if rec.oa_pdf_url:
        candidates.append({"url": rec.oa_pdf_url, "source": "unpaywall", "license": rec.license})
    # Europe PMC
    if rec.provenance.get("epmc"):
        for ft in rec.provenance["epmc"].get("fulltext", []):
            if ft.get("documentStyle") == "pdf":
                candidates.append({"url": ft.get("url"), "source": "epmc"})
    # Semantic Scholar
    if rec.provenance.get("s2"):
        s2_pdf = rec.provenance["s2"].get("open_access_pdf")
        if s2_pdf:
            candidates.append({"url": s2_pdf, "source": "s2"})
    # preprint source
    if rec.is_preprint and rec.preprint_source:
        preprint_source, pdf_url = rec.preprint_source, _preprint_pdf_url(rec)
        if pdf_url:
            candidates.append({"url": pdf_url, "source": preprint_source.lower()})
    # Crossref
    if rec.provenance.get("crossref"):
        cr_pdf = rec.provenance["crossref"].get("oa_pdf_url")
        if cr_pdf:
            candidates.append({"url": cr_pdf, "source": "crossref"})
    # Prefer repository > preprint > publisher OA
    # (Simple: order as appended; in production, add more ranking logic)
    return candidates
