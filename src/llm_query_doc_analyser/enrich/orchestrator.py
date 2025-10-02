import re
from typing import Any

from ..core.models import Record
from ..utils.log import get_logger
from .arxiv import fetch_arxiv
from .crossref import fetch_crossref
from .europepmc import fetch_europepmc
from .openalex import fetch_openalex
from .pubmed import fetch_pubmed
from .semanticscholar import fetch_semanticscholar
from .unpaywall import fetch_unpaywall

log = get_logger(__name__)


async def enrich_record(rec: Record, clients: dict[str, Any]) -> Record:
    """
    Enrich a record with abstract and OA info, keeping provenance for each service.
    Precedence: S2 > Crossref > OpenAlex > EPMC/PubMed.
    """
    log.debug("enrichment_started", doi=rec.doi_norm, title=rec.title[:100])
    provenance = {}
    ARXIV_DOI_PATTERN = re.compile(r"arxiv:(\d{4}\.\d{4,5})(v\d+)?", re.IGNORECASE)
    # Set arxiv_id if DOI is arXiv
    if rec.doi_norm and ARXIV_DOI_PATTERN.match(rec.doi_norm):
        m = ARXIV_DOI_PATTERN.match(rec.doi_norm)
        rec.arxiv_id = m.group(1) if m else None

    if rec.arxiv_id:
        arxiv, arxiv_raw = await fetch_arxiv(rec)
        log.debug("fetched_arxiv", arxiv_id=rec.arxiv_id, has_abstract=bool(arxiv and arxiv.get("abstract")))
        if arxiv and arxiv.get("abstract"):
            rec.abstract_text = arxiv["abstract"]
            rec.abstract_source = "arxiv"
            # Ensure provenance is always a dict
            if not isinstance(arxiv_raw, dict):
                provenance["arxiv"] = {"raw": arxiv_raw}
            else:
                provenance["arxiv"] = arxiv_raw
    else:
        # Semantic Scholar (optional)
        if clients.get("s2"):
            s2, s2_raw = await fetch_semanticscholar(rec, clients["s2"])
            log.debug("fetched_semanticscholar", doi=rec.doi_norm, has_abstract=bool(s2 and s2.get("abstract")))
            if s2 and s2.get("abstract"):
                rec.abstract_text = s2["abstract"]
                rec.abstract_source = "s2"
                provenance["s2"] = s2_raw
        # Crossref
        if not rec.abstract_text:
            cr, cr_raw = await fetch_crossref(rec)
            if cr and cr.get("abstract"):
                rec.abstract_text = cr["abstract"]
                rec.abstract_source = "crossref"
                provenance["crossref"] = cr_raw
        # OpenAlex
        if not rec.abstract_text:
            oa, oa_raw = await fetch_openalex(rec)
            if oa and oa.get("abstract"):
                rec.abstract_text = oa["abstract"]
                rec.abstract_source = "openalex"
                provenance["openalex"] = oa_raw
        # EuropePMC
        if not rec.abstract_text:
            epmc, epmc_raw = await fetch_europepmc(rec)
            if epmc and epmc.get("abstract"):
                rec.abstract_text = epmc["abstract"]
                rec.abstract_source = "epmc"
                provenance["epmc"] = epmc_raw
        # PubMed
        if not rec.abstract_text:
            pm, pm_raw = await fetch_pubmed(rec)
            if pm and pm.get("abstract"):
                rec.abstract_text = pm["abstract"]
                rec.abstract_source = "pubmed"
                provenance["pubmed"] = pm_raw
    # OA info (Unpaywall)
    upw, upw_raw = await fetch_unpaywall(rec)
    if upw:
        rec.is_oa = upw.get("is_oa")
        rec.oa_status = upw.get("oa_status")
        rec.license = upw.get("license")
        rec.oa_pdf_url = upw.get("oa_pdf_url")
        provenance["unpaywall"] = upw_raw
    rec.provenance.update(provenance)
    log.debug(
        "enrichment_completed",
        doi=rec.doi_norm,
        has_abstract=bool(rec.abstract_text),
        abstract_source=rec.abstract_source,
        is_oa=rec.is_oa,
        oa_status=rec.oa_status,
    )
    return rec
