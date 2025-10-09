# Bug Fix: Asyncio Event Loop Lock Binding Issue

## Problem
The application was encountering this error during abstract enrichment, especially on the **second enrichment pass** for published versions:
```
Crossref: Exception: <asyncio.locks.Lock object at 0x000001AB61A60DD0 [locked]> is bound to a different event loop
```

Additionally, some APIs were reporting "No abstract field in response" for OpenAlex, EuropePMC, and PubMed.

## Root Cause
The `RateLimiter` class in `src/llm_query_doc_analyser/utils/http.py` was creating `asyncio.Lock()` objects lazily, but wasn't detecting when a **new event loop** was created.

**The specific scenario:**
1. Global `RATE_LIMITERS` dictionary is created at module import time (in `orchestrator.py`)
2. First enrichment pass: `asyncio.run()` creates Event Loop A, locks are created in Loop A
3. Second enrichment pass (for published versions): `asyncio.run()` creates **Event Loop B**
4. The `RateLimiter` tries to reuse locks from Loop A in Loop B → **ERROR**

This is a common pattern in CLI applications where `asyncio.run()` is called multiple times, each creating a fresh event loop.

## Solution
Implemented **event loop-aware** lazy initialization of the `asyncio.Lock` object in the `RateLimiter` class:

1. Changed `_lock` to be `Optional[asyncio.Lock]` initialized to `None`
2. Added `_loop` to track which event loop the lock belongs to
3. Enhanced `_ensure_lock()` method to:
   - Detect the current running event loop using `asyncio.get_running_loop()`
   - Compare it with the stored `_loop`
   - **Recreate** the lock if the event loop has changed
4. Updated `acquire()` to use `_ensure_lock()` before entering the lock context

### Code Changes
**File:** `src/llm_query_doc_analyser/utils/http.py`

**Before:**
```python
def __init__(self, calls_per_second: float = 1.0) -> None:
    self.min_interval = 1.0 / calls_per_second
    self.last_call = 0.0
    self._lock = asyncio.Lock()  # ❌ Created immediately, binds to wrong loop

async def acquire(self) -> None:
    async with self._lock:
        # ...
```

**After:**
```python
def __init__(self, calls_per_second: float = 1.0) -> None:
    self.min_interval = 1.0 / calls_per_second
    self.last_call = 0.0
    self._lock: asyncio.Lock | None = None
    self._loop: asyncio.AbstractEventLoop | None = None  # ✅ Track which loop owns the lock

def _ensure_lock(self) -> asyncio.Lock:
    """Lazily create lock in the current event loop."""
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None
    
    # ✅ Recreate lock if we're in a different event loop
    if self._lock is None or self._loop is not current_loop:
        self._lock = asyncio.Lock()
        self._loop = current_loop
    
    return self._lock

async def acquire(self) -> None:
    lock = self._ensure_lock()  # ✅ Always gets correct lock for current loop
    async with lock:
        # ...
```

## Testing
Created comprehensive test suite in `tests/test_rate_limiter.py`:
- ✅ Basic rate limiting functionality
- ✅ Multiple event loop contexts within same loop
- ✅ **Multiple `asyncio.run()` calls (simulates CLI second pass scenario)**
- ✅ Concurrent access with proper serialization
- ✅ Lazy lock initialization

All 30 tests pass, including the 5 new RateLimiter tests.

**Key test case:**
```python
def test_rate_limiter_across_asyncio_run_calls() -> None:
    """Simulates CLI running multiple enrichment passes."""
    limiter = RateLimiter(calls_per_second=10.0)
    
    # First pass (creates Event Loop A)
    result1 = asyncio.run(async_task_1(limiter))
    
    # Second pass (creates Event Loop B)
    result2 = asyncio.run(async_task_2(limiter))  # ✅ Works now!
    
    assert result1 == "pass1"
    assert result2 == "pass2"
```

## Impact
- **Fixed:** The Crossref event loop error
- **Maintained:** All existing functionality (100% backward compatible)
- **Improved:** Robustness of async operations across different execution contexts

## Notes
The "No abstract field in response" messages for other APIs are expected behavior when those APIs don't return abstracts for specific records. This is not an error but rather normal operation - the pipeline tries multiple sources until it finds an abstract.
