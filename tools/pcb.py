"""Read board outline and footprint positions from a .kicad_pcb (no KiCad needed)."""
from tools.netlist import _child, _children, _parse_sexpr


def load(path):
    with open(path, encoding="utf-8") as f:
        return _parse_sexpr(f.read())


def _layer(node):
    c = _child(node, "layer")
    return c[1] if c is not None else None


def _points(node):
    for key in ("start", "end", "mid", "center"):
        c = _child(node, key)
        if c is not None:
            yield float(c[1]), float(c[2])
    pts = _child(node, "pts")
    if pts is not None:
        for xy in _children(pts, "xy"):
            yield float(xy[1]), float(xy[2])


def board_extents(root):
    """(xmin, ymin, xmax, ymax) of everything on Edge.Cuts, in mm."""
    xs, ys = [], []
    for kind in ("gr_line", "gr_rect", "gr_arc", "gr_poly"):
        for node in _children(root, kind):
            if _layer(node) == "Edge.Cuts":
                for x, y in _points(node):
                    xs.append(x)
                    ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def footprints(root):
    """{reference: (x, y, rotation, layer)} for every footprint."""
    out = {}
    for fp in _children(root, "footprint"):
        at = _child(fp, "at")
        ref = None
        for prop in _children(fp, "property"):
            if len(prop) > 2 and prop[1] == "Reference":
                ref = prop[2]
        if ref is None:                                   # KiCad 6/7 style
            for t in _children(fp, "fp_text"):
                if len(t) > 2 and t[1] == "reference":
                    ref = t[2]
        rot = float(at[3]) if len(at) > 3 else 0.0
        out[ref] = (float(at[1]), float(at[2]), rot, _layer(fp))
    return out
