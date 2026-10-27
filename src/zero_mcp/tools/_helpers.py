"""Small argument helpers shared by otherwise independent tool slices."""

import re

from mcp.server.mcpserver.exceptions import ToolError

_ISIN_PATTERN = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]")


def normalize_isin(value: str) -> str:
    """Return the ISIN in canonical uppercase form, or raise ``ToolError``.

    Instruments are addressed by ISIN everywhere in the ZERO API; catching
    malformed input here yields a clearer message than a broker 404.
    """
    cleaned = value.strip().upper()
    if not _ISIN_PATTERN.fullmatch(cleaned):
        raise ToolError(
            f"Invalid ISIN {value!r}: expected 12 characters such as US0378331005."
        )
    return cleaned
