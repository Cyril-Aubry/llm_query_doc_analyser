"""Migration: Add citation and bibliographic fields to research_articles table.

This migration adds:
- total_citations (INTEGER)
- citations_per_year (REAL)
- authors (TEXT)
- source_title (TEXT)

Run this if you have an existing database.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path("data/cache/records.db")


def migrate():
    """Add new columns to existing research_articles table."""
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}. No migration needed.")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if columns already exist
    cursor.execute("PRAGMA table_info(research_articles)")
    columns = {row[1] for row in cursor.fetchall()}
    
    migrations_needed = []
    
    if "total_citations" not in columns:
        migrations_needed.append(("total_citations", "INTEGER"))
    if "citations_per_year" not in columns:
        migrations_needed.append(("citations_per_year", "REAL"))
    if "authors" not in columns:
        migrations_needed.append(("authors", "TEXT"))
    if "source_title" not in columns:
        migrations_needed.append(("source_title", "TEXT"))
    
    if not migrations_needed:
        print("All columns already exist. No migration needed.")
        conn.close()
        return
    
    print(f"Adding {len(migrations_needed)} new columns to research_articles table...")
    
    for col_name, col_type in migrations_needed:
        try:
            cursor.execute(f"ALTER TABLE research_articles ADD COLUMN {col_name} {col_type}")
            print(f"  \u2713 Added column: {col_name} ({col_type})")
        except sqlite3.OperationalError as e:
            print(f"  \u2717 Failed to add {col_name}: {e}")
    
    conn.commit()
    conn.close()
    print("Migration complete!")


if __name__ == "__main__":
    migrate()
