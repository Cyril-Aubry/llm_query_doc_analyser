"""Download full-text HTML pages using npx single-file-cli."""

import asyncio
import contextlib
import platform
from pathlib import Path
from typing import Any

from ..utils.files import make_safe_filename
from ..utils.log import get_logger

log = get_logger(__name__)


async def download_html_page(
    url: str, 
    dest_dir: Path, 
    title: str, 
    source: str | None = None
) -> dict[str, Any]:
    """
    Download full-text HTML page using npx single-file-cli.
    
    This function uses npx to call single-file-cli, which downloads a web page
    as a single HTML file with all assets (images, CSS, etc.) embedded as base64.
    Files are named using the research paper title (same as PDF downloads).
    
    Args:
        url: URL of the HTML page to download
        dest_dir: Destination directory for the HTML file
        title: Research paper title to use for filename
        source: Preprint source (arxiv, biorxiv, medrxiv, preprints) for logging
        
    Returns:
        Dictionary with:
            - status: 'downloaded', 'error', 'timeout'
            - path: Local file path (if downloaded)
            - file_size_bytes: File size in bytes (if downloaded)
            - error: Error message (if error)
            - url: Original URL
    """
    if not url:
        log.warning("html_download_no_url")
        return {"status": "error", "error": "No URL provided", "url": url}
    
    # Ensure destination directory exists
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate safe filename from title
    safe_filename = make_safe_filename(title, extension="html", max_length=120)
    target_path = dest_dir / safe_filename
    
    # Handle filename collisions by appending counter
    if target_path.exists():
        stem = target_path.stem
        suffix = target_path.suffix
        counter = 1
        while True:
            candidate = dest_dir / f"{stem}-{counter}{suffix}"
            if not candidate.exists():
                target_path = candidate
                break
            counter += 1
    
    # Build the npx single-file-cli command
    # Note: single-file-cli embeds images and other assets as base64 by default
    cmd = [
        "npx",
        "--yes",  # Auto-install if not present
        "single-file-cli",
        url,
        str(target_path),
    ]
    
    log.debug(
        "html_download_starting",
        url=url,
        source=source,
        title=title,
        target_path=str(target_path),
    )
    
    try:
        # Run subprocess with timeout
        # single-file-cli can take time for complex pages, use generous timeout
        # On Windows, we need shell=True for npx to be found in PATH
        is_windows = platform.system() == "Windows"
        
        if is_windows:
            # On Windows, join command as string and use shell
            cmd_str = " ".join(f'"{arg}"' if " " in arg else arg for arg in cmd)
            process = await asyncio.create_subprocess_shell(
                cmd_str,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        else:
            # On Unix-like systems, use exec
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=180.0,  # 3 minutes timeout
            )
        except TimeoutError:
            log.error("html_download_timeout", url=url, source=source)
            process.kill()
            await process.wait()
            return {
                "status": "timeout",
                "url": url,
                "error": "Download timeout after 180 seconds",
            }
        
        return_code = process.returncode
        
        if return_code == 0:
            # Check if file was created and has content
            if not target_path.exists():
                log.error("html_download_file_not_created", url=url, source=source, title=title)
                return {
                    "status": "error",
                    "url": url,
                    "error": "File was not created by single-file-cli",
                }
            
            # Get file size
            file_size_bytes = target_path.stat().st_size
            
            if file_size_bytes == 0:
                log.error("html_download_empty_file", url=url, source=source, title=title)
                target_path.unlink()  # Delete empty file
                return {
                    "status": "error",
                    "url": url,
                    "error": "Downloaded file is empty",
                }
            
            log.info(
                "html_downloaded",
                url=url,
                source=source,
                title=title,
                size=file_size_bytes,
                path=str(target_path),
            )
            
            return {
                "status": "downloaded",
                "path": str(target_path),
                "file_size_bytes": file_size_bytes,
                "url": url,
            }
        
        else:
            # Command failed
            stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""
            stdout_text = stdout.decode("utf-8", errors="replace") if stdout else ""
            error_msg = f"single-file-cli failed (exit code {return_code})"
            
            if stderr_text:
                error_msg += f": {stderr_text[:500]}"  # Limit error message length
            
            log.error(
                "html_download_failed",
                url=url,
                source=source,
                title=title,
                return_code=return_code,
                stderr=stderr_text[:200],
                stdout=stdout_text[:200],
            )
            
            # Clean up target file if it exists (partial download)
            if target_path.exists():
                target_path.unlink()
            
            return {
                "status": "error",
                "url": url,
                "error": error_msg,
            }
    
    except FileNotFoundError:
        log.error(
            "npx_not_found",
            url=url,
            source=source,
            title=title,
        )
        return {
            "status": "error",
            "url": url,
            "error": "npx command not found. Please ensure Node.js and npm are installed.",
        }
    
    except Exception as e:
        log.exception("html_download_unexpected_error", url=url, source=source, title=title)
        
        # Clean up target file if it exists (partial download)
        if target_path.exists():
            with contextlib.suppress(Exception):
                target_path.unlink()
        
        return {
            "status": "error",
            "url": url,
            "error": f"Unexpected error: {e!s}",
        }
