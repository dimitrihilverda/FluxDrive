"""Fan out the SMD ground pads to the B.Cu ground plane with a short track and a via.

    "/c/Program Files/KiCad/10.0/bin/python.exe" tools/pcb_fanout.py FluxDrive.kicad_pcb

Adapted from the Nano-Tek tool (2623d2f): 2 layers, one plane net (GND on B.Cu), the board of pcb_place.

Run it before Freerouting (which does not fan out to planes itself). Only pads that have no
track attached yet. Pass 1 gives each pad its own via: it tries positions around the pad
(outward first) and takes the first one that keeps clearance to every other copper item on
F.Cu and B.Cu, keeps holes 0.5 mm apart and stays away from the board edge. Pass 2 joins the
pads that had no room (fine-pitch corner pins) to a fanned-out pad or via of the same net with
a straight or L-shaped track. New tracks and vias are locked, so Freerouting keeps them.
"""
import math
import sys

import pcbnew

NETS = ("/GND",)
VIA_D, VIA_DRILL = 0.6, 0.3
TRACK_W = 0.3
CLEARANCE = 0.22          # via to other copper: a bit more than the 0.2 board rule
SEG_CLEARANCE = 0.21      # stubs: the board rule plus a hair
HOLE_GAP = 0.52           # hole edge to hole edge, board rule 0.5 (also between vias of the same net)
EDGE = 0.6                # copper to board edge
X0, X1, Y0, Y1 = 100.0, 160.0, 100.0, 148.0


def mm(v):
    return pcbnew.FromMM(v)


def has_track(board, pad):
    for t in board.GetTracks():
        if t.GetNetCode() == pad.GetNetCode() and t.GetClass() == "PCB_TRACK":
            if pad.HitTest(t.GetStart()) or pad.HitTest(t.GetEnd()):
                return True
    return False


def obstacles(board, layer, netcode):
    out = []
    for t in board.GetTracks():
        if t.GetNetCode() != netcode and t.IsOnLayer(layer):
            out.append(t.GetEffectiveShape(layer))
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() != netcode and p.IsOnLayer(layer):
                out.append(p.GetEffectiveShape(layer))
    return out


def holes(board):
    hs = [(v.GetPosition(), v.GetDrillValue()) for v in board.GetTracks() if v.GetClass() == "PCB_VIA"]
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.HasHole():
                hs.append((p.GetPosition(), max(p.GetDrillSize().x, p.GetDrillSize().y)))
    return hs


def free(pos, seg_from, width, cache, hole_list):
    x, y = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
    if not (X0 + EDGE + VIA_D / 2 < x < X1 - EDGE - VIA_D / 2 and Y0 + EDGE + VIA_D / 2 < y < Y1 - EDGE - VIA_D / 2):
        return False
    for hp, hd in hole_list:
        if (pos - hp).EuclideanNorm() < mm(VIA_DRILL / 2 + pcbnew.ToMM(hd) / 2 + HOLE_GAP):
            return False
    circle = pcbnew.SHAPE_CIRCLE(pos, mm(VIA_D / 2))
    for s in cache[pcbnew.F_Cu] + cache[pcbnew.B_Cu]:
        if s.Collide(circle, mm(CLEARANCE)):
            return False
    return clear_path([seg_from, pos], width, cache)


def clear_path(points, width, cache):
    """True if an F.Cu track of this width along the points keeps SEG_CLEARANCE to other nets and the edge."""
    for a, b in zip(points, points[1:]):
        for q in (a, b):
            x, y = pcbnew.ToMM(q.x), pcbnew.ToMM(q.y)
            if not (X0 + EDGE < x < X1 - EDGE and Y0 + EDGE < y < Y1 - EDGE):
                return False
        seg = pcbnew.SHAPE_SEGMENT(a, b, mm(width))
        if any(s.Collide(seg, mm(SEG_CLEARANCE)) for s in cache[pcbnew.F_Cu]):
            return False
    return True


def stub_width(pad):
    """Never wider than the pad itself, so a stub out of a fine-pitch pin keeps the pin-to-pin gap."""
    s = pad.GetSize(pcbnew.F_Cu)
    return min(TRACK_W, pcbnew.ToMM(min(s.x, s.y)))


def add_track(board, net, points, width):
    for a, b in zip(points, points[1:]):
        tr = pcbnew.PCB_TRACK(board)
        tr.SetStart(a)
        tr.SetEnd(b)
        tr.SetWidth(mm(width))
        tr.SetLayer(pcbnew.F_Cu)
        tr.SetNet(net)
        tr.SetLocked(True)
        board.Add(tr)


def same_net_targets(board, pad, with_pads):
    """Points a stub may end on: vias and F.Cu track ends of the pad's net, and (second pass) SMD pads of
    that net that are already fanned out, e.g. the +3V3 pad of the decoupling cap next to a fine-pitch pin."""
    p, out = pad.GetPosition(), []
    for t in board.GetTracks():
        if t.GetNetCode() != pad.GetNetCode():
            continue
        if t.GetClass() == "PCB_VIA":
            out.append(t.GetPosition())
        elif t.IsOnLayer(pcbnew.F_Cu):
            out += [t.GetStart(), t.GetEnd()]
    if with_pads:
        for fp in board.GetFootprints():
            for q in fp.Pads():
                same = q.GetNetCode() == pad.GetNetCode() and q is not pad
                if same and q.IsOnLayer(pcbnew.F_Cu) and has_track(board, q):
                    out.append(q.GetPosition())
    return sorted((q for q in out if 0 < (q - p).EuclideanNorm() < mm(4.0) and not pad.HitTest(q)),
                  key=lambda q: (q - p).EuclideanNorm())


def candidate_paths(p, q, axis):
    """Straight, then L-shaped, then a short stub along the pad's outward axis followed by an L."""
    V = pcbnew.VECTOR2I
    yield [p, q]
    yield [p, V(q.x, p.y), q]
    yield [p, V(p.x, q.y), q]
    for d in (0.5, 0.8, 1.2):
        m = V(int(p.x + mm(d) * math.cos(axis)), int(p.y + mm(d) * math.sin(axis)))
        yield [p, m, q]
        yield [p, m, V(q.x, m.y), q]
        yield [p, m, V(m.x, q.y), q]


def connect_to_same_net(board, pad, cache, axis, width, with_pads):
    for q in same_net_targets(board, pad, with_pads):
        for pts in candidate_paths(pad.GetPosition(), q, axis):
            pts = [a for i, a in enumerate(pts) if i == 0 or a != pts[i - 1]]
            if clear_path(pts, width, cache):
                add_track(board, pad.GetNet(), pts, width)
                return True
    return False


def place_via(board, pad, cache, axis, width):
    p = pad.GetPosition()
    hole_list = holes(board)
    for dist in (1.0, 1.3, 1.7, 2.2, 2.8, 3.5, 4.2, 4.8):
        for k in (0, 1, -1, 2, -2, 3, -3, 4, 0.5, -0.5, 1.5, -1.5, 2.5, -2.5, 3.5, -3.5, "up", "down"):
            a = -math.pi / 2 if k == "up" else math.pi / 2 if k == "down" else axis + k * math.pi / 4
            q = pcbnew.VECTOR2I(int(p.x + mm(dist) * math.cos(a)), int(p.y + mm(dist) * math.sin(a)))
            if free(q, p, width, cache, hole_list):
                via = pcbnew.PCB_VIA(board)
                via.SetPosition(q)
                via.SetWidth(pcbnew.F_Cu, mm(VIA_D))
                via.SetDrill(mm(VIA_DRILL))
                via.SetNet(pad.GetNet())
                via.SetLocked(True)
                board.Add(via)
                add_track(board, pad.GetNet(), [p, q], width)
                return True
    return False


def plane_pads(board):
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() in NETS and not pad.HasHole() and pad.IsOnLayer(pcbnew.F_Cu):
                yield fp, pad


def outward_axis(fp, pad):
    """Outward and square to the package side: a diagonal stub would graze the neighbouring pins."""
    c, p = fp.GetPosition(), pad.GetPosition()
    dx, dy = p.x - c.x, p.y - c.y
    return (0.0 if dx >= 0 else math.pi) if abs(dx) >= abs(dy) else (math.pi / 2 if dy >= 0 else -math.pi / 2)


def main(path):
    board = pcbnew.LoadBoard(path)
    done, failed = 0, []
    # pass 1: a via of its own (or a straight stub to a nearby via of the same net)
    for fp, pad in plane_pads(board):
        if has_track(board, pad):
            continue
        nc, axis, w = pad.GetNetCode(), outward_axis(fp, pad), stub_width(pad)
        cache = {pcbnew.F_Cu: obstacles(board, pcbnew.F_Cu, nc), pcbnew.B_Cu: obstacles(board, pcbnew.B_Cu, nc)}
        if connect_to_same_net(board, pad, cache, axis, w, False) or place_via(board, pad, cache, axis, w):
            done += 1
        else:
            failed.append((fp, pad))
    # pass 2: no room for a via, so join a neighbour of the same net that has one (straight or L-shaped)
    left = []
    for fp, pad in failed:
        nc, axis, w = pad.GetNetCode(), outward_axis(fp, pad), stub_width(pad)
        cache = {pcbnew.F_Cu: obstacles(board, pcbnew.F_Cu, nc), pcbnew.B_Cu: obstacles(board, pcbnew.B_Cu, nc)}
        if connect_to_same_net(board, pad, cache, axis, w, True):
            done += 1
        else:
            left.append(f"{fp.GetReference()}.{pad.GetNumber()}")
    pcbnew.SaveBoard(path, board)
    print(f"fanned out {done} pads; no room for: {left or 'none'}")


if __name__ == "__main__":
    main(sys.argv[1])
