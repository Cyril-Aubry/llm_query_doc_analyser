from pathlib import Path

import pandas as pd

from ..core.models import Record
from ..utils.log import get_logger

log = get_logger(__name__)


def export_records(records: list[Record], path: Path, format: str = "csv") -> None:
    """Export research articles to CSV/XLSX/Parquet with required columns."""
    log.info("exporting_research_articles", count=len(records), path=str(path), format=format)

    df = pd.DataFrame([r.model_dump() for r in records])
    cols = [
        "title",
        "doi_norm",
        "pub_date",
        "total_citations",
        "citations_per_year",
        "authors",
        "source_title",
        "abstract_source",
        "license",
        "is_oa",
    ]
    df = df[[c for c in cols if c in df.columns]]

    if format == "csv":
        df.to_csv(path, index=False)
    elif format == "xlsx":
        df.to_excel(path, index=False)
    elif format == "parquet":
        df.to_parquet(path, index=False)
    else:
        log.error("unsupported_export_format", format=format, path=str(path))
        raise ValueError(f"Unsupported export format: {format}")

    log.info("export_completed", count=len(records), path=str(path), format=format)
