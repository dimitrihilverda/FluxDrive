"""FluxDrive v1 rev B placement: board outline, planes and pours, rule areas and the position of every footprint.

    "/c/Program Files/KiCad/10.0/bin/python.exe" tools/pcb_place.py FluxDrive.kicad_pcb
    "/c/Program Files/KiCad/10.0/bin/python.exe" tools/pcb_place.py --check FluxDrive.kicad_pcb

Coordinates are KiCad board mm (x right = east, y down = south); the board is x 100..160, y 73.5..145.6,
4 layers (In1 GND plane, In2 +3V3 plane). South edge: J1 over CN11, even (signal) row inward; 17.78 mm north of
it J6 for the real drive, same orientation; between them the J1-J6 band (the pass-through tracks, test pads, the
builder's jumpers and pads). North edge: the module, its antenna 0.35 mm inside the edge. The table itself is
tools/placement.py (no pcbnew, so the tests can read it); this script legalises and applies it.

FIXED parts go exactly where the table says. Every other part starts at its table position and, if its
courtyard would overlap one already placed, leave the board or enter J1's or J6's connector zone (no SMD in the
bands the box-header bodies and the iron need), or if one of its pads would reach into the strip of a J1-J6
pass-through track in the band, moves to the nearest free spot (spiral search, 0.1 mm steps, up to 4 mm; then the
other orientation). The script prints every part it had to move.
Positions are footprint origins; rotation in degrees (KiCad: counter-clockwise).
"""
import math
import pathlib
import sys

import pcbnew

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from tools.placement import (CONNECTOR_ZONE, J1_PIN1, J6_PIN1, J6_ZONE, SHIFT, X0, X1, Y0, Y1,  # noqa: E402
                             corridors, pin_x, table)

PLANE_MARGIN = 0.5
MODULE_BOX = (-9.75, -13.5, 9.75, 13.47)            # U1 body courtyard (without its antenna keep-out)
OVERHANG = {"J3"}                                   # may reach past the outline: the USB-C shell
CORRIDORS = corridors()                             # the pass-through tracks' strips in the J1-J6 band
assert abs(J6_PIN1[1] - (J1_PIN1[1] - SHIFT)) < 1e-9


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


def pad_boxes(fp):
    """{rotation: [(x0, y0, x1, y1)]} of the footprint's pads (its copper) around the origin."""
    out = {}
    for rot in (0, 90, 180, 270):
        fp.SetOrientationDegrees(rot)
        fp.SetPosition(pcbnew.VECTOR2I_MM(0, 0))
        out[rot] = [tuple(round(pcbnew.ToMM(v), 3) for v in (b.GetLeft(), b.GetTop(), b.GetRight(), b.GetBottom()))
                    for b in (p.GetBoundingBox() for p in fp.Pads())]
    return out


def is_smd(fp):
    return any(p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD for p in fp.Pads())


def overlaps(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def legal(ref, box, smd, placed, pads=()):
    if any(overlaps(p, c) for p in pads for c in CORRIDORS):
        return False
    if ref not in OVERHANG and not (X0 + 0.1 <= box[0] and box[2] <= X1 - 0.1 and Y0 + 0.1 <= box[1]
                                    and box[3] <= Y1 - 0.1):
        return False
    if smd and (overlaps(box, CONNECTOR_ZONE) or overlaps(box, J6_ZONE)):
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
    """{ref: (x, y, rot)} for every footprint, and the list of parts that were moved (ref, distance, rot)."""
    fixed, soft = table()
    shapes = {r: boxes(fp) for r, fp in fps.items()}
    coppers = {r: pad_boxes(fp) for r, fp in fps.items()}
    shapes["U1"] = {0: MODULE_BOX}
    placed, where, moved = {}, {}, []
    for ref, (x, y, rot) in fixed.items():
        b = shapes[ref][rot]
        placed[ref] = (x + b[0], y + b[1], x + b[2], y + b[3])
        where[ref] = (x, y, rot)
    for ref, x, y, rot in soft:
        smd = is_smd(fps[ref])
        for r in (rot, (rot + 90) % 360):
            b, c = shapes[ref][r], coppers[ref][r]
            spot = next(((x + dx, y + dy) for dx, dy in spiral()
                         if legal(ref, (x + dx + b[0], y + dy + b[1], x + dx + b[2], y + dy + b[3]), smd, placed,
                                  [(x + dx + q[0], y + dy + q[1], x + dx + q[2], y + dy + q[3]) for q in c])),
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


def _rect(zone, x0, y0, x1, y1):
    poly = zone.Outline()
    poly.NewOutline()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        poly.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))


PLANES = ((pcbnew.In1_Cu, "/GND"), (pcbnew.In2_Cu, "/+3V3"), (pcbnew.F_Cu, "/GND"), (pcbnew.B_Cu, "/GND"))


def set_planes(board):
    """In1 a solid GND plane, In2 a solid +3V3 plane, GND pours on F.Cu and B.Cu, over the whole board; created
    once. Through-hole pads get thermal reliefs (hand soldering), SMD pads a solid connection. The module
    footprint's keep-out keeps every layer clear under the antenna."""
    have = {(z.GetLayer(), z.GetNetname()) for z in board.Zones() if not z.GetIsRuleArea()}
    for layer, net in PLANES:
        if (layer, net) in have:
            continue
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(board.FindNet(net))
        m = PLANE_MARGIN
        _rect(z, X0 - m, Y0 - m, X1 + m, Y1 + m)
        z.SetLocalClearance(pcbnew.FromMM(0.25))
        z.SetMinThickness(pcbnew.FromMM(0.25))
        z.SetThermalReliefGap(pcbnew.FromMM(0.3))
        z.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.4))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        board.Add(z)


def rows_keepout(pin1_y):
    """The rectangle over a 2x17 header's rows that keeps every track 0.8 mm from its GND row (rev B spec 9,
    review M6): from the even pads' south edge to 1.75 mm south of the GND row, 1.75 mm past the end pins."""
    even_y, odd_y = pin1_y - 2.54, pin1_y
    return (pin_x(1) - 1.75, even_y + 0.85, pin_x(33) + 1.75, odd_y + 1.75)


def keepout_areas(where):
    """[(name, layers, rects, no_vias)]: the track keep-outs of the layout reviews, from the placement."""
    ux, uy, _ = where["U1"]
    lx, ly, _ = where["L1"]
    sx, sy, _ = where["U6"]
    jx, jy, _ = where["J3"]
    return [
        # rev B spec 9: no track between J1's rows or within 0.8 mm of its GND row, on both layers (it is
        # hand-soldered, on either side); J6 is a top box header soldered on B.Cu: J1's rule on B.Cu only
        ("J1 rows F", (pcbnew.F_Cu,), [rows_keepout(J1_PIN1[1])], True),
        ("J1 rows B", (pcbnew.B_Cu,), [rows_keepout(J1_PIN1[1])], True),
        ("J6 rows B", (pcbnew.B_Cu,), [rows_keepout(J6_PIN1[1])], True),
        # LESP-1: nothing along the antenna's base line (the module keep-out covers the antenna itself)
        ("antenna edge", (pcbnew.F_Cu, pcbnew.B_Cu), [(ux - 26.0, uy - 6.75, ux + 26.0, uy - 5.85)], False),
        # rev B spec 9: the lines 1 mm outside the keep-out's sides stay free of tracks for the GND stitching
        # (tools/pcb_stitch.py places those vias after routing)
        ("antenna sides", (pcbnew.F_Cu, pcbnew.B_Cu), [(ux - 25.5, Y0, ux - 24.5, uy - 6.75),
                                                        (ux + 24.5, Y0, ux + 25.5, uy - 6.75)], False),
        # LPWR-3: nothing under the switch node and the inductor on B.Cu, nothing between L1 pads, and a strip
        # north of the switch node for the USB lines
        ("buck B", (pcbnew.B_Cu,), [(sx - 2.1, ly - 2.3, lx + 2.35, ly + 2.3)], False),
        ("buck F", (pcbnew.F_Cu,), [(lx - 0.85, ly - 1.9, lx + 0.85, ly + 1.9),
                                    (sx + 0.4, ly - 2.9, lx - 0.9, ly - 1.95)], True),
        # LESP-5: no F.Cu track under the module body; a band inside each pad row stays free for pad entry
        ("module underside", (pcbnew.F_Cu,), [(ux - 6.7, uy - 6.75, ux + 6.7, uy + 10.85)], False),
        # LPWR-13: nothing under the USB-C shell between its pads
        ("USB-C body", (pcbnew.F_Cu,), [(X0, jy - 3.2, jx + 1.15, jy + 3.2)], True),
    ]


def set_keepouts(board, where):
    have = {z.GetZoneName() for z in board.Zones() if z.GetIsRuleArea()}
    for name, layers, rects, no_vias in keepout_areas(where):
        for i, (x0, y0, x1, y1) in enumerate(rects):
            zname = f"{name} {i + 1}"
            if zname in have:
                continue
            z = pcbnew.ZONE(board)
            z.SetIsRuleArea(True)
            z.SetZoneName(zname)
            ls = pcbnew.LSET()
            for layer in layers:
                ls.AddLayer(layer)
            z.SetLayerSet(ls)
            z.SetDoNotAllowTracks(True)
            z.SetDoNotAllowVias(no_vias)
            z.SetDoNotAllowPads(False)
            z.SetDoNotAllowFootprints(False)
            z.SetDoNotAllowZoneFills(False)
            _rect(z, x0, y0, x1, y1)
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
    return where, moved


def check(board):
    """LCODE-1: every footprint where this table puts it (a board built by an older version shows up)."""
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    actual = {r: (round(pcbnew.ToMM(fp.GetPosition().x), 3), round(pcbnew.ToMM(fp.GetPosition().y), 3),
                  round(fp.GetOrientationDegrees()) % 360) for r, fp in fps.items()}
    where, _ = plan(fps)
    bad = [r for r, (x, y, rot) in where.items()
           if abs(actual[r][0] - x) > 0.005 or abs(actual[r][1] - y) > 0.005 or actual[r][2] != rot % 360]
    for r in bad:
        print(f"  {r}: board {actual[r]}, table {where[r]}")
    return bad


if __name__ == "__main__":
    if sys.argv[1] == "--check":
        bad = check(pcbnew.LoadBoard(sys.argv[2]))
        print(f"{len(bad)} footprints differ from the placement table")
        sys.exit(1 if bad else 0)
    b = pcbnew.LoadBoard(sys.argv[1])
    set_outline(b)
    where, moved = place(b)
    set_planes(b)
    set_keepouts(b, where)
    pcbnew.SaveBoard(sys.argv[1], b)            # zones are filled by: kicad-cli pcb drc --refill-zones --save-board
    print(f"placed {len(b.GetFootprints())} footprints; moved to make room: "
          + (", ".join(f"{r} {d} mm" + (f" rot {rot}" if rot is not None else "") for r, d, rot in moved) or "none"))
