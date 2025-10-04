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

    # External IDs
    pmid: str | None = None
    arxiv_id: str | None = None

    # OA + PDF
    is_oa: bool | None = None
    oa_status: str | None = None
    license: str | None = None
    oa_pdf_url: str | None = None

    # Scoring
    match_reasons: list[str] = Field(default_factory=list)

    provenance: dict[str, dict] = Field(default_factory=dict)
