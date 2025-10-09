# Event Loop Lock Recreation - Visual Explanation

## The Problem (Before Fix)

```
Module Import Time:
┌─────────────────────────────────────┐
│  RATE_LIMITERS = {                  │
│    "crossref": RateLimiter(1.0),    │  ← Created at import
│    "openalex": RateLimiter(5.0),    │     (no event loop yet)
│    ...                               │
│  }                                   │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│  RateLimiter instances created      │
│  _lock = None                        │
│  _loop = None                        │
└─────────────────────────────────────┘

First Enrichment Pass (asyncio.run() #1):
┌─────────────────────────────────────┐
│  Event Loop A created               │
├─────────────────────────────────────┤
│  ╔═══════════════════════════════╗  │
│  ║ enrich_batch(records)         ║  │
│  ║   ↓                            ║  │
│  ║ enrich_record()               ║  │
│  ║   ↓                            ║  │
│  ║ fetch_crossref()              ║  │
│  ║   ↓                            ║  │
│  ║ rate_limiter.acquire()        ║  │
│  ║   ↓                            ║  │
│  ║ _ensure_lock()                ║  │
│  ║   if _lock is None:            ║  │
│  ║     _lock = asyncio.Lock()    ║  │ ← Lock created in Loop A
│  ║                                ║  │
│  ╚═══════════════════════════════╝  │
└─────────────────────────────────────┘

Second Enrichment Pass (asyncio.run() #2):
┌─────────────────────────────────────┐
│  Event Loop B created               │  ← NEW LOOP!
├─────────────────────────────────────┤
│  ╔═══════════════════════════════╗  │
│  ║ enrich_batch(published_recs)  ║  │
│  ║   ↓                            ║  │
│  ║ enrich_record()               ║  │
│  ║   ↓                            ║  │
│  ║ fetch_crossref()              ║  │
│  ║   ↓                            ║  │
│  ║ rate_limiter.acquire()        ║  │
│  ║   ↓                            ║  │
│  ║ _ensure_lock()                ║  │
│  ║   if _lock is None:            ║  │  ← False! Lock exists
│  ║     ...                        ║  │
│  ║   return self._lock           ║  │  ← Returns lock from Loop A
│  ║   ↓                            ║  │
│  ║ async with lock: ❌ ERROR!    ║  │
│  ║   "Lock bound to different     ║  │
│  ║    event loop"                 ║  │
│  ╚═══════════════════════════════╝  │
└─────────────────────────────────────┘
```

## The Solution (After Fix)

```
Module Import Time:
┌─────────────────────────────────────┐
│  RATE_LIMITERS = {                  │
│    "crossref": RateLimiter(1.0),    │
│    "openalex": RateLimiter(5.0),    │
│    ...                               │
│  }                                   │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│  RateLimiter instances created      │
│  _lock = None                        │
│  _loop = None                        │  ← Track loop ownership
└─────────────────────────────────────┘

First Enrichment Pass (asyncio.run() #1):
┌─────────────────────────────────────┐
│  Event Loop A created               │
├─────────────────────────────────────┤
│  ╔═══════════════════════════════╗  │
│  ║ rate_limiter.acquire()        ║  │
│  ║   ↓                            ║  │
│  ║ _ensure_lock()                ║  │
│  ║   current_loop = get_running_ ║  │  ← Loop A
│  ║                  loop()        ║  │
│  ║   if _lock is None or          ║  │
│  ║      _loop is not current_loop:║  │  ← True (first time)
│  ║     _lock = asyncio.Lock()    ║  │  ← Lock created in Loop A
│  ║     _loop = current_loop      ║  │  ← Store Loop A reference
│  ║   return _lock ✅              ║  │
│  ║                                ║  │
│  ╚═══════════════════════════════╝  │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│  RateLimiter state:                 │
│  _lock = <Lock in Loop A>           │
│  _loop = <Loop A reference>         │
└─────────────────────────────────────┘

Second Enrichment Pass (asyncio.run() #2):
┌─────────────────────────────────────┐
│  Event Loop B created               │  ← NEW LOOP!
├─────────────────────────────────────┤
│  ╔═══════════════════════════════╗  │
│  ║ rate_limiter.acquire()        ║  │
│  ║   ↓                            ║  │
│  ║ _ensure_lock()                ║  │
│  ║   current_loop = get_running_ ║  │  ← Loop B
│  ║                  loop()        ║  │
│  ║   if _lock is None or          ║  │
│  ║      _loop is not current_loop:║  │  ← True! Loop B ≠ Loop A
│  ║     _lock = asyncio.Lock()    ║  │  ← NEW lock in Loop B ✅
│  ║     _loop = current_loop      ║  │  ← Store Loop B reference
│  ║   return _lock ✅              ║  │
│  ║   ↓                            ║  │
│  ║ async with lock: ✅ SUCCESS!  ║  │
│  ║                                ║  │
│  ╚═══════════════════════════════╝  │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│  RateLimiter state:                 │
│  _lock = <Lock in Loop B>           │  ← Updated!
│  _loop = <Loop B reference>         │  ← Updated!
└─────────────────────────────────────┘

Third+ Enrichment Passes:
  Same process - lock recreated for each new event loop
  ✅ No errors, works seamlessly!
```

## Key Insight

**The fix leverages event loop identity:**
- Each `asyncio.run()` creates a unique event loop object
- We compare loop references using Python's `is` operator (identity check)
- When loops differ, we know we need a new lock
- The lock is recreated in the current loop, so it works correctly

## Real-World CLI Flow

```
$ llm-query-doc-analyser enrich

Step 1: Import modules
  └─> RATE_LIMITERS created (locks = None, loops = None)

Step 2: First asyncio.run() call
  └─> Event Loop A created
      └─> Enrich 10 records
          └─> Each API call: acquire() → lock created in Loop A
      └─> 3 published versions discovered

Step 3: Second asyncio.run() call
  └─> Event Loop B created (Loop A is destroyed)
      └─> Enrich 3 published version records
          └─> Each API call: acquire() → lock RECREATED in Loop B ✅
      └─> All successful!

✓ Enrichment complete - 2 passes
```

## Why This Pattern?

Using multiple `asyncio.run()` calls is a **common pattern** in CLI applications:
- Each command execution is independent
- Clean slate for each operation
- Simpler error handling and resource cleanup
- No need to maintain a long-running event loop

The fix ensures `RateLimiter` (and any similar async primitives) work correctly in this pattern.
