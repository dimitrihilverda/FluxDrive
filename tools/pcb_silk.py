"""FluxDrive silkscreen: name and credit, pin-1 marks, header pin names, the plug-on socket note, the serial
box, JLC's order-number spot, tidy reference texts; and scale bars on Dwgs.User for the fit template.

    "/c/Program Files/KiCad/10.0/bin/python.exe" tools/pcb_silk.py FluxDrive.kicad_pcb

Every text is at least 1.0 mm high (spec 8 and JLC; layout review LPCB-4). Pin names and pin-1 marks are
placed from the pads they belong to (LCODE-7: a part the placement moved takes its labels along).
Only adds (removing drawings crashes pcbnew): a text or line that is already there (same string, place and
layer) is skipped, so a re-run is harmless.
"""
import sys

import pcbnew

SIZE = 1.0           # mm, text height (spec 8, JLC minimum)
# References that stay off the silkscreen: the passives and pads in the dense rows have no room for them.
# They remain on F.Fab, i.e. in the assembly drawing.
HIDE_REFS = ("R", "C", "D", "TP", "FID", "H", "L", "SW")     # the buttons are labelled BOOT / RESET
HIDE_REF_EXACT = {"U1", "U5", "U6", "U7", "J1", "J3", "J5"}  # obvious, or named by the texts below
# references placed by hand: (dx, dy) from the footprint origin, upright; the buffers carry theirs on the body
REF_AT = {"J2": (0.0, 10.4), "J4": (0.0, -2.1), "U2": (0.0, 0.0), "U3": (0.0, 0.0), "U4": (0.0, 0.0)}

# (text, x, y, layer, size, rotation) at fixed places, all centred
TEXTS = [
    ("FluxDrive v1 rev A", 130.0, 102.6, "B.SilkS", 1.2, 0),
    ("by Dimmy (Dimitri Hilverda)", 130.0, 104.8, "B.SilkS", 1.0, 0),
    ("S/N", 124.6, 113.5, "B.SilkS", 1.0, 0),
    ("JLCJLCJLCJLC", 130.0, 121.8, "B.SilkS", 1.0, 0),
    ("J1 option: 2x17 female socket on this side,", 130.0, 131.8, "B.SilkS", 1.0, 0),
    ("plugs onto the A500 header. Pin 1 = square pad", 130.0, 133.5, "B.SilkS", 1.0, 0),
    ("UART", 146.5, 117.3, "B.SilkS", 1.0, 0),
    # fit test (Dimitri, 2026-09-29): plugged onto CN11, pin 1 over its pin 1, the antenna edge points to the
    # A500's front (over the 8520 and Gary); on the antenna strip, which carries no copper
    ("A500 FRONT", 111.5, 96.8, "F.SilkS", 1.0, 0), ("A500 FRONT", 148.5, 96.8, "F.SilkS", 1.0, 0),
    ("A500 FRONT", 111.5, 96.8, "B.SilkS", 1.0, 0), ("A500 FRONT", 148.5, 96.8, "B.SilkS", 1.0, 0),
    ("print at 100 %: both bars must measure exactly 50 mm / 40 mm", 130.0, 154.0, "Dwgs.User", 1.5, 0),
    ("50 mm", 130.0, 152.2, "Dwgs.User", 1.5, 0),
    ("40 mm", 166.5, 120.0, "Dwgs.User", 1.5, 90),
]
# (ref, pad, text, dx, dy, layer, rotation): a label next to a pad
PAD_TEXTS = [
    ("J1", "1", "1", -2.38, 5.05, "F.SilkS", 0), ("J1", "1", "1", 0.0, 5.05, "B.SilkS", 0),
    ("J2", "1", "+5V", 3.9, 0.0, "B.SilkS", 0), ("J2", "2", "GND", 3.9, 0.0, "B.SilkS", 0),
    ("J2", "3", "GND", 3.9, 0.0, "B.SilkS", 0), ("J2", "4", "12V nc", 4.6, 0.0, "B.SilkS", 0),
    ("J4", "1", "TX", 2.8, 0.0, "B.SilkS", 0), ("J4", "2", "RX", 2.8, 0.0, "B.SilkS", 0),
    ("J4", "3", "EN", 2.8, 0.0, "B.SilkS", 0), ("J4", "4", "IO0", 2.9, 0.0, "B.SilkS", 0),
    ("J4", "5", "3V3", 2.9, 0.0, "B.SilkS", 0), ("J4", "6", "GND", 2.9, 0.0, "B.SilkS", 0),
    ("J5", "1", "IO13", -3.0, 0.0, "B.SilkS", 0), ("J5", "2", "IO14", -3.0, 0.0, "B.SilkS", 0),
    ("J5", "3", "IO47", -3.0, 0.0, "B.SilkS", 0), ("J5", "4", "IO48", -3.0, 0.0, "B.SilkS", 0),
    ("J5", "5", "3V3", -2.9, 0.0, "B.SilkS", 0), ("J5", "6", "GND", -2.9, 0.0, "B.SilkS", 0),
]
# (ref, text, dx, dy, rotation): labels beside a footprint on F.SilkS
FP_TEXTS = [("SW1", "BOOT", -4.55, 0.0, 90), ("SW2", "RESET", -4.55, 0.0, 90)]
# (x0, y0, x1, y1, layer, width)
LINES = [
    # serial number box, 15 x 6 mm
    (122.5, 112.3, 137.5, 112.3, "B.SilkS", 0.15), (137.5, 112.3, 137.5, 118.3, "B.SilkS", 0.15),
    (137.5, 118.3, 122.5, 118.3, "B.SilkS", 0.15), (122.5, 118.3, 122.5, 112.3, "B.SilkS", 0.15),
    # scale bars for the printed fit template, outside the board outline: 50 mm across, 40 mm down
    (105.0, 150.5, 155.0, 150.5, "Dwgs.User", 0.2), (105.0, 149.5, 105.0, 151.5, "Dwgs.User", 0.2),
    (155.0, 149.5, 155.0, 151.5, "Dwgs.User", 0.2),
    (164.5, 100.0, 164.5, 140.0, "Dwgs.User", 0.2), (163.5, 100.0, 165.5, 100.0, "Dwgs.User", 0.2),
    (163.5, 140.0, 165.5, 140.0, "Dwgs.User", 0.2),
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


def all_texts(board):
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    out = list(TEXTS)
    for ref, pad, text, dx, dy, layer, rot in PAD_TEXTS:
        p = next(q for q in fps[ref].Pads() if q.GetNumber() == pad).GetPosition()
        out.append((text, round(pcbnew.ToMM(p.x) + dx, 2), round(pcbnew.ToMM(p.y) + dy, 2), layer, SIZE, rot))
    for ref, text, dx, dy, rot in FP_TEXTS:
        p = fps[ref].GetPosition()
        out.append((text, round(pcbnew.ToMM(p.x) + dx, 2), round(pcbnew.ToMM(p.y) + dy, 2), "F.SilkS", SIZE, rot))
    return out


def main(path):
    b = pcbnew.LoadBoard(path)
    texts = {(d.GetText(), *key(pcbnew.ToMM(d.GetPosition().x), pcbnew.ToMM(d.GetPosition().y)), d.GetLayer())
             for d in b.GetDrawings() if d.GetClass() == "PCB_TEXT"}
    lines = {(*key(pcbnew.ToMM(d.GetStart().x), pcbnew.ToMM(d.GetStart().y)),
              *key(pcbnew.ToMM(d.GetEnd().x), pcbnew.ToMM(d.GetEnd().y)), d.GetLayer())
             for d in b.GetDrawings() if d.GetClass() == "PCB_SHAPE"}
    added = 0
    for t in all_texts(b):
        if (t[0], *key(t[1], t[2]), b.GetLayerID(t[3])) not in texts:
            add_text(b, *t)
            added += 1
    for ln in LINES:
        if (*key(ln[0], ln[1]), *key(ln[2], ln[3]), b.GetLayerID(ln[4])) not in lines:
            add_line(b, *ln)
            added += 1
    for fp in b.GetFootprints():
        ref = fp.Reference()
        ref.SetTextSize(pcbnew.VECTOR2I_MM(SIZE, SIZE))
        ref.SetTextThickness(pcbnew.FromMM(0.15))
        r = fp.GetReference()
        ref.SetVisible(not (r.rstrip("0123456789").startswith(HIDE_REFS) or r in HIDE_REF_EXACT))
        for f in fp.GetFields():            # e.g. a Part Number field a library footprint shows on the silkscreen
            if not f.IsReference() and f.IsOnLayer(pcbnew.F_SilkS):
                f.SetVisible(False)
        fp.AutoPositionFields()
        if r in REF_AT:
            c = fp.GetPosition()
            dx, dy = REF_AT[r]
            ref.SetPosition(pcbnew.VECTOR2I(c.x + pcbnew.FromMM(dx), c.y + pcbnew.FromMM(dy)))
            ref.SetTextAngleDegrees(0)
    pcbnew.SaveBoard(path, b)
    print(f"{added} texts and lines added; references resized, passives hidden")


if __name__ == "__main__":
    main(sys.argv[1])
