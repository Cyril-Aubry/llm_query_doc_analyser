import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from sqlite3 import IntegrityError
from typing import Any

import pandas as pd
import structlog
import typer
from dotenv import load_dotenv

from .core.models import Record
from .core.store import (
    DB_PATH,
    batch_insert_filtering_results,
    create_filtering_query,
    filter_already_downloaded_records,
    filter_unresolved_records,
    get_matched_records_by_filtering_query,
    get_pdf_download_stats,
    get_record_provenance,
    get_records,
    get_resolved_candidates,
    init_db,
    insert_pdf_resolution,
    insert_record,
    record_pdf_download_attempt,
    update_enrichment_record,
    update_filtering_query_stats,
)
from .enrich.orchestrator import enrich_record, format_enrichment_report
from .filter_rank.prompts import filter_records_with_llm
from .io_.load import load_records
from .pdfs.download import download_pdf
from .pdfs.resolve import resolve_pdf_candidates
from .utils.files import rename_pdf_file
from .utils.log import get_logger, setup_logging
from .utils.provenance import formatted_provenance

# Load environment variables from .env file
load_dotenv()

# Global state for logging configuration
_log_state: dict[str, Any] = {
    "session_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
    "log_file": None,
    "logger": None,
}

app = typer.Typer()


@app.callback()
def callback(
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress console log output (logs still written to file)"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose (DEBUG) logging"),
) -> None:
    """Initialize application with structured logging."""
    # Determine log level
    log_level = "DEBUG" if verbose else os.getenv("LOG_LEVEL", "INFO")

    # Setup logging with console output option
    console_output = not quiet
    _log_state["log_file"] = setup_logging(
        session_id=_log_state["session_id"],
        log_level=log_level,
        console_output=console_output,
    )
    _log_state["logger"] = get_logger(__name__)

    if console_output:
        _log_state["logger"].info(
            "application_started",
            session_id=_log_state["session_id"],
            log_file=str(_log_state["log_file"]),
            quiet=quiet,
            verbose=verbose,
        )


def _get_logger() -> structlog.BoundLogger | Any:
    """Get the application logger."""
    if _log_state["logger"] is None:
        # Fallback: initialize with defaults
        _log_state["log_file"] = setup_logging(session_id=_log_state["session_id"])
        _log_state["logger"] = get_logger(__name__)
    return _log_state["logger"]


# Module-level logger accessor
log = type("LogProxy", (), {"__getattr__": lambda self, name: getattr(_get_logger(), name)})()
session_id = _log_state["session_id"]


@app.command()
def import_(path: Path) -> None:
    """Import CSV/XLSX into DB or memory, normalize DOIs."""
    log.info("import_started", path=str(path))
    init_db()
    records = load_records(path)
    inserted_count = 0
    skipped_count = 0
    for rec in records:
        try:
            insert_record(rec)
            inserted_count += 1
        except IntegrityError as e:
            if "UNIQUE constraint failed: research_articles.doi_norm" in str(e):
                log.warning("duplicate_doi_skipped", doi_norm=rec.doi_norm, title=rec.title)
                typer.echo(f"Skipped duplicate DOI: {rec.doi_norm} (Title: {rec.title})")
                skipped_count += 1
            else:
                # Re-raise other IntegrityErrors if not related to doi_norm
                raise
    log.info(
        "import_completed",
        record_count=len(records),
        inserted_count=inserted_count,
        skipped_count=skipped_count,
        path=str(path),
    )
    typer.echo(
        f"Imported {inserted_count} research articles from {path} (skipped {skipped_count} duplicates)"
    )


@app.command()
def enrich(
    sources: str = typer.Option("unpaywall,crossref,openalex", help="Comma-separated sources"),
    max_workers: int = 8,
    auto_enrich_published: bool = typer.Option(
        True,
        help="Automatically enrich newly discovered published versions in a second pass"
    ),
) -> None:
    """Enrich research articles with abstracts and OA info.
    
    If preprints with published versions are discovered, automatically runs a second
    enrichment pass to enrich the newly created published version records.
    """
    log.info("enrich_started", sources=sources, max_workers=max_workers, auto_enrich_published=auto_enrich_published)
    
    # Helper function to get unenriched records
    def get_unenriched_records() -> list[Record]:
        all_records = get_records()
        return [rec for rec in all_records if rec.enrichment_datetime is None]
    
    # Get initial unenriched records
    records = get_unenriched_records()
    if not records:
        log.warning("no_records_to_enrich")
        typer.echo("No research articles found to enrich.")
        return

    clients: dict[str, Any] = {}  # In production, pass API clients as needed

    async def enrich_batch(
        batch_records: list[Record],
        enrichment_datetime: str,
        pass_number: int = 1
    ) -> tuple[list[Record], int]:
        """Enrich a batch of records and return enriched records with count of new published versions."""
        typer.echo(f"\n{'='*80}")
        typer.echo(f"ENRICHMENT PASS {pass_number}")
        typer.echo(f"{'='*80}")
        typer.echo(f"\nEnriching {len(batch_records)} records...\n")
        
        tasks = [enrich_record(rec, clients) for rec in batch_records]
        enriched = await asyncio.gather(*tasks)
        
        # Track newly discovered published versions
        new_published_count = 0
        
        # Display enrichment reports for all records
        typer.echo("\n" + "="*80)
        typer.echo(f"ENRICHMENT RESULTS - PASS {pass_number}")
        typer.echo("="*80 + "\n")
        
        for rec in enriched:
            rec.enrichment_datetime = enrichment_datetime
            update_enrichment_record(rec)
            
            # Check if this record has a newly discovered published version
            if rec.enrichment_report.get("preprint_detection", {}).get("published_version"):
                pub_version = rec.enrichment_report["preprint_detection"]["published_version"]
                if pub_version.get("link_created"):
                    new_published_count += 1
                    typer.echo(f"📄 Discovered published version: {pub_version.get('doi')} (Record ID: {pub_version.get('published_version_record_id')})")
            
            # Display the enrichment report
            report = format_enrichment_report(rec)
            typer.echo(report)
        
        return enriched, new_published_count

    # Run first enrichment pass
    enrichment_datetime = datetime.now(UTC).isoformat()
    enriched_records, new_published_count = asyncio.run(
        enrich_batch(records, enrichment_datetime, pass_number=1)
    )
    
    log.info(
        "enrich_pass_completed",
        pass_number=1,
        record_count=len(enriched_records),
        new_published_versions=new_published_count
    )
    
    # Check if we should run a second pass for newly discovered published versions
    if auto_enrich_published and new_published_count > 0:
        typer.echo("\n" + "="*80)
        typer.echo(f"🔄 {new_published_count} published version(s) discovered!")
        typer.echo("Starting automatic second enrichment pass...")
        typer.echo("="*80)
        
        log.info(
            "starting_second_enrichment_pass",
            new_published_count=new_published_count
        )
        
        # Get newly created unenriched records (published versions)
        second_pass_records = get_unenriched_records()
        
        if second_pass_records:
            # Run second enrichment pass with a new timestamp
            second_enrichment_datetime = datetime.now(UTC).isoformat()
            second_enriched, second_pass_new_published = asyncio.run(
                enrich_batch(second_pass_records, second_enrichment_datetime, pass_number=2)
            )
            
            log.info(
                "enrich_pass_completed",
                pass_number=2,
                record_count=len(second_enriched),
                new_published_versions=second_pass_new_published
            )
            
            # Final summary
            typer.echo("\n" + "="*80)
            typer.echo("✓ ENRICHMENT COMPLETE - 2 PASSES")
            typer.echo("="*80)
            typer.echo(f"  Pass 1: {len(enriched_records)} records enriched")
            typer.echo(f"          {new_published_count} published version(s) discovered")
            typer.echo(f"  Pass 2: {len(second_enriched)} published version(s) enriched")
            if second_pass_new_published > 0:
                typer.echo(f"          ⚠️  {second_pass_new_published} additional published version(s) discovered")
                typer.echo("          Run 'enrich' again to process them.")
            typer.echo("="*80)
        else:
            log.warning("no_records_for_second_pass")
            typer.echo("\n⚠️  No unenriched records found for second pass (this shouldn't happen)")
    else:
        # Single pass summary
        typer.echo("\n" + "="*80)
        typer.echo("✓ ENRICHMENT COMPLETE")
        typer.echo("="*80)
        typer.echo(f"  Successfully enriched {len(enriched_records)} research articles.")
        if new_published_count > 0 and not auto_enrich_published:
            typer.echo(f"  {new_published_count} published version(s) discovered but not auto-enriched.")
            typer.echo("  Run 'enrich' again or use --auto-enrich-published to process them.")
        typer.echo("="*80)


def export_records(records: list[Record], export_path: Path, format: str = "parquet") -> None:
    """Export records to the specified file format."""
    df = pd.DataFrame([rec.model_dump() for rec in records])
    if format == "parquet":
        df.to_parquet(export_path, index=False)
    elif format == "csv":
        df.to_csv(export_path, index=False)
    elif format == "xlsx":
        df.to_excel(export_path, index=False)
    else:
        raise ValueError(f"Unsupported export format: {format}")


@app.command()
def provenance(record_id: int) -> None:
    """Show provenance information for a record by ID."""
    init_db()
    prov = get_record_provenance(record_id)
    out = formatted_provenance(prov)
    typer.echo(out)


@app.command()
def version_stats() -> None:
    """Show pre-print to published version linking statistics."""
    from .core.store import get_version_linking_stats
    
    log.info("version_stats_command_started")
    init_db()
    
    stats = get_version_linking_stats()
    
    typer.echo("\n=== Pre-Print to Published Version Linking Statistics ===\n")
    typer.echo(f"Total pre-prints: {stats['total_preprints']}")
    typer.echo(f"Pre-prints with published version: {stats['preprints_with_published_version']}")
    typer.echo(f"Published articles with pre-print version: {stats['published_with_preprint_version']}")
    typer.echo(f"Linking rate: {stats['linking_rate']:.2f}%\n")
    
    if stats['by_preprint_source']:
        typer.echo("Pre-prints by source:")
        for source, count in stats['by_preprint_source'].items():
            typer.echo(f"  - {source}: {count}")
        typer.echo()
    
    if stats['by_version_discovery_source']:
        typer.echo("Version links discovered by:")
        for source, count in stats['by_version_discovery_source'].items():
            typer.echo(f"  - {source}: {count}")
        typer.echo()
    
    log.info("version_stats_command_completed", stats=stats)


@app.command()
def filter(
    query: str = typer.Option(..., "--query", "-q", help="Query string for filtering records"),
    exclude: str = "",
    max_concurrent: int = typer.Option(10, help="Maximum concurrent API calls"),
    export_path: Path | None = typer.Option(  # noqa: B008
        None, "--export", "-e", help="Optional export path for filtered records"
    ),
) -> None:
    """Filter research articles by querying OpenAI's LLM for relevance using async parallelized calls.

    Results are stored in the database (filtering_queries and records_filterings tables, referencing research_articles).
    Optionally export filtered research articles to a file.
    """
    filtering_query_datetime = datetime.now(UTC).isoformat()
    log.info(
        "filter_started",
        query=query,
        exclude=exclude,
        max_concurrent=max_concurrent,
        timestamp=filtering_query_datetime,
    )

    # Retrieve OpenAI API key and model name from environment variables
    openai_api_key = os.getenv("OPENAI_API_KEY")
    model_name = os.getenv("OPENAI_MODEL")

    if not openai_api_key:
        log.error("openai_api_key_missing")
        raise ValueError("OpenAI API key not found. Please set it in the .env file.")
    if not model_name:
        log.error("openai_model_missing")
        raise ValueError("OpenAI model name not found. Please set it in the .env file.")

    log.info("openai_client_configured", model=model_name, max_concurrent=max_concurrent)

    # Get research articles from database
    records = get_records()

    if not records:
        log.warning("no_research_articles_found")
        typer.echo("No research articles found to filter.")
        return

    log.info("filtering_research_articles", total_records=len(records))

    # Create filtering query record in database
    filtering_query_id = create_filtering_query(
        timestamp=filtering_query_datetime,
        query=query,
        exclude_criteria=exclude,
        llm_model=model_name,
        max_concurrent=max_concurrent,
    )

    log.info("filtering_query_created", filtering_query_id=filtering_query_id)

    # Progress reporting
    typer.echo(f"\nFiltering {len(records)} research articles with query: '{query}'")
    if exclude:
        typer.echo(f"Excluding: '{exclude}'")
    typer.echo(f"Using model: {model_name} (max concurrent: {max_concurrent})")
    typer.echo("Progress: 0%", nl=False)

    def progress_callback(completed: int, total: int) -> None:
        """Update progress in the terminal."""
        percent = int((completed / total) * 100)
        typer.echo(f"\rProgress: {percent}% ({completed}/{total})", nl=False)

    # Run async filtering with parallelization
    filtering_results = asyncio.run(
        filter_records_with_llm(
            records=records,
            query=query,
            exclude=exclude,
            api_key=openai_api_key,
            model_name=model_name,
            max_concurrent=max_concurrent,
            progress_callback=progress_callback,
        )
    )

    typer.echo("\n")  # New line after progress

    # Store results in database
    log.info("storing_filtering_results", count=len(filtering_results))

    # Prepare batch insert data
    batch_data = []
    matched_count = 0
    failed_count = 0
    warning_count = 0

    for result in filtering_results:
        record_id, match_result, explanation = result
        batch_data.append((record_id, filtering_query_id, match_result, explanation))

        # Count matched records (only those without errors)
        if match_result and not explanation.startswith("ERROR:"):
            matched_count += 1

        # Count processing failures (API errors, exceptions, etc.)
        if explanation.startswith("ERROR:"):
            failed_count += 1

        # Count suspicious results (missing explanations, parse failures)
        if explanation.startswith("WARNING:"):
            warning_count += 1

    # Batch insert filtering results
    batch_insert_filtering_results(batch_data)

    # Update filtering query statistics
    update_filtering_query_stats(
        filtering_query_id=filtering_query_id,
        total_records=len(records),
        matched_count=matched_count,
        failed_count=failed_count,
    )

    log.info(
        "filter_completed",
        filtering_query_id=filtering_query_id,
        total_records=len(records),
        matched_count=matched_count,
        failed_count=failed_count,
        warning_count=warning_count,
    )

    typer.echo("Filtering completed:")
    typer.echo(f"  Total research articles processed: {len(records)}")
    typer.echo(f"  Matched articles: {matched_count}")
    typer.echo(f"  Failed articles (errors): {failed_count}")
    if warning_count > 0:
        typer.echo(f"  Warning articles (missing explanation): {warning_count}")
    typer.echo(f"  Filtering query ID: {filtering_query_id}")
    typer.echo(f"\nResults stored in database: {DB_PATH}")

    # Optional export
    if export_path:
        from .io_.export import export_records

        # Get matched research articles for export (excluding error and warning records)
        matched_records = []
        for rec, result in zip(records, filtering_results, strict=False):
            record_id, match_result, explanation = result
            # Only export articles that matched AND have valid explanations (no errors or warnings)
            if (
                match_result
                and not explanation.startswith("ERROR:")
                and not explanation.startswith("WARNING:")
            ):
                matched_records.append(rec)

        export_format = export_path.suffix.lstrip(".")
        if export_format not in {"parquet", "csv", "xlsx"}:
            raise ValueError("Unsupported export format. Use .parquet, .csv, or .xlsx")

        export_records(matched_records, export_path, format=export_format)
        log.info("research_articles_exported", path=str(export_path), count=len(matched_records))
        typer.echo(f"  Exported {len(matched_records)} matched research articles to: {export_path}")


@app.command()
def pdfs(
    filtering_query_id: int = typer.Option(
        ..., "--query-id", help="Filtering query ID to download PDFs for"
    ),
    dest: Path | None = typer.Option(None, "--dest", "-d", help="Destination directory for PDFs"),  # noqa: B008
    max_concurrent: int = typer.Option(5, help="Maximum concurrent downloads"),
) -> None:
    """Download OA PDFs for matched records from a filtering query.

    Resolves PDF candidates and attempts downloads, storing results in database.
    """
    timestamp = datetime.now().isoformat()
    log.info(
        "pdf_download_started",
        filtering_query_id=filtering_query_id,
        destination=str(dest),
        timestamp=timestamp,
    )

    # Initialize database
    init_db()

    # Resolve default destination if not provided (avoid calling Path() at import time)
    if dest is None:
        dest = Path("data/pdfs")

    # Get matched records from filtering query
    typer.echo(f"\nFetching matched records from filtering query {filtering_query_id}...")
    matched_filtering_query_records = get_matched_records_by_filtering_query(filtering_query_id)

    if not matched_filtering_query_records:
        log.warning("no_matched_records_found", filtering_query_id=filtering_query_id)
        typer.echo("No matched records found for this filtering query.")
        return

    typer.echo(f"Found {len(matched_filtering_query_records)} matched records to process.")
    typer.echo(f"Destination: {dest}")

    # Separate unresolved records (need resolution) from already resolved records
    unresolved_records = filter_unresolved_records(matched_filtering_query_records)
    already_resolved_count = len(matched_filtering_query_records) - len(unresolved_records)

    log.info(
        "pdf_resolution_status",
        total_records=len(matched_filtering_query_records),
        unresolved_count=len(unresolved_records),
        already_resolved_count=already_resolved_count,
    )

    typer.echo(f"  Already resolved: {already_resolved_count} records")
    typer.echo(f"  Need resolution: {len(unresolved_records)} records")

    # PHASE 1: Resolve PDF candidates for unresolved records only
    if unresolved_records:
        typer.echo("\n[Phase 1] Resolving PDF candidates for unresolved records...")

        resolved_count = 0
        no_candidates_count = 0

        for rec in unresolved_records:
            # Resolve PDF candidates
            candidates = resolve_pdf_candidates(rec)

            # Store resolution in database
            insert_pdf_resolution(
                record_id=rec.id,
                candidates=candidates,
                resolution_datetime=timestamp,
            )

            if candidates:
                resolved_count += 1
                log.debug(
                    "pdf_candidates_resolved",
                    record_id=rec.id,
                    doi=rec.doi_norm,
                    candidate_count=len(candidates),
                )
            else:
                no_candidates_count += 1
                log.debug("no_pdf_candidates", record_id=rec.id, doi=rec.doi_norm)

        log.info(
            "pdf_resolution_completed",
            total_resolved=resolved_count,
            no_candidates=no_candidates_count,
        )

        typer.echo(f"  Resolved with candidates: {resolved_count}")
        typer.echo(f"  No candidates found: {no_candidates_count}")
    else:
        typer.echo("\n[Phase 1] Skipped - all records already resolved")

    # PHASE 2: Download PDFs for records that haven't been successfully downloaded yet
    typer.echo("\n[Phase 2] Downloading PDFs from resolved candidates, if not already downloaded...")

    # Filter records to only those not already downloaded
    records_needing_download = filter_already_downloaded_records(matched_filtering_query_records)
    already_downloaded_count = len(matched_filtering_query_records) - len(records_needing_download)

    log.info(
        "pdf_download_filtering",
        total_records=len(matched_filtering_query_records),
        already_downloaded=already_downloaded_count,
        needs_download=len(records_needing_download),
    )

    typer.echo(f"  Already downloaded: {already_downloaded_count} records")
    typer.echo(f"  Need download: {len(records_needing_download)} records")

    # Statistics
    downloaded_count = 0
    unavailable_count = 0
    too_large_count = 0
    error_count = 0
    no_candidates_for_download = 0

    # Process each record for download
    async def download_record_pdf(rec: Record) -> None:
        nonlocal downloaded_count, unavailable_count, too_large_count, error_count, no_candidates_for_download

        # Retrieve resolved candidates from database
        candidates = get_resolved_candidates(rec.id)
        if not candidates:
            no_candidates_for_download += 1
            log.debug("no_pdf_candidates_for_download", record_id=rec.id, doi=rec.doi_norm)
            # Store a "no candidates" download record
            record_pdf_download_attempt(
                record_id=rec.id,
                url="",
                source="none",
                status="no_candidates",
                download_attempt_datetime=timestamp,
                error_message="No PDF candidates found",
            )
            return

        # Try each candidate in order
        download_success = False
        for cand in candidates:
            try:
                result = await download_pdf(cand, dest)
                status = result.get("status")

                # If downloaded, attempt to rename the file into a safe, title-derived name
                if status == "downloaded":
                    orig_path = result.get("path")
                    final_path_str = None
                    try:
                        if orig_path:
                            final_path = rename_pdf_file(Path(orig_path), rec.title, dest)
                            final_path_str = str(final_path)
                    except Exception as re:
                        # If rename fails, record the error but keep the original path
                        log.error(
                            "pdf_rename_error",
                            record_id=rec.id,
                            doi=rec.doi_norm,
                            orig_path=orig_path,
                            error=str(re),
                        )

                    # Store successful download attempt, prefer the renamed path when available
                    record_pdf_download_attempt(
                        record_id=rec.id,
                        url=cand.get("url", ""),
                        source=cand.get("source", "unknown"),
                        status=status,
                        download_attempt_datetime=timestamp,
                        pdf_local_path=final_path_str or result.get("path"),
                        sha1=result.get("sha1"),
                        final_url=result.get("final_url"),
                        error_message=result.get("error"),
                    )

                    downloaded_count += 1
                    download_success = True
                    log.info(
                        "pdf_downloaded",
                        record_id=rec.id,
                        doi=rec.doi_norm,
                        source=cand.get("source"),
                        path=final_path_str or result.get("path"),
                    )
                    break

                # Non-downloaded statuses: record attempt as-is
                record_pdf_download_attempt(
                    record_id=rec.id,
                    url=cand.get("url", ""),
                    source=cand.get("source", "unknown"),
                    status=status,
                    download_attempt_datetime=timestamp,
                    pdf_local_path=result.get("path"),
                    sha1=result.get("sha1"),
                    final_url=result.get("final_url"),
                    error_message=result.get("error"),
                )

                if status == "too_large":
                    too_large_count += 1
                    log.debug("pdf_too_large", record_id=rec.id, url=cand.get("url"))
                elif status == "unavailable":
                    unavailable_count += 1
                    log.debug("pdf_unavailable", record_id=rec.id, url=cand.get("url"))

            except Exception as e:
                error_count += 1
                log.error(
                    "pdf_download_error",
                    record_id=rec.id,
                    doi=rec.doi_norm,
                    url=cand.get("url"),
                    error=str(e),
                )
                # Store error
                record_pdf_download_attempt(
                    record_id=rec.id,
                    url=cand.get("url", ""),
                    source=cand.get("source", "unknown"),
                    status="error",
                    download_attempt_datetime=timestamp,
                    error_message=str(e),
                )

        if not download_success:
            log.debug("pdf_all_attempts_failed", record_id=rec.id, doi=rec.doi_norm)

    # Process only records needing download with concurrency limit
    async def process_all_downloads() -> None:
        semaphore = asyncio.Semaphore(max_concurrent)

        async def download_with_semaphore(rec: Record) -> None:
            async with semaphore:
                await download_record_pdf(rec)

        tasks = [download_with_semaphore(rec) for rec in records_needing_download]
        await asyncio.gather(*tasks)

    # Run download processing only for records that need it
    if records_needing_download:
        asyncio.run(process_all_downloads())
    else:
        typer.echo("  All matched records already have PDFs downloaded. Skipping download phase.")

    # Get final statistics from database
    stats = get_pdf_download_stats(filtering_query_id)

    log.info(
        "pdf_download_completed",
        filtering_query_id=filtering_query_id,
        total_records=len(matched_filtering_query_records),
        stats=stats,
        destination=str(dest),
    )

    # Display results
    typer.echo("\nPDF Download Results:")
    typer.echo(f"  Total records processed: {len(matched_filtering_query_records)}")
    typer.echo(f"  Already downloaded (skipped): {already_downloaded_count}")
    typer.echo(f"  Successfully downloaded (new): {downloaded_count}")
    typer.echo(f"  No candidates found: {stats.get('no_candidates', 0)}")
    typer.echo(f"  Unavailable: {stats.get('unavailable', 0)}")
    typer.echo(f"  Too large: {stats.get('too_large', 0)}")
    typer.echo(f"  Errors: {stats.get('error', 0)}")
    typer.echo(f"\nPDFs saved to: {dest}")
    typer.echo(f"Results stored in database: {DB_PATH}")


@app.command()
def export(from_: Path | None = None, format: str = "xlsx") -> None:
    """Export results with rationale and clickable links."""
    log.info("export_started", source=str(from_), format=format)

    if from_ is None:
        from_ = typer.Option(..., "--from")
    import pandas as pd

    df = pd.read_parquet(from_)
    records = [Record(**row) for _, row in df.iterrows()]
    output_path = from_.with_suffix(f".{format}")
    export_records(records, output_path, format=format)

    log.info("export_completed", record_count=len(records), output=str(output_path), format=format)
    typer.echo(f"Exported results to {output_path}")
