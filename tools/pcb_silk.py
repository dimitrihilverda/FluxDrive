"""FluxDrive silkscreen: name and credit, pin-1 marks, header pin names, the plug-on socket note, the serial
box, JLC's order-number spot, tidy reference texts; and a 50 mm scale bar on Dwgs.User for the fit template.

    "/c/Program Files/KiCad/10.0/bin/python.exe" tools/pcb_silk.py FluxDrive.kicad_pcb

Only adds (removing drawings crashes pcbnew): a text or line that is already there (same string, place and
layer) is skipped, so a re-run is harmless.
"""
import sys

import pcbnew

SMALL = 0.8          # mm, reference text height (JLC minimum)
# References that stay off the silkscreen: the passives and pads in the dense rows have no room for them.
# They remain on F.Fab, i.e. in the assembly drawing.
HIDE_REFS = ("R", "C", "D", "TP", "FID", "H", "L", "SW")     # the buttons are labelled BOOT / RESET
HIDE_REF_EXACT = {"U1", "U5", "U6", "U7", "J1", "J5"}   # the module and the 34-way (obvious), the small ICs of
                                                        # the power corner, J5 (named on the bottom)
# references AutoPositionFields puts on a neighbour: (x, y), upright; the buffers carry theirs on the body
REF_POS = {"J2": (104.0, 146.9), "U2": (136.5, 125.2), "U3": (125.0, 125.2),
           "U4": (150.0, 125.2)}

# (text, x, y, layer, size, rotation)   all centred
TEXTS = [
    # top: pin 1 of the 34-way connector, the buttons
    ("1", 111.3, 146.6, "F.SilkS", 1.0, 0),
    ("BOOT", 151.3, 110.3, "F.SilkS", 0.8, 90),
    ("RESET", 151.3, 116.0, "F.SilkS", 0.8, 90),
    # bottom: name and credit, serial box, order number, the plug-on option, pin 1, header pins
    ("FluxDrive v1 rev A", 130.0, 102.6, "B.SilkS", 1.2, 0),
    ("by Dimmy (Dimitri Hilverda)", 130.0, 104.8, "B.SilkS", 1.0, 0),
    ("S/N", 124.4, 113.4, "B.SilkS", 0.8, 0),
    ("JLCJLCJLCJLC", 130.0, 121.8, "B.SilkS", 1.0, 0),
    ("J1 option: 2x17 FEMALE socket on this side, plugs straight", 129.0, 131.9, "B.SilkS", 0.9, 0),
    ("onto the A500 floppy header. Pin 1 = square pad", 129.0, 133.5, "B.SilkS", 0.9, 0),
    ("1", 113.68, 146.6, "B.SilkS", 1.0, 0),
    ("+5V", 107.9, 136.5, "B.SilkS", 0.8, 0), ("GND", 107.9, 139.0, "B.SilkS", 0.8, 0),
    ("GND", 107.9, 141.5, "B.SilkS", 0.8, 0), ("12V nc", 108.6, 144.0, "B.SilkS", 0.8, 0),
    ("TX", 149.2, 102.2, "B.SilkS", 0.8, 0), ("RX", 149.2, 104.74, "B.SilkS", 0.8, 0),
    ("EN", 149.2, 107.28, "B.SilkS", 0.8, 0), ("IO0", 149.2, 109.82, "B.SilkS", 0.8, 0),
    ("3V3", 149.2, 112.36, "B.SilkS", 0.8, 0), ("GND", 149.2, 114.9, "B.SilkS", 0.8, 0),
    ("UART", 146.5, 117.2, "B.SilkS", 0.8, 0),
    ("IO13", 154.6, 121.0, "B.SilkS", 0.8, 0), ("IO14", 154.6, 123.54, "B.SilkS", 0.8, 0),
    ("IO47", 154.6, 126.08, "B.SilkS", 0.8, 0), ("IO48", 154.6, 128.62, "B.SilkS", 0.8, 0),
    ("3V3", 154.6, 131.16, "B.SilkS", 0.8, 0), ("GND", 154.6, 133.7, "B.SilkS", 0.8, 0),
    ("50 mm", 130.0, 152.4, "Dwgs.User", 1.5, 0),
]
# (x0, y0, x1, y1, layer, width)
LINES = [
    # serial number box, 15 x 6 mm
    (122.5, 112.3, 137.5, 112.3, "B.SilkS", 0.15), (137.5, 112.3, 137.5, 118.3, "B.SilkS", 0.15),
    (137.5, 118.3, 122.5, 118.3, "B.SilkS", 0.15), (122.5, 118.3, 122.5, 112.3, "B.SilkS", 0.15),
    # scale bar for the printed fit template, under the board outline
    (105.0, 150.5, 155.0, 150.5, "Dwgs.User", 0.2), (105.0, 149.5, 105.0, 151.5, "Dwgs.User", 0.2),
    (155.0, 149.5, 155.0, 151.5, "Dwgs.User", 0.2),
]


def add_text(board, text, x, y, layer, size, rot):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text)
    t.SetPosition(pcbnew.VECTOR2I_MM(x, y))
    lid = board.GetLayerID(layer)
    t.SetLayer(lid)
    t.SetTextSize(pcbnew.VECTOR2I_MM(size, size))
    t.SetTextThickness(pcbnew.FromMM(max(0.15, size * 0.15)))
    t.SetTextAngleDegrees(rot)
    t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
    t.SetMirrored(lid == pcbnew.B_SilkS)
    board.Add(t)


def add_line(board, x0, y0, x1, y1, layer, width):
    s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(pcbnew.VECTOR2I_MM(x0, y0))
    s.SetEnd(pcbnew.VECTOR2I_MM(x1, y1))
    s.SetLayer(board.GetLayerID(layer))
    s.SetWidth(pcbnew.FromMM(width))
    board.Add(s)


def key(x, y):
    return round(x, 2), round(y, 2)


def main(path):
    b = pcbnew.LoadBoard(path)
    texts = {(d.GetText(), *key(pcbnew.ToMM(d.GetPosition().x), pcbnew.ToMM(d.GetPosition().y)), d.GetLayer())
             for d in b.GetDrawings() if d.GetClass() == "PCB_TEXT"}
    lines = {(*key(pcbnew.ToMM(d.GetStart().x), pcbnew.ToMM(d.GetStart().y)),
              *key(pcbnew.ToMM(d.GetEnd().x), pcbnew.ToMM(d.GetEnd().y)), d.GetLayer())
             for d in b.GetDrawings() if d.GetClass() == "PCB_SHAPE"}
    added = 0
    for t in TEXTS:
        if (t[0], *key(t[1], t[2]), b.GetLayerID(t[3])) not in texts:
            add_text(b, *t)
            added += 1
    for ln in LINES:
        if (*key(ln[0], ln[1]), *key(ln[2], ln[3]), b.GetLayerID(ln[4])) not in lines:
            add_line(b, *ln)
            added += 1
    for fp in b.GetFootprints():
        ref = fp.Reference()
        ref.SetTextSize(pcbnew.VECTOR2I_MM(SMALL, SMALL))
        ref.SetTextThickness(pcbnew.FromMM(0.15))
        r = fp.GetReference()
        ref.SetVisible(not (r.rstrip("0123456789").startswith(HIDE_REFS) or r in HIDE_REF_EXACT))
        for f in fp.GetFields():            # e.g. a Part Number field a library footprint shows on the silkscreen
            if not f.IsReference() and f.IsOnLayer(pcbnew.F_SilkS):
                f.SetVisible(False)
        fp.AutoPositionFields()
        if r in REF_POS:
            ref.SetPosition(pcbnew.VECTOR2I_MM(*REF_POS[r]))
            ref.SetTextAngleDegrees(0)
    pcbnew.SaveBoard(path, b)
    print(f"{added} texts and lines added; references resized, passives hidden")


if __name__ == "__main__":
    main(sys.argv[1])
