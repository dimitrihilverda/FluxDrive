"""Hand-made routes that go on the board before Freerouting, locked.

    "/c/Program Files/KiCad/10.0/bin/python.exe" tools/pcb_prefan.py FluxDrive.kicad_pcb

USB-C VBUS bridge: the receptacle has VBUS on two pads (A4B9 and B4A9), one above and one below the CC,
D+ and D- pads. Joined on F.Cu, VBUS has to loop around the CC pad of that side and shuts it in (Freerouting
and the maze router both left CC2 open). So each VBUS pad gets a short stub east to a via, and the two
vias are joined on B.Cu under the connector's pad row. Run after placement, before the fan-out.
Only adds: a re-run finds the bridge and places nothing.
"""
import sys

import pcbnew

STUB = 0.9              # mm, pad centre to via, east (J3 opens to the west edge); the via touches its own pad
WIDTH = 0.3             # the Power netclass
VIA_D, VIA_DRILL = 0.6, 0.3


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


def main(path):
    board = pcbnew.LoadBoard(path)
    j3 = next(fp for fp in board.GetFootprints() if fp.GetReference() == "J3")
    pads = {p.GetNumber(): p for p in j3.Pads()}
    net = pads["A4B9"].GetNet()
    if any(t.GetClass() == "PCB_VIA" and t.GetNetCode() == net.GetNetCode() for t in board.GetTracks()):
        print("VBUS bridge already there")
        return
    ends = []
    for name in ("A4B9", "B4A9"):
        p = pads[name].GetPosition()
        v = pcbnew.VECTOR2I(p.x + mm(STUB), p.y)
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(v)
        via.SetWidth(pcbnew.F_Cu, mm(VIA_D))
        via.SetDrill(mm(VIA_DRILL))
        via.SetNet(net)
        via.SetLocked(True)
        board.Add(via)
        track(board, net, p, v, pcbnew.F_Cu)
        ends.append(v)
    track(board, net, ends[0], ends[1], pcbnew.B_Cu)
    pcbnew.SaveBoard(path, board)
    print("VBUS bridge: 2 vias, joined on B.Cu")


if __name__ == "__main__":
    main(sys.argv[1])
