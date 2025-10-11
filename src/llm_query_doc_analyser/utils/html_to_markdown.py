#!/usr/bin/env python3
"""
html_to_md.py — Convert an .htm/.html file (with a sibling resources folder) to Markdown.

Usage:
  python html_to_md.py /path/to/page.htm
  # Optional:
  #   --out /path/to/output.md
  #   --resources-name page_files   # force a specific resources folder name
  #   --embed-data-uris             # keep data: URIs inline (default)
  #   --no-embed-data-uris          # export data: URIs into files in resources dir
  #   --use-convert                 # use markdownify's `convert=[...]` (pre-unwrap spans)
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup
from markdownify import markdownify as md

# --------------------------- Helpers ---------------------------

RESOURCE_DIR_CANDIDATES = (
    "{stem}_files",
    "{stem}.files",
    "{stem}_resources",
    "{stem}",
)

IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".tif", ".tiff"}
DOC_EXTS = {".pdf", ".docx", ".pptx", ".xlsx", ".zip"}

def guess_resource_dir(html_path: Path) -> Path:
    parent = html_path.parent
    stem = html_path.stem
    for fmt in RESOURCE_DIR_CANDIDATES:
        candidate = parent / fmt.format(stem=stem)
        if candidate.exists() and candidate.is_dir():
            return candidate
    # default if none exist
    return parent / f"{stem}_files"

def is_data_uri(s: str) -> bool:
    return s.strip().startswith("data:")

def filename_from_url(url: str, fallback_prefix: str = "file") -> str:
    u = urlparse(url)
    name = os.path.basename(unquote(u.path)) if u.path else ""
    if not name:
        return f"{fallback_prefix}"
    return name

def ensure_unique_path(folder: Path, name: str) -> Path:
    base = Path(name).stem
    ext = Path(name).suffix
    cand = folder / f"{base}{ext}"
    k = 1
    while cand.exists():
        cand = folder / f"{base}-{k}{ext}"
        k += 1
    return cand

def looks_local_file(url: str) -> bool:
    u = urlparse(url)
    return (u.scheme in ("", "file")) and (not url.startswith("//"))

def copy_if_local_and_exists(src_url: str, html_dir: Path, res_dir: Path) -> Optional[str]:
    u = urlparse(src_url)
    src_path = Path(unquote(u.path))
    if not src_path.is_absolute():
        src_path = (html_dir / src_path).resolve()
    if src_path.exists() and src_path.is_file():
        res_dir.mkdir(parents=True, exist_ok=True)
        target = ensure_unique_path(res_dir, src_path.name)
        shutil.copy2(src_path, target)
        return str(target.relative_to(html_dir))
    return None

def write_data_uri_as_file(data_uri: str, res_dir: Path, html_dir: Path, hint_name: str = "embed") -> Optional[str]:
    import base64
    m = re.match(r"data:(?P<mime>[\w/+.-]+)(;charset=[\w-]+)?(?P<b64>;base64)?,(?P<data>.*)$", data_uri, re.DOTALL)
    if not m:
        return None
    mime = m.group("mime")
    is_b64 = m.group("b64") is not None
    data = m.group("data")

    ext = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/svg+xml": ".svg",
        "image/bmp": ".bmp",
        "application/pdf": ".pdf",
    }.get(mime, "")

    res_dir.mkdir(parents=True, exist_ok=True)
    out = ensure_unique_path(res_dir, f"{hint_name}{ext or ''}")

    raw = base64.b64decode(data) if is_b64 else unquote(data).encode("utf-8", "ignore")
    out.write_bytes(raw)
    return str(out.relative_to(html_dir))

# --------------------------- Core converter ---------------------------

def preprocess_html(soup: BeautifulSoup) -> None:
    # Remove scripts/styles/noscripts/meta/iframes that clutter Markdown
    for tag in soup(["script", "style", "noscript", "meta", "iframe"]):
        tag.decompose()
    # leave <pre>, <code> etc. intact

def normalize_media_and_links(
    soup: BeautifulSoup,
    html_path: Path,
    res_dir: Path,
    embed_data_uris: bool = True,
) -> None:
    """
    Make <img>, <a>, <source>, <video>, <audio> resources local & relative.
    - Copies local files into res_dir when appropriate.
    - Optionally exports data: URIs to files (if embed_data_uris=False).
    """
    html_dir = html_path.parent

    # Images
    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        if not src:
            continue
        if is_data_uri(src):
            if embed_data_uris:
                continue
            new_rel = write_data_uri_as_file(src, res_dir, html_dir, hint_name="image")
            if new_rel:
                img["src"] = new_rel
            continue
        if looks_local_file(src):
            abs_from_html = (html_dir / unquote(src)).resolve()
            if abs_from_html.exists():
                try:
                    rel = abs_from_html.relative_to(html_dir)
                    img["src"] = str(rel)
                    continue
                except ValueError:
                    pass
            copied = copy_if_local_and_exists(src, html_dir, res_dir)
            if copied:
                img["src"] = copied
        # else: leave http(s) as-is

    # <source> tags
    for src_tag in soup.find_all(["source"]):
        src = (src_tag.get("src") or "").strip()
        if not src:
            continue
        if is_data_uri(src):
            if embed_data_uris:
                continue
            new_rel = write_data_uri_as_file(src, res_dir, html_dir, hint_name="media")
            if new_rel:
                src_tag["src"] = new_rel
            continue
        if looks_local_file(src):
            copied = copy_if_local_and_exists(src, html_dir, res_dir)
            if copied:
                src_tag["src"] = copied

    # <a href> (downloadable docs)
    for a in soup.find_all("a"):
        href = (a.get("href") or "").strip()
        if not href or href.startswith("#"):
            continue
        if is_data_uri(href):
            if embed_data_uris:
                continue
            new_rel = write_data_uri_as_file(href, res_dir, html_dir, hint_name="link")
            if new_rel:
                a["href"] = new_rel
            continue
        if looks_local_file(href):
            ext = Path(filename_from_url(href)).suffix.lower()
            if ext in IMG_EXTS | DOC_EXTS:
                copied = copy_if_local_and_exists(href, html_dir, res_dir)
                if copied:
                    a["href"] = copied

def _has_lxml() -> bool:
    try:
        import lxml  # noqa: F401
        return True
    except Exception:
        return False

def html_to_markdown(
    html_path: Path,
    out_md: Path | None = None,
    forced_resources_name: str | None = None,
    embed_data_uris: bool = True,
    use_convert: bool = False,
) -> Path:
    """
    Convert HTML to Markdown.
    - If use_convert=False (default): use markdownify with `strip=["span"]`
    - If use_convert=True: unwrap spans in soup and use `convert=[...]` (no `strip`)
    """
    html_path = html_path.resolve()
    if not html_path.exists():
        raise FileNotFoundError(f"HTML not found: {html_path}")

    with html_path.open("rb") as f:
        raw = f.read()

    soup = BeautifulSoup(raw, "lxml") if _has_lxml() else BeautifulSoup(raw, "html.parser")

    res_dir = (
        (html_path.parent / forced_resources_name)
        if forced_resources_name
        else guess_resource_dir(html_path)
    )

    preprocess_html(soup)
    normalize_media_and_links(soup, html_path, res_dir, embed_data_uris=embed_data_uris)

    # ---- markdownify (fixed: do NOT pass strip and convert together) ----
    if use_convert:
        # Pre-strip spans manually if you want to use `convert`
        for tag in soup.find_all("span"):
            tag.unwrap()
        markdown = md(
            str(soup),
            heading_style="ATX",
            convert=["hr", "a", "img", "table"],
            bullets="*",
            code_language_detection=False,
            keep_inline_images_in=["a"],
        )
    else:
        markdown = md(
            str(soup),
            heading_style="ATX",
            strip=["span"],   # safe: not using `convert` at the same time
            bullets="*",
            code_language_detection=False,
            keep_inline_images_in=["a"],
        )

    # Post-fixes: trim excessive blank lines
    markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip() + "\n"

    out_md = out_md or html_path.with_suffix(".md")
    out_md.write_text(markdown, encoding="utf-8")
    return out_md

# --------------------------- CLI ---------------------------

def main(argv: Iterable[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Convert a saved HTML page to Markdown.")
    p.add_argument("html", type=Path, help="Path to .htm/.html file")
    p.add_argument("--out", type=Path, default=None, help="Output .md path (default: alongside HTML)")
    p.add_argument("--resources-name", type=str, default=None,
                   help="Force resources folder name (e.g., 'page_files'). If absent, guessed.")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--embed-data-uris", action="store_true", default=True,
                   help="Keep existing data: URIs inline (default).")
    g.add_argument("--no-embed-data-uris", dest="embed_data_uris", action="store_false",
                   help="Export data: URIs into files in the resources folder.")
    p.add_argument("--use-convert", action="store_true",
                   help="Use markdownify `convert=[...]` (pre-unwraps <span>; disables `strip`).")
    args = p.parse_args(argv)

    out = html_to_markdown(
        args.html,
        out_md=args.out,
        forced_resources_name=args.resources_name,
        embed_data_uris=args.embed_data_uris,
        use_convert=args.use_convert,
    )
    print(f"Markdown written to: {out}")

if __name__ == "__main__":
    main()
