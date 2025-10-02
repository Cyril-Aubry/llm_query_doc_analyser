from pydantic import BaseModel, Field


class Record(BaseModel):
    id: int | None = None
    title: str
    doi_raw: str | None = None
    doi_norm: str | None = None
    pub_date: str | None = None

    # Enrichment
    abstract_text: str | None = None
    abstract_source: str | None = None  # 's2'|'crossref'|'openalex'|'epmc'|'pubmed'

    # External IDs
    pmid: str | None = None
    pmcid: str | None = None
    openalex_id: str | None = None
    s2_paper_id: str | None = None
    arxiv_id: str | None = None

    # OA + PDF
    is_oa: bool | None = None
    oa_status: str | None = None
    license: str | None = None
    oa_pdf_url: str | None = None
    pdf_status: str | None = None       # 'downloaded'|'restricted'|'unavailable'
    pdf_local_path: str | None = None
    manual_url_publisher: str | None = None
    manual_url_repository: str | None = None

    # Scoring
    rule_score: float | None = None
    embed_score: float | None = None
    llm_score: float | None = None
    relevance_score: float | None = None
    match_reasons: list[str] = Field(default_factory=list)

    provenance: dict[str, dict] = Field(default_factory=dict)
