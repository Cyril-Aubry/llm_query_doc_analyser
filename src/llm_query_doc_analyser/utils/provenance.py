"""Utilities for formatting provenance information."""

import json


def formatted_provenance(prov: dict) -> str:
    """Return a human-readable string representing provenance dict.

    This formats nested dictionaries and lists, showing the source keys and brief snippets.
    """
    if not prov:
        return "No provenance available for this record."

    lines = []
    for source, val in sorted(prov.items()):
        lines.append(f"Source: {source}")
        # If value is a dict, pretty-print keys and small snippets
        if isinstance(val, dict):
            for k, v in val.items():
                snippet = json.dumps(v) if isinstance(v, (dict, list)) else str(v)
                lines.append(f"  {k}: {snippet}")
        elif isinstance(val, list):
            # Show up to first 5 items
            for i, item in enumerate(val):
                lines.append(f"  [{i}] {json.dumps(item)}")
            # if len(val) > 5:
            #     lines.append(f"  ... and {len(val) - 5} more items")
        else:
            lines.append(f"  raw: {val!s}")
        lines.append("")
    return "\n".join(lines)
