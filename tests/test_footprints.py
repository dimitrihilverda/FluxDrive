import pathlib

from tools.netlist import _child, _children, _parse_sexpr

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_module_ground_pad_solder_through_hole():
    """Rev B §9: a 1.0 mm plated hole at the ground pad's centre, mask open on both sides; the four inner thermal
    vias go, the other eight stay tented."""
    fp = _parse_sexpr((ROOT / "FluxDrive.pretty" / "ESP32-S3-WROOM-1.kicad_mod").read_text(encoding="utf-8"))
    pads41 = [p for p in _children(fp, "pad") if p[1] == "41"]
    ep = next(p for p in pads41 if p[2] == "smd" and float(_child(p, "size")[1]) > 3)
    cx, cy = float(_child(ep, "at")[1]), float(_child(ep, "at")[2])
    holes = [p for p in pads41 if p[2] == "thru_hole"]
    big = [p for p in holes if abs(float(_child(p, "drill")[1]) - 1.0) < 0.01]
    assert len(big) == 1
    bx, by = float(_child(big[0], "at")[1]), float(_child(big[0], "at")[2])
    assert abs(bx - cx) < 0.01 and abs(by - cy) < 0.01
    assert {"F.Mask", "B.Mask"} <= set(_child(big[0], "layers")[1:])
    small = [p for p in holes if p is not big[0]]
    assert len(small) == 8 and all("B.Mask" not in _child(p, "layers")[1:] for p in small)


def _segments(fp, layer):
    """The fp_lines of one layer as sorted (start, end) tuples, so a line reads the same either way round."""
    return {tuple(sorted(((float(_child(ln, "start")[1]), float(_child(ln, "start")[2])),
                          (float(_child(ln, "end")[1]), float(_child(ln, "end")[2])))))
            for ln in _children(fp, "fp_line") if _child(ln, "layer")[1] == layer}


def _rect(x0, y0, x1, y1):
    return {((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x0, y1), (x1, y1)), ((x0, y0), (x0, y1))}


def test_floppy_power_header_outline_and_wall():
    """Rev B O15 (TE drawing C-171825 rev Y4, plug C-171822 rev L5): the header body is 10.0 x 4.9 mm with pin 1 at
    1.25 mm from its end, the wall (the partial shroud) on the local -y side from y -2.5 to -1.6; the plug follows the
    wall, so a header soldered the other way round puts +12 V on pin 1. The wall is marked on F.SilkS and F.Fab, the
    mated plug is drawn on F.Fab, the courtyard is the body plus 0.5 mm, the pads (rev A's) are unchanged."""
    fp = _parse_sexpr((ROOT / "FluxDrive.pretty" / "171825-4.kicad_mod").read_text(encoding="utf-8"))
    body = _rect(-1.25, -2.5, 8.75, 2.4)
    wall = ((-1.25, -1.6), (8.75, -1.6))
    for layer in ("F.SilkS", "F.Fab"):
        segs = _segments(fp, layer)
        assert body <= segs, layer
        assert wall in segs, layer                       # the wall's inner face: the strip y -2.5..-1.6 is the wall
    assert _rect(-2.2, -2.5, 9.7, 3.3) <= _segments(fp, "F.Fab")                  # the mated plug, latch face on the wall
    xs = [p[0] for s in _segments(fp, "F.CrtYd") for p in s]
    ys = [p[1] for s in _segments(fp, "F.CrtYd") for p in s]
    assert (min(xs), min(ys), max(xs), max(ys)) == (-1.75, -3.0, 9.25, 2.9)
    pads = sorted((p[1], float(_child(p, "at")[1]), float(_child(p, "at")[2]), float(_child(p, "drill")[1]))
                  for p in _children(fp, "pad"))
    assert pads == [("1", 0.0, 0.0, 1.2), ("2", 2.5, 0.0, 1.2), ("3", 5.0, 0.0, 1.2), ("4", 7.5, 0.0, 1.2)]
