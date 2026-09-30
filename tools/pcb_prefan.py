"""Hand-made routes that go on the board before Freerouting, locked.

    "/c/Program Files/KiCad/10.0/bin/python.exe" tools/pcb_prefan.py FluxDrive.kicad_pcb

1. USB-C VBUS bridge: the receptacle has VBUS on two pads (A4B9 and B4A9), one above and one below the CC,
   D+ and D- pads. Joined on F.Cu, VBUS has to loop around the CC pad of that side and shuts it in
   (Freerouting and the maze router both left CC2 open). So each VBUS pad gets a short stub east to a via,
   the two vias are joined on B.Cu under the connector's pad row, and the bridge runs on down to D2's anode.
   The vias sit 1.8 mm east of the pads, clear of the D- join below.
2. The +5V_A rail to the bus pull-ups (layout review LBUS-1): one B.Cu track along the channel between
   row A and row B, from a via at the eFuse's OUT pin, with a via and a short F.Cu stub to the +5V_A pad of
   every pull-up. No signal between the rows has to cross it on F.Cu, and the router does not have to thread
   the rail through the rows (it left it open when it did).
3. The eFuse's own connections (WSON-8, 0.5 mm pitch): EN to its divider, dVdt, ILM, GND to the exposed pad
   and R48, the IN pins to their capacitor and to the divider's top (via the TVS pad). Every run of the
   router left EN or ILM open between the fine-pitch pins and the fan-out vias.
4. The USB data pads (LESP-3): the receptacle has D+ twice and D- twice, interleaved (B7 D-, A6 D+, A7 D-, B6 D+
   from north to south). Joined on the east side both, one pair shuts the other's inner pad in (build 9 left
   A7 open). D+ goes round the west end of A7, in the 0.6 mm strip between the pads and the USB-C body rule
   area; D- goes round the east end of A6. Both on F.Cu, no via; the router takes them on to the ESD part.
5. /DKRD_D, the flux stream (spec 8, LBUS-4): from U4's output straight down through the gap in row B to its
   33 ohm in row A, on F.Cu. Left to the fan-out and the router, the +3V3 pads of row B were chained on F.Cu
   across that gap and /DKRD_D took 20 mm and two vias round the row.
Run after placement, before the fan-out. Only adds: a re-run finds the routes and places nothing.
"""
import math
import sys

import pcbnew

STUB = 1.8              # mm, VBUS pad centre to its via, east (J3 opens to the west edge)
WIDTH = 0.3             # the Power netclass
VIA_D, VIA_DRILL = 0.6, 0.3
RAIL_Y = 132.7          # mm, the +5V_A rail: between row B (y 130.2) and row A (y 134.3) of pcb_place
RAIL_X = (112.0, 156.0)  # pull-up pads in this x range, rows A and B


def mm(v):
    return pcbnew.FromMM(v)


def track(board, net, a, b, layer):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(a)
    t.SetEnd(b)
    t.SetWidth(mm(WIDTH))
    t.SetLayer(layer)
    t.SetNet(net)
    t.SetLocked(True)
    board.Add(t)


def via(board, net, pos):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pos)
    v.SetWidth(pcbnew.F_Cu, mm(VIA_D))
    v.SetDrill(mm(VIA_DRILL))
    v.SetNet(net)
    v.SetLocked(True)
    board.Add(v)


def pad(fps, ref, number):
    return next(p for p in fps[ref].Pads() if p.GetNumber() == number)


def vbus_bridge(board, fps):
    pads = {p.GetNumber(): p for p in fps["J3"].Pads()}
    net = pads["A4B9"].GetNet()
    ends = []
    for name in ("A4B9", "B4A9"):
        p = pads[name].GetPosition()
        v = pcbnew.VECTOR2I(p.x + mm(STUB), p.y)
        via(board, net, v)
        track(board, net, p, v, pcbnew.F_Cu)
        ends.append(v)
    track(board, net, ends[0], ends[1], pcbnew.B_Cu)
    anode = pad(fps, "D2", "2").GetPosition()              # SS34: pad 2 is the anode, on VBUS
    down = pcbnew.VECTOR2I(ends[1].x, anode.y)
    track(board, net, ends[1], down, pcbnew.B_Cu)
    via(board, net, down)
    track(board, net, down, anode, pcbnew.F_Cu)


def pullup_rail(board, fps):
    out = pad(fps, "U5", "5")                                 # TPS259531 OUT
    net = out.GetNet()
    y = mm(RAIL_Y)
    src = pcbnew.VECTOR2I(out.GetPosition().x + mm(1.15), y)
    track(board, net, out.GetPosition(), src, pcbnew.F_Cu)
    via(board, net, src)
    xs = [src.x]
    for ref, fp in sorted(fps.items()):
        if not ref.startswith("R"):
            continue
        for p in fp.Pads():
            x, py = pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)
            if p.GetNetCode() == net.GetNetCode() and RAIL_X[0] < x < RAIL_X[1] and 129.0 < py < 135.0:
                v = pcbnew.VECTOR2I(p.GetPosition().x, y)
                via(board, net, v)
                track(board, net, p.GetPosition(), v, pcbnew.F_Cu)
                xs.append(v.x)
    track(board, net, pcbnew.VECTOR2I(min(xs), y), pcbnew.VECTOR2I(max(xs), y), pcbnew.B_Cu)
    return len(xs) - 1


USB_W = 0.2             # mm, the Default netclass
USB_WEST = 106.42       # mm, D+ round A7: 0.21 mm from the pad row's west end (106.73), clear of the body area (106.09)
USB_EAST = 0.9          # mm east of the pad centres, D- round A6: 0.22 mm from its east end


def usb_pairs(board, fps):
    pads = {p.GetNumber(): p for p in fps["J3"].Pads()}
    for (a, b), x in ((("A6", "B6"), mm(USB_WEST)), (("A7", "B7"), pads["A7"].GetPosition().x + mm(USB_EAST))):
        pa, pb = pads[a].GetPosition(), pads[b].GetPosition()
        net = pads[a].GetNet()
        assert net.GetNetCode() == pads[b].GetNetCode(), (a, b)
        corners = [pa, pcbnew.VECTOR2I(x, pa.y), pcbnew.VECTOR2I(x, pb.y), pb]
        for u, v in zip(corners, corners[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(u)
            t.SetEnd(v)
            t.SetWidth(mm(USB_W))
            t.SetLayer(pcbnew.F_Cu)
            t.SetNet(net)
            t.SetLocked(True)
            board.Add(t)


ROW_B = (129.0, 131.4)  # mm, the y band of row B's pads (pcb_place ROW_B 130.2, 0603 parts at 130.6)
DKRD_W = 0.2
DKRD_GAP = 0.17         # mm, where the jog into the gap ends: this far above the row's pads


def mm_box(p):
    bb = p.GetBoundingBox()
    return tuple(pcbnew.ToMM(v) for v in (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()))


def dkrd(board, fps):
    src, dst = pad(fps, "U4", "4"), pad(fps, "R35", "1")
    net = src.GetNet()
    assert net.GetNetCode() == dst.GetNetCode()
    sx, sy = pcbnew.ToMM(src.GetPosition().x), pcbnew.ToMM(src.GetPosition().y)
    dx, dy = pcbnew.ToMM(dst.GetPosition().x), pcbnew.ToMM(dst.GetPosition().y)
    row = sorted(mm_box(p) for fp in board.GetFootprints() for p in fp.Pads()
                 if ROW_B[0] < pcbnew.ToMM(p.GetPosition().y) < ROW_B[1])
    edges = sorted((b[0], b[2]) for b in row)
    # the gap in the row nearest the straight line, wide enough for the track with 0.2 mm each side
    gaps = [(a[1], b[0]) for a, b in zip(edges, edges[1:]) if b[0] - a[1] >= DKRD_W + 0.4 + 0.05]
    left, right = min(gaps, key=lambda g: abs((g[0] + g[1]) / 2 - (sx + dx) / 2))
    xg = round((left + right) / 2, 3)
    top = min(b[1] for b in row if b[2] >= left - 0.01 and b[0] <= right + 0.01) - DKRD_GAP
    bottom = max(b[3] for b in row if b[2] >= left - 0.01 and b[0] <= right + 0.01) + 0.25
    pts = [(sx, sy), (sx, top - abs(sx - xg)), (xg, top), (xg, bottom), (dx, bottom + abs(xg - dx)), (dx, dy)]
    assert pts[1][1] >= sy and pts[4][1] <= dy, pts
    pts = [pcbnew.VECTOR2I_MM(x, y) for x, y in pts]
    for u, v in zip(pts, pts[1:]):
        if u == v:
            continue
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(u)
        t.SetEnd(v)
        t.SetWidth(mm(DKRD_W))
        t.SetLayer(pcbnew.F_Cu)
        t.SetNet(net)
        t.SetLocked(True)
        board.Add(t)
    return sum(math.dist((pcbnew.ToMM(u.x), pcbnew.ToMM(u.y)), (pcbnew.ToMM(v.x), pcbnew.ToMM(v.y)))
               for u, v in zip(pts, pts[1:]))


# (ref, pad, ref, pad, width): straight tracks between two pads, F.Cu
EFUSE = [("U5", "2", "R46", "2", 0.2), ("R46", "2", "R47", "1", 0.2),         # EN and the UVLO divider
         ("U5", "1", "C9", "1", 0.2),                                         # dVdt
         ("U5", "7", "R48", "1", 0.2),                                        # ILM
         ("U5", "8", "R48", "2", 0.25), ("U5", "8", "U5", "9", 0.25),         # GND to R48 and the exposed pad
         ("U5", "3", "U5", "4", 0.25), ("U5", "4", "C8", "1", 0.25),          # IN pins and their capacitor
         ("R46", "1", "D4", "1", 0.3)]                                        # the divider's top, +5V_IN


def efuse(board, fps):
    for ra, pa, rb, pb, w in EFUSE:
        a, b = pad(fps, ra, pa), pad(fps, rb, pb)
        assert a.GetNetCode() == b.GetNetCode(), (ra, pa, rb, pb)
        end = b.GetPosition()
        if (rb, pb) == ("U5", "9"):                  # into the exposed pad straight, clear of pin 7 (ILM)
            end = pcbnew.VECTOR2I(end.x + mm(0.3), a.GetPosition().y)
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(a.GetPosition())
        t.SetEnd(end)
        t.SetWidth(mm(w))
        t.SetLayer(pcbnew.F_Cu)
        t.SetNet(a.GetNet())
        t.SetLocked(True)
        board.Add(t)
    return len(EFUSE)


def main(path):
    board = pcbnew.LoadBoard(path)
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    vbus = pad(fps, "J3", "A4B9").GetNetCode()
    if any(t.GetClass() == "PCB_VIA" and t.GetNetCode() == vbus for t in board.GetTracks()):
        print("hand-made routes already there")
        return
    vbus_bridge(board, fps)
    n = pullup_rail(board, fps)
    e = efuse(board, fps)
    usb_pairs(board, fps)
    d = dkrd(board, fps)
    pcbnew.SaveBoard(path, board)
    print(f"VBUS bridge to D2; +5V_A rail on B.Cu to {n} pull-up pads; {e} eFuse tracks; USB D+/D- pad joins; "
          f"/DKRD_D {d:.1f} mm")


if __name__ == "__main__":
    main(sys.argv[1])
