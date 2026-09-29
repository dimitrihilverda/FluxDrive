"""Ground stitching: GND vias between the F.Cu fill and the B.Cu plane, after routing (spec 8).

    "/c/Program Files/KiCad/10.0/bin/python.exe" tools/pcb_stitch.py FluxDrive.kicad_pcb

Candidates lie on a 2.5 mm grid over the board. A via goes where it keeps the clearance of
tools/pcb_fanout.py to every other net on both layers, the hole-to-hole rule and the edge, stays out of
the module's footprint (only its own ground vias belong under it) and is at least SPACING from every GND
via already there (the fan-out included). Along the edges the spacing is tighter. New vias are locked.
Only adds: a re-run finds the vias of the last run and places nothing new. A via that DRC then reports as
unconnected (it joined two cut-off pieces of pour, not the plane) is taken out again, in a fresh process.
"""
import json
import pathlib
import subprocess
import sys

import pcbnew

from pcb_fanout import CLEARANCE, HOLE_GAP, VIA_D, VIA_DRILL, holes, mm

X0, Y0, X1, Y1 = 100.0, 100.0, 160.0, 148.0
GRID = 2.5
SPACING, EDGE_SPACING = 5.0, 4.0
EDGE_BAND = 2.5            # mm: candidates this close to the outline count as edge stitching
EDGE_MIN = 1.0             # via centre to the outline
NO_GO = [("U1", 9.3, 13.0)]  # footprint: half width, half height around its origin
KICAD_CLI = r"C:/Program Files/KiCad/10.0/bin/kicad-cli.exe"


def main(path):
    board = pcbnew.LoadBoard(path)
    gnd = board.FindNet("/GND")
    others = {layer: [] for layer in (pcbnew.F_Cu, pcbnew.B_Cu)}
    for t in board.GetTracks():
        for layer in others:
            if t.GetNetCode() != gnd.GetNetCode() and t.IsOnLayer(layer):
                others[layer].append(t.GetEffectiveShape(layer))
    for fp in board.GetFootprints():
        for p in fp.Pads():
            for layer in others:
                if p.IsOnLayer(layer) and (p.GetNetCode() != gnd.GetNetCode() or not p.HasHole()):
                    others[layer].append(p.GetEffectiveShape(layer))   # SMD GND pads too: no via in a pad
    for z in list(board.Zones()) + [z for fp in board.GetFootprints() for z in fp.Zones()]:
        if z.GetIsRuleArea() and z.GetDoNotAllowVias():
            for layer in others:
                others[layer].append(z.Outline())
    no_go = []
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    for ref, hw, hh in NO_GO:
        c = fps[ref].GetPosition()
        no_go.append((pcbnew.ToMM(c.x) - hw, pcbnew.ToMM(c.y) - hh, pcbnew.ToMM(c.x) + hw, pcbnew.ToMM(c.y) + hh))
    gnd_vias = [(pcbnew.ToMM(v.GetPosition().x), pcbnew.ToMM(v.GetPosition().y)) for v in board.GetTracks()
                if v.GetClass() == "PCB_VIA" and v.GetNetCode() == gnd.GetNetCode()]
    hole_list = holes(board)
    added = 0
    nx, ny = int((X1 - X0) / GRID * 2), int((Y1 - Y0) / GRID * 2)
    cands = sorted({(round(X0 + EDGE_MIN + i * GRID / 2, 2), round(Y0 + EDGE_MIN + j * GRID / 2, 2))
                    for i in range(nx + 1) for j in range(ny + 1)},
                   key=lambda p: min(p[0] - X0, X1 - p[0], p[1] - Y0, Y1 - p[1]))   # edges first
    for x, y in cands:
        if not (X0 + EDGE_MIN <= x <= X1 - EDGE_MIN and Y0 + EDGE_MIN <= y <= Y1 - EDGE_MIN):
            continue
        if any(a <= x <= c and b <= y <= d for a, b, c, d in no_go):
            continue
        edge = min(x - X0, X1 - x, y - Y0, Y1 - y) <= EDGE_BAND
        need = EDGE_SPACING if edge else SPACING
        if any((x - vx) ** 2 + (y - vy) ** 2 < need ** 2 for vx, vy in gnd_vias):
            continue
        pos = pcbnew.VECTOR2I_MM(x, y)
        if any((pos - hp).EuclideanNorm() < mm(VIA_DRILL / 2 + pcbnew.ToMM(hd) / 2 + HOLE_GAP) for hp, hd in hole_list):
            continue
        circle = pcbnew.SHAPE_CIRCLE(pos, mm(VIA_D / 2))
        if any(s.Collide(circle, mm(CLEARANCE)) for layer in others for s in others[layer]):
            continue
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pos)
        via.SetWidth(pcbnew.F_Cu, mm(VIA_D))
        via.SetDrill(mm(VIA_DRILL))
        via.SetNet(gnd)
        via.SetLocked(True)
        board.Add(via)
        gnd_vias.append((x, y))
        hole_list.append((pos, mm(VIA_DRILL)))
        added += 1
    pcbnew.SaveBoard(path, board)
    print(f"added {added} ground stitching vias")


def island_vias(path):
    """Positions (x, y) in mm of GND vias that DRC lists as unconnected."""
    report = pathlib.Path(path).with_suffix(".drc.json")
    subprocess.run([KICAD_CLI, "pcb", "drc", "--format", "json", "--severity-error", "--refill-zones",
                    "-o", str(report), str(path)], capture_output=True, check=True)
    out = set()
    for u in json.loads(report.read_text(encoding="utf-8"))["unconnected_items"]:
        for it in u["items"]:
            if it["description"].startswith("Via [/GND]"):
                out.add((round(it["pos"]["x"], 3), round(it["pos"]["y"], 3)))
    return out


def remove_vias(path, spots):
    board = pcbnew.LoadBoard(path)
    doomed = [v for v in board.GetTracks() if v.GetClass() == "PCB_VIA" and v.GetNetname() == "/GND"
              and (round(pcbnew.ToMM(v.GetPosition().x), 3), round(pcbnew.ToMM(v.GetPosition().y), 3)) in spots]
    for v in doomed:                      # one pass: removing while iterating the board's list crashes pcbnew
        board.Remove(v)
    pcbnew.SaveBoard(path, board)
    return len(doomed)


if __name__ == "__main__":
    if sys.argv[1] == "--remove":
        spots = {tuple(float(c) for c in xy.split(",")) for xy in sys.argv[3:]}
        print(f"removed {remove_vias(sys.argv[2], spots)} stitching vias on cut-off pour")
    else:
        main(sys.argv[1])
        for _ in range(3):
            bad = island_vias(sys.argv[1])
            if not bad:
                break
            subprocess.run([sys.executable, __file__, "--remove", sys.argv[1], *(f"{x},{y}" for x, y in bad)],
                           check=True)
