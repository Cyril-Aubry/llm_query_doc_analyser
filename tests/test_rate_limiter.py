"""Tests for RateLimiter to ensure it works across different event loops."""

import asyncio
import time

import pytest

from llm_query_doc_analyser.utils.http import RateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_basic() -> None:
    """Test basic rate limiting functionality."""
    limiter = RateLimiter(calls_per_second=5.0)  # 5 calls per second = 0.2s interval
    
    start = time.time()
    
    # Make 3 calls
    await limiter.acquire()
    await limiter.acquire()
    await limiter.acquire()
    
    elapsed = time.time() - start
    
    # Should take at least 2 * 0.2s = 0.4s (for 3 calls, 2 intervals)
    assert elapsed >= 0.4, f"Rate limiting too fast: {elapsed}s"
    assert elapsed < 0.6, f"Rate limiting too slow: {elapsed}s"


@pytest.mark.asyncio
async def test_rate_limiter_multiple_event_loops() -> None:
    """
    Test that RateLimiter works across different event loops.
    This addresses the bug where Lock objects were bound to the wrong event loop.
    """
    # Create a global limiter (simulating module-level instantiation)
    limiter = RateLimiter(calls_per_second=10.0)
    
    # First event loop (within current test's event loop)
    async def task1() -> str:
        await limiter.acquire()
        return "task1"
    
    result1 = await task1()
    assert result1 == "task1"
    
    # Simulate using the same limiter in a new event loop context
    # (This would previously fail with "Lock bound to different event loop")
    async def task2() -> str:
        await limiter.acquire()
        return "task2"
    
    result2 = await task2()
    assert result2 == "task2"


def test_rate_limiter_across_asyncio_run_calls() -> None:
    """
    Test that RateLimiter works across multiple asyncio.run() calls.
    This simulates the real-world scenario of CLI running multiple enrichment passes.
    """
    # Create a global limiter (simulating module-level instantiation)
    limiter = RateLimiter(calls_per_second=10.0)
    
    # First asyncio.run() call (first enrichment pass)
    async def first_pass() -> str:
        await limiter.acquire()
        return "pass1"
    
    result1 = asyncio.run(first_pass())
    assert result1 == "pass1"
    assert limiter._lock is not None
    first_loop = limiter._loop
    
    # Second asyncio.run() call (second enrichment pass)
    # This creates a NEW event loop, which should trigger lock recreation
    async def second_pass() -> str:
        await limiter.acquire()
        return "pass2"
    
    result2 = asyncio.run(second_pass())
    assert result2 == "pass2"
    assert limiter._lock is not None
    second_loop = limiter._loop
    
    # The loops should be different (asyncio.run creates new loops)
    assert first_loop is not second_loop
    
    # Third pass to ensure it continues working
    async def third_pass() -> str:
        await limiter.acquire()
        return "pass3"
    
    result3 = asyncio.run(third_pass())
    assert result3 == "pass3"


@pytest.mark.asyncio
async def test_rate_limiter_concurrent_access() -> None:
    """Test that rate limiter works correctly with concurrent tasks."""
    limiter = RateLimiter(calls_per_second=10.0)  # 0.1s interval
    
    results: list[tuple[int, float]] = []
    
    async def make_request(task_id: int) -> None:
        await limiter.acquire()
        results.append((task_id, time.time()))
    
    start = time.time()
    
    # Launch 5 concurrent tasks
    tasks = [make_request(i) for i in range(5)]
    await asyncio.gather(*tasks)
    
    elapsed = time.time() - start
    
    # Should take at least 4 * 0.1s = 0.4s (for 5 calls, 4 intervals)
    assert elapsed >= 0.4, f"Concurrent rate limiting too fast: {elapsed}s"
    assert elapsed < 0.7, f"Concurrent rate limiting too slow: {elapsed}s"
    
    # All tasks should complete
    assert len(results) == 5


@pytest.mark.asyncio
async def test_rate_limiter_lazy_lock_initialization() -> None:
    """Test that lock is created lazily in the current event loop."""
    limiter = RateLimiter(calls_per_second=5.0)
    
    # Lock should not be created yet
    assert limiter._lock is None
    
    # First acquire should create the lock
    await limiter.acquire()
    assert limiter._lock is not None
    assert isinstance(limiter._lock, asyncio.Lock)
    
    # Subsequent acquires should reuse the same lock
    lock_ref = limiter._lock
    await limiter.acquire()
    assert limiter._lock is lock_ref
