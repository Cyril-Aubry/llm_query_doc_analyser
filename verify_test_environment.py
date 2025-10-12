"""Verification script for test environment feature.

This script verifies that the test mode correctly separates production and test data.
Run this script to ensure the test environment feature is working correctly.
"""

from pathlib import Path

from llm_query_doc_analyser.core.config import (
    get_config,
    is_test_mode,
    set_production_mode,
    set_test_mode,
)


def verify_production_paths() -> bool:
    """Verify production mode uses correct paths."""
    print("\n[Test 1] Verifying production paths...")
    set_production_mode()
    
    config = get_config()
    
    checks = [
        (config.mode == "production", "Mode should be 'production'"),
        (config.db_path == Path("data/cache/research_articles_management.db"), "DB path should be in data/cache/"),
        (config.pdf_dir == Path("data/pdfs"), "PDF dir should be data/pdfs"),
        (config.docx_dir == Path("data/docx"), "DOCX dir should be data/docx"),
        (config.markdown_dir == Path("data/markdown"), "Markdown dir should be data/markdown"),
        (not is_test_mode(), "is_test_mode() should return False"),
    ]
    
    passed = 0
    failed = 0
    
    for check, description in checks:
        if check:
            print(f"  ✓ {description}")
            passed += 1
        else:
            print(f"  ✗ {description}")
            failed += 1
    
    print(f"\nResult: {passed} passed, {failed} failed")
    return failed == 0


def verify_test_paths() -> bool:
    """Verify test mode uses correct paths."""
    print("\n[Test 2] Verifying test paths...")
    set_test_mode()
    
    config = get_config()
    
    checks = [
        (config.mode == "test", "Mode should be 'test'"),
        (config.db_path == Path("test_data/cache/test_research_articles.db"), "DB path should be in test_data/cache/"),
        (config.pdf_dir == Path("test_data/pdfs"), "PDF dir should be test_data/pdfs"),
        (config.docx_dir == Path("test_data/docx"), "DOCX dir should be test_data/docx"),
        (config.markdown_dir == Path("test_data/markdown"), "Markdown dir should be test_data/markdown"),
        (is_test_mode(), "is_test_mode() should return True"),
    ]
    
    passed = 0
    failed = 0
    
    for check, description in checks:
        if check:
            print(f"  ✓ {description}")
            passed += 1
        else:
            print(f"  ✗ {description}")
            failed += 1
    
    print(f"\nResult: {passed} passed, {failed} failed")
    return failed == 0


def verify_mode_switching() -> bool:
    """Verify mode switching works correctly."""
    print("\n[Test 3] Verifying mode switching...")
    
    checks = []
    
    # Start in production
    set_production_mode()
    checks.append((get_config().mode == "production", "Initial mode should be production"))
    
    # Switch to test
    set_test_mode()
    checks.append((get_config().mode == "test", "Mode should switch to test"))
    checks.append((is_test_mode(), "is_test_mode() should return True after switch"))
    
    # Switch back to production
    set_production_mode()
    checks.append((get_config().mode == "production", "Mode should switch back to production"))
    checks.append((not is_test_mode(), "is_test_mode() should return False after switch back"))
    
    passed = 0
    failed = 0
    
    for check, description in checks:
        if check:
            print(f"  ✓ {description}")
            passed += 1
        else:
            print(f"  ✗ {description}")
            failed += 1
    
    print(f"\nResult: {passed} passed, {failed} failed")
    return failed == 0


def verify_path_isolation() -> bool:
    """Verify paths are completely isolated between modes."""
    print("\n[Test 4] Verifying path isolation...")
    
    set_production_mode()
    prod_paths = {
        "db": str(get_config().db_path),
        "pdf": str(get_config().pdf_dir),
        "docx": str(get_config().docx_dir),
        "markdown": str(get_config().markdown_dir),
    }
    
    set_test_mode()
    test_paths = {
        "db": str(get_config().db_path),
        "pdf": str(get_config().pdf_dir),
        "docx": str(get_config().docx_dir),
        "markdown": str(get_config().markdown_dir),
    }
    
    checks = []
    for key in prod_paths:
        different = prod_paths[key] != test_paths[key]
        no_overlap = "test_data" in test_paths[key] and "data" in prod_paths[key]
        checks.append((
            different and no_overlap,
            f"{key.upper()} paths should be completely different: prod='{prod_paths[key]}' vs test='{test_paths[key]}'"
        ))
    
    passed = 0
    failed = 0
    
    for check, description in checks:
        if check:
            print(f"  ✓ {description}")
            passed += 1
        else:
            print(f"  ✗ {description}")
            failed += 1
    
    print(f"\nResult: {passed} passed, {failed} failed")
    return failed == 0


def main() -> None:
    """Run all verification tests."""
    print("=" * 80)
    print("Test Environment Feature - Verification Script")
    print("=" * 80)
    
    results = [
        verify_production_paths(),
        verify_test_paths(),
        verify_mode_switching(),
        verify_path_isolation(),
    ]
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    if all(results):
        print("\n✓ All tests PASSED!")
        print("\nThe test environment feature is working correctly.")
        print("You can safely use --test flag with CLI commands.")
    else:
        print("\n✗ Some tests FAILED!")
        print("\nPlease review the failures above and fix any issues.")
        print("Do NOT use --test flag until all tests pass.")
    
    # Reset to production mode at the end
    set_production_mode()
    print("\n[Cleanup] Reset to production mode")
    print("=" * 80)


if __name__ == "__main__":
    main()
