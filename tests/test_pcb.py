import pathlib

import pytest

from tools import pcb

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def board():
    return pcb.load(ROOT / "FluxDrive.kicad_pcb")


def test_outline(board):
    x0, y0, x1, y1 = pcb.board_extents(board)
    assert x1 - x0 >= 56.0 and 40.0 <= y1 - y0 <= 48.0


def test_connector_along_south_edge(board):
    fps = pcb.footprints(board)
    x0, y0, x1, y1 = pcb.board_extents(board)
    jx, jy, rot, layer = fps["J1"]
    assert layer == "F.Cu" and rot in (90.0, 270.0) and jy > y1 - 8.0


def test_module_antenna_over_north_edge(board):
    fps = pcb.footprints(board)
    x0, y0, x1, y1 = pcb.board_extents(board)
    ux, uy, rot, layer = fps["U1"]
    assert layer == "F.Cu" and rot == 0.0 and uy - 12.75 < y0          # body top (antenna end) past the edge


def test_power_header_next_to_connector(board):
    fps = pcb.footprints(board)
    assert abs(fps["J2"][1] - fps["J1"][1]) < 12.0


def _pads(board, ref, net=None):
    """[(x, y)] of the pads of footprint `ref` (optionally only those on `net`), in board mm."""
    import math
    from tools.netlist import _child, _children
    for fp in _children(board, "footprint"):
        refs = [p[2] for p in _children(fp, "property") if len(p) > 2 and p[1] == "Reference"]
        if refs != [ref]:
            continue
        at = _child(fp, "at")
        fx, fy = float(at[1]), float(at[2])
        rot = math.radians(float(at[3]) if len(at) > 3 else 0.0)
        out = []
        for pad in _children(fp, "pad"):
            pn = _child(pad, "net")
            if net and (pn is None or pn[-1] != net):
                continue
            pat = _child(pad, "at")
            px, py = float(pat[1]), float(pat[2])
            out.append((fx + px * math.cos(rot) + py * math.sin(rot), fy - px * math.sin(rot) + py * math.cos(rot)))
        return out
    raise KeyError(ref)


def test_buck_away_from_dkrd_and_antenna(board):
    """Spec 8: the buck (switch node: U6, L1) at least 15 mm from /DKRD and from the antenna."""
    import math
    fps = pcb.footprints(board)
    x0, y0, x1, y1 = pcb.board_extents(board)
    ux = fps["U1"][0]
    sw = _pads(board, "U6", "/BUCK_SW") + _pads(board, "L1", "/BUCK_SW")
    dkrd = _pads(board, "J1", "/_DKRD") + _pads(board, "R35", "/_DKRD") + _pads(board, "R35", "/DKRD_D") \
        + _pads(board, "U4", "/DKRD_D")
    assert sw and len(dkrd) == 4
    for sx, sy in sw:
        assert min(math.dist((sx, sy), d) for d in dkrd) >= 15.0
        ax = min(max(sx, ux - 9.0), ux + 9.0)                   # nearest point of the antenna edge (module top)
        assert math.dist((sx, sy), (ax, y0)) >= 15.0


def _texts(board, layer):
    from tools.netlist import _child, _children
    out = []
    for t in _children(board, "gr_text"):
        lay = _child(t, "layer")
        if lay is not None and lay[1] == layer:
            out.append(t[1])
    return out


def test_pin1_marked_both_sides(board):
    """Review focus 4."""
    for layer in ("F.SilkS", "B.SilkS"):
        assert any("1" == t.strip() or "PIN 1" in t.upper() for t in _texts(board, layer)), layer


def test_credit_and_revision(board):
    texts = " ".join(_texts(board, "F.SilkS") + _texts(board, "B.SilkS"))
    assert "FluxDrive v1 rev A" in texts and "Dimmy (Dimitri Hilverda)" in texts


def test_connector_zone_free(board):
    """Review focus 5: no SMD part in the 54 x 10 mm band the boxed header body and the iron need."""
    fps = pcb.footprints(board)
    jx, jy = fps["J1"][0] + 20.32, fps["J1"][1] - 1.27      # centre of the 2x17 pin field
    for ref, (x, y, rot, layer) in fps.items():
        if ref in ("J1", "J2") or ref.startswith(("H", "FID", "TP")) or layer != "F.Cu":
            continue
        assert not (abs(x - jx) < 27.0 and abs(y - jy) < 5.0), ref
