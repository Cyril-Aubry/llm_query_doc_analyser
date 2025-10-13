import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ..utils.log import get_logger
from .config import get_config
from .models import Record  # Ensure the Record class is defined in models.py

log = get_logger(__name__)


# Legacy constant for backward compatibility - use get_config().db_path instead
DB_PATH = Path("data/cache/research_articles_management.db")


def _get_db_path() -> Path:
    """Get current database path from configuration."""
    return get_config().db_path

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
    abstract_no_retrieval_reason TEXT,
    pmid TEXT,
    arxiv_id TEXT,
    is_oa INTEGER,
    oa_status TEXT,
    license TEXT,
    oa_pdf_url TEXT,
    provenance TEXT,
    import_datetime TEXT,
    enrichment_datetime TEXT,
    is_preprint INTEGER,
    preprint_source TEXT,
    published_doi TEXT,
    published_journal TEXT,
    published_url TEXT,
    published_fulltext_url TEXT
);
"""

CREATE_ARTICLE_VERSIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS article_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    preprint_id INTEGER NOT NULL,
    published_id INTEGER NOT NULL,
    discovered_at TEXT NOT NULL,
    discovery_source TEXT NOT NULL,
    discovery_metadata TEXT,
    FOREIGN KEY (preprint_id) REFERENCES research_articles(id) ON DELETE CASCADE,
    FOREIGN KEY (published_id) REFERENCES research_articles(id) ON DELETE CASCADE,
    UNIQUE(preprint_id, published_id)
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
    resolution_datetime TEXT NOT NULL,
    candidates TEXT NOT NULL,
    FOREIGN KEY (record_id) REFERENCES research_articles(id) ON DELETE CASCADE
);
"""

CREATE_PDF_DOWNLOADS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pdf_downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL,
    download_attempt_datetime TEXT NOT NULL,
    url TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    pdf_local_path TEXT,
    sha1 TEXT,
    final_url TEXT,
    file_size_bytes INTEGER,
    error_message TEXT,
    FOREIGN KEY (record_id) REFERENCES research_articles(id) ON DELETE CASCADE
);
"""

CREATE_DOCX_VERSIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS docx_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL,
    retrieved_attempt_datetime TEXT NOT NULL,
    docx_local_path TEXT,
    file_size_bytes INTEGER,
    error_message TEXT,
    FOREIGN KEY (record_id) REFERENCES research_articles(id) ON DELETE CASCADE
);
"""

CREATE_MARKDOWN_VERSIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS markdown_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL,
    docx_version_id INTEGER,
    created_datetime TEXT NOT NULL,
    variant TEXT NOT NULL,
    md_local_path TEXT,
    file_size_bytes INTEGER,
    error_message TEXT,
    FOREIGN KEY (record_id) REFERENCES research_articles(id) ON DELETE CASCADE,
    FOREIGN KEY (docx_version_id) REFERENCES docx_versions(id) ON DELETE SET NULL
);
"""

CREATE_HTML_DOWNLOADS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS html_downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL,
    download_attempt_datetime TEXT NOT NULL,
    url TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    html_local_path TEXT,
    file_size_bytes INTEGER,
    error_message TEXT,
    FOREIGN KEY (record_id) REFERENCES research_articles(id) ON DELETE CASCADE
);
"""

CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_records_filterings_record_id ON records_filterings(record_id);",
    "CREATE INDEX IF NOT EXISTS idx_records_filterings_filtering_query_id ON records_filterings(filtering_query_id);",
    "CREATE INDEX IF NOT EXISTS idx_filtering_queries_datetime ON filtering_queries(filtering_query_datetime);",
    "CREATE INDEX IF NOT EXISTS idx_pdf_resolutions_record_id ON pdf_resolutions(record_id);",
    "CREATE INDEX IF NOT EXISTS idx_pdf_downloads_record_id ON pdf_downloads(record_id);",
    "CREATE INDEX IF NOT EXISTS idx_pdf_downloads_status ON pdf_downloads(status);",
    "CREATE INDEX IF NOT EXISTS idx_html_downloads_record_id ON html_downloads(record_id);",
    "CREATE INDEX IF NOT EXISTS idx_html_downloads_status ON html_downloads(status);",
    "CREATE INDEX IF NOT EXISTS idx_research_articles_is_preprint ON research_articles(is_preprint);",
    "CREATE INDEX IF NOT EXISTS idx_article_versions_preprint_id ON article_versions(preprint_id);",
    "CREATE INDEX IF NOT EXISTS idx_article_versions_published_id ON article_versions(published_id);",
]

CREATE_ARTICLE_FILE_VERSIONS_VIEW_SQL = """
CREATE VIEW IF NOT EXISTS article_file_versions_view AS
SELECT 
    ra.id AS record_id,
    ra.title,
    ra.doi_norm,
    ra.pub_date,
    ra.authors,
    ra.source_title,
    -- PDF Download Information
    CASE WHEN pd.id IS NOT NULL THEN 1 ELSE 0 END AS has_pdf,
    pd.status AS pdf_status,
    pd.pdf_local_path,
    pd.download_attempt_datetime AS pdf_download_datetime,
    pd.url AS pdf_url,
    pd.source AS pdf_source,
    pd.sha1 AS pdf_sha1,
    -- DOCX Version Information
    CASE WHEN dv.id IS NOT NULL THEN 1 ELSE 0 END AS has_docx,
    dv.id AS docx_version_id,
    dv.docx_local_path,
    dv.retrieved_attempt_datetime AS docx_retrieved_datetime,
    dv.error_message AS docx_error_message,
    -- Markdown Version Information (no_images variant)
    CASE WHEN mv_no_images.id IS NOT NULL THEN 1 ELSE 0 END AS has_markdown_no_images,
    mv_no_images.id AS markdown_no_images_id,
    mv_no_images.md_local_path AS markdown_no_images_path,
    mv_no_images.created_datetime AS markdown_no_images_created_datetime,
    mv_no_images.error_message AS markdown_no_images_error_message,
    -- Markdown Version Information (with_images variant)
    CASE WHEN mv_with_images.id IS NOT NULL THEN 1 ELSE 0 END AS has_markdown_with_images,
    mv_with_images.id AS markdown_with_images_id,
    mv_with_images.md_local_path AS markdown_with_images_path,
    mv_with_images.created_datetime AS markdown_with_images_created_datetime,
    mv_with_images.error_message AS markdown_with_images_error_message,
    -- Combined markdown flags
    CASE WHEN mv_no_images.id IS NOT NULL OR mv_with_images.id IS NOT NULL THEN 1 ELSE 0 END AS has_markdown,
    CASE WHEN mv_no_images.id IS NOT NULL AND mv_with_images.id IS NOT NULL THEN 1 ELSE 0 END AS has_both_markdown_variants,
    -- Summary flags for easy filtering
    CASE 
        WHEN pd.id IS NOT NULL AND dv.id IS NOT NULL 
             AND mv_no_images.id IS NOT NULL AND mv_with_images.id IS NOT NULL THEN 1 
        ELSE 0 
    END AS has_all_versions,
    CASE 
        WHEN pd.id IS NULL AND dv.id IS NULL 
             AND mv_no_images.id IS NULL AND mv_with_images.id IS NULL THEN 1 
        ELSE 0 
    END AS has_no_versions
FROM research_articles ra
LEFT JOIN (
    -- Get the most recent successful PDF download per record
    SELECT pd1.*
    FROM pdf_downloads pd1
    INNER JOIN (
        SELECT record_id, MAX(id) AS max_id
        FROM pdf_downloads
        WHERE status = 'downloaded'
        GROUP BY record_id
    ) pd2 ON pd1.id = pd2.max_id
) pd ON ra.id = pd.record_id
LEFT JOIN (
    -- Get the most recent DOCX version per record
    SELECT dv1.*
    FROM docx_versions dv1
    INNER JOIN (
        SELECT record_id, MAX(id) AS max_id
        FROM docx_versions
        GROUP BY record_id
    ) dv2 ON dv1.id = dv2.max_id
) dv ON ra.id = dv.record_id
LEFT JOIN (
    -- Get the most recent Markdown version per record (no_images variant)
    SELECT mv1.*
    FROM markdown_versions mv1
    INNER JOIN (
        SELECT record_id, MAX(id) AS max_id
        FROM markdown_versions
        WHERE variant = 'no_images'
        GROUP BY record_id
    ) mv2 ON mv1.id = mv2.max_id
) mv_no_images ON ra.id = mv_no_images.record_id
LEFT JOIN (
    -- Get the most recent Markdown version per record (with_images variant)
    SELECT mv1.*
    FROM markdown_versions mv1
    INNER JOIN (
        SELECT record_id, MAX(id) AS max_id
        FROM markdown_versions
        WHERE variant = 'with_images'
        GROUP BY record_id
    ) mv2 ON mv1.id = mv2.max_id
) mv_with_images ON ra.id = mv_with_images.record_id;
"""


@contextmanager
def get_conn() -> Generator[sqlite3.Connection, None, None]:
    db_path = _get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
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


def _migrate_add_file_size_columns() -> None:
    """Add file_size_bytes columns to existing tables if they don't exist."""
    log.info("running_file_size_migration")
    with get_conn() as conn:
        cur = conn.cursor()
        
        # Check and add file_size_bytes to pdf_downloads table
        cur.execute("PRAGMA table_info(pdf_downloads)")
        pdf_columns = [col[1] for col in cur.fetchall()]
        if "file_size_bytes" not in pdf_columns:
            log.info("adding_file_size_bytes_to_pdf_downloads")
            cur.execute("ALTER TABLE pdf_downloads ADD COLUMN file_size_bytes INTEGER")
            conn.commit()
        
        # Check and add file_size_bytes to docx_versions table
        cur.execute("PRAGMA table_info(docx_versions)")
        docx_columns = [col[1] for col in cur.fetchall()]
        if "file_size_bytes" not in docx_columns:
            log.info("adding_file_size_bytes_to_docx_versions")
            cur.execute("ALTER TABLE docx_versions ADD COLUMN file_size_bytes INTEGER")
            conn.commit()
        
        # Check and add file_size_bytes to markdown_versions table
        cur.execute("PRAGMA table_info(markdown_versions)")
        markdown_columns = [col[1] for col in cur.fetchall()]
        if "file_size_bytes" not in markdown_columns:
            log.info("adding_file_size_bytes_to_markdown_versions")
            cur.execute("ALTER TABLE markdown_versions ADD COLUMN file_size_bytes INTEGER")
            conn.commit()
    
    log.info("file_size_migration_completed")


def update_pdf_file_sizes() -> dict[str, int]:
    """
    Update file_size_bytes for existing PDF downloads that have a local file but no size recorded.
    
    This utility function scans the pdf_downloads table for records with:
    - status = 'downloaded'
    - pdf_local_path is not NULL
    - file_size_bytes is NULL
    
    For each such record, it reads the actual file size from disk and updates the database.
    
    Returns:
        Dictionary with statistics:
        - 'checked': Number of records checked
        - 'updated': Number of records updated successfully
        - 'missing': Number of files not found on disk
        - 'errors': Number of errors encountered
    """
    log.info("starting_pdf_file_size_update")
    
    stats = {
        'checked': 0,
        'updated': 0,
        'missing': 0,
        'errors': 0
    }
    
    with get_conn() as conn:
        cur = conn.cursor()
        
        # Find all downloaded PDFs without file size
        cur.execute(
            """
            SELECT id, pdf_local_path 
            FROM pdf_downloads 
            WHERE status = 'downloaded' 
            AND pdf_local_path IS NOT NULL 
            AND file_size_bytes IS NULL
            """
        )
        rows = cur.fetchall()
        stats['checked'] = len(rows)
        
        log.info("found_pdfs_without_size", count=stats['checked'])
        
        for download_id, pdf_path in rows:
            try:
                pdf_file = Path(pdf_path)
                
                if not pdf_file.exists():
                    log.warning(
                        "pdf_file_not_found",
                        download_id=download_id,
                        path=str(pdf_path)
                    )
                    stats['missing'] += 1
                    continue
                
                # Get file size in bytes
                file_size = pdf_file.stat().st_size
                
                # Update the database
                cur.execute(
                    "UPDATE pdf_downloads SET file_size_bytes = ? WHERE id = ?",
                    (file_size, download_id)
                )
                
                stats['updated'] += 1
                log.debug(
                    "pdf_file_size_updated",
                    download_id=download_id,
                    file_size_bytes=file_size,
                    path=str(pdf_path)
                )
                
            except Exception as e:
                log.error(
                    "failed_to_update_pdf_file_size",
                    download_id=download_id,
                    path=str(pdf_path),
                    error=str(e)
                )
                stats['errors'] += 1
        
        conn.commit()
    
    log.info(
        "pdf_file_size_update_completed",
        checked=stats['checked'],
        updated=stats['updated'],
        missing=stats['missing'],
        errors=stats['errors']
    )
    
    return stats


def init_db() -> None:
    db_path = _get_db_path()
    log.info("initializing_database", path=str(db_path), mode=get_config().mode)
    with get_conn() as conn:
        conn.execute(CREATE_RESEARCH_ARTICLES_TABLE_SQL)
        conn.execute(CREATE_ARTICLE_VERSIONS_TABLE_SQL)
        conn.execute(CREATE_FILTERING_QUERIES_TABLE_SQL)
        conn.execute(CREATE_RECORDS_FILTERINGS_TABLE_SQL)
        conn.execute(CREATE_PDF_RESOLUTIONS_TABLE_SQL)
        conn.execute(CREATE_PDF_DOWNLOADS_TABLE_SQL)
        conn.execute(CREATE_DOCX_VERSIONS_TABLE_SQL)
        conn.execute(CREATE_MARKDOWN_VERSIONS_TABLE_SQL)
        conn.execute(CREATE_HTML_DOWNLOADS_TABLE_SQL)
        for index_sql in CREATE_INDEXES_SQL:
            conn.execute(index_sql)
        # Create the article versions view
        conn.execute(CREATE_ARTICLE_FILE_VERSIONS_VIEW_SQL)
        conn.commit()
    
    # Run migration to add file_size_bytes columns if needed
    _migrate_add_file_size_columns()
    
    log.info("database_initialized", path=str(db_path), mode=get_config().mode)


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
                abstract_no_retrieval_reason,
                pmid,
                arxiv_id,
                is_oa,
                oa_status,
                license,
                oa_pdf_url,
                provenance,
                import_datetime,
                is_preprint,
                preprint_source,
                published_doi,
                published_journal,
                published_url,
                published_fulltext_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                rec.abstract_no_retrieval_reason,
                rec.pmid,
                rec.arxiv_id,
                int(rec.is_oa) if rec.is_oa is not None else None,
                rec.oa_status,
                rec.license,
                rec.oa_pdf_url,
                json.dumps(rec.provenance),
                rec.import_datetime,
                int(rec.is_preprint) if rec.is_preprint is not None else None,
                rec.preprint_source,
                rec.published_doi,
                rec.published_journal,
                rec.published_url,
                rec.published_fulltext_url,
            ),
        )
        conn.commit()
        return cur.lastrowid


def get_records() -> list[Record]:
    db_path = _get_db_path()
    log.debug("fetching_records_from_db", path=str(db_path))
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM research_articles")
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
        records = []
        for row in rows:
            data = dict(zip(cols, row, strict=False))
            data["provenance"] = json.loads(data["provenance"] or "{}")
            # MIGRATION: ensure all provenance values are dicts (not strings)
            if isinstance(data["provenance"], dict):
                for k, v in list(data["provenance"].items()):
                    if isinstance(v, str):
                        data["provenance"][k] = {"raw": v}
            records.append(Record(**data))
        log.info("records_fetched", count=len(records), path=str(db_path))
        return records


def update_enrichment_record(rec: Record) -> int | None:
    """
    Update record with enrichment. Returns the last inserted row id if available,
    or None for non-insert operations.
    """
    log.debug("updating enrichment of the record", doi=rec.doi_norm, title=rec.title[:100])
    with get_conn() as conn:
        cur = conn.cursor()
        # Try update by doi_norm
        cur.execute(
            """
            UPDATE research_articles SET
                abstract_text=?,
                abstract_source=?,
                abstract_no_retrieval_reason=?,
                pmid=?,
                arxiv_id=?,
                is_oa=?,
                oa_status=?,
                license=?,
                oa_pdf_url=?,
                provenance=?,
                enrichment_datetime=?,
                is_preprint=?,
                preprint_source=?,
                published_doi=?,
                published_journal=?,
                published_url=?,
                published_fulltext_url=?
            WHERE doi_norm=?
            """,
            (
                rec.abstract_text,
                rec.abstract_source,
                rec.abstract_no_retrieval_reason,
                rec.pmid,
                rec.arxiv_id,
                int(rec.is_oa) if rec.is_oa is not None else None,
                rec.oa_status,
                rec.license,
                rec.oa_pdf_url,
                json.dumps(rec.provenance),
                rec.enrichment_datetime,
                int(rec.is_preprint) if rec.is_preprint is not None else None,
                rec.preprint_source,
                rec.published_doi,
                rec.published_journal,
                rec.published_url,
                rec.published_fulltext_url,
                rec.doi_norm,
            ),
        )
        conn.commit()
        log.debug("record_updated", doi=rec.doi_norm)
        return cur.lastrowid


def upsert_record(rec: Record) -> int | None:
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
                abstract_no_retrieval_reason=?,
                pmid=?,
                arxiv_id=?,
                is_oa=?,
                oa_status=?,
                license=?,
                oa_pdf_url=?,
                provenance=?,
                is_preprint=?,
                preprint_source=?,
                published_doi=?,
                published_journal=?,
                published_url=?,
                published_fulltext_url=?
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
                rec.abstract_no_retrieval_reason,
                rec.pmid,
                rec.arxiv_id,
                int(rec.is_oa) if rec.is_oa is not None else None,
                rec.oa_status,
                rec.license,
                rec.oa_pdf_url,
                json.dumps(rec.provenance),
                int(rec.is_preprint) if rec.is_preprint is not None else None,
                rec.preprint_source,
                rec.published_doi,
                rec.published_journal,
                rec.published_url,
                rec.published_fulltext_url,
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
                    abstract_no_retrieval_reason,
                    pmid, 
                    arxiv_id,
                    is_oa, 
                    oa_status, 
                    license, 
                    oa_pdf_url, 
                    provenance,
                    is_preprint,
                    preprint_source,
                    published_doi,
                    published_journal,
                    published_url,
                    published_fulltext_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    rec.abstract_no_retrieval_reason,
                    rec.pmid,
                    rec.arxiv_id,
                    int(rec.is_oa) if rec.is_oa is not None else None,
                    rec.oa_status,
                    rec.license,
                    rec.oa_pdf_url,
                    json.dumps(rec.provenance),
                    int(rec.is_preprint) if rec.is_preprint is not None else None,
                    rec.preprint_source,
                    rec.published_doi,
                    rec.published_journal,
                    rec.published_url,
                    rec.published_fulltext_url,
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
) -> int | None:
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
) -> None:
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
) -> None:
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
) -> None:
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
            if data.get("provenance"):
                data["provenance"] = json.loads(data["provenance"])
            records.append(Record(**data))

    log.info(
        "matched_records_fetched",
        filtering_query_id=filtering_query_id,
        count=len(records),
    )
    return records


def get_record_provenance(record_id: int) -> dict[Any, Any]:
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
            # If the parsed provenance is not a dict, return an empty dict to match the declared return type
            if not isinstance(prov, dict):
                log.warning(
                    "provenance_not_a_dict", record_id=record_id, value_type=type(prov).__name__
                )
                return {}
            # Ensure values are dicts
            for k, v in list(prov.items()):
                if isinstance(v, str):
                    prov[k] = {"raw": v}
            return prov
        except Exception as e:
            log.error("provenance_parse_error", record_id=record_id, error=str(e))
            return {}


def filter_unresolved_records(records: list[Record]) -> list[Record]:
    """
    Filter records to exclude those already resolved with non-empty candidates in pdf_resolutions.
    Records with empty candidate lists will NOT be skipped (they will be re-resolved).
    """
    log.debug("filter_unresolved_records_start", total_input=len(records))
    with get_conn() as conn:
        cursor = conn.cursor()
        unresolved = []
        checked = 0
        skipped = 0
        for rec in records:
            checked += 1
            cursor.execute("SELECT candidates FROM pdf_resolutions WHERE record_id = ?", (rec.id,))
            row = cursor.fetchone()
            if row and row[0]:
                try:
                    candidates = json.loads(row[0])
                    if candidates:  # If candidates list is not empty
                        skipped += 1
                        log.debug(
                            "record_skipped_already_resolved",
                            record_id=rec.id,
                            candidate_count=len(candidates),
                        )
                        continue  # Already resolved with candidates, skip
                except json.JSONDecodeError:
                    log.warning("invalid_candidates_json_for_record", record_id=rec.id)
                    # If invalid JSON, treat as not resolved
            unresolved.append(rec)

    log.info(
        "filter_unresolved_records_completed",
        total_checked=checked,
        total_skipped=skipped,
        total_unresolved=len(unresolved),
    )
    return unresolved


def get_resolved_candidates(record_id: int) -> list[dict]:
    """
    Retrieve the most recent resolved PDF candidates for a record.

    Args:
        record_id: ID of the record

    Returns:
        List of PDF candidate dictionaries, or empty list if no resolution found
    """
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT candidates 
            FROM pdf_resolutions 
            WHERE record_id = ? 
            """,
            (record_id,),
        )
        row = cursor.fetchone()

        if row and row[0]:
            try:
                candidates = json.loads(row[0])
                log.debug(
                    "resolved_candidates_retrieved",
                    record_id=record_id,
                    candidate_count=len(candidates),
                )
                return candidates
            except json.JSONDecodeError:
                log.warning("invalid_candidates_json_for_record", record_id=record_id)
                return []

        log.debug("no_resolved_candidates_found", record_id=record_id)
        return []


def insert_pdf_resolution(
    record_id: int,
    candidates: list[dict],
    resolution_datetime: str,
) -> int | None:
    """
    Store or update PDF resolution candidates for a record.
    If a resolution already exists for the record_id, it will be updated.

    Args:
        record_id: ID of the record
        candidates: List of PDF candidate dictionaries
        timestamp: ISO format timestamp

    Returns:
        ID of the inserted or updated resolution record
    """
    with get_conn() as conn:
        cur = conn.cursor()
        
        # Check if resolution already exists for this record
        cur.execute(
            "SELECT id FROM pdf_resolutions WHERE record_id = ?",
            (record_id,)
        )
        existing_row = cur.fetchone()
        
        if existing_row:
            # Update existing resolution
            resolution_id = existing_row[0]
            cur.execute(
                """
                UPDATE pdf_resolutions 
                SET resolution_datetime = ?, candidates = ?
                WHERE id = ?
                """,
                (resolution_datetime, json.dumps(candidates), resolution_id),
            )
            conn.commit()
            log.debug(
                "pdf_resolution_updated",
                resolution_id=resolution_id,
                record_id=record_id,
                candidate_count=len(candidates),
            )
        else:
            # Insert new resolution
            cur.execute(
                """
                INSERT INTO pdf_resolutions 
                (record_id, resolution_datetime, candidates)
                VALUES (?, ?, ?)
                """,
                (record_id, resolution_datetime, json.dumps(candidates)),
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


def record_pdf_download_attempt(
    record_id: int,
    url: str,
    source: str,
    status: str,
    download_attempt_datetime: str,
    pdf_local_path: str | None = None,
    sha1: str | None = None,
    final_url: str | None = None,
    file_size_bytes: int | None = None,
    error_message: str | None = None,
) -> int | None:
    """
    Store or update PDF download attempt result.
    If a download attempt already exists for the record_id, it will be updated.

    Args:
        record_id: ID of the record
        url: URL attempted
        source: Source of the PDF (unpaywall, arxiv, etc.)
        status: Status (downloaded, unavailable, too_large, error)
        download_attempt_datetime: ISO format download_attempt_datetime
        pdf_local_path: Local path if downloaded
        sha1: SHA1 hash if downloaded
        final_url: Final URL after redirects
        file_size_bytes: Size of the PDF file in bytes (if downloaded)
        error_message: Error message if failed

    Returns:
        ID of the inserted or updated download record
    """
    with get_conn() as conn:
        cur = conn.cursor()
        
        # Check if download attempt already exists for this record
        cur.execute(
            "SELECT id FROM pdf_downloads WHERE record_id = ? ORDER BY id DESC LIMIT 1",
            (record_id,)
        )
        existing_row = cur.fetchone()
        
        if existing_row:
            # Update existing download attempt
            download_id = existing_row[0]
            cur.execute(
                """
                UPDATE pdf_downloads 
                SET download_attempt_datetime = ?, url = ?, source = ?, status = ?,
                    pdf_local_path = ?, sha1 = ?, final_url = ?, file_size_bytes = ?, error_message = ?
                WHERE id = ?
                """,
                (
                    download_attempt_datetime,
                    url,
                    source,
                    status,
                    pdf_local_path,
                    sha1,
                    final_url,
                    file_size_bytes,
                    error_message,
                    download_id,
                ),
            )
            conn.commit()
            log.debug(
                "pdf_download_trial_updated",
                download_id=download_id,
                record_id=record_id,
                status=status,
                file_size_bytes=file_size_bytes,
            )
        else:
            # Insert new download attempt
            cur.execute(
                """
                INSERT INTO pdf_downloads 
                (record_id, download_attempt_datetime, url, source, status,
                 pdf_local_path, sha1, final_url, file_size_bytes, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    download_attempt_datetime,
                    url,
                    source,
                    status,
                    pdf_local_path,
                    sha1,
                    final_url,
                    file_size_bytes,
                    error_message,
                ),
            )
            download_id = cur.lastrowid
            conn.commit()
            log.debug(
                "pdf_download_trial_inserted",
                download_id=download_id,
                record_id=record_id,
                status=status,
                file_size_bytes=file_size_bytes,
            )
        
        return download_id


def insert_docx_version(
    record_id: int,
    docx_local_path: str | None,
    retrieved_attempt_datetime: str,
    file_size_bytes: int | None = None,
    error_message: str | None = None,
) -> int | None:
    """Insert a docx version entry tied to a record.
    
    Args:
        record_id: ID of the record
        docx_local_path: Path to the DOCX file
        retrieved_attempt_datetime: ISO format timestamp of retrieval
        file_size_bytes: Size of the DOCX file in bytes
        error_message: Error message if retrieval failed
        
    Returns:
        ID of the inserted docx_versions row
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO docx_versions (record_id, retrieved_attempt_datetime, docx_local_path, file_size_bytes, error_message)
            VALUES (?, ?, ?, ?, ?)
            """,
            (record_id, retrieved_attempt_datetime, docx_local_path, file_size_bytes, error_message),
        )
        conn.commit()
        log.debug(
            "docx_version_inserted",
            docx_id=cur.lastrowid,
            record_id=record_id,
            file_size_bytes=file_size_bytes,
        )
        return cur.lastrowid


def insert_markdown_version(
    record_id: int,
    docx_version_id: int | None,
    variant: str,
    md_local_path: str | None,
    created_datetime: str,
    file_size_bytes: int | None = None,
    error_message: str | None = None,
) -> int | None:
    """Insert a markdown version entry tied to a record and optional docx_version.
    
    Args:
        record_id: ID of the record
        docx_version_id: ID of the source DOCX version (if applicable)
        variant: Markdown variant ('no_images' or 'with_images')
        md_local_path: Path to the markdown file
        created_datetime: ISO format timestamp of creation
        file_size_bytes: Size of the markdown file in bytes
        error_message: Error message if conversion failed
        
    Returns:
        ID of the inserted markdown_versions row
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO markdown_versions (record_id, docx_version_id, created_datetime, variant, md_local_path, file_size_bytes, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (record_id, docx_version_id, created_datetime, variant, md_local_path, file_size_bytes, error_message),
        )
        conn.commit()
        log.debug(
            "markdown_version_inserted",
            markdown_id=cur.lastrowid,
            record_id=record_id,
            variant=variant,
            file_size_bytes=file_size_bytes,
        )
        return cur.lastrowid


def create_article_version_relation(
    preprint_id: int,
    published_id: int,
    discovery_source: str,
    discovery_metadata: dict[str, Any] | None = None
) -> int | None:
    """Create a relation between a preprint and its published version.
    
    Args:
        preprint_id: ID of the preprint record
        published_id: ID of the published version record  
        discovery_source: API source that provided the version info (e.g., 'crossref')
        discovery_metadata: Optional metadata about the discovery
        
    Returns:
        ID of the created relation, or None if already exists or error
    """
    from datetime import UTC, datetime
    
    log.debug(
        "creating_article_version_relation",
        preprint_id=preprint_id,
        published_id=published_id,
        discovery_source=discovery_source
    )
    
    with get_conn() as conn:
        cur = conn.cursor()
        
        # Check if relation already exists
        cur.execute(
            "SELECT id FROM article_versions WHERE preprint_id = ? AND published_id = ?",
            (preprint_id, published_id)
        )
        existing = cur.fetchone()
        if existing:
            log.debug("article_version_relation_exists", relation_id=existing[0])
            return existing[0]
        
        # Insert new relation
        try:
            cur.execute(
                """
                INSERT INTO article_versions (
                    preprint_id,
                    published_id,
                    discovered_at,
                    discovery_source,
                    discovery_metadata
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    preprint_id,
                    published_id,
                    datetime.now(UTC).isoformat(),
                    discovery_source,
                    json.dumps(discovery_metadata or {})
                )
            )
            conn.commit()
            relation_id = cur.lastrowid
            log.info(
                "article_version_relation_created",
                relation_id=relation_id,
                preprint_id=preprint_id,
                published_id=published_id,
                discovery_source=discovery_source
            )
            return relation_id
        except Exception as e:
            log.error(
                "failed_to_create_article_version_relation",
                preprint_id=preprint_id,
                published_id=published_id,
                error=str(e)
            )
            return None


def get_published_version_id(preprint_id: int) -> int | None:
    """Get the published version ID for a given preprint ID.
    
    Args:
        preprint_id: ID of the preprint record
        
    Returns:
        ID of the published version, or None if not found
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT published_id FROM article_versions WHERE preprint_id = ?",
            (preprint_id,)
        )
        result = cur.fetchone()
        return result[0] if result else None


def get_preprint_version_id(published_id: int) -> int | None:
    """Get the preprint version ID for a given published article ID.
    
    Args:
        published_id: ID of the published article record
        
    Returns:
        ID of the preprint version, or None if not found
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT preprint_id FROM article_versions WHERE published_id = ?",
            (published_id,)
        )
        result = cur.fetchone()
        return result[0] if result else None


def get_article_version_relations() -> list[dict[str, Any]]:
    """Get all article version relations.
    
    Returns:
        List of relation dictionaries with all fields
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 
                av.id,
                av.preprint_id,
                av.published_id,
                av.discovered_at,
                av.discovery_source,
                av.discovery_metadata,
                r1.doi_norm as preprint_doi,
                r1.title as preprint_title,
                r2.doi_norm as published_doi,
                r2.title as published_title
            FROM article_versions av
            JOIN research_articles r1 ON av.preprint_id = r1.id
            JOIN research_articles r2 ON av.published_id = r2.id
            """
        )
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
        
        relations = []
        for row in rows:
            data = dict(zip(cols, row, strict=False))
            data['discovery_metadata'] = json.loads(data.get('discovery_metadata') or '{}')
            relations.append(data)
        
        return relations


def get_version_linking_stats() -> dict[str, Any]:
    """Get statistics on pre-print ↔ published version linking.
    
    Returns:
        Dictionary with linking statistics
    """
    with get_conn() as conn:
        cursor = conn.cursor()
        
        # Count total preprints
        cursor.execute("SELECT COUNT(*) FROM research_articles WHERE is_preprint = 1")
        total_preprints = cursor.fetchone()[0]
        
        # Count preprints with published versions (via relation table)
        cursor.execute(
            """
            SELECT COUNT(DISTINCT preprint_id) 
            FROM article_versions
            """
        )
        preprints_with_published = cursor.fetchone()[0]
        
        # Count published articles with preprint versions (via relation table)
        cursor.execute(
            """
            SELECT COUNT(DISTINCT published_id) 
            FROM article_versions
            """
        )
        published_with_preprint = cursor.fetchone()[0]
        
        # Count by preprint source
        cursor.execute(
            """
            SELECT preprint_source, COUNT(*) 
            FROM research_articles 
            WHERE is_preprint = 1 
            GROUP BY preprint_source
            """
        )
        by_source = dict(cursor.fetchall())
        
        # Count by version discovery source
        cursor.execute(
            """
            SELECT discovery_source, COUNT(*) 
            FROM article_versions 
            GROUP BY discovery_source
            """
        )
        by_discovery_source = dict(cursor.fetchall())

    return {
        "total_preprints": total_preprints,
        "preprints_with_published_version": preprints_with_published,
        "published_with_preprint_version": published_with_preprint,
        "linking_rate": (
            preprints_with_published / total_preprints * 100 
            if total_preprints > 0 else 0
        ),
        "by_preprint_source": by_source,
        "by_version_discovery_source": by_discovery_source,
    }


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
                SELECT d.status, COUNT(*) as count
                FROM pdf_downloads d
                JOIN records_filterings rf ON d.record_id = rf.record_id
                WHERE rf.filtering_query_id = ?
                GROUP BY d.status
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


def filter_already_downloaded_records(records: list[Record]) -> list[Record]:
    """
    Filter records to exclude those already successfully downloaded.
    Records with failed or no download attempts will NOT be skipped (they will be re-attempted).
    
    Args:
        records: List of records to check
        
    Returns:
        List of records that haven't been successfully downloaded yet
    """
    log.debug("filter_already_downloaded_records_start", total_input=len(records))
    with get_conn() as conn:
        cursor = conn.cursor()
        records_needing_download = []
        checked = 0
        skipped = 0
        
        for rec in records:
            checked += 1
            cursor.execute(
                """
                SELECT COUNT(*) 
                FROM pdf_downloads 
                WHERE record_id = ? AND status = 'downloaded'
                """,
                (rec.id,)
            )
            row = cursor.fetchone()
            
            if row and row[0] > 0:
                # Record already has a successful download
                skipped += 1
                log.debug(
                    "record_skipped_already_downloaded",
                    record_id=rec.id,
                    doi=rec.doi_norm,
                )
                continue
            
            records_needing_download.append(rec)
    
    log.info(
        "filter_already_downloaded_records_completed",
        total_checked=checked,
        total_skipped=skipped,
        total_needing_download=len(records_needing_download),
    )
    return records_needing_download


def record_html_download_attempt(
    record_id: int,
    url: str,
    source: str,
    status: str,
    download_attempt_datetime: str,
    html_local_path: str | None = None,
    file_size_bytes: int | None = None,
    error_message: str | None = None,
) -> int | None:
    """
    Record an HTML full-text download attempt.
    
    Args:
        record_id: ID of the research article record
        url: URL of the HTML page
        source: Preprint source (arxiv, biorxiv, medrxiv, preprints)
        status: Download status ('downloaded', 'error', 'no_url')
        download_attempt_datetime: ISO datetime of download attempt
        html_local_path: Local file path if downloaded
        file_size_bytes: File size in bytes if downloaded
        error_message: Error message if failed
        
    Returns:
        ID of the inserted record or None if failed
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO html_downloads (
                record_id,
                download_attempt_datetime,
                url,
                source,
                status,
                html_local_path,
                file_size_bytes,
                error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                download_attempt_datetime,
                url,
                source,
                status,
                html_local_path,
                file_size_bytes,
                error_message,
            ),
        )
        download_id = cur.lastrowid
        log.debug(
            "html_download_attempt_recorded",
            record_id=record_id,
            download_id=download_id,
            status=status,
            url=url,
        )
        return download_id


def get_html_download_stats(filtering_query_id: int | None = None) -> dict[str, Any]:
    """
    Get HTML download statistics, optionally filtered by filtering query.
    
    Args:
        filtering_query_id: Optional filtering query ID to scope stats
        
    Returns:
        Dictionary with counts by status
    """
    with get_conn() as conn:
        cursor = conn.cursor()
        
        if filtering_query_id is not None:
            # Get stats for specific filtering query
            cursor.execute(
                """
                SELECT hd.status, COUNT(*) as count
                FROM html_downloads hd
                INNER JOIN records_filterings rf ON hd.record_id = rf.record_id
                WHERE rf.filtering_query_id = ? AND rf.match_result = 1
                GROUP BY hd.status
                """,
                (filtering_query_id,),
            )
        else:
            # Get overall stats
            cursor.execute(
                """
                SELECT status, COUNT(*) as count
                FROM html_downloads
                GROUP BY status
                """
            )
        
        rows = cursor.fetchall()
        stats = {row[0]: row[1] for row in rows}
        
        log.debug("html_download_stats_retrieved", filtering_query_id=filtering_query_id, stats=stats)
        return stats


def filter_already_downloaded_html(records: list[Record]) -> list[Record]:
    """
    Filter records to exclude those already successfully downloaded as HTML.
    Records with failed or no download attempts will NOT be skipped (they will be re-attempted).
    
    Args:
        records: List of records to check
        
    Returns:
        List of records that haven't been successfully downloaded yet
    """
    log.debug("filter_already_downloaded_html_start", total_input=len(records))
    with get_conn() as conn:
        cursor = conn.cursor()
        records_needing_download = []
        checked = 0
        skipped = 0
        
        for rec in records:
            checked += 1
            cursor.execute(
                """
                SELECT COUNT(*) 
                FROM html_downloads 
                WHERE record_id = ? AND status = 'downloaded'
                """,
                (rec.id,)
            )
            row = cursor.fetchone()
            
            if row and row[0] > 0:
                # Record already has a successful download
                skipped += 1
                log.debug(
                    "record_skipped_already_downloaded_html",
                    record_id=rec.id,
                    doi=rec.doi_norm,
                )
                continue
            
            records_needing_download.append(rec)
    
    log.info(
        "filter_already_downloaded_html_completed",
        total_checked=checked,
        total_skipped=skipped,
        total_needing_download=len(records_needing_download),
    )
    return records_needing_download
