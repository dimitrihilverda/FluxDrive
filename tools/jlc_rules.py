"""The JLC BOM and CPL rules of tools/jlc_export.py that need no pcbnew, so the tests (system Python) can import them.

Rotation: KiCad's plus a correction per footprint for JLC's package orientation. The corrections are the ones the
Nano-Tek Rev 1.2 CPL (made by the JLCPCB Tools plugin, assembled by JLC) used; SOIC follows TSSOP, the same KiCad
pin-1 orientation.
"""
import re

# footprint name regex -> degrees added to KiCad's rotation, first match wins
ROTATION = [
    (r"^LQFP-", 270),                 # U1 in Rev 1.2
    (r"^SOT-23", 180),                # U3 (SOT-23-5) and Q1 (SOT-23) in Rev 1.2; also SOT-23-6
    (r"^SOT-363", 180),               # SC-70-6: the same orientation as the SOT-23 family
    (r"^TSSOP-", 0),                  # U2 in Rev 1.2
    (r"^SOIC-", 0),                   # same pin-1 orientation as TSSOP in KiCad (check in JLC's preview)
    (r"^(MSOP|VSSOP)-", 0),           # the same pin-1 orientation as TSSOP in KiCad
    (r"^IDC-Header_2x", 270),         # CN3 in Rev 1.2
    (r"^Pin(Header|Socket)_", 270),   # J1-J4 in Rev 1.2
]


def correction(fp_name):
    """Degrees JLC's CPL adds to KiCad's rotation for this footprint name (the library item, no library prefix)."""
    for pattern, deg in ROTATION:
        if re.search(pattern, fp_name):
            return deg
    return 0


def comment(values):
    """BOM comment for a group of parts: every distinct value, in order of first appearance, joined by "/"."""
    seen = []
    for v in values:
        if v not in seen:
            seen.append(v)
    return "/".join(seen)
