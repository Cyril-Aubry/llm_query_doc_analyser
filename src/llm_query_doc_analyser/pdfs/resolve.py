from typing import Any

from ..core.models import Record


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
    # arXiv
    if rec.arxiv_id:
        candidates.append({"url": f"https://arxiv.org/pdf/{rec.arxiv_id}.pdf", "source": "arxiv"})
    # Crossref
    if rec.provenance.get("crossref"):
        cr_pdf = rec.provenance["crossref"].get("oa_pdf_url")
        if cr_pdf:
            candidates.append({"url": cr_pdf, "source": "crossref"})
    # Prefer repository > preprint > publisher OA
    # (Simple: order as appended; in production, add more ranking logic)
    return candidates
