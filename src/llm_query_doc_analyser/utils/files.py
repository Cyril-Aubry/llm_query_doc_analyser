import re
from contextlib import suppress
from pathlib import Path

import nltk  # type: ignore
import spacy

INVALID_CHARS_RE = re.compile(r"[^\w\s\-\.,]", flags=re.U)
WHITESPACE_RE = re.compile(r"[\s_/]+")


def sanitize_text_for_filename(text: str) -> str:
    """Sanitize arbitrary text to a filesystem-friendly string.

    Removes characters that are not letters, numbers, whitespace, dash, dot or underscore.
    Collapses whitespace and replaces with a single space. Trims leading/trailing space.
    """
    if not text:
        return ""
    # Normalize whitespace-like characters and underscores/slashes to space
    text = WHITESPACE_RE.sub(" ", text)
    # Remove any remaining invalid characters
    text = INVALID_CHARS_RE.sub("", text)
    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text).strip()
    return text


def shorten_text(text: str, max_chars: int) -> str:
    """Shorten text to at most max_chars, preserving word boundaries when possible.

    If the text must be truncated, preserve the start and end with a hash in the middle
    when the name is very long to keep it comprehensible.
    """
    # Fast path
    if len(text) <= max_chars:
        return sanitize_text_for_filename(text)

    # Try to use spaCy (preferred) or NLTK to remove stopwords/punctuation, falling back to a simple regex-based approach
    reduced = None

    # Helper fallback stopwords
    _FALLBACK_STOPWORDS = {
        "the",
        "and",
        "a",
        "an",
        "of",
        "in",
        "on",
        "for",
        "with",
        "to",
        "from",
        "by",
        "using",
        "via",
        "is",
        "are",
        "be",
        "this",
        "that",
    }

    try:
        # spaCy preferred for robust tokenization and stopword removal

        try:
            nlp = spacy.load("en_core_web_sm", disable=["parser", "ner"])
        except Exception:
            # If the small model isn't available, try the blank English model
            nlp = spacy.blank("en")

        doc = nlp(text)
        tokens = [tok.text for tok in doc if not (tok.is_stop or tok.is_punct or tok.is_space)]
        reduced = " ".join(tokens)
    except Exception:
        # Try NLTK
        try:
            from nltk.corpus import stopwords  # type: ignore

            try:
                stops = set(stopwords.words("english"))
            except Exception:
                # Attempt to download stopwords if missing
                with suppress(Exception):
                    nltk.download("stopwords", quiet=True)
                stops = set()
                with suppress(Exception):
                    stops = set(stopwords.words("english"))

            # Simple tokenization: split on non-word characters
            words = [w for w in re.split(r"\W+", text) if w]
            tokens = [w for w in words if w.lower() not in stops]
            reduced = " ".join(tokens)
        except Exception:
            # Final fallback: remove common stopwords via regex and the small fallback set
            words = [w for w in re.split(r"\W+", text) if w]
            tokens = [w for w in words if w.lower() not in _FALLBACK_STOPWORDS]
            reduced = " ".join(tokens)

    # Sanitize reduced text to be filename-friendly
    reduced = sanitize_text_for_filename(reduced)

    # If it's still too long, truncate by words (keep the start words until max_chars)
    if len(reduced) <= max_chars:
        return reduced

    words = reduced.split()
    if not words:
        # As a last resort, truncate original sanitized text
        return sanitize_text_for_filename(text)[:max_chars].rstrip()

    out_words: list[str] = []
    current_len = 0
    for w in words:
        add_len = (1 if out_words else 0) + len(w)  # space if not first
        if current_len + add_len > max_chars:
            break
        out_words.append(w)
        current_len += add_len

    if out_words:
        return " ".join(out_words)

    # If no words fit (single long token), truncate the token to max_chars
    first = words[0]
    return first[:max_chars].rstrip()


def make_safe_filename(title: str, extension: str = "pdf", max_length: int = 120) -> str:
    """Produce a safe filename from a title with specified extension.

    Ensures reasonable length. Uniqueness is handled by collision checks
    in the caller (numeric suffixes appended when needed).

    Args:
        title: Title text to convert to filename
        extension: File extension without leading dot (e.g., 'pdf', 'html')
        max_length: Maximum total filename length including extension

    Returns:
        Safe filename with extension
    """
    base = sanitize_text_for_filename(title)
    if not base:
        base = "document"
    # Do not include hashes in filenames per project policy; uniqueness handled by file collision checks
    suffix = ""
    # Ensure extension has no leading dot
    extension = extension.lstrip(".")
    # Reserve space for extension (dot + extension length)
    max_base = max_length - len(suffix) - len(extension) - 1
    base = shorten_text(base, max_base)
    filename = f"{base}{suffix}.{extension}"
    # Final safety: remove any leading/trailing dots or spaces
    filename = filename.strip().strip(".")
    return filename


def make_safe_pdf_filename(title: str, max_length: int = 120) -> str:
    """Produce a safe PDF filename from a title.

    Ensures reasonable length and a .pdf extension. Uniqueness is handled by collision checks
    in the caller (numeric suffixes appended when needed).

    This is a convenience wrapper around make_safe_filename() for backwards compatibility.
    """
    return make_safe_filename(title, extension="pdf", max_length=max_length)


def rename_file(
    orig_path: Path, title: str, dest_dir: Path, extension: str | None = None, max_length: int = 120
) -> Path:
    """Move/rename orig_path into dest_dir using a safe filename derived from title.

    Ensures dest_dir exists. If a filename collision occurs, append a numeric suffix.
    Returns the new Path.

    Args:
        orig_path: Original file path to rename
        title: Title to use for filename
        dest_dir: Destination directory
        extension: File extension without leading dot. If None, uses original file extension
        max_length: Maximum filename length

    Returns:
        New file path after rename
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Determine extension
    if extension is None:
        extension = orig_path.suffix.lstrip(".")

    safe_name = make_safe_filename(title, extension=extension, max_length=max_length)
    target = dest_dir / safe_name

    # If target exists, append counter
    if target.exists():
        stem = target.stem
        suffix = target.suffix
        counter = 1
        while True:
            candidate = dest_dir / f"{stem}-{counter}{suffix}"
            if not candidate.exists():
                target = candidate
                break
            counter += 1

    # Move file
    try:
        orig_path.rename(target)
    except Exception:
        # Fallback to copy (if rename across filesystems) then unlink
        from shutil import copy2

        copy2(orig_path, target)
        with suppress(Exception):
            orig_path.unlink()

    return target


def rename_pdf_file(orig_path: Path, title: str, dest_dir: Path, max_length: int = 120) -> Path:
    """Move/rename PDF file into dest_dir using a safe filename derived from title.

    Ensures dest_dir exists. If a filename collision occurs, append a numeric suffix.
    Returns the new Path.

    This is a convenience wrapper around rename_file() for backwards compatibility.
    """
    return rename_file(orig_path, title, dest_dir, extension="pdf", max_length=max_length)
