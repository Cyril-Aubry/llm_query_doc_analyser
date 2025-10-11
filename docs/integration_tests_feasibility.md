Cyrilaubry: #codebase What would be the available strategies to test integrations tests with the sqlite database and the pdf, docx and markdown files to be able to check that informations get created and updated in the database, and files get registrered and created? Don't implement any code, just propose adequate strategies that could easily be implemented in our project.

Based on your codebase, here are effective strategies for integration testing SQLite database operations and file management:

## 1. **Fixture-Based Temporary Environment**
- Use pytest fixtures to create isolated temporary databases and file directories for each test
- Already partially implemented in test_import_research_articles.py with `temp_db` fixture
- Extend to include temporary directories for PDF, DOCX, and markdown files

**Benefits:**
- Clean slate for each test
- No cross-test contamination
- Easy cleanup via `tmp_path` pytest fixture

## 2. **Factory Pattern for Test Data**
- Create factory functions/classes to generate test `Record` objects with controlled attributes
- Build factories for:
  - Records with various enrichment states (with/without abstracts, OA status, etc.)
  - Mock PDF download responses
  - Mock file system structures

**Benefits:**
- Reusable test data generation
- Parameterized testing for edge cases
- Reduces test boilerplate

## 3. **Database State Verification Helpers**
- Create assertion helper functions to verify database state:
  - `assert_record_in_db(record, expected_fields)`
  - `assert_pdf_download_recorded(record_id, expected_status)`
  - `assert_file_versions_exist(record_id, pdf=True, docx=True, markdown=True)`
  - `assert_provenance_structure(record, required_sources)`

**Benefits:**
- Readable, expressive test assertions
- Centralized verification logic
- Easy to extend for new tables/views

## 4. **Staged Integration Tests**
Organize tests into logical stages mirroring your workflow:

**Stage 1: Import & Storage**
- Test `load_records()` → `upsert_record()` → database persistence
- Verify indexes, foreign keys, unique constraints

**Stage 2: Enrichment Cycle**
- Test enrichment orchestration → database updates
- Verify provenance JSON structure
- Check abstract/OA status updates

**Stage 3: File Resolution & Download**
- Test PDF resolution → `pdf_resolutions` table
- Test download simulation → `pdf_downloads` table + file creation
- Test DOCX lookup → `docx_versions` table

**Stage 4: File Conversion**
- Test DOCX → Markdown conversion (mocked pandoc calls)
- Verify `markdown_versions` table updates
- Check file naming and directory structure

**Stage 5: View Queries**
- Test `article_file_versions_view` returns correct joined data
- Verify filtering by `has_pdf`, `has_markdown`, etc.

## 5. **Mock External Dependencies**
- Use `respx` (already in dependencies) to mock HTTP calls for PDF downloads
- Mock `subprocess.run` for pandoc calls using `unittest.mock.patch`
- Create fixture for mock `httpx.Client` with predefined responses

**Benefits:**
- Fast tests (no real network/external tool calls)
- Deterministic outcomes
- Test error handling paths

## 6. **File System Verification Helpers**
- Create utilities to assert file existence and properties:
  - `assert_file_exists(path, min_size=0)`
  - `assert_file_matches_sha1(path, expected_sha1)`
  - `assert_directory_contains_files(dir, expected_count, pattern="*.pdf")`

## 7. **Transactional Test Isolation**
- Each test gets a fresh database via `monkeypatch.setattr("...core.store.DB_PATH", temp_db_path)`
- Use `get_conn()` context manager's rollback capability for negative tests

## 8. **Snapshot Testing for Complex Structures**
- For complex JSON provenance or enrichment reports, use `pytest-snapshot` or similar
- Store expected database row snapshots as JSON fixtures
- Compare actual vs. expected with diff output on mismatch

## 9. **End-to-End Workflow Tests**
- One comprehensive test that runs through the full pipeline:
  ```
  import → enrich → resolve PDFs → download → convert DOCX → export
  ```
- Verify database state and file system at each step
- Use markers (`@pytest.mark.slow`) to separate from unit tests

## 10. **Database Schema Migration Testing**
- Test that `init_db()` can be called multiple times safely
- Verify all tables, indexes, and views exist after initialization
- Test adding a record before and after migration (forward compatibility)

## 11. **Parametrized File Format Tests**
- Use `@pytest.mark.parametrize` to test different file types:
  - CSV vs. XLSX import
  - Different PDF content types (actual PDF vs. HTML redirect)
  - DOCX vs. no DOCX available

## 12. **Concurrency & Race Condition Tests** (Advanced)
- Test multiple async enrichment tasks updating the same record
- Verify SQLite's `busy_timeout` and locking behavior
- Use `pytest-asyncio` fixtures for async test setup/teardown

## Implementation Priority
1. **High Priority:** Fixture-based temporary environment (1), Database state verification helpers (3)
2. **Medium Priority:** Factory pattern (2), Staged integration tests (4), Mock external dependencies (5)
3. **Low Priority (Nice-to-have):** Snapshot testing (8), End-to-end workflow (9), Concurrency tests (12)

---

These strategies align with your existing test structure and would integrate seamlessly with pytest, respx, and your current async testing setup. They provide good coverage without requiring major architectural changes to your production code.