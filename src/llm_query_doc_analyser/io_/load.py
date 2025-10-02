from pathlib import Path

# Removed deprecated List import
import pandas as pd

from ..core.hashing import normalize_doi
from ..core.models import Record
from ..utils.log import get_logger

log = get_logger(__name__)


def load_records(path: Path) -> list[Record]:
    """Load records from CSV/XLSX, normalize DOIs, dedupe."""
    log.info("loading_records", path=str(path), format=path.suffix)
    
    df = pd.read_excel(path) if path.suffix.lower() == ".xlsx" else pd.read_csv(path)
    
    # Require title, optional doi/date
    if "Title" not in df.columns:
        log.error("missing_title_column", path=str(path))
        raise ValueError("Input must have a 'Title' column.")
    df["doi_norm"] = df["DOI"].apply(normalize_doi) if "DOI" in df.columns else None
    # Dedupe by doi_norm else fuzzy title (not implemented here)
    def to_pub_date(val):
        if pd.isnull(val):
            return None
        if hasattr(val, 'isoformat'):
            return val.isoformat()
        return str(val)

    records = [Record(
        title=row["Title"],
        doi_raw=row.get("DOI"),
        doi_norm=row.get("doi_norm"),
        pub_date=to_pub_date(row.get("Publication Date"))
    ) for _, row in df.iterrows()]
    
    log.info("records_loaded", count=len(records), path=str(path))
    return records
