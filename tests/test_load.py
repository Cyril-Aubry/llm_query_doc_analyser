
import pandas as pd

from src.llm_query_doc_analyser.io_.load import load_records


def test_load_records(tmp_path):
    df = pd.DataFrame({'Title': ['A', 'B'], 'DOI': ['10.1/abc', '10.2/def'], 'Publication Date': ['2020-07-20', '2021-06-21']}).astype({'Publication Date': str})
    f = tmp_path / 'test.csv'
    df.to_csv(f, index=False)
    records = load_records(f)
    assert len(records) == 2
    assert records[0].title == 'A'
    assert records[0].doi_norm == '10.1/abc'
