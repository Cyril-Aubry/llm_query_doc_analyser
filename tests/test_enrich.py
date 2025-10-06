from typing import Any

import pytest

from llm_query_doc_analyser.core.models import Record
from llm_query_doc_analyser.enrich.orchestrator import enrich_record


async def test_enrich_record(monkeypatch: pytest.MonkeyPatch) -> None:
    # Accept any args to match real call sites (fetch_xxx(rec), etc.)
    async def dummy(*args: tuple[Any], **kwargs: dict[Any, Any]) -> tuple[dict[str, str], dict[str, str]]:
        return ({"abstract": "test abstract", "title": "Test Title"}, {"raw": "json"})

    # Patch the names used inside orchestrator.py
    monkeypatch.setattr("llm_query_doc_analyser.enrich.orchestrator.fetch_crossref", dummy)
    monkeypatch.setattr("llm_query_doc_analyser.enrich.orchestrator.fetch_unpaywall", dummy)
    monkeypatch.setattr("llm_query_doc_analyser.enrich.orchestrator.fetch_openalex", dummy)
    monkeypatch.setattr("llm_query_doc_analyser.enrich.orchestrator.fetch_europepmc", dummy)
    monkeypatch.setattr("llm_query_doc_analyser.enrich.orchestrator.fetch_pubmed", dummy)
    monkeypatch.setattr("llm_query_doc_analyser.enrich.orchestrator.fetch_semanticscholar", dummy)
    monkeypatch.setattr("llm_query_doc_analyser.enrich.orchestrator.fetch_arxiv", dummy)

    rec = Record(title="Test", doi_raw="10.1/abc", doi_norm="10.1/abc")

    # clients is empty => s2 branch is skipped; others are called with (rec)
    result = await enrich_record(rec, clients={})

    assert result.abstract_text == "test abstract"
    assert result.abstract_source in {"crossref", "openalex", "epmc", "pubmed", "arxiv"}  # whichever hit first
    assert "unpaywall" in result.provenance  # since we patched fetch_unpaywall too