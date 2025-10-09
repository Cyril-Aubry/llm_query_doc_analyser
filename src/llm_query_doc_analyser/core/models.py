from typing import Any

from pydantic import BaseModel, Field


class Record(BaseModel):
    id: int | None = None
    title: str
    doi_raw: str | None = None
    doi_norm: str | None = None
    pub_date: str | None = None
    import_datetime: str | None = None
    
    # Citation metrics
    total_citations: int | None = None
    citations_per_year: float | None = None
    
    # Bibliographic
    authors: str | None = None
    source_title: str | None = None

    # Enrichment
    enrichment_datetime: str | None = None
    abstract_text: str | None = None
    abstract_source: str | None = None  # 's2'|'crossref'|'openalex'|'epmc'|'pubmed'
    abstract_no_retrieval_reason: str | None = None  # Reason why abstract was not retrieved

    # External IDs
    pmid: str | None = None
    arxiv_id: str | None = None

    # OA + PDF
    is_oa: bool | None = None
    oa_status: str | None = None
    license: str | None = None
    oa_pdf_url: str | None = None
    
    # Pre-print Tracking (no bidirectional fields - use relation table)
    is_preprint: bool | None = None
    preprint_source: str | None = None  # 'arXiv'|'medRxiv'|'bioRxiv'|'Preprints'
    
    # Published version metadata (if preprint has been published)
    published_doi: str | None = None
    published_journal: str | None = None
    published_url: str | None = None
    published_fulltext_url: str | None = None

    provenance: dict[str, Any] = Field(default_factory=dict)
    
    # Enrichment report (for detailed tracking of enrichment process)
    enrichment_report: dict[str, Any] = Field(default_factory=dict)
