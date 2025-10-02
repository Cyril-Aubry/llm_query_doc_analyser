from src.llm_query_doc_analyser.core.hashing import normalize_doi, sha1_bytes

def test_normalize_doi():
    assert normalize_doi('https://doi.org/10.1000/xyz') == '10.1000/xyz'
    assert normalize_doi('10.1000/xyz') == '10.1000/xyz'
    assert normalize_doi('') is None
    assert normalize_doi(None) is None

def test_sha1_bytes():
    assert sha1_bytes(b'abc') == 'a9993e364706816aba3e25717850c26c9cd0d89d'
