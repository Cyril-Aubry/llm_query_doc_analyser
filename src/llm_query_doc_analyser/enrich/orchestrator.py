import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from ..core.models import Record
from ..utils.http import RateLimiter
from ..utils.log import get_logger
from .crossref import fetch_crossref
from .europepmc import fetch_europepmc
from .openalex import fetch_openalex
from .preprint_detection import detect_preprint_source
from .preprint_providers import fetch_preprint_metadata
from .pubmed import fetch_pubmed
from .semanticscholar import fetch_semanticscholar
from .unpaywall import fetch_unpaywall
from .version_linking import process_preprint_to_published_linking

log = get_logger(__name__)

# Global rate limiters for different APIs (calls per second)
# ArXiv recommends 1 call per 3 seconds = 0.33 calls/sec
RATE_LIMITERS = {
    "arxiv": RateLimiter(calls_per_second=0.33),
    "crossref": RateLimiter(calls_per_second=1.0),  # Polite rate
    "openalex": RateLimiter(calls_per_second=5.0),  # No strict limit but be polite
    "europepmc": RateLimiter(calls_per_second=2.0),  # Be polite
    "pubmed": RateLimiter(calls_per_second=3.0),  # NCBI guideline without API key
    "s2": RateLimiter(calls_per_second=5.0),  # With API key can be higher
    "unpaywall": RateLimiter(calls_per_second=5.0),  # Be polite
    "preprints": RateLimiter(calls_per_second=2.0),  # General preprint sources
}


def extract_arxiv_id(rec: Record) -> None:
    """
    Extract and set arXiv ID from DOI if present.
    
    Parameters:
    rec (Record): The record to process.
    """
    ARXIV_DOI_PATTERN = re.compile(r"arxiv:(\d{4}\.\d{4,5})(v\d+)?", re.IGNORECASE)
    # Set arxiv_id if DOI is arXiv
    if rec.doi_norm and ARXIV_DOI_PATTERN.match(rec.doi_norm):
        m = ARXIV_DOI_PATTERN.match(rec.doi_norm)
        rec.arxiv_id = m.group(1) if m else None


@dataclass
class EnrichmentSource:
    """Represents an enrichment source with its metadata."""
    name: str
    key: str
    fetcher: Callable[..., Awaitable[tuple[dict[str, Any] | None, dict[str, Any] | None]]]
    requires_client: bool = False
    
    
@dataclass
class EnrichmentResult:
    """Result of an enrichment attempt from a single source."""
    source_name: str
    success: bool
    has_abstract: bool
    reason: str
    data: dict[str, Any] | None = None
    raw_data: dict[str, Any] | None = None


class AbstractEnrichmentPipeline:
    """
    Chain of Responsibility pattern for abstract retrieval.
    Tries multiple sources in order until an abstract is found.
    """
    
    def __init__(self, sources: list[EnrichmentSource]):
        """
        Initialize the pipeline with ordered sources.
        
        Parameters:
        sources (list[EnrichmentSource]): Ordered list of sources to try.
        """
        self.sources = sources
    
    async def enrich(
        self,
        rec: Record,
        clients: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """
        Attempt to enrich record with abstract from available sources.
        
        Parameters:
        rec (Record): The record to enrich.
        clients (dict[str, Any]): Dictionary of API clients.
        
        Returns:
        tuple: (list of attempt reports, provenance dict)
        """
        attempts = []
        provenance = {}
        
        for source in self.sources:
            # Check if source is available (e.g., S2 is optional)
            if source.key == "s2" and not clients.get("s2"):
                continue
            
            result = await self._try_source(rec, source, clients)
            provenance[source.key] = result.raw_data
            
            # Record attempt
            attempt_report = {
                "source": result.source_name,
                "status": "success" if result.success else "failed",
                "reason": result.reason,
            }
            attempts.append(attempt_report)
            
            # If we found an abstract and record doesn't have one yet, use it
            if result.has_abstract and not rec.abstract_text and result.data:
                rec.abstract_text = result.data.get("abstract")
                rec.abstract_source = source.key
                log.info(
                    "abstract_retrieved",
                    doi=rec.doi_norm,
                    source=source.key,
                )
            
            # Continue checking other sources even after finding abstract
            # to populate provenance data
        
        return attempts, provenance
    
    async def _try_source(
        self,
        rec: Record,
        source: EnrichmentSource,
        clients: dict[str, Any]
    ) -> EnrichmentResult:
        """
        Try to fetch abstract from a single source with rate limiting.
        
        Parameters:
        rec (Record): The record to enrich.
        source (EnrichmentSource): The source to try.
        clients (dict[str, Any]): Dictionary of API clients.
        
        Returns:
        EnrichmentResult: Result of the enrichment attempt.
        """
        try:
            # Apply rate limiting before API call
            rate_limiter = RATE_LIMITERS.get(source.key)
            if rate_limiter:
                await rate_limiter.acquire()
            
            # Handle sources that require client parameter
            if source.requires_client:
                data, raw = await source.fetcher(rec, clients.get(source.key))
            else:
                data, raw = await source.fetcher(rec)
            
            if data is None:
                return EnrichmentResult(
                    source_name=source.name,
                    success=False,
                    has_abstract=False,
                    reason="API returned no data or timed out",
                    raw_data=raw,
                )
            
            if data.get("abstract"):
                reason = (
                    "Abstract retrieved successfully"
                    if not rec.abstract_text
                    else f"Abstract already retrieved successfully by {rec.abstract_source}"
                )
                return EnrichmentResult(
                    source_name=source.name,
                    success=True,
                    has_abstract=True,
                    reason=reason,
                    data=data,
                    raw_data=raw,
                )
            else:
                return EnrichmentResult(
                    source_name=source.name,
                    success=False,
                    has_abstract=False,
                    reason="No abstract field in response",
                    data=data,
                    raw_data=raw,
                )
        except Exception as e:
            log.error(
                "enrichment_source_error",
                source=source.name,
                doi=rec.doi_norm,
                error=str(e),
            )
            return EnrichmentResult(
                source_name=source.name,
                success=False,
                has_abstract=False,
                reason=f"Exception: {e!s}",
                raw_data=None,
            )


class PreprintEnricher:
    """Strategy pattern for preprint-specific enrichment."""
    
    async def enrich(
        self,
        rec: Record
    ) -> dict[str, Any]:
        """
        Enrich preprint record with metadata and published version info.
        
        Parameters:
        rec (Record): The preprint record to enrich.
        
        Returns:
        dict: Preprint enrichment report.
        """
        report: dict[str, Any] = {}
        
        preprint_source = rec.preprint_source
        if not preprint_source:
            return report
        
        # Apply rate limiting before fetching preprint metadata
        rate_limiter = RATE_LIMITERS.get("preprints")
        if rate_limiter:
            await rate_limiter.acquire()
        
        # Fetch preprint metadata
        preprint_data, preprint_raw = await fetch_preprint_metadata(rec, preprint_source)
        log.debug(
            "fetched_preprint_metadata",
            doi=rec.doi_norm,
            preprint_source=preprint_source,
            has_abstract=bool(preprint_data and preprint_data.get("abstract")),
            has_published_doi=bool(preprint_data and preprint_data.get("published_doi")),
        )
        
        if not preprint_data:
            log.warning(
                "preprint_metadata_fetch_failed",
                doi=rec.doi_norm,
                preprint_source=preprint_source,
            )
            return report
        
        # Set abstract if available and not already set
        if preprint_data.get("abstract") and not rec.abstract_text:
            rec.abstract_text = preprint_data["abstract"]
            rec.abstract_source = preprint_source
            report["abstract_set"] = True
        
        # Handle published version if found
        published_doi = preprint_data.get("published_doi")
        if published_doi and published_doi != "NA":
            rec.published_doi = published_doi
            rec.published_journal = preprint_data.get("published_journal")
            rec.published_url = preprint_data.get("published_url")
            rec.published_fulltext_url = preprint_data.get("published_fulltext_url")
            
            # Process preprint-to-published linking
            published_version_record_id, link_created, process_message = (
                process_preprint_to_published_linking(
                    rec,
                    published_doi,
                    preprint_source,
                    {"discovered_via": "preprint_metadata", "preprint_raw": preprint_raw},
                )
            )
            
            report["published_version"] = {
                "doi": published_doi,
                "journal": rec.published_journal,
                "status": "found",
                "published_version_record_id": published_version_record_id,
                "link_created": link_created,
                "message": process_message,
            }
            
            log.info(
                "preprint_published_version_found",
                preprint_doi=rec.doi_norm,
                published_doi=published_doi,
                published_journal=rec.published_journal,
                link_created=link_created,
            )
        
        # Store provenance
        if preprint_raw:
            report["raw_data"] = preprint_raw
        
        log.info(
            "preprint_metadata_enriched",
            doi=rec.doi_norm,
            preprint_source=preprint_source,
            has_abstract=bool(rec.abstract_text),
            has_published_doi=bool(rec.published_doi),
        )
        
        return report


class OpenAccessEnricher:
    """Strategy pattern for Open Access enrichment via Unpaywall."""
    
    async def enrich(
        self,
        rec: Record
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """
        Enrich record with Open Access information.
        
        Parameters:
        rec (Record): The record to enrich.
        
        Returns:
        tuple: (OA report dict, raw provenance data)
        """
        # Apply rate limiting before fetching unpaywall data
        rate_limiter = RATE_LIMITERS.get("unpaywall")
        if rate_limiter:
            await rate_limiter.acquire()
        
        upw, upw_raw = await fetch_unpaywall(rec)
        
        if upw:
            rec.is_oa = upw.get("is_oa")
            rec.oa_status = upw.get("oa_status")
            rec.license = upw.get("license")
            rec.oa_pdf_url = upw.get("oa_pdf_url")
            
            report = {
                "status": "success",
                "is_oa": rec.is_oa,
                "oa_status": rec.oa_status,
                "has_pdf": bool(rec.oa_pdf_url),
                "reason": "Successfully retrieved OA status",
            }
            
            log.info(
                "oa_info_retrieved",
                doi=rec.doi_norm,
                is_oa=rec.is_oa,
                oa_status=rec.oa_status,
                has_pdf=bool(rec.oa_pdf_url),
            )
        else:
            report = {
                "status": "failed",
                "reason": "API returned no data or timed out",
            }
            log.warning("oa_check_failed", doi=rec.doi_norm)
        
        return report, upw_raw


async def _detect_and_mark_preprint(rec: Record) -> dict[str, Any]:
    """
    Detect if record is a preprint and mark it accordingly.
    
    Parameters:
    rec (Record): The record to check.
    
    Returns:
    dict: Preprint detection report.
    """
    preprint_source = detect_preprint_source(rec)
    
    if preprint_source:
        rec.is_preprint = True
        rec.preprint_source = preprint_source
        
        log.info(
            "preprint_detected",
            record_id=rec.id,
            doi=rec.doi_norm,
            preprint_source=preprint_source,
            source_title=rec.source_title,
        )
        
        return {
            "is_preprint": True,
            "source": preprint_source,
            "status": "success",
        }
    else:
        rec.is_preprint = False
        rec.preprint_source = None
        
        log.info(
            "not_a_preprint",
            record_id=rec.id,
            doi=rec.doi_norm,
            source_title=rec.source_title,
        )
        
        return {
            "is_preprint": False,
            "status": "success",
        }


async def enrich_record(rec: Record, clients: dict[str, Any]) -> Record:
    """
    Enrich a record with abstract and OA info, keeping provenance for each service.
    
    This refactored version uses:
    - Strategy pattern for different enrichment types (preprint, abstract, OA)
    - Chain of Responsibility for abstract retrieval with fallback
    - Clear separation of concerns for better maintainability
    
    Parameters:
    rec (Record): The record to enrich.
    clients (dict[str, Any]): Dictionary of API clients (e.g., {'s2': client}).
    
    Returns:
    Record: The enriched record with detailed enrichment_report.
    """
    log.debug("enrichment_started", doi=rec.doi_norm, title=rec.title[:200])

    # Initialize enrichment report
    enrichment_report: dict[str, Any] = {
        "record_title": rec.title[:80] + "..." if len(rec.title) > 80 else rec.title,
        "doi": rec.doi_norm,
        "preprint_detection": {},
        "abstract_attempts": [],
        "oa_check": {},
        "final_status": {},
    }

    # Step 1: Detect and mark preprint
    enrichment_report["preprint_detection"] = await _detect_and_mark_preprint(rec)

    # Step 2: Handle preprint-specific enrichment
    preprint_provenance: dict[str, Any] = {}
    if rec.is_preprint and rec.preprint_source:
        preprint_enricher = PreprintEnricher()
        preprint_report = await preprint_enricher.enrich(rec)
        
        # Update enrichment report with preprint-specific info
        if preprint_report.get("abstract_set"):
            enrichment_report["abstract_attempts"].append({
                "source": rec.preprint_source,
                "status": "success",
                "reason": "Abstract retrieved successfully from preprint source",
            })
        
        if preprint_report.get("published_version"):
            enrichment_report["preprint_detection"]["published_version"] = (
                preprint_report["published_version"]
            )
        
        if preprint_report.get("raw_data"):
            preprint_provenance[rec.preprint_source] = preprint_report["raw_data"]
        
        # If no abstract from preprint, continue to standard sources
        if not rec.abstract_text:
            log.debug(
                "preprint_no_abstract",
                doi=rec.doi_norm,
                preprint_source=rec.preprint_source,
            )

    # Step 3: Try standard abstract sources
    # Define enrichment sources in order of precedence
    abstract_sources = [
        EnrichmentSource(
            name="Semantic Scholar",
            key="s2",
            fetcher=fetch_semanticscholar,
            requires_client=True,
        ),
        EnrichmentSource(
            name="Crossref",
            key="crossref",
            fetcher=fetch_crossref,
            requires_client=False,
        ),
        EnrichmentSource(
            name="OpenAlex",
            key="openalex",
            fetcher=fetch_openalex,
            requires_client=False,
        ),
        EnrichmentSource(
            name="EuropePMC",
            key="epmc",
            fetcher=fetch_europepmc,
            requires_client=False,
        ),
        EnrichmentSource(
            name="PubMed",
            key="pubmed",
            fetcher=fetch_pubmed,
            requires_client=False,
        ),
    ]
    
    abstract_pipeline = AbstractEnrichmentPipeline(abstract_sources)
    abstract_attempts, abstract_provenance = await abstract_pipeline.enrich(rec, clients)
    
    enrichment_report["abstract_attempts"].extend(abstract_attempts)

    # Step 4: Open Access enrichment
    oa_enricher = OpenAccessEnricher()
    oa_report, oa_provenance = await oa_enricher.enrich(rec)
    enrichment_report["oa_check"] = oa_report

    # Step 5: Combine all provenance data
    all_provenance = {**preprint_provenance, **abstract_provenance}
    if oa_provenance:
        all_provenance["unpaywall"] = oa_provenance
    rec.provenance.update(all_provenance)

    # Step 6: Generate final status summary and track abstract retrieval failure reasons
    if not rec.abstract_text:
        # Compile reasons why abstract wasn't retrieved
        failure_reasons = []
        for attempt in enrichment_report["abstract_attempts"]:
            if attempt["status"] == "failed":
                failure_reasons.append(f"{attempt['source']}: {attempt['reason']}")
        
        if failure_reasons:
            rec.abstract_no_retrieval_reason = "; ".join(failure_reasons)
        else:
            rec.abstract_no_retrieval_reason = "No enrichment sources attempted"
        
        log.warning(
            "abstract_not_retrieved",
            doi=rec.doi_norm,
            reasons=rec.abstract_no_retrieval_reason,
        )
    else:
        rec.abstract_no_retrieval_reason = None  # Clear if abstract was found
    
    enrichment_report["final_status"] = {
        "abstract_found": bool(rec.abstract_text),
        "abstract_source": rec.abstract_source if rec.abstract_text else None,
        "abstract_no_retrieval_reason": rec.abstract_no_retrieval_reason,
        "is_oa": rec.is_oa,
        "oa_status": rec.oa_status,
        "is_preprint": rec.is_preprint,
        "preprint_source": rec.preprint_source,
        "has_published_version": bool(rec.published_doi),
    }

    # Store the report in the record for later retrieval
    rec.enrichment_report = enrichment_report

    log.debug(
        "enrichment_completed",
        doi=rec.doi_norm,
        has_abstract=bool(rec.abstract_text),
        abstract_source=rec.abstract_source,
        abstract_no_retrieval_reason=rec.abstract_no_retrieval_reason,
        is_oa=rec.is_oa,
        oa_status=rec.oa_status,
        is_preprint=rec.is_preprint,
        preprint_source=rec.preprint_source,
        has_published_version=bool(rec.published_doi),
    )

    return rec


def format_enrichment_report(rec: Record) -> str:
    """
    Format the enrichment report for a record into a readable string.

    Parameters:
    rec (Record): The enriched record with enrichment_report attribute.

    Returns:
    str: A formatted multi-line string with enrichment details.
    """
    if not hasattr(rec, "enrichment_report"):
        return f"No enrichment report available for: {rec.title[:60]}"

    report = rec.enrichment_report
    lines = []

    # Header
    lines.append("=" * 80)
    lines.append(f"Record: {report['record_title']}")
    lines.append(f"DOI: {report['doi']}")
    lines.append("-" * 80)

    # Preprint detection
    preprint_info = report["preprint_detection"]
    if preprint_info["is_preprint"]:
        lines.append(f"✓ Preprint detected: {preprint_info['source']}")
        if "published_version" in preprint_info:
            pub_ver = preprint_info["published_version"]
            lines.append(f"  → Published version found: {pub_ver['doi']}")
            if pub_ver.get("journal"):
                lines.append(f"     Journal: {pub_ver['journal']}")
    else:
        lines.append("○ Not a preprint")

    # Abstract attempts
    lines.append("")
    lines.append("Abstract retrieval attempts:")
    if not report["abstract_attempts"]:
        lines.append("  (No attempts made - preprint abstract used)")
    else:
        for attempt in report["abstract_attempts"]:
            status_icon = "✓" if attempt["status"] == "success" else "✗"
            lines.append(f"  {status_icon} {attempt['source']}: {attempt['reason']}")

    # OA check
    lines.append("")
    oa_info = report["oa_check"]
    if oa_info["status"] == "success":
        if oa_info["is_oa"]:
            pdf_status = "with PDF" if oa_info["has_pdf"] else "no PDF"
            lines.append(f"✓ Open Access: {oa_info['oa_status']} ({pdf_status})")
        else:
            lines.append("○ Not Open Access")
    else:
        lines.append(f"✗ OA check failed: {oa_info['reason']}")

    # Final summary
    lines.append("")
    lines.append("Final Status:")
    final = report["final_status"]
    if final["abstract_found"]:
        lines.append(f"  • Abstract: ✓ (from {final['abstract_source']})")
    else:
        lines.append("  • Abstract: ✗ (not found from any source)")
        if final.get("abstract_no_retrieval_reason"):
            lines.append(f"    Reason: {final['abstract_no_retrieval_reason']}")

    if final["is_preprint"]:
        lines.append(f"  • Preprint: ✓ ({final['preprint_source']})")
        if final["has_published_version"]:
            lines.append("  • Published version: ✓")

    if final["is_oa"]:
        lines.append(f"  • Open Access: ✓ ({final['oa_status']})")
    else:
        lines.append("  • Open Access: ✗")

    lines.append("=" * 80)
    lines.append("")

    return "\n".join(lines)
