"""SMD parts the builder places by hand: JLC's assembly leaves them out, and their pads get no solder paste.

U1, the ESP32-S3-WROOM-1 module: Dimitri places it himself (2026-09-30). JLC prints paste on every stencil opening,
also on a part it does not place; reflowed, that paste leaves bumps (the worst on the module's ground pad), and the
module would not sit flat. Without paste its pads come flat and tinned by the surface finish.
Used by tools/pcb_sync.py (paste), tools/jlc_export.py (BOM and CPL) and the board tests.
"""
HAND_PLACED = ("U1",)
