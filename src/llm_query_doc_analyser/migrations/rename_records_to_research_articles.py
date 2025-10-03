"""Migration: Rename 'records' table to 'research_articles' and update all foreign keys.

This migration will:
- Rename the 'records' table to 'research_articles'
- Update all foreign key references in related tables (records_filterings, pdf_resolutions, pdf_downloads)
- Update indexes referencing the old table name

Run this script ONCE on your existing database before using the new codebase.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path("data/cache/records.db")

def migrate():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}. No migration needed.")  # noqa: T201
        return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    print("Renaming 'records' table to 'research_articles'...")  # noqa: T201
    # 1. Rename main table
    cursor.execute("ALTER TABLE records RENAME TO research_articles")
    # 2. Update foreign keys: SQLite does not support direct FK alteration, so we must recreate tables
    # For each dependent table, we will:
    #   - Create a new table with updated FK
    #   - Copy data
    #   - Drop old table
    #   - Rename new table
    # Helper for table recreation
    def recreate_table(old, new, create_sql, copy_cols):
        cursor.execute(create_sql)
        cursor.execute(f"INSERT INTO {new} SELECT {copy_cols} FROM {old}")
        cursor.execute(f"DROP TABLE {old}")
        cursor.execute(f"ALTER TABLE {new} RENAME TO {old}")
    # records_filterings
    recreate_table(
        "records_filterings", "_new_records_filterings",
        """
        CREATE TABLE _new_records_filterings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL,
            filtering_query_id INTEGER NOT NULL,
            match_result INTEGER NOT NULL,
            explanation TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (record_id) REFERENCES research_articles(id) ON DELETE CASCADE,
            FOREIGN KEY (filtering_query_id) REFERENCES filtering_queries(id) ON DELETE CASCADE
        )
        """,
        "id, record_id, filtering_query_id, match_result, explanation, timestamp"
    )
    # pdf_resolutions
    recreate_table(
        "pdf_resolutions", "_new_pdf_resolutions",
        """
        CREATE TABLE _new_pdf_resolutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL,
            filtering_query_id INTEGER,
            timestamp TEXT NOT NULL,
            candidates TEXT NOT NULL,
            FOREIGN KEY (record_id) REFERENCES research_articles(id) ON DELETE CASCADE,
            FOREIGN KEY (filtering_query_id) REFERENCES filtering_queries(id) ON DELETE SET NULL
        )
        """,
        "id, record_id, filtering_query_id, timestamp, candidates"
    )
    # pdf_downloads
    recreate_table(
        "pdf_downloads", "_new_pdf_downloads",
        """
        CREATE TABLE _new_pdf_downloads (
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
        )
        """,
        "id, record_id, filtering_query_id, timestamp, url, source, status, pdf_local_path, sha1, final_url, error_message"
    )
    # 3. Recreate indexes
    print("Recreating indexes...")  # noqa: T201
    cursor.executescript("""
    DROP INDEX IF EXISTS idx_records_filterings_record_id;
    CREATE INDEX IF NOT EXISTS idx_records_filterings_record_id ON records_filterings(record_id);
    DROP INDEX IF EXISTS idx_records_filterings_filtering_query_id;
    CREATE INDEX IF NOT EXISTS idx_records_filterings_filtering_query_id ON records_filterings(filtering_query_id);
    DROP INDEX IF EXISTS idx_pdf_resolutions_record_id;
    CREATE INDEX IF NOT EXISTS idx_pdf_resolutions_record_id ON pdf_resolutions(record_id);
    DROP INDEX IF EXISTS idx_pdf_resolutions_filtering_query_id;
    CREATE INDEX IF NOT EXISTS idx_pdf_resolutions_filtering_query_id ON pdf_resolutions(filtering_query_id);
    DROP INDEX IF EXISTS idx_pdf_downloads_record_id;
    CREATE INDEX IF NOT EXISTS idx_pdf_downloads_record_id ON pdf_downloads(record_id);
    DROP INDEX IF EXISTS idx_pdf_downloads_filtering_query_id;
    CREATE INDEX IF NOT EXISTS idx_pdf_downloads_filtering_query_id ON pdf_downloads(filtering_query_id);
    DROP INDEX IF EXISTS idx_pdf_downloads_status;
    CREATE INDEX IF NOT EXISTS idx_pdf_downloads_status ON pdf_downloads(status);
    """)
    conn.commit()
    conn.close()
    print("Migration complete! Table 'records' is now 'research_articles' and all foreign keys are updated.")  # noqa: T201

if __name__ == "__main__":
    migrate()
