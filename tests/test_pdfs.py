from llm_query_doc_analyser.core.models import Record
from llm_query_doc_analyser.pdfs.resolve import resolve_pdf_candidates


def test_resolve_pdf_candidates() -> None:
    rec = Record(
        title="Test",
        doi_raw="10.1/abc",
        doi_norm="10.1/abc",
        oa_pdf_url="http://example.com/test.pdf",
    )
    candidates = resolve_pdf_candidates(rec)
    assert any(c["url"] == "http://example.com/test.pdf" for c in candidates)
