# Automatic Second Enrichment Pass - Visual Flow Diagram

## High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        USER RUNS: enrich                                │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │ Get Unenriched Records │
                    │ (enrichment_datetime   │
                    │      IS NULL)          │
                    └────────────┬───────────┘
                                 │
                                 ▼
              ┌──────────────────────────────────┐
              │  ENRICHMENT PASS 1               │
              │  - Enrich all records            │
              │  - Detect preprints              │
              │  - Discover published versions   │
              │  - Count discoveries             │
              └──────────────┬───────────────────┘
                             │
                             ▼
                ┌─────────────────────────────┐
                │ New Published Versions > 0? │
                │ auto_enrich_published=True? │
                └─────────┬───────────────┬───┘
                          │               │
                      YES │               │ NO
                          │               │
                          ▼               ▼
┌─────────────────────────────────┐     ┌──────────────────┐
│  ENRICHMENT PASS 2              │     │  Single Pass     │
│  - Load new records             │     │  Complete        │
│  - Enrich published versions    │     │  - Show summary  │
│  - Mark as enriched             │     │  - Exit          │
└─────────────┬───────────────────┘     └──────────────────┘
              │
              ▼
    ┌─────────────────────┐
    │  Two-Pass Complete  │
    │  - Show summary     │
    │  - Report counts    │
    └─────────────────────┘
```

## Detailed Pass 1 Flow

```
PASS 1: INITIAL ENRICHMENT
│
├─ Record 1 (Regular Article)
│  ├─ Preprint Detection → NOT a preprint
│  ├─ Abstract Pipeline → Found in Crossref
│  ├─ OA Check → Open Access (gold)
│  └─ Mark enriched ✓
│
├─ Record 2 (Preprint - arXiv)
│  ├─ Preprint Detection → IS a preprint (arXiv)
│  │
│  ├─ Preprint Enrichment
│  │  ├─ Fetch arXiv metadata
│  │  ├─ Get abstract from arXiv
│  │  └─ Check for published version
│  │     │
│  │     └─ Published DOI found! → 10.1038/nature12345
│  │        │
│  │        ├─ Create new Record:
│  │        │  - doi_norm: 10.1038/nature12345
│  │        │  - is_preprint: False
│  │        │  - enrichment_datetime: NULL ← Key!
│  │        │  - INSERT into database
│  │        │
│  │        ├─ Link in article_versions table
│  │        │  - preprint_id: 2
│  │        │  - published_id: 101 (new)
│  │        │
│  │        └─ new_published_count++ (now = 1)
│  │
│  ├─ Abstract already set (from arXiv)
│  ├─ OA Check → Open Access (green)
│  └─ Mark enriched ✓
│
├─ Record 3 (Preprint - bioRxiv)
│  ├─ Preprint Detection → IS a preprint (bioRxiv)
│  │
│  ├─ Preprint Enrichment
│  │  ├─ Fetch bioRxiv metadata
│  │  └─ No published version found
│  │
│  ├─ Abstract from bioRxiv
│  ├─ OA Check → Open Access (bronze)
│  └─ Mark enriched ✓
│
└─ Pass 1 Complete
   ├─ Records enriched: 3
   ├─ new_published_count: 1
   └─ Trigger Pass 2? → YES (count > 0, auto=True)
```

## Detailed Pass 2 Flow

```
PASS 2: PUBLISHED VERSION ENRICHMENT
│
├─ Get Unenriched Records
│  └─ Query: enrichment_datetime IS NULL
│     └─ Returns: [Record 101] (the newly created published version)
│
├─ Record 101 (Published Version - Nature)
│  │
│  ├─ Preprint Detection → NOT a preprint
│  │  (is_preprint=False was set during creation)
│  │
│  ├─ Skip Preprint Enrichment
│  │  (not a preprint, so this block is skipped)
│  │
│  ├─ Abstract Pipeline
│  │  ├─ Try Semantic Scholar → Not found
│  │  ├─ Try Crossref → Found! ✓
│  │  │  - Set abstract_text
│  │  │  - Set abstract_source = "crossref"
│  │  ├─ Try OpenAlex → Also has abstract (provenance)
│  │  ├─ Try EuropePMC → Not found
│  │  └─ Try PubMed → Not found
│  │
│  ├─ OA Check (Unpaywall)
│  │  ├─ is_oa = True
│  │  ├─ oa_status = "gold"
│  │  ├─ license = "cc-by"
│  │  └─ oa_pdf_url = "https://..."
│  │
│  ├─ Provenance Collected
│  │  ├─ crossref: {...}
│  │  ├─ openalex: {...}
│  │  └─ unpaywall: {...}
│  │
│  └─ Mark enriched ✓
│     - enrichment_datetime = "2025-10-08T14:32:01Z"
│
└─ Pass 2 Complete
   ├─ Records enriched: 1
   ├─ new_published_count: 0 (no more discoveries)
   └─ Exit with success
```

## Database State Changes

```
BEFORE ENRICHMENT
─────────────────
research_articles:
┌────┬───────────────┬──────────────────┬─────────────┬────────────────────┐
│ id │ doi_norm      │ is_preprint      │ abstract    │ enrichment_datetime│
├────┼───────────────┼──────────────────┼─────────────┼────────────────────┤
│ 1  │ 10.1000/...   │ 0                │ NULL        │ NULL               │
│ 2  │ 2103.12345    │ 1 (arXiv)        │ NULL        │ NULL               │
│ 3  │ 2021.04.567   │ 1 (bioRxiv)      │ NULL        │ NULL               │
└────┴───────────────┴──────────────────┴─────────────┴────────────────────┘

article_versions:
(empty)


AFTER PASS 1
────────────
research_articles:
┌────┬───────────────┬──────────────────┬─────────────┬────────────────────┐
│ id │ doi_norm      │ is_preprint      │ abstract    │ enrichment_datetime│
├────┼───────────────┼──────────────────┼─────────────┼────────────────────┤
│ 1  │ 10.1000/...   │ 0                │ "..."       │ 2025-10-08T14:30:00│
│ 2  │ 2103.12345    │ 1 (arXiv)        │ "..."       │ 2025-10-08T14:30:01│
│ 3  │ 2021.04.567   │ 1 (bioRxiv)      │ "..."       │ 2025-10-08T14:30:02│
│101 │ 10.1038/...   │ 0                │ NULL        │ NULL               │← NEW!
└────┴───────────────┴──────────────────┴─────────────┴────────────────────┘

article_versions:
┌────┬──────────────┬──────────────┬──────────────────┐
│ id │ preprint_id  │ published_id │ discovery_source │
├────┼──────────────┼──────────────┼──────────────────┤
│ 1  │ 2            │ 101          │ arXiv            │← NEW!
└────┴──────────────┴──────────────┴──────────────────┘


AFTER PASS 2
────────────
research_articles:
┌────┬───────────────┬──────────────────┬─────────────┬────────────────────┐
│ id │ doi_norm      │ is_preprint      │ abstract    │ enrichment_datetime│
├────┼───────────────┼──────────────────┼─────────────┼────────────────────┤
│ 1  │ 10.1000/...   │ 0                │ "..."       │ 2025-10-08T14:30:00│
│ 2  │ 2103.12345    │ 1 (arXiv)        │ "..."       │ 2025-10-08T14:30:01│
│ 3  │ 2021.04.567   │ 1 (bioRxiv)      │ "..."       │ 2025-10-08T14:30:02│
│101 │ 10.1038/...   │ 0                │ "..."       │ 2025-10-08T14:32:00│← ENRICHED!
└────┴───────────────┴──────────────────┴─────────────┴────────────────────┘

article_versions:
(no change - relation already established)
```

## Routing Logic

```
                        ┌──────────────────┐
                        │   Record Entry   │
                        └────────┬─────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │  is_preprint field?    │
                    └──────┬────────┬────────┘
                           │        │
                    True   │        │   False
                           │        | 
                           |        └──────────────┬
                           |                       │  
                           |                       |  
                           ▼                       |
              ┌──────────────────────────────────┐ |
              │  PreprintEnricher                │ |
              │  - Fetch preprint metadata       │ |
              │  - Discover published version    │ |
              │  - Create new record if found    │ |
              └──────────────────────────────────┘ |
              │                                    |
              └──────────────┬                     |
                             │                     │
                             ▼                     ▼
              ┌──────────────────────────────────────────┐
              │  AbstractEnrichmentPipeline              │
              │  - Try multiple sources in order         │
              │  - S2 → Crossref → OpenAlex → EPMC → PM  │
              └──────────────────────────────────────────┘
                             │
                             ▼
              ┌──────────────────────────────────┐
              │  OpenAccessEnricher              │
              │  - Check Unpaywall for OA status │
              │  - Get PDF URL if available      │
              └──────────────────────────────────┘
                             │
                             ▼
                    ┌────────────────┐
                    │  Mark Enriched │
                    │  (set datetime)│
                    └────────────────┘
```

## Key Design Decisions

### ✅ Why Automatic Second Pass?

| Decision | Rationale |
|----------|-----------|
| Default ON | Most users want complete enrichment |
| Separate Pass | Cleaner separation, better logging |
| New Timestamp | Track when each record was enriched |
| Count Tracking | User visibility into discoveries |

### ✅ Why Not Immediate Enrichment?

| Option | Why Not Chosen |
|--------|----------------|
| Enrich in Pass 1 | Would require dynamic task queue, more complex |
| Queue for later | Adds complexity, requires message broker |
| Parallel passes | Race conditions, harder to debug |
| **Separate Pass 2** | ✓ Simple, clean, debuggable |

### ✅ Why Track Counts?

```python
new_published_count = 0
for rec in enriched:
    if rec.enrichment_report.get("preprint_detection", {}).get("published_version"):
        if pub_version.get("link_created"):
            new_published_count += 1
```

- User knows exactly how many discoveries were made
- Decides whether to trigger Pass 2
- Logged for analytics and monitoring
- Helps detect issues (e.g., if count is always 0)

## Edge Cases & Handling

### Case 1: No Published Versions Discovered
```
✓ ENRICHMENT COMPLETE
Successfully enriched 10 research articles.
```
→ Single pass only, clean exit

### Case 2: Published Version Already Exists
```
📄 Published version already exists (Record ID: 123)
```
→ Links to existing record, doesn't create duplicate
→ Existing record enriched if unenriched, otherwise skipped

### Case 3: Nested Discovery (Pass 2 finds more published versions)
```
Pass 2: 2 published version(s) enriched
        ⚠️ 1 additional published version(s) discovered
        Run 'enrich' again to process them.
```
→ User prompted to run another enrichment cycle
→ This is rare but possible (preprint of a preprint's published version)

### Case 4: Second Pass Has No Records
```
⚠️ No unenriched records found for second pass (this shouldn't happen)
```
→ Logged as warning
→ Indicates potential race condition or database issue

## Technical Details

### Record Creation Flow

1. **`PreprintEnricher.enrich()`** calls:
   ```python
   published_version_record_id, link_created, process_message = 
       process_preprint_to_published_linking(...)
   ```

2. **`process_preprint_to_published_linking()`** calls:
   ```python
   create_published_version_record(preprint_rec, published_doi, ...)
   ```

3. **New record created with**:
   - `is_preprint = False`
   - `enrichment_datetime = None` ← Key for second pass selection

4. **Second pass query**:
   ```python
   records = [rec for rec in get_records() if rec.enrichment_datetime is None]
   ```
   → Automatically includes newly created records

### Performance Considerations

- **API Calls**: Second pass makes new API calls (no duplicate work)
- **Database**: Two database update cycles (one per pass)
- **Memory**: Records from both passes held in memory briefly for reporting
- **Time**: Additional ~30-60 seconds per discovered published version

### Logging

Structured logs track:
- `enrich_started`: Initial parameters including `auto_enrich_published`
- `enrich_pass_completed`: Pass number, record count, new published versions count
- `starting_second_enrichment_pass`: Trigger for second pass with count
- `preprint_published_version_found`: Each discovery with DOIs and link status

## Migration from Previous Behavior

### Before
Users needed to:
1. Run `enrich` command
2. Check logs for discovered published versions
3. Manually run `enrich` again to process them

### After
Users simply:
1. Run `enrich` command
2. System automatically processes everything in one session

### Backward Compatibility
✅ No breaking changes
- Default behavior is the new auto-enrichment
- Can revert to old behavior with `--no-auto-enrich-published`
- All existing enrichment logic unchanged

## Testing Recommendations

### Unit Tests
```python
async def test_enrich_batch_tracks_new_published():
    """Test that enrich_batch counts newly discovered published versions."""
    # Setup preprint record that will discover published version
    # Run enrich_batch
    # Assert new_published_count > 0

async def test_second_pass_enriches_published_versions():
    """Test that second pass properly enriches newly created records."""
    # Create preprint with known published version
    # Run first pass (creates published version record)
    # Verify record exists with enrichment_datetime=None
    # Run second pass
    # Verify record enriched with enrichment_datetime set
```

### Integration Tests
```python
def test_full_two_pass_enrichment_workflow():
    """Test complete workflow from preprint discovery to published enrichment."""
    # Import preprint records
    # Run enrich command with auto_enrich_published=True
    # Verify both preprints and published versions are enriched
    # Check relation table for proper linking
```

## Future Enhancements

### Potential Improvements
1. **Max Passes Limit**: Add `--max-enrichment-passes` to handle cascading discoveries
2. **Selective Enrichment**: `--enrich-only-published` to skip preprints
3. **Parallel Passes**: Run Pass 2 in parallel with Pass 1 (complex, needs queue)
4. **Smart Batching**: Batch second pass records with first pass for efficiency
5. **Progress Bar**: Add `tqdm` progress indicators for large batches

### Configuration Options
Could add to `.env`:
```bash
AUTO_ENRICH_PUBLISHED=true
MAX_ENRICHMENT_PASSES=3
ENRICH_BATCH_SIZE=50
```

## Troubleshooting

### Issue: Second pass doesn't find records
**Symptom**: "⚠️ No unenriched records found for second pass"

**Causes**:
- Database not flushed between passes
- Records created but not committed
- Race condition with enrichment_datetime setting

**Solution**: Check `insert_record()` and ensure proper transaction handling

### Issue: Infinite enrichment loop
**Symptom**: Pass 2 keeps discovering more published versions

**Causes**:
- Preprint provider returning preprints of published versions
- Circular references in preprint ↔ published relationships

**Solution**: Add cycle detection or max passes limit

### Issue: Duplicate published version records
**Symptom**: Multiple records with same DOI after enrichment

**Causes**:
- Race condition in `find_record_by_doi()`
- Multiple preprints pointing to same published version

**Solution**: Database-level unique constraint on `doi_norm`

---

**Last Updated**: October 8, 2025
**Author**: Cyril Aubry
**Version**: 1.0.0
