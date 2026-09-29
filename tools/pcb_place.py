"""FluxDrive v1 placement: board outline, ground pours and the position of every footprint.

    "/c/Program Files/KiCad/10.0/bin/python.exe" tools/pcb_place.py FluxDrive.kicad_pcb

Coordinates are KiCad board mm (x right = east, y down = south); the board is x 100..160, y 100..148.
South edge: the 34-way connector J1, even (signal) row inward. North edge: the module, its antenna
6 mm past the edge. West: power header next to J1, TVS pad, bulk capacitors, diodes, eFuse, buck, USB-C.
East: recovery and spare headers, buttons, LED, the output buffer at the pin 26-34 end of J1.
Between the module and J1: the input buffers, row B (100 kOhm / 10 kOhm at the buffers) and row A
(pull-ups, 100 Ohm and 33 Ohm at the connector pins).

FIXED parts go exactly where the table says. Every other part starts at its table position and, if its
courtyard would overlap one already placed, leave the board or enter the connector zone (spec 8: no SMD
in the 54 x 10 mm band over J1), moves to the nearest free spot (spiral search, 0.1 mm steps, up to 4 mm;
then the other orientation). The script prints every part it had to move.
Positions are footprint origins; rotation in degrees (KiCad: counter-clockwise).
"""
import math
import sys

import pcbnew

X0, Y0, X1, Y1 = 100.0, 100.0, 160.0, 148.0
PLANE_MARGIN = 0.5
J1_PIN1 = (113.68, 141.55)           # 2.4 mm strip south of its body for test pads and a fiducial
ROW_A, ROW_B, ROW_B_0603 = 134.3, 130.2, 130.6
SOUTH_STRIP = 146.6                  # y of the test pads and FID3 between J1's body and the south edge
BUF_Y = 125.2                        # the three buffers; row B is 5 mm below, row A 4.1 mm below that
CONNECTOR_ZONE = (107.0, J1_PIN1[1] - 6.27, 161.0, J1_PIN1[1] + 3.73)   # the test's band: pin field centre +-27 x +-5 mm
MODULE_BOX = (-9.75, -13.5, 9.75, 13.47)            # U1 body courtyard (its antenna keep-out lies off the board)
OVERHANG = {"U1", "J3"}                             # may reach past the outline: antenna, USB-C shell


def pin_x(n):
    """x of J1 pin n (both rows run east from pin 1/2)."""
    return J1_PIN1[0] + ((n - 1) // 2) * 2.54


FIXED = {
    "J1": (J1_PIN1[0], J1_PIN1[1], 90),
    "U1": (130.0, 106.75, 0),
    "J2": (104.0, 136.5, 270),        # pin 1 (+5 V) north, pin 4 (+12 V, unused) south
    "J3": (104.945, 112.5, 270),      # USB-C, opening to the west edge
    "U3": (125.0, BUF_Y, 90),         # 74LVC14A: MTR0_P4, PIN6, PIN14, DKWD, DKWE
    "U2": (136.5, BUF_Y, 90),         # 74LVC14A: STEP, DIR, SIDE, SEL0, SEL1, MTR0
    "U4": (150.0, BUF_Y, 90),         # 74LVC07A
    "H1": (103.5, 103.5, 0),
    "H2": (156.5, 103.5, 0),
}
# row A, at the connector: (J1 pin, ref, offset from the pin's x, rotation). Pull-ups and 100 ohm have
# pad 1 (the connector net) south with rotation 90; the 33 ohm have pad 2 (the connector net) south: 270.
ROW_A_PARTS = [
    (2, "R43", 0.0, 270), (4, "R26", 0.55, 90), (6, "R28", -0.55, 90), (6, "R29", 0.55, 90),
    (8, "R37", 0.0, 270), (10, "R10", -0.55, 90), (10, "R11", 0.55, 90), (12, "R13", -0.55, 90),
    (12, "R14", 0.55, 90), (14, "R31", -0.55, 90), (14, "R32", 0.55, 90), (16, "R17", 0.55, 90),
    (18, "R4", -0.55, 90), (18, "R5", 0.55, 90), (20, "R1", -0.55, 90), (20, "R2", 0.55, 90),
    (22, "R19", -0.55, 90), (22, "R20", 0.55, 90), (24, "R22", -0.55, 90), (24, "R23", 0.55, 90),
    (26, "R39", 0.0, 270), (28, "R41", 0.0, 270), (30, "R35", 0.0, 270), (32, "R7", -0.55, 90),
    (32, "R8", 0.55, 90), (34, "R45", 0.0, 270),
]
for _pin, _ref, _dx, _rot in ROW_A_PARTS:
    FIXED[_ref] = (round(pin_x(_pin) + _dx, 3), ROW_A, _rot)

# every other part: its preferred spot, in the order they are legalised (the ones that matter most first)
SOFT = [
    # power column along the west edge, then eFuse, buck
    ("D2", 104.0, 118.9, 0), ("D1", 104.0, 122.55, 0), ("C10", 104.0, 125.65, 0), ("C11", 104.0, 128.15, 0),
    ("D4", 104.0, 131.25, 0),
    ("U5", 110.2, 131.9, 0), ("C8", 110.0, 129.4, 0), ("C9", 108.2, 129.4, 90), ("R46", 108.7, 133.9, 0),
    ("R47", 110.8, 133.9, 0), ("R48", 112.4, 131.0, 90), ("C12", 108.8, 127.3, 0),
    ("U6", 112.5, 121.3, 180), ("C13", 109.0, 120.6, 90), ("C14", 109.0, 123.3, 90), ("L1", 117.2, 121.5, 0),
    ("C17", 117.6, 125.3, 0), ("R50", 111.4, 124.9, 0), ("R51", 111.4, 126.2, 0), ("C16", 114.2, 125.3, 90),
    ("R49", 113.5, 128.4, 0), ("C15", 116.6, 128.4, 0),
    # USB
    ("U7", 111.3, 112.5, 0), ("R56", 110.0, 109.2, 0), ("R57", 110.0, 115.8, 0), ("R58", 109.2, 117.6, 0),
    ("R60", 118.9, 116.7, 0), ("R59", 118.9, 118.0, 0), ("C22", 115.9, 116.6, 0), ("C21", 115.9, 118.3, 0),
    # module support, west of its top-left pins
    ("C18", 116.9, 101.5, 0), ("C19", 118.9, 103.2, 0), ("R54", 116.4, 104.6, 0), ("C20", 116.4, 105.9, 0),
    # east
    ("J4", 146.5, 102.2, 0), ("SW1", 155.9, 110.3, 0), ("SW2", 155.9, 116.0, 0),
    ("J5", 157.4, 121.0, 0),              # spare GPIO east of U4: its pins meet the channel above the buffers
    ("D3", 150.8, 102.0, 0), ("R62", 150.8, 104.2, 0), ("R52", 141.2, 102.4, 90), ("R53", 142.4, 102.4, 90),
    ("R61", 142.4, 106.2, 90), ("R55", 141.2, 117.4, 90),
    # decoupling at pin 14 (top-left) of each buffer, in the gap at its west end
    ("C6", 119.8, BUF_Y - 1.4, 90), ("C5", 131.3, BUF_Y - 1.4, 90), ("C7", 144.8, BUF_Y - 1.4, 90),
]
# row B, at the buffers: 100 kOhm (pad 1 = the _B net, north), the unfitted 220 pF and /MTR0 pull-up pads
# (0603, a little lower), the output pull-ups 10 kOhm at U4. A 1.3 mm pitch leaves one track between two.
for _ref, _x in (("R27", 121.2), ("R30", 122.5), ("R33", 123.8), ("R21", 125.1), ("R24", 126.4),
                 ("R12", 131.9), ("R15", 133.2), ("R18", 134.5), ("R6", 135.8), ("R3", 137.1), ("R9", 138.4),
                 ("R42", 145.6), ("R36", 146.9), ("R38", 148.2), ("R40", 149.5), ("R34", 150.8), ("R44", 152.1)):
    SOFT.append((_ref, _x, ROW_B, 90))
for _ref, _x in (("R25", 119.4), ("R16", 128.0), ("C1", 129.7), ("C2", 140.0), ("C3", 141.7), ("C4", 143.4)):
    SOFT.append((_ref, _x, ROW_B_0603, 90))
SOFT += [
    # test pads: bus pairs near their parts, power ones in the west
    # (none in the strip between the module and the buffers: that is the routing channel to the module)
    ("TP10", 130.75, 127.2, 0), ("TP6", 142.6, 127.8, 0), ("TP8", 142.4, 119.6, 0), ("TP4", 142.4, 121.9, 0),
    ("TP2", 142.6, 125.3, 0),
    # connector side: in the strip south of J1, each between two odd (GND) pins, below its own pin
    ("TP3", pin_x(8) + 1.27, SOUTH_STRIP, 0), ("TP5", pin_x(10) + 1.27, SOUTH_STRIP, 0),
    ("TP9", pin_x(16) + 1.27, SOUTH_STRIP, 0), ("TP7", pin_x(20) + 1.27, SOUTH_STRIP, 0),
    ("TP1", pin_x(30) + 1.27, SOUTH_STRIP, 0), ("TP16", pin_x(34) + 1.27, SOUTH_STRIP, 0),
    ("TP11", 107.8, 124.0, 0), ("TP12", 109.2, 118.0, 0), ("TP13", 112.6, 117.4, 0), ("TP14", 113.9, 101.6, 0),
    ("TP15", 113.9, 105.3, 0),
    ("FID1", 108.3, 102.0, 0), ("FID2", 150.9, 106.4, 0), ("FID3", 158.3, SOUTH_STRIP, 0),
]


def boxes(fp):
    """{rotation: (x0, y0, x1, y1)} of the courtyard around the origin, for 0/90/180/270 degrees."""
    out = {}
    for rot in (0, 90, 180, 270):
        fp.SetOrientationDegrees(rot)
        fp.SetPosition(pcbnew.VECTOR2I_MM(0, 0))
        fp.BuildCourtyardCaches()
        poly = fp.GetCourtyard(pcbnew.F_CrtYd)
        bb = poly.BBox() if poly.OutlineCount() else fp.GetBoundingBox(False)
        out[rot] = tuple(round(pcbnew.ToMM(v), 3) for v in (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()))
    return out


def is_smd(fp):
    return any(p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD for p in fp.Pads())


def overlaps(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def legal(ref, box, smd, placed):
    if ref not in OVERHANG and not (X0 + 0.1 <= box[0] and box[2] <= X1 - 0.1 and Y0 + 0.1 <= box[1]
                                    and box[3] <= Y1 - 0.1):
        return False
    if smd and overlaps(box, CONNECTOR_ZONE):
        return False
    return not any(overlaps(box, b) for b in placed.values())


def spiral(max_r=4.0, step=0.1):
    yield 0.0, 0.0
    r = step
    while r <= max_r + 1e-9:
        n = max(8, int(2 * math.pi * r / step))
        for k in range(n):
            a = 2 * math.pi * k / n
            yield r * math.cos(a), r * math.sin(a)
        r += step


def plan(fps):
    """{ref: (x, y, rot)} for every footprint, and the list of parts that were moved (ref, distance)."""
    shapes = {r: boxes(fp) for r, fp in fps.items()}
    shapes["U1"] = {0: MODULE_BOX}
    placed, where, moved = {}, {}, []
    for ref, (x, y, rot) in FIXED.items():
        b = shapes[ref][rot]
        placed[ref] = (x + b[0], y + b[1], x + b[2], y + b[3])
        where[ref] = (x, y, rot)
    for ref, x, y, rot in SOFT:
        smd = is_smd(fps[ref])
        for r in (rot, (rot + 90) % 360):
            b = shapes[ref][r]
            spot = next(((x + dx, y + dy) for dx, dy in spiral()
                         if legal(ref, (x + dx + b[0], y + dy + b[1], x + dx + b[2], y + dy + b[3]), smd, placed)),
                        None)
            if spot:
                break
        assert spot, f"no room for {ref} near ({x}, {y})"
        sx, sy = round(spot[0], 2), round(spot[1], 2)
        placed[ref] = (sx + b[0], sy + b[1], sx + b[2], sy + b[3])
        where[ref] = (sx, sy, r)
        d = math.hypot(sx - x, sy - y)
        if d > 0.01 or r != rot:
            moved.append((ref, round(d, 2), r))
    missing = sorted(set(fps) - set(where))
    assert not missing, f"not in the placement table: {missing}"
    return where, moved


def set_outline(board):
    """A rectangle on Edge.Cuts, once: drawings are never removed (that crashes pcbnew)."""
    if any(d.GetLayer() == pcbnew.Edge_Cuts for d in board.GetDrawings()):
        return
    pts = [(X0, Y0), (X1, Y0), (X1, Y1), (X0, Y1)]
    for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
        s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pcbnew.VECTOR2I_MM(ax, ay))
        s.SetEnd(pcbnew.VECTOR2I_MM(bx, by))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(pcbnew.FromMM(0.05))
        board.Add(s)


def set_planes(board):
    """GND pours on B.Cu (the plane) and F.Cu (fill) over the whole board, created once. Through-hole pads
    get thermal reliefs (hand soldering), SMD pads a solid connection."""
    have = {z.GetLayer() for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname() == "/GND"}
    gnd = board.FindNet("/GND")
    for layer in (pcbnew.B_Cu, pcbnew.F_Cu):
        if layer in have:
            continue
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(gnd)
        m = PLANE_MARGIN
        poly = z.Outline()
        poly.NewOutline()
        for x, y in ((X0 - m, Y0 - m), (X1 + m, Y0 - m), (X1 + m, Y1 + m), (X0 - m, Y1 + m)):
            poly.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
        z.SetLocalClearance(pcbnew.FromMM(0.25))
        z.SetMinThickness(pcbnew.FromMM(0.25))
        z.SetThermalReliefGap(pcbnew.FromMM(0.3))
        z.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.4))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        board.Add(z)


# B.Cu under the 34-way pin field, up to just past the odd (GND) row: no tracks, so the plane stays whole
# between the rows and every GND pin reaches it from the north (spec 8: unbroken ground plane under the
# bus). The strip along the south edge stays free for the long east-west runs. Vias and the pour are allowed.
J1_KEEPOUT = (107.5, 137.4, X1 - 0.2, J1_PIN1[1] + 1.2)


def set_keepouts(board):
    if any(z.GetIsRuleArea() and z.GetZoneName() == "J1 plane" for z in board.Zones()):
        return
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetZoneName("J1 plane")
    z.SetLayer(pcbnew.B_Cu)
    z.SetDoNotAllowTracks(True)
    z.SetDoNotAllowVias(False)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowFootprints(False)
    z.SetDoNotAllowZoneFills(False)
    x0, y0, x1, y1 = J1_KEEPOUT
    poly = z.Outline()
    poly.NewOutline()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        poly.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    board.Add(z)


def place(board):
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    where, moved = plan(fps)
    for ref, (x, y, rot) in where.items():
        fp = fps[ref]
        if fp.IsFlipped():
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)
        fp.SetOrientationDegrees(rot)
        fp.SetPosition(pcbnew.VECTOR2I_MM(x, y))
    return moved


if __name__ == "__main__":
    b = pcbnew.LoadBoard(sys.argv[1])
    set_outline(b)
    moved = place(b)
    set_planes(b)
    set_keepouts(b)
    pcbnew.SaveBoard(sys.argv[1], b)            # zones are filled by: kicad-cli pcb drc --refill-zones --save-board
    print(f"placed {len(b.GetFootprints())} footprints; moved to make room: "
          + (", ".join(f"{r} {d} mm" + (f" rot {rot}" if rot is not None else "") for r, d, rot in moved) or "none"))
