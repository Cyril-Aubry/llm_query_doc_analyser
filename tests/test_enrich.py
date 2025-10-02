import pytest

from src.llm_query_doc_analyser.core.models import Record
from src.llm_query_doc_analyser.enrich.orchestrator import enrich_record


@pytest.mark.asyncio
async def test_enrich_record(monkeypatch):
    # Patch all API clients to return dummy data
    async def dummy(*args, **kwargs):
        return ({'abstract': 'test abstract', 'title': 'Test Title'}, {'raw': 'json'})

    monkeypatch.setattr('src.llm_query_doc_analyser.enrich.crossref.fetch_crossref', dummy)
    monkeypatch.setattr('src.llm_query_doc_analyser.enrich.unpaywall.fetch_unpaywall', dummy)
    monkeypatch.setattr('src.llm_query_doc_analyser.enrich.openalex.fetch_openalex', dummy)
    monkeypatch.setattr('src.llm_query_doc_analyser.enrich.europepmc.fetch_europepmc', dummy)
    monkeypatch.setattr('src.llm_query_doc_analyser.enrich.pubmed.fetch_pubmed', dummy)
    monkeypatch.setattr('src.llm_query_doc_analyser.enrich.semanticscholar.fetch_semanticscholar', dummy)
    monkeypatch.setattr('src.llm_query_doc_analyser.enrich.arxiv.fetch_arxiv', dummy)

    rec = Record(title='Test', doi_raw='10.1/abc', doi_norm='10.1/abc')
    result = await enrich_record(rec, clients={})

    # Validate that the abstract_text is updated correctly
    assert result.abstract_text is not None
    assert result.abstract_text == 'test abstract'
