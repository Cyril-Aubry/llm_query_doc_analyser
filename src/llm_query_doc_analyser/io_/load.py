from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Removed deprecated List import
import pandas as pd

from ..core.hashing import normalize_doi
from ..core.models import Record
from ..enrich.preprint_detection import detect_preprint_source
from ..utils.log import get_logger

log = get_logger(__name__)


def load_records(path: Path) -> list[Record]:
    """Load research articles from CSV/XLSX, normalize DOIs, dedupe."""
    log.info("loading_research_articles", path=str(path), format=path.suffix)

    df = pd.read_excel(path) if path.suffix.lower() == ".xlsx" else pd.read_csv(path)

    # Require title, optional doi/date
    if "Title" not in df.columns:
        log.error("missing_title_column", path=str(path))
        raise ValueError("Input must have a 'Title' column.")
    df["doi_norm"] = df["DOI"].apply(normalize_doi) if "DOI" in df.columns else None

    def to_pub_date(val: datetime | None) -> None | Any | str:
        if pd.isnull(val):
            return None
        if hasattr(val, "isoformat"):
            return val.isoformat()
        return str(val)

    # Convert to numeric, coercing errors to NaN
    if "Total Citations" in df.columns:
        # Use 'Int64' to store integers with nullable capability (no NaN for int)
        df["Total Citations"] = pd.to_numeric(df["Total Citations"], errors="coerce").astype(
            "Int64"
        )

    if "Average per Year" in df.columns:
        df["Average per Year"] = pd.to_numeric(df["Average per Year"], errors="coerce")

    # Convert Publication Date
    if "Publication Date" in df.columns:

        def safe_isoformat(val: datetime) -> None | Any | str:
            if pd.isnull(val):
                return None
            # Attempt to convert to datetime first, then format
            try:
                # If it's already a datetime object (from read_excel), it works.
                # Otherwise, pd.to_datetime tries to parse it.
                dt = pd.to_datetime(val)
                return dt.isoformat()
            except (ValueError, TypeError):
                # If conversion fails, return the string representation, or None
                return str(val) if val is not None else None

        # Apply the function *to the Series*, which is still faster than row-wise iteration
        df["pub_date_norm"] = df["Publication Date"].apply(safe_isoformat)

    # Convert strings (Source Title, Authors) and replace NaNs with None for the Record object
    # The existing to_str function logic is effectively what is needed,
    # but we can apply it to the Series for speed.
    def to_str_or_none(val: str) -> str | None:
        return str(val) if pd.notna(val) else None

    for col in ["Authors", "Source Title"]:
        if col in df.columns:
            # Applying a function to a Series is faster than df.iterrows()
            df[col] = df[col].apply(to_str_or_none)

    df["import_datetime"] = datetime.now(UTC).isoformat()

    # --- Update the final Record creation ---

    records = [
        Record(
            title=row["Title"],
            doi_raw=row.get("DOI"),
            doi_norm=row.get("doi_norm"),
            # Use the pre-processed column if available, otherwise use original and apply logic
            pub_date=row.get("pub_date_norm")
            if "pub_date_norm" in df.columns
            else to_pub_date(row.get("Publication Date")),
            total_citations=row.get(
                "Total Citations"
            ),  # Nullable Int64 converts to None in row.get() if Null
            import_datetime=row.get("import_datetime"),
            citations_per_year=row.get("Average per Year"),  # NaN converts to None in row.get()
            authors=row.get("Authors"),  # Already converted to str or None
            source_title=row.get("Source Title"),  # Already converted to str or None
        )
        for _, row in df.iterrows()
    ]
    
    # Detect pre-print sources at import time
    preprint_count = 0
    for rec in records:
        preprint_source = detect_preprint_source(rec)
        if preprint_source:
            rec.is_preprint = True
            rec.preprint_source = preprint_source
            preprint_count += 1
            log.debug(
                "preprint_detected_at_import",
                doi=rec.doi_norm,
                source_title=rec.source_title,
                preprint_source=preprint_source
            )
        if preprint_source == 'arxiv' and rec.doi_norm and rec.doi_norm.startswith("arxiv:"):
                rec.doi_norm = rec.doi_norm.replace("arxiv:", "10.48550/arXiv.")

    log.info(
        "research_articles_loaded", 
        count=len(records), 
        preprint_count=preprint_count,
        path=str(path)
    )
    return records
