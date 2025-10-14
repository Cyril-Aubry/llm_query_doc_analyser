# Markdown Versions Schema Design

**Date:** 2025-10-13  
**Status:** Implemented  
**Decision:** Option 1 - Single table with CHECK constraint

## Problem Statement

The `markdown_versions` table needs to track markdown files converted from multiple source types (DOCX, HTML, potentially XML/PDF in the future). Each markdown record is derived from exactly one source, creating a design challenge for foreign key relationships.

## Schema Requirements

1. Each markdown version must reference exactly one source (DOCX or HTML)
2. Must link back to the original research article
3. Must track conversion metadata (timestamps, file sizes, errors)
4. Should support multiple conversion variants (with/without images)
5. Should be extensible for future source types (XML, PDF, etc.)

## Design Options Considered

### Option 1: Single Table with CHECK Constraint ✅ **SELECTED**

```sql
CREATE TABLE markdown_versions (
    id INTEGER PRIMARY KEY,
    record_id INTEGER NOT NULL,
    docx_version_id INTEGER,              -- NULL if source_type='html'
    html_version_id INTEGER,              -- NULL if source_type='docx'
    source_type TEXT NOT NULL,            -- 'docx' or 'html'
    created_datetime TEXT NOT NULL,
    variant TEXT NOT NULL,                -- 'no_images' or 'with_images'
    md_local_path TEXT,
    file_size_bytes INTEGER,
    error_message TEXT,
    FOREIGN KEY (record_id) REFERENCES research_articles(id),
    FOREIGN KEY (docx_version_id) REFERENCES docx_versions(id),
    FOREIGN KEY (html_version_id) REFERENCES html_downloads(id),
    CHECK (
        (source_type = 'docx' AND docx_version_id IS NOT NULL AND html_version_id IS NULL) OR
        (source_type = 'html' AND html_version_id IS NOT NULL AND docx_version_id IS NULL)
    )
);
```

**Pros:**
- ✅ Database-enforced integrity via CHECK constraint
- ✅ Single table - simple queries, no UNIONs needed
- ✅ Easy to extend for new source types
- ✅ Clear and explicit with `source_type`
- ✅ Minimal code changes from initial implementation
- ✅ Good performance for queries and joins

**Cons:**
- ⚠️ Contains NULL columns (acceptable trade-off)
- ⚠️ Slight redundancy between `source_type` and which FK is set

**Why Selected:**
- Best balance of simplicity, integrity, and extensibility
- CHECK constraint prevents invalid states at database level
- Straightforward to query: `WHERE source_type = 'html'`
- Easy migration path from current schema
- Standard pattern in many production databases

### Option 2: Separate Tables (Normalized)

```sql
CREATE TABLE docx_markdown_versions (
    id INTEGER PRIMARY KEY,
    record_id INTEGER NOT NULL,
    docx_version_id INTEGER NOT NULL,    -- No NULLs
    -- ... other fields
);

CREATE TABLE html_markdown_versions (
    id INTEGER PRIMARY KEY,
    record_id INTEGER NOT NULL,
    html_version_id INTEGER NOT NULL,    -- No NULLs
    -- ... other fields
);
```

**Pros:**
- ✅ Perfect normalization - no NULL columns
- ✅ Impossible to have invalid FK combinations
- ✅ Type-safe at schema level

**Cons:**
- ❌ Need UNION for "all markdown versions" queries
- ❌ More code duplication (insert/update logic per table)
- ❌ Views required for unified access
- ❌ More complex joins in queries
- ❌ Harder to add fields common to all sources

**Why Rejected:**
- Significant code complexity increase
- Poor developer experience (must remember which table)
- Query performance may suffer from UNIONs
- Overkill for current requirements

### Option 3: Polymorphic Association (Generic FK)

```sql
CREATE TABLE markdown_versions (
    id INTEGER PRIMARY KEY,
    record_id INTEGER NOT NULL,
    source_type TEXT NOT NULL,           -- 'docx', 'html', 'xml', etc.
    source_id INTEGER NOT NULL,          -- Generic ID
    -- ... other fields
    -- NO foreign key constraint on source_id
);
```

**Pros:**
- ✅ Highly flexible - easy to add source types
- ✅ No NULL columns
- ✅ Minimal schema changes for new sources

**Cons:**
- ❌ **No referential integrity** - database can't enforce valid IDs
- ❌ Application must ensure data consistency
- ❌ Can't use cascade deletes effectively
- ❌ Joins require application logic to determine correct table
- ❌ Anti-pattern in relational databases
- ❌ Risk of orphaned records

**Why Rejected:**
- Loss of referential integrity is a serious issue
- Goes against relational database best practices
- Harder to debug data issues
- SQLite foreign keys would be wasted

## Implementation Details

### CHECK Constraint Enforcement

The CHECK constraint ensures:
```sql
(source_type = 'docx' AND docx_version_id IS NOT NULL AND html_version_id IS NULL) OR
(source_type = 'html' AND html_version_id IS NOT NULL AND docx_version_id IS NULL)
```

This means:
- If `source_type='docx'`: MUST have `docx_version_id`, MUST NOT have `html_version_id`
- If `source_type='html'`: MUST have `html_version_id`, MUST NOT have `docx_version_id`

Any INSERT or UPDATE that violates this will fail with a constraint error.

### Query Patterns

**Find all markdown from HTML sources:**
```sql
SELECT mv.* FROM markdown_versions mv
WHERE mv.source_type = 'html'
```

**Find all markdown for a record (all sources):**
```sql
SELECT mv.* FROM markdown_versions mv
WHERE mv.record_id = ?
```

**Join with source table:**
```sql
-- For DOCX sources
SELECT mv.*, dv.docx_local_path, dv.retrieved_attempt_datetime
FROM markdown_versions mv
JOIN docx_versions dv ON mv.docx_version_id = dv.id
WHERE mv.source_type = 'docx'

-- For HTML sources  
SELECT mv.*, hd.html_local_path, hd.download_attempt_datetime
FROM markdown_versions mv
JOIN html_downloads hd ON mv.html_version_id = hd.id
WHERE mv.source_type = 'html'
```

**Unified query using LEFT JOINs:**
```sql
SELECT 
    mv.*,
    dv.docx_local_path,
    hd.html_local_path,
    COALESCE(dv.retrieved_attempt_datetime, hd.download_attempt_datetime) as source_datetime
FROM markdown_versions mv
LEFT JOIN docx_versions dv ON mv.docx_version_id = dv.id
LEFT JOIN html_downloads hd ON mv.html_version_id = hd.id
WHERE mv.record_id = ?
```

### Application Code Pattern

```python
# For DOCX conversion
insert_markdown_version(
    record_id=rec.id,
    source_type='docx',
    docx_version_id=docx_id,
    html_version_id=None,  # Explicitly NULL
    variant='no_images',
    md_local_path='/path/to/file.md',
    created_datetime=now,
)

# For HTML conversion
insert_markdown_version(
    record_id=rec.id,
    source_type='html',
    docx_version_id=None,  # Explicitly NULL
    html_version_id=html_id,
    variant='with_images',
    md_local_path='/path/to/file.md',
    created_datetime=now,
)
```

## Future Extensibility

To add a new source type (e.g., XML from JATS files):

1. Add new source table:
   ```sql
   CREATE TABLE xml_versions (
       id INTEGER PRIMARY KEY,
       record_id INTEGER NOT NULL,
       xml_local_path TEXT,
       -- ...
   );
   ```

2. Update CHECK constraint:
   ```sql
   CHECK (
       (source_type = 'docx' AND docx_version_id IS NOT NULL AND html_version_id IS NULL AND xml_version_id IS NULL) OR
       (source_type = 'html' AND html_version_id IS NOT NULL AND docx_version_id IS NULL AND xml_version_id IS NULL) OR
       (source_type = 'xml' AND xml_version_id IS NOT NULL AND docx_version_id IS NULL AND html_version_id IS NULL)
   )
   ```

3. Add column with migration:
   ```sql
   ALTER TABLE markdown_versions ADD COLUMN xml_version_id INTEGER REFERENCES xml_versions(id);
   ```

4. Update application code to support `source_type='xml'`

## Migration Notes

**For Existing Databases:**

The migration code automatically handles:
1. Adding `html_version_id` column (initially NULL)
2. Adding `source_type` column (defaults to 'docx' for existing records)
3. CHECK constraint is added only for new table creations

**Note:** SQLite doesn't support adding CHECK constraints to existing tables via ALTER TABLE. For existing databases, the constraint will only apply to new tables created by `init_db()`. This is acceptable because:
- Application logic already enforces the constraint
- The constraint prevents future mistakes, not retroactive fixes
- Existing data should already be valid from application logic

To retrofit the constraint on an existing database (optional):
```sql
-- Create new table with constraint
CREATE TABLE markdown_versions_new (...with CHECK constraint...);

-- Copy data
INSERT INTO markdown_versions_new SELECT * FROM markdown_versions;

-- Swap tables
DROP TABLE markdown_versions;
ALTER TABLE markdown_versions_new RENAME TO markdown_versions;
```

## Alternatives Considered and Rejected

| Aspect | Option 1 (Selected) | Option 2 (Separate) | Option 3 (Polymorphic) |
|--------|---------------------|---------------------|------------------------|
| Referential Integrity | ✅ Full | ✅ Full | ❌ None |
| NULL columns | ⚠️ Yes | ✅ None | ✅ None |
| Query Complexity | ✅ Simple | ⚠️ Medium | ❌ Complex |
| Code Duplication | ✅ Low | ❌ High | ✅ Low |
| Extensibility | ✅ Good | ⚠️ OK | ✅ Excellent |
| Type Safety | ✅ Good | ✅ Excellent | ❌ Poor |
| Best Practice | ✅ Yes | ✅ Yes | ❌ Anti-pattern |

## Conclusion

The single-table approach with CHECK constraint (Option 1) provides the best balance of:
- **Simplicity**: Easy to understand and query
- **Integrity**: Database-enforced correctness
- **Performance**: Single table, efficient joins
- **Maintainability**: Minimal code duplication
- **Extensibility**: Straightforward to add new source types

This design follows established database design principles while remaining practical for the application's needs.

## References

- SQLite CHECK Constraints: https://www.sqlite.org/lang_createtable.html#check_constraints
- Database Design Patterns: Martin Fowler's "Patterns of Enterprise Application Architecture"
- Implementation: `src/llm_query_doc_analyser/core/store.py`
