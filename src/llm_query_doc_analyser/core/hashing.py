import hashlib


def normalize_doi(s: str | None) -> str | None:
    if not s:
        return None
    s = s.strip().lower()
    if s.startswith("https://doi.org/"):
        s = s.replace("https://doi.org/", "")
    return s or None


def sha1_bytes(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()
