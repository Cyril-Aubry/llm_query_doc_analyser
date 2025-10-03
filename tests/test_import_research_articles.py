# tests/test_import_research_articles.py
import sqlite3
from pathlib import Path

import pytest

from llm_query_doc_analyser.core.store import get_records, init_db, upsert_record
from llm_query_doc_analyser.io_.load import load_records

SAMPLE_XLSX = Path("docs/sample_import_example.xlsx")


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test_records.db"
    monkeypatch.setattr("llm_query_doc_analyser.core.store.DB_PATH", db_path)
    init_db()
    yield db_path
    # Optional: ensure no pending WAL and nuke any lingering refs.
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception:
        pass
    import gc

    gc.collect()


def test_import_research_articles_from_xlsx(temp_db):
    records = load_records(SAMPLE_XLSX)
    assert records, "No records loaded from sample XLSX."

    for rec in records:
        upsert_record(rec)

    db_records = get_records()
    assert len(db_records) == len(records), f"Expected {len(records)} in DB, got {len(db_records)}"

    for orig, db_rec in zip(records, db_records, strict=True):
        assert orig.title == db_rec.title
        assert orig.doi_norm == db_rec.doi_norm
