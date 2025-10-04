from pathlib import Path
from typing import Any

import httpx

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
    
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            resp = await client.get(url)
            
            if resp.status_code == 200:
                content_type = resp.headers.get("content-type", "")
                
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
