"""Pre-print provider detection and linking utilities.

This module provides functionality to:
1. Detect pre-print sources from research article metadata
2. Extract published version information from enrichment API responses
3. Maintain bidirectional links between pre-print and published versions
"""

from typing import Any

from ..core.models import Record
from ..utils.log import get_logger

log = get_logger(__name__)

# Pre-print provider patterns (case-insensitive matching)
PREPRINT_PROVIDERS = {
    "arxiv": {
        "source_patterns": ["arxiv", "ar xiv"],
        "issn_patterns": [],  # arXiv doesn't have ISSN
    },
    "medrxiv": {
        "source_patterns": ["medrxiv", "med rxiv"],
        "issn_patterns": [],
    },
    "biorxiv": {
        "source_patterns": ["biorxiv", "bio rxiv"],
        "issn_patterns": [],
    },
    "preprints": {
        "source_patterns": ["preprints", "preprints.org"],
        "issn_patterns": [],
    },
}


def detect_preprint_source(rec: Record) -> str | None:
    """
    Detect if a record is from a pre-print provider based on source_title.

    Args:
        rec: Research article record

    Returns:
        Pre-print provider name (lowercase) or None if not a preprint
    """
    if not rec.source_title:
        # If arxiv_id is present, assume it's an arXiv preprint
        if rec.arxiv_id:
            log.debug("preprint_detected_by_arxiv_id", arxiv_id=rec.arxiv_id)
            return "arxiv"
        return None

    source_lower = rec.source_title.lower().strip()

    for provider, patterns in PREPRINT_PROVIDERS.items():
        for pattern in patterns["source_patterns"]:
            if pattern in source_lower:
                log.debug(
                    "preprint_detected", 
                    provider=provider, 
                    source_title=rec.source_title,
                    doi=rec.doi_norm
                )
                return provider

    return None


def extract_published_doi_from_crossref(crossref_data: dict[str, Any]) -> str | None:
    """
    Extract published version DOI from Crossref API response.

    Crossref provides 'relation' field with related works including published versions.
    
    Args:
        crossref_data: Raw Crossref API response

    Returns:
        Published version DOI or None if not found
    """
    if not crossref_data:
        return None

    message = crossref_data.get("message", {})
    relations = message.get("relation", {})

    # Check for 'is-preprint-of' relation
    if "is-preprint-of" in relations:
        preprint_of = relations["is-preprint-of"]
        if isinstance(preprint_of, list) and len(preprint_of) > 0:
            published_doi = preprint_of[0].get("id")
            if published_doi:
                log.info(
                    "published_version_found_in_crossref",
                    published_doi=published_doi,
                    source="crossref"
                )
                return published_doi

    # Check for 'has-version' relation
    if "has-version" in relations:
        has_version = relations["has-version"]
        if isinstance(has_version, list):
            for version in has_version:
                version_type = version.get("type")
                if version_type in ["vor", "am", "published"]:  # Version of Record
                    published_doi = version.get("id")
                    if published_doi:
                        log.info(
                            "published_version_found_in_crossref",
                            published_doi=published_doi,
                            version_type=version_type,
                            source="crossref"
                        )
                        return published_doi

    return None


def extract_published_doi_from_openalex(openalex_data: dict[str, Any]) -> str | None:
    """
    Extract published version DOI from OpenAlex API response.

    OpenAlex tracks multiple versions of works in the 'related_works' field.
    
    Args:
        openalex_data: Raw OpenAlex API response

    Returns:
        Published version DOI or None if not found
    """
    if not openalex_data:
        return None

    # Check primary_location and other locations for published version
    locations = [openalex_data.get("primary_location")]
    locations.extend(openalex_data.get("locations", []))

    for location in locations:
        if not location:
            continue

        # Check if this is a published version (not a preprint repository)
        version = location.get("version")
        source = location.get("source", {})
        source_type = source.get("type")

        # Published versions typically have version 'publishedVersion' 
        # and source_type 'journal'
        if version == "publishedVersion" and source_type == "journal":
            # Get DOI from landing page URL or doi field
            landing_page = location.get("landing_page_url", "")
            if "doi.org" in landing_page:
                # Extract DOI from URL
                doi_parts = landing_page.split("doi.org/")
                if len(doi_parts) > 1:
                    published_doi = doi_parts[1]
                    log.info(
                        "published_version_found_in_openalex",
                        published_doi=published_doi,
                        source="openalex"
                    )
                    return published_doi

    # Check related_works for published version
    related_works = openalex_data.get("related_works", [])
    for work_url in related_works:
        # OpenAlex work URLs contain the DOI
        if "doi.org" in work_url:
            doi_parts = work_url.split("doi.org/")
            if len(doi_parts) > 1:
                published_doi = doi_parts[1]
                log.info(
                    "published_version_found_in_openalex_related",
                    published_doi=published_doi,
                    source="openalex"
                )
                return published_doi

    return None


def extract_published_doi_from_europepmc(europepmc_data: dict[str, Any]) -> str | None:
    """
    Extract published version DOI from EuropePMC API response.

    EuropePMC tracks relationships between preprints and published articles.
    
    Args:
        europepmc_data: Raw EuropePMC API response

    Returns:
        Published version DOI or None if not found
    """
    if not europepmc_data:
        return None

    results = europepmc_data.get("resultList", {}).get("result", [])
    if not results:
        return None

    result = results[0]

    # Check for published DOI in the result
    # EuropePMC provides 'pmcid' and 'doi' fields
    # For preprints, check if there's a published version DOI
    relationships = result.get("relationshipList", {}).get("relationship", [])
    
    for rel in relationships:
        rel_type = rel.get("type", "").lower()
        if "published" in rel_type or "version" in rel_type:
            published_doi = rel.get("doi")
            if published_doi:
                log.info(
                    "published_version_found_in_europepmc",
                    published_doi=published_doi,
                    source="europepmc"
                )
                return published_doi

    return None


def extract_published_doi_from_pubmed(pubmed_data: dict[str, Any]) -> str | None:
    """
    Extract published version DOI from PubMed API response.

    PubMed tracks preprint-to-publication links via CommentsCorrectionsList.
    
    Args:
        pubmed_data: Raw PubMed API response

    Returns:
        Published version DOI or None if not found
    """
    if not pubmed_data:
        return None

    # PubMed returns XML, check if parsed data contains linkout DOIs
    xml_content = pubmed_data.get("xml", "")
    
    if not xml_content:
        return None

    # Look for ArticleIdList with IdType="doi" for related published article
    import re
    
    # Pattern to find DOI in PubMed XML
    doi_pattern = re.compile(r'<ArticleId IdType="doi">([^<]+)</ArticleId>')
    matches = doi_pattern.findall(xml_content)
    
    # Look for CommentsCorrectionsList indicating publication relationship
    if "PublishedInto" in xml_content or "RepublishedFrom" in xml_content:
        for doi_match in matches:
            if doi_match:
                log.info(
                    "published_version_found_in_pubmed",
                    published_doi=doi_match,
                    source="pubmed"
                )
                return doi_match

    return None


def extract_published_doi_from_provenance(provenance: dict[str, Any]) -> tuple[str | None, str | None]:
    """
    Extract published version DOI from all enrichment provenance data.

    Args:
        provenance: Dictionary of enrichment API responses

    Returns:
        Tuple of (published_doi, source) or (None, None) if not found
    """
    # Try each source in priority order
    sources_to_check = [
        ("crossref", extract_published_doi_from_crossref),
        ("openalex", extract_published_doi_from_openalex),
        ("europepmc", extract_published_doi_from_europepmc),
        ("pubmed", extract_published_doi_from_pubmed),
    ]

    for source_name, extractor_func in sources_to_check:
        source_data = provenance.get(source_name)
        if source_data:
            published_doi = extractor_func(source_data)
            if published_doi:
                return published_doi, source_name

    return None, None
