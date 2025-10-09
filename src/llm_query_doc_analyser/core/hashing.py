import hashlib


def normalize_doi(s: str | None) -> str | None:
    if not s:
        return None
    s = s.strip().lower()
    if s.startswith("https://doi.org/"):
        s = s.replace("https://doi.org/", "")
    if s.startswith("https://dx.doi.org/"):
        s = s.replace("https://dx.doi.org/", "")
    if s.startswith("http://doi.org/"):
        s = s.replace("http://doi.org/", "")
    if s.startswith("http://dx.doi.org/"):
        s = s.replace("http://dx.doi.org/", "")
    return s or None


def sha1_bytes(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()
