"""Download full-text HTML pages using npx single-file-cli."""

import asyncio
import contextlib
import platform
from pathlib import Path
from typing import Any

from ..utils.files import make_safe_filename
from ..utils.log import get_logger

log = get_logger(__name__)


def _is_arxiv_html_not_available_page(html_path: Path) -> bool:
    """
    Check if arXiv page indicates HTML version is not available.
    
    arXiv returns a specific error page when HTML conversion failed or
    source files are not in a compatible format.
    
    Args:
        html_path: Path to HTML file to check
        
    Returns:
        True if page indicates HTML is not available for this article
    """
    try:
        # single-file-cli inlines base64 data which makes files large
        # For efficiency, read in chunks and search, or read the whole file if small
        file_size = html_path.stat().st_size
        
        # If file is small (<= 1MB), read entire file
        # Otherwise read first and last 100KB (error message is typically at the end)
        if file_size <= 1_000_000:
            content = html_path.read_text(encoding='utf-8', errors='ignore')
        else:
            # Read first 100KB and last 100KB
            with html_path.open('r', encoding='utf-8', errors='ignore') as f:
                first_chunk = f.read(100_000)
                # Seek to 100KB from end
                f.seek(max(0, file_size - 100_000))
                last_chunk = f.read()
                content = first_chunk + last_chunk
        
        content_lower = content.lower()
        
        # Check for arXiv HTML unavailability indicators
        indicators = [
            "html is not available for the source",
            "no html for",
            "this could be due to the source files not being html, latex, or a conversion failure",
        ]
        
        found = any(ind in content_lower for ind in indicators)
        
        if found:
            log.info(
                "arxiv_html_not_available_detected",
                path=str(html_path),
            )
            return True
        
        return False
        
    except Exception as e:
        log.error("arxiv_html_check_failed", path=str(html_path), error=str(e))
        return False


def _is_bot_detection_page(html_path: Path) -> bool:
    """
    Check if downloaded HTML is a bot detection/challenge page.
    
    Looks for common indicators:
    - Cloudflare challenge pages
    - "Verifying you are human" text
    - "Just a moment..." titles
    - Challenge redirect scripts
    
    Args:
        html_path: Path to HTML file to check
        
    Returns:
        True if file appears to be a bot detection page
    """
    try:
        # Read first 50KB to check for bot detection indicators
        # (challenge pages are typically small)
        content = html_path.read_text(encoding='utf-8', errors='ignore')[:50000]
        content_lower = content.lower()
        
        # Common bot detection indicators
        indicators = [
            "just a moment",
            "verifying you are human",
            "checking your browser",
            "please wait while we check your browser",
            "cloudflare",
            "ray id:",  # Cloudflare Ray ID
            "cf-ray",
            "challenge-platform",
            "cf-browser-verification",
            "__cf_chl_",  # Cloudflare challenge tokens
            "enable javascript and cookies to continue",
        ]
        
        # Check for indicators
        found_indicators = [ind for ind in indicators if ind in content_lower]
        
        if found_indicators:
            log.warning(
                "bot_detection_page_detected",
                path=str(html_path),
                indicators=found_indicators[:3],  # Log first 3 matches
            )
            return True
        
        # Additional check: very small HTML files are often challenge pages
        # Check if it has minimal actual content
        if len(content) < 5000 and "<body" in content_lower and "</body>" in content_lower:
            body_start = content_lower.find("<body")
            body_end = content_lower.find("</body>")
            if body_end > body_start:
                body_content = content[body_start:body_end]
                # If body has very little text content, likely a challenge page
                text_content = len([c for c in body_content if c.isalnum()])
                if text_content < 500:
                    log.warning(
                        "minimal_content_detected",
                        path=str(html_path),
                        text_chars=text_content,
                    )
                    return True
        
        return False
        
    except Exception as e:
        log.error("bot_detection_check_failed", path=str(html_path), error=str(e))
        return False  # If we can't check, assume it's OK


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
    
    # Build the npx single-file-cli command with browser-like headers
    # Note: single-file-cli embeds images and other assets as base64 by default
    # Add browser emulation headers to avoid bot detection (especially for bioRxiv/medRxiv)
    
    # Comprehensive browser-like user agent and headers
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    
    cmd = [
        "npx",
        "--yes",  # Auto-install if not present
        "single-file-cli",
        url,
        str(target_path),
        "--browser-headless=true",  # Use headless browser mode
        "--browser-wait-until=networkidle",  # Wait for network to be idle
        f"--user-agent={user_agent}",
    ]
    
    # Add source-specific optimizations
    if source == "biorxiv" or source == "medrxiv":
        # bioRxiv and medRxiv use aggressive bot detection
        # Wait longer for JS-rendered content and use more realistic timing
        cmd.extend([
            "--browser-wait-delay=5000",  # 5 seconds for bioRxiv/medRxiv
            "--max-resource-size=50",  # Limit resource size to 50MB
        ])
    elif source == "arxiv":
        # arXiv is generally less aggressive but still benefits from delays
        cmd.extend([
            "--browser-wait-delay=2000",  # 2 seconds for arXiv
        ])
    else:
        # Default wait delay for other sources
        cmd.extend([
            "--browser-wait-delay=3000",  # 3 seconds default
        ])
    
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
            # Properly escape arguments: quote if contains spaces
            def escape_arg(arg: str) -> str:
                # If already starts and ends with quote, leave as-is
                if arg.startswith('"') and arg.endswith('"'):
                    return arg
                # If contains space, quote it (including key=value parameters)
                elif " " in arg:
                    return f'"{arg}"'
                # Otherwise use as-is
                else:
                    return arg
            
            cmd_str = " ".join(escape_arg(arg) for arg in cmd)
            log.debug(
                "html_download_command",
                url=url,
                command=cmd_str[:500],  # Log first 500 chars of command
            )
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
        
        # Adjust timeout based on source - bioRxiv/medRxiv need more time for bot detection avoidance
        timeout = 300.0 if source in ("biorxiv", "medrxiv") else 180.0  # 5 min for bioRxiv/medRxiv, 3 min others
        
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
        except TimeoutError:
            log.error("html_download_timeout", url=url, source=source, timeout=timeout)
            process.kill()
            await process.wait()
            return {
                "status": "timeout",
                "url": url,
                "error": f"Download timeout after {timeout} seconds",
            }
        
        return_code = process.returncode
        
        if return_code == 0:
            # Check if file was created and has content
            if not target_path.exists():
                # Decode output to see what happened
                stdout_text = stdout.decode('utf-8', errors='ignore')[:1000] if stdout else ""
                stderr_text = stderr.decode('utf-8', errors='ignore')[:1000] if stderr else ""
                log.error(
                    "html_download_file_not_created",
                    url=url,
                    source=source,
                    title=title,
                    stdout=stdout_text,
                    stderr=stderr_text,
                )
                return {
                    "status": "error",
                    "url": url,
                    "error": f"File was not created by single-file-cli. stderr: {stderr_text[:200]}",
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
            
            # Check if downloaded file is a bot detection/challenge page
            if _is_bot_detection_page(target_path):
                log.error(
                    "bot_detection_page_downloaded",
                    url=url,
                    source=source,
                    title=title,
                    path=str(target_path),
                )
                target_path.unlink()  # Delete challenge page
                return {
                    "status": "error",
                    "url": url,
                    "error": "Downloaded page is a bot detection/verification page (Cloudflare challenge). The site blocked automated access.",
                }
            
            # Check if arXiv page indicates HTML is not available
            if source == "arxiv" and _is_arxiv_html_not_available_page(target_path):
                log.warning(
                    "arxiv_html_not_available",
                    url=url,
                    title=title,
                    path=str(target_path),
                )
                target_path.unlink()  # Delete the error page
                return {
                    "status": "not_available",
                    "url": url,
                    "error": "HTML version is not available for this arXiv article. This may be due to source files not being in a compatible format (HTML/LaTeX) or a conversion failure.",
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
