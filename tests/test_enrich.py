from typing import Any

import pytest

from llm_query_doc_analyser.core.models import Record
from llm_query_doc_analyser.enrich.orchestrator import enrich_record, format_enrichment_report


async def test_enrich_record(monkeypatch: pytest.MonkeyPatch) -> None:
    # Accept any args to match real call sites (fetch_xxx(rec), etc.)
    async def dummy(*args: tuple[Any], **kwargs: dict[Any, Any]) -> tuple[dict[str, str], dict[str, str]]:
        return ({"abstract": "test abstract", "title": "Test Title"}, {"raw": "json"})

    # Patch the names used inside orchestrator.py
    monkeypatch.setattr("llm_query_doc_analyser.enrich.orchestrator.detect_preprint_source", lambda rec: None)
    monkeypatch.setattr("llm_query_doc_analyser.enrich.orchestrator.fetch_crossref", dummy)
    monkeypatch.setattr("llm_query_doc_analyser.enrich.orchestrator.fetch_unpaywall", dummy)
    monkeypatch.setattr("llm_query_doc_analyser.enrich.orchestrator.fetch_openalex", dummy)
    monkeypatch.setattr("llm_query_doc_analyser.enrich.orchestrator.fetch_europepmc", dummy)
    monkeypatch.setattr("llm_query_doc_analyser.enrich.orchestrator.fetch_pubmed", dummy)
    monkeypatch.setattr("llm_query_doc_analyser.enrich.orchestrator.fetch_semanticscholar", dummy)

    rec = Record(title="Test", doi_raw="10.1/abc", doi_norm="10.1/abc")

    # clients is empty => s2 branch is skipped; others are called with (rec)
    result = await enrich_record(rec, clients={})

    assert result.abstract_text == "test abstract"
    assert result.abstract_source in {"crossref", "openalex", "epmc", "pubmed"}  # whichever hit first
    assert "unpaywall" in result.provenance  # since we patched fetch_unpaywall too
    
    # Check that enrichment_report was created
    assert hasattr(result, "enrichment_report")
    assert "record_title" in result.enrichment_report
    assert "abstract_attempts" in result.enrichment_report
    assert "final_status" in result.enrichment_report


def test_format_enrichment_report() -> None:
    """Test the enrichment report formatting function."""
    rec = Record(
        title="Test Article",
        doi_raw="10.1/abc",
        doi_norm="10.1/abc",
        abstract_text="Test abstract",
        abstract_source="crossref",
        is_oa=True,
        oa_status="gold",
        is_preprint=False,
    )
    
    # Manually set enrichment report
    rec.enrichment_report = {
        "record_title": "Test Article",
        "doi": "10.1/abc",
        "preprint_detection": {
            "is_preprint": False,
            "status": "success",
        },
        "abstract_attempts": [
            {
                "source": "Crossref",
                "status": "success",
                "reason": "Abstract retrieved successfully",
            }
        ],
        "oa_check": {
            "status": "success",
            "is_oa": True,
            "oa_status": "gold",
            "has_pdf": False,
            "reason": "Successfully retrieved OA status",
        },
        "final_status": {
            "abstract_found": True,
            "abstract_source": "crossref",
            "is_oa": True,
            "oa_status": "gold",
            "is_preprint": False,
            "preprint_source": None,
            "has_published_version": False,
        },
    }
    
    report = format_enrichment_report(rec)
    assert isinstance(report, str)
    assert "Test Article" in report
    assert "10.1/abc" in report
    assert "Crossref" in report
    assert "gold" in report
    assert "Not a preprint" in report