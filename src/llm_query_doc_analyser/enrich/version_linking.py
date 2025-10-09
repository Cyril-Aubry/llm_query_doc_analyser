"""Version linking service for pre-print ↔ published article relationships.

This module handles:
1. Creating new research article records for published versions
2. Creating relations in the article_versions table (no bidirectional FK fields)
3. Preventing duplicate entries
4. Maintaining data provenance in the relation table
"""

from datetime import UTC, datetime
from typing import Any

from ..core.hashing import normalize_doi
from ..core.models import Record
from ..core.store import (
    create_article_version_relation,
    get_published_version_id,
    get_records,
    insert_record,
)
from ..utils.log import get_logger

log = get_logger(__name__)


def find_record_by_doi(doi_norm: str) -> Record | None:
    """
    Find a research article record by normalized DOI.

    Args:
        doi_norm: Normalized DOI to search for

    Returns:
        Record if found, None otherwise
    """
    if not doi_norm:
        return None

    records = get_records()
    for rec in records:
        if rec.doi_norm and rec.doi_norm == doi_norm:
            return rec
    return None


def create_published_version_record(
    preprint_rec: Record,
    published_doi: str,
    discovery_source: str | None = None,
    discovery_metadata: dict[str, Any] | None = None
) -> tuple[str, Record] | None:
    """
    Create a new research article record for a published version.

    The new record inherits metadata from the preprint but marks it as
    a published article (not a preprint). No bidirectional FK fields - 
    the relation is managed via the article_versions table.

    Args:
        preprint_rec: Original pre-print record
        published_doi: DOI of the published version
        discovery_source: API source that provided the version link
        discovery_metadata: Optional metadata about the discovery

    Returns:
        New published version Record, or None if creation failed
    """
    published_doi_norm = normalize_doi(published_doi)
    
    if not published_doi_norm:
        log.warning("invalid_published_doi", published_doi=published_doi)
        return None
    
    # Check if published version already exists
    existing = find_record_by_doi(published_doi_norm)
    if existing:
        log.info(
            "published_version_already_exists",
            published_doi=published_doi_norm,
            existing_id=existing.id,
            preprint_id=preprint_rec.id
        )
        return ("Existing", existing)

    # Create new record for published version
    # Start with preprint metadata, but mark as NOT a preprint
    published_rec = Record(
        title=preprint_rec.title,  # Will be updated during enrichment
        doi_raw=published_doi,
        doi_norm=published_doi_norm,
        pub_date=preprint_rec.pub_date,  # May be updated during enrichment
        authors=preprint_rec.authors,
        source_title=None,  # Will be filled during enrichment
        is_preprint=False,
        preprint_source=None,
        import_datetime=datetime.now(UTC).isoformat(),
    )

    try:
        # Insert the new published version record
        published_id = insert_record(published_rec)
        published_rec.id = published_id
        
        log.info(
            "published_version_created",
            published_id=published_id,
            published_doi=published_doi_norm,
            preprint_id=preprint_rec.id,
            preprint_doi=preprint_rec.doi_norm,
            discovery_source=discovery_source
        )
        
        return ("New", published_rec)

    except Exception as e:
        log.error(
            "failed_to_create_published_version",
            published_doi=published_doi_norm,
            preprint_id=preprint_rec.id,
            error=str(e)
        )
        return None


def link_preprint_to_published(
    preprint_rec: Record,
    published_rec: Record,
    discovery_source: str,
    discovery_metadata: dict[str, Any] | None = None
) -> bool:
    """
    Create relation between pre-print and published records in article_versions table.

    This replaces the old bidirectional FK approach with a proper relation table.

    Args:
        preprint_rec: Pre-print record
        published_rec: Published version record
        discovery_source: API source that provided the version link
        discovery_metadata: Optional metadata about the discovery

    Returns:
        True if linking succeeded, False otherwise
    """
    if not preprint_rec.id or not published_rec.id:
        log.error(
            "cannot_link_versions_missing_ids",
            preprint_id=preprint_rec.id,
            published_id=published_rec.id
        )
        return False

    try:
        relation_id = create_article_version_relation(
            preprint_id=preprint_rec.id,
            published_id=published_rec.id,
            discovery_source=discovery_source,
            discovery_metadata=discovery_metadata
        )
        
        if relation_id:
            log.info(
                "preprint_published_linked_via_relation",
                relation_id=relation_id,
                preprint_id=preprint_rec.id,
                preprint_doi=preprint_rec.doi_norm,
                published_id=published_rec.id,
                published_doi=published_rec.doi_norm,
                discovery_source=discovery_source
            )
            return True
        else:
            log.warning(
                "failed_to_create_version_relation",
                preprint_id=preprint_rec.id,
                published_id=published_rec.id
            )
            return False

    except Exception as e:
        log.error(
            "failed_to_link_versions",
            preprint_id=preprint_rec.id,
            published_id=published_rec.id,
            error=str(e)
        )
        return False


def process_preprint_to_published_linking(
    preprint_rec: Record,
    published_doi: str,
    discovery_source: str,
    discovery_metadata: dict[str, Any] | None = None
) -> tuple[int| None, bool, str]:
    """
    Complete workflow to link a pre-print to its published version.

    This function:
    1. Checks if published version exists (by normalized DOI)
    2. Creates new record if not found (inheriting metadata from pre-print)
    3. Creates relation in article_versions table (no bidirectional FK fields)
    4. Handles edge cases and errors

    Args:
        preprint_rec: Pre-print record
        published_doi: DOI of published version
        discovery_source: API source that provided the link
        discovery_metadata: Optional metadata about the discovery

    Returns:
        Tuple of (success: bool, message: str)
    """
    if not published_doi:
        return None, False, "No published DOI provided"

    # Normalize the published DOI
    published_doi_norm = normalize_doi(published_doi)
    
    if not published_doi_norm:
        log.warning(
            "invalid_published_doi",
            published_doi=published_doi,
            preprint_id=preprint_rec.id
        )
        return None, False, f"Invalid published DOI: {published_doi}"

    # Check if this link already exists (via relation table)
    if preprint_rec.id:
        existing_published_id = get_published_version_id(preprint_rec.id)
        if existing_published_id:
            log.debug(
                "version_link_already_exists",
                preprint_id=preprint_rec.id,
                published_id=existing_published_id
            )
            return existing_published_id, True, "Link already exists"

    # Find or create published version record
    published_rec: Record | None = find_record_by_doi(published_doi_norm)
    
    if not published_rec:
        # Create new record for published version
        is_new, published_rec = create_published_version_record(
            preprint_rec,
            published_doi,
            discovery_source,
            discovery_metadata
        ) or (None, None)
        
        if not published_rec:
            return None, False, "Failed to create published version record"
    
    # Create relation in article_versions table
    success = link_preprint_to_published(
        preprint_rec,
        published_rec,
        discovery_source,
        discovery_metadata
    )
    
    if success and is_new == "New":
        return published_rec.id, True, f"Successfully linked preprint to new published version record(ID: {published_rec.id})"
    elif success and is_new == "Existing":
        return published_rec.id, True, f"Successfully linked preprint to existing published version record(ID: {published_rec.id})"
    else:
        return None, False, "Failed to establish version link"


# Statistics are now provided by get_version_linking_stats() in core/store.py
