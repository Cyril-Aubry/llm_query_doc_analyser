"""Tests for pre-print detection and version linking functionality."""

from typing import Any

import pytest

from llm_query_doc_analyser.core.models import Record
from llm_query_doc_analyser.enrich.preprint_detection import (
    detect_preprint_source,
    extract_published_doi_from_crossref,
    extract_published_doi_from_europepmc,
    extract_published_doi_from_openalex,
    extract_published_doi_from_provenance,
)


class TestPreprintDetection:
    """Test pre-print source detection."""

    def test_detect_arxiv_by_source_title(self) -> None:
        """Test arXiv detection from source_title."""
        rec = Record(
            title="Test Paper",
            source_title="arXiv",
            doi_norm="10.48550/arxiv.2301.12345"
        )
        assert detect_preprint_source(rec) == "arxiv"

    def test_detect_arxiv_by_arxiv_id(self) -> None:
        """Test arXiv detection from arxiv_id."""
        rec = Record(
            title="Test Paper",
            arxiv_id="2301.12345"
        )
        assert detect_preprint_source(rec) == "arxiv"

    def test_detect_medrxiv(self) -> None:
        """Test medRxiv detection."""
        rec = Record(
            title="Test Paper",
            source_title="medRxiv"
        )
        assert detect_preprint_source(rec) == "medrxiv"

    def test_detect_biorxiv(self) -> None:
        """Test bioRxiv detection."""
        rec = Record(
            title="Test Paper",
            source_title="bioRxiv"
        )
        assert detect_preprint_source(rec) == "biorxiv"

    def test_detect_preprints_org(self) -> None:
        """Test Preprints.org detection."""
        rec = Record(
            title="Test Paper",
            source_title="Preprints.org"
        )
        assert detect_preprint_source(rec) == "preprints"

    def test_no_preprint_detection(self) -> None:
        """Test that non-preprint sources return None."""
        rec = Record(
            title="Test Paper",
            source_title="Nature"
        )
        assert detect_preprint_source(rec) is None


class TestPublishedVersionExtraction:
    """Test extraction of published version DOIs from API responses."""

    def test_extract_from_crossref_is_preprint_of(self) -> None:
        """Test extraction from Crossref is-preprint-of relation."""
        crossref_data = {
            "message": {
                "relation": {
                    "is-preprint-of": [
                        {"id": "10.1234/published-version"}
                    ]
                }
            }
        }
        doi = extract_published_doi_from_crossref(crossref_data)
        assert doi == "10.1234/published-version"

    def test_extract_from_crossref_has_version(self) -> None:
        """Test extraction from Crossref has-version relation."""
        crossref_data = {
            "message": {
                "relation": {
                    "has-version": [
                        {
                            "id": "10.1234/published-vor",
                            "type": "vor"
                        }
                    ]
                }
            }
        }
        doi = extract_published_doi_from_crossref(crossref_data)
        assert doi == "10.1234/published-vor"

    def test_extract_from_crossref_no_relation(self) -> None:
        """Test that missing relation returns None."""
        crossref_data: dict[str, Any] = {"message": {}}
        doi = extract_published_doi_from_crossref(crossref_data)
        assert doi is None

    def test_extract_from_openalex_published_version(self) -> None:
        """Test extraction from OpenAlex published version location."""
        openalex_data = {
            "primary_location": {
                "version": "publishedVersion",
                "source": {"type": "journal"},
                "landing_page_url": "https://doi.org/10.1234/published"
            }
        }
        doi = extract_published_doi_from_openalex(openalex_data)
        assert doi == "10.1234/published"

    def test_extract_from_openalex_related_works(self) -> None:
        """Test extraction from OpenAlex related_works."""
        openalex_data = {
            "related_works": [
                "https://doi.org/10.1234/published-work"
            ]
        }
        doi = extract_published_doi_from_openalex(openalex_data)
        assert doi == "10.1234/published-work"

    def test_extract_from_europepmc_relationships(self) -> None:
        """Test extraction from EuropePMC relationships."""
        europepmc_data = {
            "resultList": {
                "result": [
                    {
                        "relationshipList": {
                            "relationship": [
                                {
                                    "type": "published_version",
                                    "doi": "10.1234/published-pmc"
                                }
                            ]
                        }
                    }
                ]
            }
        }
        doi = extract_published_doi_from_europepmc(europepmc_data)
        assert doi == "10.1234/published-pmc"

    def test_extract_from_provenance_priority(self) -> None:
        """Test that provenance extraction follows priority order."""
        provenance = {
            "crossref": {
                "message": {
                    "relation": {
                        "is-preprint-of": [{"id": "10.1234/crossref"}]
                    }
                }
            },
            "openalex": {
                "primary_location": {
                    "version": "publishedVersion",
                    "source": {"type": "journal"},
                    "landing_page_url": "https://doi.org/10.1234/openalex"
                }
            }
        }
        # Crossref should be checked first
        doi, source = extract_published_doi_from_provenance(provenance)
        assert doi == "10.1234/crossref"
        assert source == "crossref"


class TestVersionLinking:
    """Test version linking functionality."""

    def test_create_published_version_record(self) -> None:
        """Test creation of published version record from preprint."""
        preprint = Record(
            id=123,
            title="Preprint Title",
            doi_norm="10.48550/arxiv.2301.12345",
            authors="Smith, J.; Doe, A.",
            pub_date="2023-01-15",
            is_preprint=True,
            preprint_source="arxiv"
        )
        
        # Note: This test requires database connection
        # In real test, would mock the database operations
        # published = create_published_version_record(
        #     preprint,
        #     "10.1234/published",
        #     "crossref"
        # )
        # assert published.is_preprint == False
        # assert published.preprint_version_doi == preprint.doi_norm
        # assert published.preprint_version_id == preprint.id

    def test_find_record_by_doi(self) -> None:
        """Test finding record by normalized DOI."""
        # Note: Requires database with test data
        # rec = find_record_by_doi("10.1234/test")
        # assert rec is not None or rec is None  # depending on test data
        pass


# Integration test examples (require database):
@pytest.mark.integration
class TestVersionLinkingIntegration:
    """Integration tests for version linking (requires database)."""

    @pytest.fixture
    def test_db(self) -> None:
        """Setup test database."""
        # Initialize test database
        # yield connection
        # cleanup
        pass

    def test_complete_linking_workflow(self, test_db: None) -> None:
        """Test complete preprint-to-published linking workflow."""
        # 1. Import preprint record
        # 2. Enrich with API data containing published version
        # 3. Verify bidirectional link created
        # 4. Verify statistics updated correctly
        pass

    def test_duplicate_prevention(self, test_db: None) -> None:
        """Test that duplicate published versions are not created."""
        # 1. Create preprint
        # 2. Create published version manually
        # 3. Run linking
        # 4. Verify no duplicate created
        pass

    def test_linking_statistics(self, test_db: None) -> None:
        """Test that linking statistics are accurate."""
        # 1. Create test data with known linking patterns
        # 2. Query statistics
        # 3. Verify counts match expected values
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
