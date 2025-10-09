from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def preprint_published_link(doi: str) -> dict[str, Any]:
    """
    Async query to Crossref using httpx to determine if a DOI is a preprint and
    to extract a linked published DOI (if any).

    Returns a dict with:
      - queried_doi: the input DOI
      - is_preprint: bool
      - published_doi: the first linked published DOI or None
      - all_links: raw relation object from Crossref
    """
    url = f"https://api.crossref.org/works/{doi}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        msg = resp.json().get("message", {})

    is_preprint = (msg.get("type") == "posted-content") and (msg.get("subtype") == "preprint")
    rel = msg.get("relation") or {}
    preprint_of = [x.get("id") for x in rel.get("is-preprint-of", []) if x.get("id")]

    return {
        "queried_doi": doi,
        "is_preprint": is_preprint,
        "published_doi": preprint_of[0] if preprint_of else None,
        "all_links": rel,
    }


@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def datacite_preprint_published_link(doi: str) -> dict[str, Any]:
    """
    Async query to DataCite using httpx to determine if a DOI is a preprint and
    to extract a linked published DOI (if any).

    Returns a dict with:
      - queried_doi: the input DOI
      - is_preprint: bool
      - published_doi: the first linked published DOI or None
      - all_relations: raw relatedIdentifiers from DataCite
    """
    url = f"https://api.datacite.org/dois/{doi}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        attributes = data.get("attributes", {})

    # DataCite uses resourceTypeGeneral for type classification
    types = attributes.get("types", {})
    resource_type = types.get("resourceTypeGeneral", "").lower()
    resource_type_specific = types.get("resourceType", "").lower()
    
    # Check if it's a preprint based on resourceType or resourceTypeGeneral
    is_preprint = (
        resource_type == "preprint" or
        "preprint" in resource_type_specific or
        (resource_type == "text" and "preprint" in resource_type_specific)
    )
    
    # Extract related identifiers (relationships)
    related_identifiers = attributes.get("relatedIdentifiers", [])
    
    # Look for published versions
    # Common relation types: "IsVariantFormOf", "IsVersionOf", "IsPreviousVersionOf", "IsPublishedIn"
    published_dois = []
    for rel in related_identifiers:
        rel_type = rel.get("relationType", "")
        identifier_type = rel.get("relatedIdentifierType", "")
        identifier = rel.get("relatedIdentifier", "")
        
        # Look for DOIs that represent published versions
        if identifier_type == "DOI" and rel_type in [
            "IsVariantFormOf", 
            "IsVersionOf", 
            "IsPreviousVersionOf",
            "IsPublishedIn"
        ]:
            # Clean the DOI if it's a full URL
            if identifier.startswith("http"):
                identifier = identifier.replace("https://doi.org/", "").replace("http://doi.org/", "")
            published_dois.append(identifier)

    return {
        "queried_doi": doi,
        "is_preprint": is_preprint,
        "published_doi": published_dois[0] if published_dois else None,
        "all_relations": related_identifiers,
    }


if __name__ == "__main__":
    import asyncio
    import json

    print("=== Testing Crossref ===")  # noqa: T201
    # doi_input = "10.48550/arXiv.2405.11029"
    # crossref_doi = "10.48550/arXiv.2312.06458"
    crossref_doi = "10.20944/preprints202311.1954.v2"
    # crossref_doi = "10.1007/s11042-024-20016-1"
    # crossref_doi = "10.1101/2024.01.30.24301606"
    # crossref_doi = "10.1101/2024.07.28.24311154"
    result = asyncio.run(preprint_published_link(crossref_doi))
    print(json.dumps(result, indent=2))  # noqa: T201

    print("\n=== Testing DataCite ===")  # noqa: T201
    # Common DataCite DOI prefixes: 10.5281 (Zenodo), 10.48550 (arXiv)
    datacite_doi = "10.48550/arXiv.2312.06458"
    # datacite_doi = "10.48550/arXiv.2405.11029"
    # datacite_doi = "10.5281/zenodo.1234567"  # Example Zenodo DOI
    result_datacite = asyncio.run(datacite_preprint_published_link(datacite_doi))
    print(json.dumps(result_datacite, indent=2))  # noqa: T201
