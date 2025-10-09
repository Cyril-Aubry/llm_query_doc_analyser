from pathlib import Path
from typing import Any

import httpx
import typer

from ..core.hashing import sha1_bytes

MAX_PDF_SIZE = 50 * 1024 * 1024  # 50 MB


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
    if not url:
        return {"status": "error", "error": "No URL provided"}

    if "preprints.org" in url:
        # Use the tailored headers for preprints.org
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/pdf,*/*;q=0.8",
            "Referer": url.split("/download")[0],  # Use the manuscript page as the referrer
            "Connection": "close",
        }
    else:
        # Use the generic but effective headers for other sites like bioRxiv
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/pdf, */*;q=0.8",  # Specify you want a PDF
            "Referer": "https://www.google.com/",  # May help some sites
            "Cache-Control": "no-cache",
            "Connection": "close",
        }

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=30.0,
            headers=headers,
        ) as client:
            resp = await client.get(url)

            if resp.status_code == 200:
                content_type = resp.headers.get("content-type", "")
                typer.echo(f"Content-Type: {content_type}")

                # Check if content is PDF
                if content_type.startswith("application/pdf"):
                    # Check size
                    content_length = int(resp.headers.get("content-length", len(resp.content)))
                    if content_length > MAX_PDF_SIZE:
                        return {"status": "too_large", "url": url, "size": content_length}

                    # Download and save
                    sha1 = sha1_bytes(resp.content)
                    pdf_path = dest_dir / f"{sha1}.pdf"
                    pdf_path.write_bytes(resp.content)

                    return {
                        "status": "downloaded",
                        "path": str(pdf_path),
                        "sha1": sha1,
                        "final_url": str(resp.url),
                        "url": url,
                    }
                else:
                    return {
                        "status": "unavailable",
                        "url": url,
                        "error": f"Content type is {content_type}, not PDF",
                    }
            else:
                return {
                    "status": "unavailable",
                    "url": url,
                    "error": f"HTTP {resp.status_code}",
                }

    except httpx.TimeoutException:
        return {"status": "error", "url": url, "error": "Request timeout"}
    except httpx.HTTPError as e:
        return {"status": "error", "url": url, "error": f"HTTP error: {e!s}"}
    except Exception as e:
        return {"status": "error", "url": url, "error": f"Unexpected error: {e!s}"}
