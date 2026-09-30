"""Finish the connections Freerouting leaves open: a grid maze router (A*, F.Cu + B.Cu, vias) with rip-up.

    "/c/Program Files/KiCad/10.0/bin/python.exe" tools/pcb_maze.py [--lock] [--no-ripup] FluxDrive.kicad_pcb [NET ...]

With net names, only the open connections of those nets are routed. --lock locks the new tracks, so a
later Freerouting run keeps them. --no-ripup treats autorouted tracks of other nets as fixed.
Adapted from the Nano-Tek tool (2623d2f): the two outer layers (In1/In2 are planes), FluxDrive's 0.2/0.2 mm rules
and netclasses.

Takes the unconnected items from kicad-cli DRC (JSON) and routes each pair over a 0.05 mm grid that
keeps the board rules: 0.2 mm clearance to other nets, 0.3 mm to the edge, 0.5 mm between drill
holes, no copper in rule areas (the antenna keep-out).

Locked copper (the fan-out, pinned routes), pads and holes are hard obstacles. Autorouted (unlocked)
tracks of other nets may be crossed at a cost; such a net is then ripped up and routed again in the
next round, and every rip-up makes that net dearer (negotiated congestion). New tracks stay
unlocked, like Freerouting's. Zones are ignored: refill them afterwards.
"""
import collections
import heapq
import json
import math
import pathlib
import subprocess
import sys
from array import array

import numpy as np
from PIL import Image, ImageDraw

import pcbnew

KICAD_CLI = r"C:/Program Files/KiCad/10.0/bin/kicad-cli.exe"
G = 0.05                  # mm per grid cell: fine enough for one track between 2.54 mm header pins
CLEARANCE = 0.2           # both netclasses: 0.2 mm apart (spec 8)
MARGIN = 0.04             # grid error: rasterising, and string-pulled segments sampled between cell centres
EDGE = 0.3
HOLE_GAP = 0.5
VIA_D, VIA_DRILL = 0.6, 0.3
VIA_COST = 40.0           # in cells: a via costs as much as 2 mm of track
WINDOWS = (5.0, 15.0, 100.0)   # mm searched around the two ends; a wider window only when the narrow one fails
MAX_EXPAND = 8_000_000    # give up on a connection after this many grid cells (a whole board is 3.7 million)
# Costs of running through autorouted copper of another net (which is then ripped up), per grid cell:
# crossing a 0.2 mm track takes about 16 cells, so 6 per cell is about 4 mm of detour.
SOFT = 6.0
SOFT_POWER = 18.0         # the 0.3 mm power tracks
HISTORY = 8.0             # extra for every earlier rip-up of that net, so two nets do not keep swapping
SOFT_STUB = 12            # the same, counted in cells, for an exact stub out of a pad
MAX_ROUNDS = 80            # each round is a fresh process with at most one rip-up
LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)
LAYER_COST = {}                                                  # per cell, times the normal cost
POWER = {"/+5V_IN", "/+5V_A", "/V5SYS", "/VBUS", "/+3V3", "/GND", "/BUCK_SW"}   # the "Power" netclass: 0.3 mm
STEPS = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
         (1, 1, math.sqrt(2)), (1, -1, math.sqrt(2)), (-1, 1, math.sqrt(2)), (-1, -1, math.sqrt(2))]


def mm(v):
    return pcbnew.FromMM(v)


class Grid:
    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0 = x0, y0
        self.W = int(math.ceil((x1 - x0) / G)) + 1
        self.H = int(math.ceil((y1 - y0) / G)) + 1

    def px(self, x, y):
        return (x - self.x0) / G, (y - self.y0) / G

    def at(self, i, j):
        return self.x0 + i * G, self.y0 + j * G

    def box(self):
        return pcbnew.BOX2I(pcbnew.VECTOR2I(mm(self.x0), mm(self.y0)), pcbnew.VECTOR2L(mm(self.W * G), mm(self.H * G)))

    def canvas(self):
        return Image.new("1", (self.W, self.H), 0)


def draw_polyset(draw, grid, ps, di=0, dj=0):
    for k in range(ps.OutlineCount()):
        ol = ps.Outline(k)
        pts = []
        for n in range(ol.PointCount()):
            x, y = grid.px(pcbnew.ToMM(ol.CPoint(n).x), pcbnew.ToMM(ol.CPoint(n).y))
            pts.append((x - di, y - dj))
        if len(pts) >= 3:
            draw.polygon(pts, fill=1)


def shape(item, layer, inflate):
    ps = pcbnew.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(ps, layer, mm(inflate), mm(0.005), pcbnew.ERROR_OUTSIDE)
    return ps


def own_clearance(item, layer):
    """The board clearance, or more where a pad asks for it (the fiducials keep 1 mm free around them)."""
    if item.GetClass() == "PAD":
        return max(CLEARANCE, pcbnew.ToMM(item.GetOwnClearance(layer)))
    return CLEARANCE


def small_mask(grid, ps):
    """Rasterise a polygon set into a mask the size of its bounding box: (i0, j0, mask) or None."""
    bb = ps.BBox()
    i0, j0 = grid.px(pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()))
    i1, j1 = grid.px(pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))
    i0, j0 = max(int(math.floor(i0)) - 1, 0), max(int(math.floor(j0)) - 1, 0)
    i1, j1 = min(int(math.ceil(i1)) + 1, grid.W - 1), min(int(math.ceil(j1)) + 1, grid.H - 1)
    if i1 < i0 or j1 < j0:
        return None
    img = Image.new("1", (i1 - i0 + 1, j1 - j0 + 1), 0)
    draw_polyset(ImageDraw.Draw(img), grid, ps, i0, j0)
    return i0, j0, np.array(img, dtype=bool)


def dilate(mask, r_mm):
    r = int(math.ceil(r_mm / G))
    out = mask.copy()
    H, W = mask.shape
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy > r * r or (dx == 0 and dy == 0):
                continue
            ys, yd = (slice(0, H - dy), slice(dy, H)) if dy >= 0 else (slice(-dy, H), slice(0, H + dy))
            xs, xd = (slice(0, W - dx), slice(dx, W)) if dx >= 0 else (slice(-dx, W), slice(0, W + dx))
            out[yd, xd] |= mask[ys, xs]
    return out


def copper_items(board):
    items = list(board.GetTracks())
    for fp in board.GetFootprints():
        items += list(fp.Pads())
        items += [g for g in fp.GraphicalItems() if g.IsOnCopperLayer()]
    items += [d for d in board.GetDrawings() if d.IsOnCopperLayer()]
    return items


def soft(it):
    """Autorouted copper: may be ripped up. Locked tracks (fan-out, pinned routes) never are."""
    return it.GetClass() in ("PCB_TRACK", "PCB_VIA", "PCB_ARC") and not it.IsLocked()


def is_other(it, netcode):
    return it.GetClass() in ("PCB_SHAPE", "PCB_TEXT") or it.GetNetCode() != netcode


class Obstacles:
    """hard_t / hard_v: cells a track centre (per layer) or a via centre may never use.
    pen_t / pen_v: extra cost of a cell covered by autorouted copper of other nets; owners says whose."""

    def __init__(self, board, grid, netcode, w, history):
        win = grid.box()
        win.Inflate(mm(1.0))
        t_img = [grid.canvas() for _ in LAYERS]
        v_img = grid.canvas()
        td = [ImageDraw.Draw(im) for im in t_img]
        vd = ImageDraw.Draw(v_img)
        self.pen_t = [np.zeros((grid.H, grid.W), np.float32) for _ in LAYERS]
        self.pen_v = np.zeros((grid.H, grid.W), np.float32)
        self.owners = []                                   # (netcode, "t0" / "t1" / "v", i0, j0, mask)
        for it in copper_items(board):
            if not win.Intersects(it.GetBoundingBox()):
                continue
            nc = it.GetNetCode()
            other = is_other(it, netcode)
            cost = (SOFT_POWER if it.GetNetname() in POWER else SOFT) + HISTORY * history[nc]
            for li, layer in enumerate(LAYERS):
                if not it.IsOnLayer(layer):
                    continue
                if other and soft(it) and RIPUP:
                    for kind, inflate, pen in ((f"t{li}", CLEARANCE + w / 2 + MARGIN, self.pen_t[li]),
                                               ("v", CLEARANCE + VIA_D / 2 + MARGIN, self.pen_v)):
                        m = small_mask(grid, shape(it, layer, inflate))
                        if m:
                            i0, j0, mask = m
                            pen[j0:j0 + mask.shape[0], i0:i0 + mask.shape[1]][mask] += cost
                            self.owners.append((nc, kind, i0, j0, mask))
                elif other:
                    c = own_clearance(it, layer)
                    draw_polyset(td[li], grid, shape(it, layer, c + w / 2 + MARGIN))
                    draw_polyset(vd, grid, shape(it, layer, c + VIA_D / 2 + MARGIN))
                elif it.GetClass() == "PAD":                  # no via in a pad of its own net either
                    draw_polyset(vd, grid, shape(it, layer, VIA_D / 2 + MARGIN))
        # hole to hole; the copper mask of another net's autorouted via already covers its hole
        for v in board.GetTracks():
            if v.GetClass() == "PCB_VIA" and not (soft(v) and v.GetNetCode() != netcode):
                self._hole(vd, grid, v.GetPosition(), pcbnew.ToMM(v.GetDrillValue()))
        for fp in board.GetFootprints():
            for p in fp.Pads():
                if p.HasHole():
                    self._hole(vd, grid, p.GetPosition(), pcbnew.ToMM(max(p.GetDrillSize().x, p.GetDrillSize().y)))
        t = [np.array(im, dtype=bool) for im in t_img]
        v = np.array(v_img, dtype=bool)
        inside_img = grid.canvas()
        outline = pcbnew.SHAPE_POLY_SET()
        board.GetBoardPolygonOutlines(outline, True)
        draw_polyset(ImageDraw.Draw(inside_img), grid, outline)
        outside = ~np.array(inside_img, dtype=bool)
        t = [m | dilate(outside, EDGE + w / 2 + MARGIN) for m in t]
        v |= dilate(outside, EDGE + VIA_D / 2 + MARGIN)
        zones = list(board.Zones()) + [z for fp in board.GetFootprints() for z in fp.Zones()]
        for z in zones:                                       # rule areas: the antenna keep-out of the module
            if not z.GetIsRuleArea():
                continue
            img = grid.canvas()
            draw_polyset(ImageDraw.Draw(img), grid, z.Outline())
            area = np.array(img, dtype=bool)
            for li, layer in enumerate(LAYERS):
                if z.GetDoNotAllowTracks() and z.IsOnLayer(layer):
                    t[li] |= dilate(area, w / 2 + MARGIN)
            if z.GetDoNotAllowVias():
                v |= dilate(area, VIA_D / 2 + MARGIN)
        self.hard_t, self.hard_v = t, v

    @staticmethod
    def _hole(vd, grid, pos, drill):
        cx, cy = grid.px(pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y))
        r = (drill / 2 + VIA_DRILL / 2 + HOLE_GAP + MARGIN) / G
        vd.ellipse((cx - r, cy - r, cx + r, cy + r), fill=1)

    def nets_at(self, kind, i, j):
        return {nc for nc, k, i0, j0, m in self.owners
                if k == kind and 0 <= j - j0 < m.shape[0] and 0 <= i - i0 < m.shape[1] and m[j - j0, i - i0]}


def escapes(board, grid, item, layer, w, free):
    """Short straight stubs out of a pad, checked exactly against the other nets' copper (not on the grid:
    a fine-pitch pin is closer to its neighbours than the grid margin allows).
    Returns {cell: (stub, autorouted nets it runs through)}."""
    c = item.GetPosition()
    near = pcbnew.BOX2I(c - pcbnew.VECTOR2I(mm(3), mm(3)), pcbnew.VECTOR2L(mm(6), mm(6)))
    hard, softs = [], []
    for it in copper_items(board):
        if it.IsOnLayer(layer) and near.Intersects(it.GetBoundingBox()) and is_other(it, item.GetNetCode()):
            (softs if soft(it) and RIPUP else hard).append((it.GetNetCode(), it.GetEffectiveShape(layer)))
    out = {}
    for k in range(16):
        a = k * math.pi / 8
        for step in range(1, 41):                              # up to 2 mm out
            d = 0.05 * step
            q = pcbnew.VECTOR2I(int(c.x + mm(d) * math.cos(a)), int(c.y + mm(d) * math.sin(a)))
            if any(s.Collide(pcbnew.SHAPE_SEGMENT(c, q, mm(w)), mm(CLEARANCE + 0.01)) for _, s in hard):
                break                                          # this direction is closed
            i, j = grid.px(pcbnew.ToMM(q.x), pcbnew.ToMM(q.y))
            i, j = int(round(i)), int(round(j))
            if 0 <= i < grid.W and 0 <= j < grid.H and free[j, i]:
                end = pcbnew.VECTOR2I_MM(*grid.at(i, j))
                seg = pcbnew.SHAPE_SEGMENT(c, end, mm(w))
                if not any(s.Collide(seg, mm(CLEARANCE + 0.01)) for _, s in hard):
                    crossed = {nc for nc, s in softs if s.Collide(seg, mm(CLEARANCE + 0.01))}
                    out.setdefault((i, j), ([c, end], crossed))
                    break
    return out


def end_cells(board, grid, item, w, hard_t):
    """Per layer: the cells a route may start or end on, and for pads the exact stub to the pad centre."""
    masks, stubs = [], [{} for _ in LAYERS]
    for li, layer in enumerate(LAYERS):
        img = grid.canvas()
        if item.IsOnLayer(layer) and item.GetClass() == "PCB_TRACK":
            a = grid.px(pcbnew.ToMM(item.GetStart().x), pcbnew.ToMM(item.GetStart().y))
            b = grid.px(pcbnew.ToMM(item.GetEnd().x), pcbnew.ToMM(item.GetEnd().y))
            ImageDraw.Draw(img).line([a, b], fill=1, width=1)      # on the track itself
        m = np.array(img, dtype=bool)
        if item.IsOnLayer(layer) and item.GetClass() != "PCB_TRACK":
            stubs[li] = escapes(board, grid, item, layer, w, ~hard_t[li])
            for i, j in stubs[li]:
                m[j, i] = True
        masks.append(m)
    return masks, stubs


def astar(grid, free, via_ok, pen_t, pen_v, starts, goals):
    """starts: {(layer, i, j): initial cost}; goals: per layer a bool mask. Returns [(layer, i, j), ...] or None.
    Every state is expanded once (closed set); the heap holds plain ints (cost << 23 | state) to stay small."""
    H, W = grid.H, grid.W
    HW = H * W
    L = len(LAYERS)
    assert L * HW < 1 << 23, "window too large for the heap key"
    MASK = (1 << 23) - 1
    ft = np.concatenate([m.ravel() for m in free]).astype(np.uint8).tobytes()
    fv = via_ok.ravel().astype(np.uint8).tobytes()
    gl = np.concatenate([m.ravel() for m in goals]).astype(np.uint8).tobytes()
    pt = array("f")
    pt.frombytes(np.concatenate([m.ravel() for m in pen_t]).astype(np.float32).tobytes())
    pv = array("f")
    pv.frombytes(pen_v.ravel().astype(np.float32).tobytes())
    factor = [LAYER_COST.get(layer, 1.0) for layer in LAYERS]
    gy, gx = np.nonzero(np.logical_or.reduce(goals))
    if not len(gx) or not starts:
        return None
    bx0, bx1, by0, by1 = int(gx.min()), int(gx.max()), int(gy.min()), int(gy.max())
    r2 = math.sqrt(2) - 1

    def h(x, y):
        dx = max(bx0 - x, 0, x - bx1)
        dy = max(by0 - y, 0, y - by1)
        return 1.3 * (max(dx, dy) + r2 * min(dx, dy))

    g = array("f", [math.inf]) * (L * HW)
    parent = array("i", [-1]) * (L * HW)
    closed = bytearray(L * HW)
    heap, expanded = [], 0
    push, pop = heapq.heappush, heapq.heappop
    for (li, x, y), c0 in starts.items():
        idx = li * HW + y * W + x
        if c0 < g[idx]:
            g[idx] = c0
            push(heap, (int((c0 + h(x, y)) * 16) << 23) | idx)
    while heap:
        idx = pop(heap) & MASK
        if closed[idx]:
            continue
        closed[idx] = 1
        expanded += 1
        if expanded > MAX_EXPAND:
            return None
        if gl[idx]:
            path = []
            while idx != -1:
                path.append(idx)
                idx = parent[idx]
            return [(i // HW, (i % HW) % W, (i % HW) // W) for i in reversed(path)]
        gc = g[idx]
        li, rest = divmod(idx, HW)
        y, x = divmod(rest, W)
        f = factor[li]
        for dx, dy, c in STEPS:
            nx, ny = x + dx, y + dy
            if 0 <= nx < W and 0 <= ny < H:
                n = li * HW + ny * W + nx
                if ft[n] and not closed[n]:
                    ng = gc + c * f + pt[n]
                    if ng < g[n]:
                        g[n] = ng
                        parent[n] = idx
                        push(heap, (int((ng + h(nx, ny)) * 16) << 23) | n)
        if fv[rest]:
            for lj in range(L):
                n = lj * HW + rest
                if lj != li and ft[n] and not closed[n]:
                    ng = gc + VIA_COST + pv[rest] + pt[n]
                    if ng < g[n]:
                        g[n] = ng
                        parent[n] = idx
                        push(heap, (int((ng + h(x, y)) * 16) << 23) | n)
    return None


def clear_line(ok, a, b):
    (x0, y0), (x1, y1) = a, b
    n = int(max(abs(x1 - x0), abs(y1 - y0)) * 4) + 1
    for k in range(n + 1):
        t = k / n
        if not ok[int(round(y0 + (y1 - y0) * t)), int(round(x0 + (x1 - x0) * t))]:
            return False
    return True


def pull(ok, cells):
    """String pulling: keep only the corners, a straight segment wherever it stays on allowed cells."""
    out, i = [cells[0]], 0
    while i < len(cells) - 1:
        j = len(cells) - 1
        while j > i + 1 and not clear_line(ok, cells[i], cells[j]):
            j -= 1
        out.append(cells[j])
        i = j
    return out


LOCK = False                  # --lock: new tracks and vias are locked
RIPUP = True                  # --no-ripup: never cross autorouted tracks of other nets


def add_track(board, net, w, layer, a, b):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(a)
    t.SetEnd(b)
    t.SetWidth(mm(w))
    t.SetLayer(layer)
    t.SetNet(net)
    t.SetLocked(LOCK)
    board.Add(t)


def add_path(board, grid, net, w, path, ok, stub_a, stub_b):
    first, last = path[0], path[-1]
    if (first[1], first[2]) in stub_a[first[0]]:               # pad centre -> first cell
        p, q = stub_a[first[0]][(first[1], first[2])][0]
        add_track(board, net, w, LAYERS[first[0]], p, q)
    if (last[1], last[2]) in stub_b[last[0]]:                  # last cell -> pad centre
        p, q = stub_b[last[0]][(last[1], last[2])][0]
        add_track(board, net, w, LAYERS[last[0]], q, p)
    runs, cur = [], [path[0]]
    for p in path[1:]:
        if p[0] != cur[-1][0]:
            runs.append(cur)
            cur = [p]
        else:
            cur.append(p)
    runs.append(cur)
    for k, run in enumerate(runs):
        li = run[0][0]
        pts = pull(ok[li], [(x, y) for _, x, y in run])
        for a, b in zip(pts, pts[1:]):
            add_track(board, net, w, LAYERS[li], pcbnew.VECTOR2I_MM(*grid.at(*a)), pcbnew.VECTOR2I_MM(*grid.at(*b)))
        if k < len(runs) - 1:
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I_MM(*grid.at(run[-1][1], run[-1][2])))
            v.SetWidth(pcbnew.F_Cu, mm(VIA_D))
            v.SetDrill(mm(VIA_DRILL))
            v.SetNet(net)
            v.SetLocked(LOCK)
            board.Add(v)
    return len(runs) - 1


def unconnected(pcb):
    report = pathlib.Path(pcb).with_suffix(".drc.json")
    # --refill-zones: with stale zone fills every new track "violates" the old pour
    subprocess.run([KICAD_CLI, "pcb", "drc", "--format", "json", "--severity-error", "--refill-zones",
                    "-o", str(report), str(pcb)], capture_output=True, check=True)
    data = json.loads(report.read_text(encoding="utf-8"))
    return [[i["uuid"] for i in u["items"]] for u in data["unconnected_items"]]


def index(board):
    by_uuid = {t.m_Uuid.AsString(): t for t in board.GetTracks()}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            by_uuid[p.m_Uuid.AsString()] = p
    return by_uuid


def route_one(board, ia, ib, history):
    """Returns (path, nets to rip up, grid, allowed masks, stubs a, stubs b, width) or None."""
    for window in WINDOWS:
        res = route_in_window(board, ia, ib, history, window)
        if res:
            return res
    return None


def route_in_window(board, ia, ib, history, window):
    net = ia.GetNet()
    w = 0.3 if net.GetNetname() in POWER else 0.2
    bb = ia.GetBoundingBox()
    bb.Merge(ib.GetBoundingBox())
    e = board.GetBoardEdgesBoundingBox()
    e.Inflate(mm(1.0))                  # a margin of cells outside the board, so the edge rule has something to grow from
    grid = Grid(max(pcbnew.ToMM(bb.GetLeft()) - window, pcbnew.ToMM(e.GetLeft())),
                max(pcbnew.ToMM(bb.GetTop()) - window, pcbnew.ToMM(e.GetTop())),
                min(pcbnew.ToMM(bb.GetRight()) + window, pcbnew.ToMM(e.GetRight())),
                min(pcbnew.ToMM(bb.GetBottom()) + window, pcbnew.ToMM(e.GetBottom())))
    ob = Obstacles(board, grid, net.GetNetCode(), w, history)
    (sa, stub_a), (sb, stub_b) = end_cells(board, grid, ia, w, ob.hard_t), end_cells(board, grid, ib, w, ob.hard_t)
    ok = [~ob.hard_t[i] | sa[i] | sb[i] for i in range(len(LAYERS))]
    starts = {}
    for li in range(len(LAYERS)):
        for j, i in zip(*np.nonzero(sa[li])):
            crossed = stub_a[li].get((i, j), (None, set()))[1]
            starts[(li, int(i), int(j))] = sum(SOFT_STUB * (SOFT + HISTORY * history[nc]) for nc in crossed)
    path = astar(grid, ok, ~ob.hard_v, ob.pen_t, ob.pen_v, starts, sb)
    if path is None:
        return None
    rip = set()
    for n, (li, i, j) in enumerate(path):
        rip |= ob.nets_at(f"t{li}", i, j)
        if n and path[n - 1][0] != li:
            rip |= ob.nets_at("v", i, j)
    for stubs, cell in ((stub_a, path[0]), (stub_b, path[-1])):
        if (cell[1], cell[2]) in stubs[cell[0]]:
            rip |= stubs[cell[0]][(cell[1], cell[2])][1]
    rip.discard(net.GetNetCode())
    # string pulling may only straighten over cells that are free of other autorouted copper, or the path's own
    strict = [ok[i] & (ob.pen_t[i] == 0) for i in range(len(LAYERS))]
    for li, i, j in path:
        strict[li][j, i] = True
    return path, rip, grid, strict, stub_a, stub_b, w


def one_round(pcb, only=()):
    """Route what can be routed; at most one connection that needs a rip-up, because removing tracks leaves
    pcbnew's Python bindings unusable for the rest of the process. Exit code: 0 all connected, 1 progress,
    2 stuck. The rip-up history lives next to the board, in <board>.maze.json."""
    hist_file = pathlib.Path(pcb).with_suffix(".maze.json")
    history = collections.Counter()
    if hist_file.exists():
        history.update({int(k): v for k, v in json.loads(hist_file.read_text()).items()})
    pairs = unconnected(pcb)
    if not pairs:
        print("everything connected")
        return 0
    board = pcbnew.LoadBoard(pcb)
    items = index(board)
    jobs, zones = [], 0
    for a, b in pairs:
        if a in items and b in items:
            if not only or items[a].GetNetname() in only:
                jobs.append(((items[a].GetPosition() - items[b].GetPosition()).EuclideanNorm(), a, b))
        else:
            zones += 1                                      # a zone island: not something to route
    if zones:
        print(f"({zones} open connections to zone islands left alone) ", end="")
    if not jobs:
        print("nothing to route")
        return 0
    done, failed, deferred = [], [], 0
    ripped = False
    for _, a, b in sorted(jobs):
        ia, ib = items[a], items[b]
        name = ia.GetNetname()
        res = route_one(board, ia, ib, history)
        if res is None:
            failed.append(name)
            continue
        path, rip, grid, ok, stub_a, stub_b, w = res
        if rip and ripped:
            deferred += 1                                   # next round, in a fresh process
            continue
        if rip:
            names = sorted(board.FindNet(nc).GetNetname() for nc in rip)
            for t in [t for t in board.GetTracks() if t.GetNetCode() in rip and soft(t)]:
                board.Remove(t)
            for nc in rip:
                history[nc] += 1
            ripped = True
            add_path(board, grid, ia.GetNet(), w, path, ok, stub_a, stub_b)
            done.append(f"{name} (ripped up {', '.join(names)})")
            break                                           # the item handles may be stale now
        add_path(board, grid, ia.GetNet(), w, path, ok, stub_a, stub_b)
        done.append(name)
    pcbnew.SaveBoard(pcb, board)
    hist_file.write_text(json.dumps(history))
    print(f"{len(pairs)} open; routed {done or 'none'}; no path {failed or 'none'}"
          + (f"; {deferred} wait for a rip-up" if deferred else ""), flush=True)
    return 1 if done else 2


def main(pcb, only=()):
    pathlib.Path(pcb).with_suffix(".maze.json").unlink(missing_ok=True)
    for rnd in range(1, MAX_ROUNDS + 1):
        print(f"round {rnd}: ", end="", flush=True)
        flags = [f for f, on in (("--lock", LOCK), ("--no-ripup", not RIPUP)) if on]
        code = subprocess.run([sys.executable, "-u", __file__, *flags, "--round", pcb, *only]).returncode
        if code == 0:
            return
        if code != 1:
            break
    print("open connections:", len(unconnected(pcb)))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    LOCK = "--lock" in sys.argv
    RIPUP = "--no-ripup" not in sys.argv
    if "--round" in sys.argv:
        sys.exit(one_round(args[0], args[1:]))
    main(args[0], args[1:])
