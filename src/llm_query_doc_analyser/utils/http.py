from typing import Any

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

log = structlog.get_logger()

@retry(stop=stop_after_attempt(5), wait=wait_exponential_jitter(1, 10))
async def get_with_retry(url: str, headers: dict[str, str] | None = None) -> Any:
    async with httpx.AsyncClient(http2=True, timeout=30) as client:
        resp = await client.get(url, headers=headers)
        log.info("http_request", url=url, status=resp.status_code)
        return resp

def get_client(email: str | None = None) -> httpx.AsyncClient:
    headers = {"User-Agent": f"llm_query_doc_analyser/1.0 (mailto:{email})" if email else "llm_query_doc_analyser/1.0"}
    return httpx.AsyncClient(http2=True, headers=headers, timeout=30)
