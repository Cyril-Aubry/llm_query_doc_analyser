import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from ..utils.log import get_logger
from .models import Record  # Ensure the Record class is defined in models.py

log = get_logger(__name__)


DB_PATH = Path("data/cache/research_articles_management.db")

CREATE_RESEARCH_ARTICLES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS research_articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    doi_raw TEXT,
    doi_norm TEXT UNIQUE,
    pub_date TEXT,
    total_citations INTEGER,
    citations_per_year REAL,
    authors TEXT,
    source_title TEXT,
    abstract_text TEXT,
    abstract_source TEXT,
    pmid TEXT,
    arxiv_id TEXT,
    is_oa INTEGER,
    oa_status TEXT,
    license TEXT,
    oa_pdf_url TEXT,
    match_reasons TEXT,
    provenance TEXT,
    import_datetime TEXT,
    enrichment_datetime TEXT
);
"""

CREATE_FILTERING_QUERIES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS filtering_queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filtering_query_datetime TEXT NOT NULL,
    query TEXT NOT NULL,
    exclude_criteria TEXT,
    llm_model TEXT NOT NULL,
    max_concurrent INTEGER,
    total_records INTEGER,
    matched_count INTEGER,
    failed_count INTEGER
);
"""

CREATE_RECORDS_FILTERINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS records_filterings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL,
    filtering_query_id INTEGER NOT NULL,
    match_result INTEGER NOT NULL,
    explanation TEXT,
    FOREIGN KEY (record_id) REFERENCES research_articles(id) ON DELETE CASCADE,
    FOREIGN KEY (filtering_query_id) REFERENCES filtering_queries(id) ON DELETE CASCADE
);
"""

CREATE_PDF_RESOLUTIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pdf_resolutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL,
    filtering_query_id INTEGER,
    timestamp TEXT NOT NULL,
    candidates TEXT NOT NULL,
    FOREIGN KEY (record_id) REFERENCES research_articles(id) ON DELETE CASCADE,
    FOREIGN KEY (filtering_query_id) REFERENCES filtering_queries(id) ON DELETE SET NULL
);
"""

CREATE_PDF_DOWNLOADS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pdf_downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL,
    filtering_query_id INTEGER,
    timestamp TEXT NOT NULL,
    url TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    pdf_local_path TEXT,
    sha1 TEXT,
    final_url TEXT,
    error_message TEXT,
    FOREIGN KEY (record_id) REFERENCES research_articles(id) ON DELETE CASCADE,
    FOREIGN KEY (filtering_query_id) REFERENCES filtering_queries(id) ON DELETE SET NULL
);
"""

CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_records_filterings_record_id ON records_filterings(record_id);",
    "CREATE INDEX IF NOT EXISTS idx_records_filterings_filtering_query_id ON records_filterings(filtering_query_id);",
    "CREATE INDEX IF NOT EXISTS idx_filtering_queries_datetime ON filtering_queries(filtering_query_datetime);",
    "CREATE INDEX IF NOT EXISTS idx_pdf_resolutions_record_id ON pdf_resolutions(record_id);",
    "CREATE INDEX IF NOT EXISTS idx_pdf_resolutions_filtering_query_id ON pdf_resolutions(filtering_query_id);",
    "CREATE INDEX IF NOT EXISTS idx_pdf_downloads_record_id ON pdf_downloads(record_id);",
    "CREATE INDEX IF NOT EXISTS idx_pdf_downloads_filtering_query_id ON pdf_downloads(filtering_query_id);",
    "CREATE INDEX IF NOT EXISTS idx_pdf_downloads_status ON pdf_downloads(status);",
]


@contextmanager
def get_conn() -> Generator[sqlite3.Connection, None, None]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        # Reduce chance of WAL leftovers & enforce FK
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=FULL")  # or FULL if you prefer stronger durability
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA busy_timeout=5000") 
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    log.info("initializing_database", path=str(DB_PATH))
    with get_conn() as conn:
        conn.execute(CREATE_RESEARCH_ARTICLES_TABLE_SQL)
        conn.execute(CREATE_FILTERING_QUERIES_TABLE_SQL)
        conn.execute(CREATE_RECORDS_FILTERINGS_TABLE_SQL)
        conn.execute(CREATE_PDF_RESOLUTIONS_TABLE_SQL)
        conn.execute(CREATE_PDF_DOWNLOADS_TABLE_SQL)
        for index_sql in CREATE_INDEXES_SQL:
            conn.execute(index_sql)
        conn.commit()
    log.info("database_initialized", path=str(DB_PATH))


def insert_record(rec: Record) -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO research_articles (
                title,
                doi_raw,
                doi_norm,
                pub_date,
                total_citations,
                citations_per_year,
                authors,
                source_title,
                abstract_text,
                abstract_source,
                pmid,
                arxiv_id,
                is_oa,
                oa_status,
                license,
                oa_pdf_url,
                match_reasons,
                provenance,
                import_datetime
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rec.title,
                rec.doi_raw,
                rec.doi_norm,
                rec.pub_date,
                rec.total_citations,
                rec.citations_per_year,
                rec.authors,
                rec.source_title,
                rec.abstract_text,
                rec.abstract_source,
                rec.pmid,
                rec.arxiv_id,
                int(rec.is_oa) if rec.is_oa is not None else None,
                rec.oa_status,
                rec.license,
                rec.oa_pdf_url,
                json.dumps(rec.match_reasons),
                json.dumps(rec.provenance),
                rec.import_datetime
            ),
        )
        conn.commit()
        return cur.lastrowid


def get_records() -> list[Record]:
    log.debug("fetching_records_from_db", path=str(DB_PATH))
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM research_articles")
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
        records = []
        for row in rows:
            data = dict(zip(cols, row, strict=False))
            data["match_reasons"] = json.loads(data["match_reasons"] or "[]")
            data["provenance"] = json.loads(data["provenance"] or "{}")
            # MIGRATION: ensure all provenance values are dicts (not strings)
            if isinstance(data["provenance"], dict):
                for k, v in list(data["provenance"].items()):
                    if isinstance(v, str):
                        data["provenance"][k] = {"raw": v}
            records.append(Record(**data))
        log.info("records_fetched", count=len(records), path=str(DB_PATH))
        return records


def update_enrichment_record(rec: Record) -> int:
    """Update record with enrichment."""
    log.debug("updating enrichment of the record", doi=rec.doi_norm, title=rec.title[:100])
    with get_conn() as conn:
        cur = conn.cursor()
        # Try update by doi_norm
        cur.execute(
            """
            UPDATE research_articles SET
                abstract_text=?,
                abstract_source=?,
                pmid=?,
                arxiv_id=?,
                is_oa=?,
                oa_status=?,
                license=?,
                oa_pdf_url=?,
                match_reasons=?,
                provenance=?,
                enrichment_datetime=?
            WHERE doi_norm=?
            """,
            (
                rec.abstract_text,
                rec.abstract_source,
                rec.pmid,
                rec.arxiv_id,
                int(rec.is_oa) if rec.is_oa is not None else None,
                rec.oa_status,
                rec.license,
                rec.oa_pdf_url,
                json.dumps(rec.match_reasons),
                json.dumps(rec.provenance),
                rec.enrichment_datetime,
                rec.doi_norm
            ),
        )
        conn.commit()
        log.debug("record_updated", doi=rec.doi_norm)
        return cur.lastrowid


def upsert_record(rec: Record) -> int:
    """Update if doi_norm exists, else insert."""
    log.debug("upserting_record", doi=rec.doi_norm, title=rec.title[:100])
    with get_conn() as conn:
        cur = conn.cursor()
        # Try update by doi_norm
        cur.execute(
            """
            UPDATE research_articles SET
                title=?,
                doi_raw=?,
                pub_date=?,
                total_citations=?,
                citations_per_year=?,
                authors=?,
                source_title=?,
                abstract_text=?,
                abstract_source=?,
                pmid=?,
                arxiv_id=?,
                is_oa=?,
                oa_status=?,
                license=?,
                oa_pdf_url=?,
                match_reasons=?,
                provenance=?
            WHERE doi_norm=?
            """,
            (
                rec.title,
                rec.doi_raw,
                rec.pub_date,
                rec.total_citations,
                rec.citations_per_year,
                rec.authors,
                rec.source_title,
                rec.abstract_text,
                rec.abstract_source,
                rec.pmid,
                rec.arxiv_id,
                int(rec.is_oa) if rec.is_oa is not None else None,
                rec.oa_status,
                rec.license,
                rec.oa_pdf_url,
                json.dumps(rec.match_reasons),
                json.dumps(rec.provenance),
                rec.doi_norm,
            ),
        )
        if cur.rowcount == 0:
            # Insert if not found
            log.debug("inserting_new_record", doi=rec.doi_norm)
            cur.execute(
                """
                INSERT INTO research_articles (
                    title, 
                    doi_raw, 
                    doi_norm, 
                    pub_date, 
                    total_citations, 
                    citations_per_year, 
                    authors, 
                    source_title,
                    abstract_text, 
                    abstract_source, 
                    pmid, 
                    arxiv_id,
                    is_oa, 
                    oa_status, 
                    license, 
                    oa_pdf_url, 
                    match_reasons, 
                    provenance
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec.title,
                    rec.doi_raw,
                    rec.doi_norm,
                    rec.pub_date,
                    rec.total_citations,
                    rec.citations_per_year,
                    rec.authors,
                    rec.source_title,
                    rec.abstract_text,
                    rec.abstract_source,
                    rec.pmid,
                    rec.arxiv_id,
                    int(rec.is_oa) if rec.is_oa is not None else None,
                    rec.oa_status,
                    rec.license,
                    rec.oa_pdf_url,
                    json.dumps(rec.match_reasons),
                    json.dumps(rec.provenance),
                ),
            )
            conn.commit()
            log.debug("record_inserted", doi=rec.doi_norm, id=cur.lastrowid)
            return cur.lastrowid
        else:
            conn.commit()
            log.debug("record_updated", doi=rec.doi_norm)
            return cur.lastrowid


def create_filtering_query(
    timestamp: str,
    query: str,
    exclude_criteria: str,
    llm_model: str,
    max_concurrent: int,
) -> int:
    """
    Create a new filtering query record.

    Args:
        timestamp: ISO 8601 timestamp of the filtering session
        query: Inclusive criteria query string
        exclude_criteria: Exclusive criteria string
        llm_model: OpenAI model name used
        max_concurrent: Maximum concurrent API calls

    Returns:
        The ID of the created filtering query record
    """
    log.debug(
        "creating_filtering_query",
        timestamp=timestamp,
        query=query[:100],
        model=llm_model,
    )

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO filtering_queries (
                filtering_query_datetime, query, exclude_criteria, llm_model, max_concurrent,
                total_records, matched_count, failed_count
            ) VALUES (?, ?, ?, ?, ?, 0, 0, 0)
            """,
            (timestamp, query, exclude_criteria, llm_model, max_concurrent),
        )
        conn.commit()
        filtering_query_id = cur.lastrowid

    log.info(
        "filtering_query_created",
        filtering_query_id=filtering_query_id,
        timestamp=timestamp,
    )
    return filtering_query_id


def update_filtering_query_stats(
    filtering_query_id: int,
    total_records: int,
    matched_count: int,
    failed_count: int,
):
    """
    Update statistics for a filtering query.

    Args:
        filtering_query_id: ID of the filtering query
        total_records: Total number of records processed
        matched_count: Number of records that matched
        failed_count: Number of records that failed processing
    """
    log.debug(
        "updating_filtering_query_stats",
        filtering_query_id=filtering_query_id,
        total_records=total_records,
        matched_count=matched_count,
        failed_count=failed_count,
    )

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE filtering_queries 
            SET total_records = ?, matched_count = ?, failed_count = ?
            WHERE id = ?
            """,
            (total_records, matched_count, failed_count, filtering_query_id),
        )
        conn.commit()

    log.info(
        "filtering_query_stats_updated",
        filtering_query_id=filtering_query_id,
        total_records=total_records,
        matched_count=matched_count,
        failed_count=failed_count,
    )


def insert_filtering_result(
    record_id: int,
    filtering_query_id: int,
    match_result: bool,
    explanation: str,
    timestamp: str,
):
    """
    Insert a filtering result for a record.

    Args:
        record_id: ID of the record from records table
        filtering_query_id: ID of the filtering query
        match_result: Boolean indicating if the record matched
        explanation: Explanation from the LLM
        timestamp: ISO 8601 timestamp of the filtering
    """
    log.debug(
        "inserting_filtering_result",
        record_id=record_id,
        filtering_query_id=filtering_query_id,
        match_result=match_result,
    )

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO records_filterings (
                record_id, filtering_query_id, match_result, explanation, timestamp
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (record_id, filtering_query_id, int(match_result), explanation, timestamp),
        )
        conn.commit()


def batch_insert_filtering_results(
    results: list[tuple[int, int, bool, str]],
):
    """
    Batch insert filtering results for efficiency.

    Args:
        results: List of tuples (record_id, filtering_query_id, match_result, explanation, timestamp)
    """
    if not results:
        return

    log.debug("batch_inserting_filtering_results", count=len(results))

    with get_conn() as conn:
        conn.executemany(
            """
            INSERT INTO records_filterings (
                record_id, filtering_query_id, match_result, explanation
            ) VALUES (?, ?, ?, ?)
            """,
            [(r[0], r[1], int(r[2]), r[3]) for r in results],
        )
        conn.commit()

    log.info("filtering_results_batch_inserted", count=len(results))


def get_filtering_results(filtering_query_id: int) -> list[dict]:
    """
    Retrieve all filtering results for a given filtering query.

    Args:
        filtering_query_id: ID of the filtering query

    Returns:
        List of dictionaries containing filtering results with record details
    """
    log.debug("fetching_filtering_results", filtering_query_id=filtering_query_id)

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 
                r.id, r.doi_norm, r.title,
                rf.match_result, rf.explanation, rf.timestamp
            FROM records_filterings rf
            JOIN research_articles r ON rf.record_id = r.id
            WHERE rf.filtering_query_id = ?
            ORDER BY rf.timestamp
            """,
            (filtering_query_id,),
        )
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
        results = [dict(zip(cols, row, strict=False)) for row in rows]

    log.info(
        "filtering_results_fetched",
        filtering_query_id=filtering_query_id,
        count=len(results),
    )
    return results


def get_record_id_by_doi(doi_norm: str) -> int | None:
    """
    Get record ID by normalized DOI.

    Args:
        doi_norm: Normalized DOI

    Returns:
        Record ID or None if not found
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM research_articles WHERE doi_norm = ?", (doi_norm,))
        row = cur.fetchone()
        return row[0] if row else None


def get_matched_records_by_filtering_query(filtering_query_id: int) -> list[Record]:
    """
    Get all matched records from a filtering query (excluding errors and warnings).

    Args:
        filtering_query_id: ID of the filtering query

    Returns:
        List of Record objects that matched
    """
    log.debug("fetching_matched_records", filtering_query_id=filtering_query_id)

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT r.* FROM research_articles r
            JOIN records_filterings rf ON r.id = rf.record_id
            WHERE rf.filtering_query_id = ?
                AND rf.match_result = 1
                AND rf.explanation NOT LIKE 'ERROR:%'
                AND rf.explanation NOT LIKE 'WARNING:%'
            ORDER BY r.id
            """,
            (filtering_query_id,),
        )
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
        records = []
        for row in rows:
            data = dict(zip(cols, row, strict=False))
            # Parse JSON fields
            if data.get("match_reasons"):
                data["match_reasons"] = json.loads(data["match_reasons"])
            if data.get("provenance"):
                data["provenance"] = json.loads(data["provenance"])
            records.append(Record(**data))

    log.info(
        "matched_records_fetched",
        filtering_query_id=filtering_query_id,
        count=len(records),
    )
    return records


def get_record_provenance(record_id: int) -> dict:
    """Retrieve the provenance JSON for a specific record.

    Args:
        record_id: ID of the record in the records table

    Returns:
        A dictionary representing provenance (empty dict if none found)
    """
    log.debug("fetching_record_provenance", record_id=record_id)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT provenance FROM research_articles WHERE id = ?", (record_id,))
        row = cur.fetchone()
        if not row or not row[0]:
            log.info("provenance_not_found", record_id=record_id)
            return {}
        try:
            prov = json.loads(row[0])
            # Ensure values are dicts
            if isinstance(prov, dict):
                for k, v in list(prov.items()):
                    if isinstance(v, str):
                        prov[k] = {"raw": v}
            return prov
        except Exception as e:
            log.error("provenance_parse_error", record_id=record_id, error=str(e))
            return {}


def insert_pdf_resolution(
    record_id: int,
    candidates: list[dict],
    timestamp: str,
    filtering_query_id: int | None = None,
) -> int:
    """
    Store PDF resolution candidates for a record.

    Args:
        record_id: ID of the record
        candidates: List of PDF candidate dictionaries
        timestamp: ISO format timestamp
        filtering_query_id: Optional filtering query ID

    Returns:
        ID of the inserted resolution record
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO pdf_resolutions 
            (record_id, filtering_query_id, timestamp, candidates)
            VALUES (?, ?, ?, ?)
            """,
            (record_id, filtering_query_id, timestamp, json.dumps(candidates)),
        )
        resolution_id = cur.lastrowid
        conn.commit()

    log.debug(
        "pdf_resolution_inserted",
        resolution_id=resolution_id,
        record_id=record_id,
        candidate_count=len(candidates),
    )
    return resolution_id


def insert_pdf_download(
    record_id: int,
    url: str,
    source: str,
    status: str,
    timestamp: str,
    filtering_query_id: int | None = None,
    pdf_local_path: str | None = None,
    sha1: str | None = None,
    final_url: str | None = None,
    error_message: str | None = None,
) -> int:
    """
    Store PDF download attempt result.

    Args:
        record_id: ID of the record
        url: URL attempted
        source: Source of the PDF (unpaywall, arxiv, etc.)
        status: Status (downloaded, unavailable, too_large, error)
        timestamp: ISO format timestamp
        filtering_query_id: Optional filtering query ID
        pdf_local_path: Local path if downloaded
        sha1: SHA1 hash if downloaded
        final_url: Final URL after redirects
        error_message: Error message if failed

    Returns:
        ID of the inserted download record
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO pdf_downloads 
            (record_id, filtering_query_id, timestamp, url, source, status,
             pdf_local_path, sha1, final_url, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                filtering_query_id,
                timestamp,
                url,
                source,
                status,
                pdf_local_path,
                sha1,
                final_url,
                error_message,
            ),
        )
        download_id = cur.lastrowid
        conn.commit()

    log.debug(
        "pdf_download_inserted",
        download_id=download_id,
        record_id=record_id,
        status=status,
    )
    return download_id


def get_pdf_download_stats(filtering_query_id: int | None = None) -> dict:
    """
    Get statistics on PDF download attempts.

    Args:
        filtering_query_id: Optional filtering query ID to filter by

    Returns:
        Dictionary with status counts
    """
    with get_conn() as conn:
        cur = conn.cursor()
        if filtering_query_id:
            cur.execute(
                """
                SELECT status, COUNT(*) as count
                FROM pdf_downloads
                WHERE filtering_query_id = ?
                GROUP BY status
                """,
                (filtering_query_id,),
            )
        else:
            cur.execute(
                """
                SELECT status, COUNT(*) as count
                FROM pdf_downloads
                GROUP BY status
                """
            )
        rows = cur.fetchall()
        return {row[0]: row[1] for row in rows}
