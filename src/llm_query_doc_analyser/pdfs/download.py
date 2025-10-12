import asyncio
import random
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

from ..core.config import get_config
from ..core.hashing import sha1_bytes
from ..utils.files import sanitize_text_for_filename
from ..utils.http import get_with_retry
from ..utils.log import get_logger

log = get_logger(__name__)

MAX_PDF_SIZE = 50 * 1024 * 1024  # 50 MB

# Legacy constants for backward compatibility - use get_config() instead
DOCX_DIR = Path("data/docx")
MD_OUTPUT_DIR = Path("data/markdown")


def _get_docx_dir() -> Path:
    """Get current DOCX directory from configuration."""
    return get_config().docx_dir


def _get_markdown_dir() -> Path:
    """Get current Markdown directory from configuration."""
    return get_config().markdown_dir


def _get_pdf_headers(url: str, source: str | None = None) -> dict[str, str]:
    """Get appropriate headers for PDF download based on source."""
    # More complete browser-like headers to avoid bot detection
    base_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/pdf,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    
    # arXiv specific headers
    if source == "arxiv" or "arxiv.org" in url.lower():
        base_headers["Referer"] = "https://arxiv.org/"
        # Add stronger cache-busting for arXiv to bypass Varnish cache
        base_headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    
    # bioRxiv/medRxiv specific headers
    elif source in ("biorxiv", "medrxiv") or any(x in url.lower() for x in ("biorxiv.org", "medrxiv.org")):
        base_headers["Referer"] = "https://www.google.com/"
        base_headers["Cache-Control"] = "no-cache"
    
    # preprints.org specific headers
    elif source == "preprints" or "preprints.org" in url.lower():
        base_headers["Referer"] = url.split("/download")[0] if "/download" in url else url
    
    return base_headers


async def download_pdf(candidate: dict[str, Any], dest_dir: Path) -> dict[str, Any]:
    """Download PDF if OA, return status and path info.

    Args:
        candidate: Dictionary with 'url' and optional 'source', 'license' fields
        dest_dir: Destination directory for downloaded PDFs

    Returns:
        Dictionary with:
            - status: 'downloaded', 'unavailable', 'too_large', or 'error'
            - path: Local file path (if downloaded)
            - sha1: SHA1 hash (if downloaded)
            - final_url: Final URL after redirects (if downloaded)
            - url: Original URL
            - error: Error message (if error)
    """
    url = candidate.get("url")
    source = candidate.get("source")
    
    if not url:
        log.warning("pdf_download_no_url", candidate=candidate)
        return {"status": "error", "error": "No URL provided"}

    # Add cache-busting for arXiv to bypass Varnish caching of bot-detected responses
    if source == "arxiv" or "arxiv.org" in url.lower():
        # Add timestamp as query param to bust cache
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}_cb={int(time.time() * 1000)}"
        # Add small random delay (0-2 seconds) to further avoid pattern detection
        await asyncio.sleep(random.uniform(0, 2))
        log.debug("arxiv_cache_busting_applied", original_url=candidate.get("url"), modified_url=url)

    headers = _get_pdf_headers(url, source)
    
    try:
        # Use retry logic with proper error handling
        resp = await get_with_retry(url, headers=headers, timeout=30.0)
        
        if resp.status_code == 200:
            content_type = resp.headers.get("content-type", "")
            
            # Check if content is PDF
            if content_type.startswith("application/pdf"):
                # Check size
                content_length = int(resp.headers.get("content-length", len(resp.content)))
                
                if content_length > MAX_PDF_SIZE:
                    log.warning("pdf_too_large", url=url, size=content_length, max_size=MAX_PDF_SIZE)
                    return {"status": "too_large", "url": url, "size": content_length}

                # Download and save
                sha1 = sha1_bytes(resp.content)
                pdf_path = dest_dir / f"{sha1}.pdf"
                pdf_path.write_bytes(resp.content)
                
                # Get actual file size from written file for accuracy
                file_size_bytes = pdf_path.stat().st_size

                log.info("pdf_downloaded", url=url, sha1=sha1, size=file_size_bytes, source=source)
                return {
                    "status": "downloaded",
                    "path": str(pdf_path),
                    "sha1": sha1,
                    "final_url": str(resp.url),
                    "url": url,
                    "file_size_bytes": file_size_bytes,
                }
            else:
                log.warning("pdf_wrong_content_type", url=url, content_type=content_type, source=source)
                return {
                    "status": "unavailable",
                    "url": url,
                    "error": f"Content type is {content_type}, not PDF",
                }
        else:
            log.warning("pdf_http_error", url=url, status=resp.status_code, source=source)
            return {
                "status": "unavailable",
                "url": url,
                "error": f"HTTP {resp.status_code}",
            }

    except httpx.TimeoutException as e:
        log.error("pdf_timeout", url=url, source=source, error=str(e))
        return {"status": "error", "url": url, "error": "Request timeout"}
    except httpx.HTTPError as e:
        log.error("pdf_http_error", url=url, source=source, error=str(e))
        return {"status": "error", "url": url, "error": f"HTTP error: {e!s}"}
    except Exception as e:
        log.exception("pdf_unexpected_error", url=url, source=source)
        return {"status": "error", "url": url, "error": f"Unexpected error: {e!s}"}


def get_docx_for_pdf(pdf_path: Path) -> Path | None:
    """Try to find a corresponding .docx file in the configured DOCX directory using the PDF filename stem.

    Matching rules (deterministic):
    - Use pdf_path.stem (filename without extension).
    - Check DOCX directory for files with same stem + .docx (case-insensitive).
    - Also try a sanitized version of the stem (remove unsafe chars) to match common filename variants.

    Returns Path to the docx file if found, otherwise None.
    """
    docx_dir = _get_docx_dir()
    try:
        stem = pdf_path.stem
        # Direct exact match
        candidate = docx_dir / f"{stem}.docx"
        if candidate.exists():
            log.info("docx_found_exact", pdf=str(pdf_path), docx=str(candidate))
            return candidate

        # Case-insensitive search and sanitized match
        sanitized = sanitize_text_for_filename(stem)
        for p in docx_dir.glob("*.docx"):
            if p.stem.lower() == stem.lower() or p.stem == sanitized:
                log.info("docx_found_variant", pdf=str(pdf_path), docx=str(p))
                return p

        # Fallback: look for any docx whose stem is contained in pdf stem or vice versa
        for p in docx_dir.glob("*.docx"):
            if p.stem.lower() in stem.lower() or stem.lower() in p.stem.lower():
                log.info("docx_found_fuzzy", pdf=str(pdf_path), docx=str(p))
                return p

    except Exception as e:
        log.error("docx_lookup_error", pdf=str(pdf_path), error=str(e))

    log.debug("docx_not_found", pdf=str(pdf_path))
    return None


def _run_cmd(cmd: str, timeout: int = 60) -> tuple[int, str, str]:
    """Run a shell command (string) and return (returncode, stdout, stderr)."""
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        return 124, "", f"Timeout: {e!s}"
    except Exception as e:
        return 1, "", str(e)


def convert_docx_to_markdown_versions(docx_path: Path, output_dir: Path | None = None) -> dict[str, str | None]:
    """Create two markdown versions from a docx using pandoc.

    - No-images md: pandoc -s -t markdown_strict "file.docx" -o "file-no images.md"
    - With-images md: pandoc -s -t html --embed-resources=true "file.docx" | pandoc -f html -t markdown_strict -o "file.md"

    Returns dict with keys: docx, md_no_images, md_with_images and values as string paths or None on failure.
    """
    # Use configured markdown directory if not specified
    if output_dir is None:
        output_dir = _get_markdown_dir()
    else:
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    base_name = docx_path.stem
    md_no_images = output_dir / f"{base_name}-no images.md"
    md_with_images = output_dir / f"{base_name}.md"

    results: dict[str, str | None] = {
        "docx": str(docx_path),
        "md_no_images": None,
        "md_with_images": None,
    }

    # 1) No images conversion
    try:
        cmd1 = ["pandoc", "-s", "-t", "markdown_strict", str(docx_path), "-o", str(md_no_images)]
        log.debug("pandoc_cmd_no_images", cmd=cmd1)
        proc1 = subprocess.run(cmd1, capture_output=True, text=True, timeout=120)
        if proc1.returncode == 0 and md_no_images.exists():
            results["md_no_images"] = str(md_no_images)
            log.info("pandoc_no_images_success", docx=str(docx_path), out=str(md_no_images))
        else:
            log.error(
                "pandoc_no_images_failed",
                docx=str(docx_path),
                rc=proc1.returncode,
                stderr=proc1.stderr,
            )
    except subprocess.TimeoutExpired as e:
        log.error("pandoc_no_images_timeout", docx=str(docx_path), error=str(e))
    except Exception as e:
        log.exception("pandoc_no_images_exception", docx=str(docx_path), error=str(e))

    # 2) With images conversion via HTML embedding (create HTML with embedded resources, pipe to pandoc)
    try:
        # Use shell pipe to convert docx -> html with embedded resources -> markdown in one step
        cmd_with_images = f'pandoc -s -t html --embed-resources=true "{docx_path}" | pandoc -f html -t markdown_strict -o "{md_with_images}"'
        log.debug("pandoc_cmd_with_images", cmd=cmd_with_images)
        proc = subprocess.run(cmd_with_images, shell=True, capture_output=True, text=True, timeout=240)
        if proc.returncode == 0 and md_with_images.exists():
            results["md_with_images"] = str(md_with_images)
            log.info("pandoc_with_images_success", docx=str(docx_path), out=str(md_with_images))
        else:
            log.error(
                "pandoc_with_images_failed",
                docx=str(docx_path),
                rc=proc.returncode,
                stderr=proc.stderr,
            )
    except subprocess.TimeoutExpired as e:
        log.error("pandoc_with_images_timeout", docx=str(docx_path), error=str(e))
    except Exception as e:
        log.exception("pandoc_with_images_exception", docx=str(docx_path), error=str(e))

    return results