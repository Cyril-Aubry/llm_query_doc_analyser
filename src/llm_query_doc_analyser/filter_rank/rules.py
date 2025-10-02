"""
Rule-based filtering using regex patterns (DEPRECATED).

This module is deprecated in favor of LLM-based filtering in prompts.py.
It is kept for backward compatibility and reference purposes only.
"""
import re

INCLUDE_ANY = [
    r"\bsemantic segmentation\b",
    r"\bpixel[-\s]?wise\b",
    r"\bpixel[-\s]?level\b"
]
EXCLUDE_ANY = [
    r"\b3d\b",
    r"\bvolumetric\b",
    r"\bvoxel(s)?\b",
    r"\bpoint cloud(s)?\b",
    r"\blidar\b",
    r"\bmri volume\b",
    r"\bct volume\b",
    r"\bmesh(es)?\b"
]
OPTIONAL_EXCLUDES = [
    r"\bobject detection\b(?!.*segmentation)",
    r"\bclassification\b(?!.*segmentation)"
]

def rule_filter(text: str) -> tuple[bool, float, list[str]]:
    """Return (keep, rule_score, reasons) based on regex rules."""
    reasons = []
    for pat in INCLUDE_ANY:
        if re.search(pat, text, re.I):
            reasons.append(f"include: {pat}")
    for pat in EXCLUDE_ANY + OPTIONAL_EXCLUDES:
        if re.search(pat, text, re.I):
            reasons.append(f"exclude: {pat}")
    keep = any(re.search(p, text, re.I) for p in INCLUDE_ANY) and not any(re.search(p, text, re.I) for p in EXCLUDE_ANY + OPTIONAL_EXCLUDES)
    rule_score = float(len(reasons)) / (len(INCLUDE_ANY) + len(EXCLUDE_ANY) + len(OPTIONAL_EXCLUDES))
    return keep, rule_score, reasons
