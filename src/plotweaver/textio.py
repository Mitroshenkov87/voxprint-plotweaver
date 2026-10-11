"""Text reads that accept UTF-8 and Windows PowerShell encodings.

PowerShell 5.1 ``>`` writes UTF-16LE with a BOM. ``Out-File -Encoding utf8``
writes UTF-8 with a BOM. Both must load.
"""

from __future__ import annotations

from pathlib import Path


def read_text(path: Path) -> str:
    """Read ``path``, sniffing a UTF-16 or UTF-8 BOM before plain UTF-8."""
    data = path.read_bytes()
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    return data.decode("utf-8")
