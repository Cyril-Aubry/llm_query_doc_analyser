import asyncio
import logging

import httpx
import structlog
from tenacity import (
    after_log,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

log = structlog.get_logger()
# Get standard logger for tenacity callbacks
std_log = logging.getLogger(__name__)


def should_retry_on_status(exception: BaseException) -> bool:
    """Determine if we should retry based on exception type or status code."""
    if isinstance(exception, httpx.HTTPStatusError):
        # Retry on 429 (rate limit), 5xx (server errors), and 408 (timeout)
        return exception.response.status_code in (408, 429, 500, 502, 503, 504)
    return isinstance(exception, (httpx.TimeoutException, httpx.ConnectError, httpx.ReadTimeout))


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception_type(
        (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError, httpx.ReadTimeout)
    ),
    before_sleep=before_sleep_log(std_log, logging.WARNING),
    after=after_log(std_log, logging.INFO),
    reraise=True,
)
async def get_with_retry(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    client: httpx.AsyncClient | None = None,
) -> httpx.Response:
    """
    Make an HTTP GET request with automatic retry logic.
    
    Args:
        url: The URL to request
        headers: Optional headers dict
        timeout: Request timeout in seconds (default: 30)
        client: Optional existing client to use (useful for connection pooling)
    
    Returns:
        httpx.Response object
        
    Raises:
        httpx.HTTPStatusError: For non-retryable HTTP errors
        httpx.TimeoutException: After all retries exhausted
    """
    should_close = False
    if client is None:
        client = httpx.AsyncClient(http2=True, timeout=timeout)
        should_close = True
    
    try:
        resp = await client.get(url, headers=headers)
        
        log.info(
            "http_request_success",
            url=url,
            status=resp.status_code,
            content_length=len(resp.content) if resp.content else 0,
        )
        
        # Raise for status to trigger retry on error codes
        resp.raise_for_status()
        
        return resp
    except httpx.HTTPStatusError as e:
        log.error(
            "http_status_error",
            url=url,
            status=e.response.status_code,
            error=str(e),
            response_text=e.response.text[:500] if e.response.text else None,
        )
        if should_retry_on_status(e):
            raise
        # Don't retry on 4xx errors (except 408, 429)
        return e.response
    except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadTimeout) as e:
        log.error("http_network_error", url=url, error=str(e), error_type=type(e).__name__)
        raise
    finally:
        if should_close and client:
            await client.aclose()


def get_client(email: str | None = None, timeout: float = 30.0) -> httpx.AsyncClient:
    """
    Create an httpx AsyncClient with sensible defaults.
    
    Args:
        email: Optional email for polite user agent
        timeout: Request timeout in seconds (default: 30)
        
    Returns:
        Configured httpx.AsyncClient
    """
    headers = {
        "User-Agent": (
            f"llm_query_doc_analyser/1.0 (mailto:{email})"
            if email
            else "llm_query_doc_analyser/1.0"
        )
    }
    
    # Use connection limits to avoid overwhelming APIs
    limits = httpx.Limits(
        max_keepalive_connections=10,
        max_connections=20,
        keepalive_expiry=30.0,
    )
    
    return httpx.AsyncClient(
        http2=True,
        headers=headers,
        timeout=timeout,
        limits=limits,
        follow_redirects=True,
    )


class RateLimiter:
    """Simple rate limiter using token bucket algorithm."""
    
    def __init__(self, calls_per_second: float = 1.0) -> None:
        """
        Initialize rate limiter.
        
        Args:
            calls_per_second: Maximum number of calls allowed per second
        """
        self.min_interval = 1.0 / calls_per_second
        self.last_call = 0.0
        self._lock: asyncio.Lock | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
    
    def _ensure_lock(self) -> asyncio.Lock:
        """
        Lazily create lock in the current event loop.
        
        If the lock was created in a different event loop (e.g., across multiple
        asyncio.run() calls), recreate it for the current loop.
        """
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            # No event loop running
            current_loop = None
        
        # Recreate lock if:
        # 1. Lock doesn't exist yet, OR
        # 2. Lock was created for a different event loop
        if self._lock is None or self._loop is not current_loop:
            self._lock = asyncio.Lock()
            self._loop = current_loop
            if current_loop is not None:
                log.debug(
                    "rate_limiter_lock_created",
                    loop_id=id(current_loop),
                    recreated=self._loop is not None,
                )
        
        return self._lock
    
    async def acquire(self) -> None:
        """Wait until rate limit allows next call."""
        lock = self._ensure_lock()
        async with lock:
            now = asyncio.get_event_loop().time()
            time_since_last = now - self.last_call
            
            if time_since_last < self.min_interval:
                wait_time = self.min_interval - time_since_last
                log.debug("rate_limit_wait", wait_time=wait_time)
                await asyncio.sleep(wait_time)
            
            self.last_call = asyncio.get_event_loop().time()
