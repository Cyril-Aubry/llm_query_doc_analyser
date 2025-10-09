from pathlib import Path
from typing import Any

import httpx

from ..core.hashing import sha1_bytes
from ..utils.http import get_with_retry
from ..utils.log import get_logger

log = get_logger(__name__)

MAX_PDF_SIZE = 50 * 1024 * 1024  # 50 MB


def _get_pdf_headers(url: str, source: str | None = None) -> dict[str, str]:
    """Get appropriate headers for PDF download based on source."""
    base_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/pdf,*/*;q=0.8",
    }
    
    # bioRxiv/medRxiv specific headers
    if source in ("biorxiv", "medrxiv") or any(x in url.lower() for x in ("biorxiv.org", "medrxiv.org")):
        base_headers.update({
            "Referer": "https://www.google.com/",
            "Cache-Control": "no-cache",
        })
    
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

                log.info("pdf_downloaded", url=url, sha1=sha1, size=content_length, source=source)
                return {
                    "status": "downloaded",
                    "path": str(pdf_path),
                    "sha1": sha1,
                    "final_url": str(resp.url),
                    "url": url,
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