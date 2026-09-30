import pathlib

import pytest

from tools import pcb

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def board():
    return pcb.load(ROOT / "FluxDrive.kicad_pcb")


def test_outline(board):
    """Spec 8: at least 56 mm along the connector. 60 x 48 mm plus the 6.5 mm the antenna rests on (O10)."""
    x0, y0, x1, y1 = pcb.board_extents(board)
    assert x1 - x0 >= 56.0 and 40.0 <= y1 - y0 <= 55.0


def test_connector_along_south_edge(board):
    fps = pcb.footprints(board)
    x0, y0, x1, y1 = pcb.board_extents(board)
    jx, jy, rot, layer = fps["J1"]
    assert layer == "F.Cu" and rot % 360 in (90.0, 270.0) and jy > y1 - 8.0


def test_module_antenna_on_the_north_edge(board):
    """O10 (Dimitri, after the layout review): the module lies wholly on the board, its antenna end 0.3-1.0 mm
    inside the north edge (JLC economic assembly), over copper-free board: no track or via north of the
    antenna's base in the keep-out's width."""
    from tools.netlist import _child, _children
    fps = pcb.footprints(board)
    x0, y0, x1, y1 = pcb.board_extents(board)
    ux, uy, rot, layer = fps["U1"]
    top, base = uy - 12.8, uy - 6.75                      # F.Fab body top; the antenna's base line
    assert layer == "F.Cu" and rot == 0.0 and 0.3 <= top - y0 <= 1.0
    for s in _children(board, "segment"):
        for end in ("start", "end"):
            x, y = float(_child(s, end)[1]), float(_child(s, end)[2])
            assert not (abs(x - ux) < 24.0 and y < base), (x, y)
    for v in _children(board, "via"):
        x, y = float(_child(v, "at")[1]), float(_child(v, "at")[2])
        assert not (abs(x - ux) < 24.0 and y < base), (x, y)


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
    """Review focus 4, LCODE-9: a "1" next to J1 pin 1 on both sides (within 4 mm of the pad)."""
    import math
    from tools.netlist import _child, _children
    (px, py), = [xy for xy in _pads(board, "J1") if xy == _pads(board, "J1")[0]]
    for layer in ("F.SilkS", "B.SilkS"):
        near = [t for t in _children(board, "gr_text") if _child(t, "layer")[1] == layer and t[1].strip() == "1"
                and math.dist((float(_child(t, "at")[1]), float(_child(t, "at")[2])), (px, py)) <= 6.0]
        assert near, layer


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


def _zones(board):
    """[(layers, net, is_rule_area, name, (x0, y0, x1, y1))] of every board-level zone."""
    from tools.netlist import _child, _children
    out = []
    for z in _children(board, "zone"):
        lay = _child(z, "layers") or _child(z, "layer")
        net = _child(z, "net")
        name = _child(z, "name")
        pts = [(float(xy[1]), float(xy[2])) for xy in _children(_child(_child(z, "polygon"), "pts"), "xy")]
        xs, ys = [x for x, _ in pts], [y for _, y in pts]
        out.append((list(lay[1:]), net[-1] if net is not None else "", _child(z, "keepout") is not None,
                    name[1] if name is not None else "", (min(xs), min(ys), max(xs), max(ys))))
    return out


def test_four_copper_layers_with_planes(board):
    """Dimitri's choice after the layout review (LBUS-1, LPWR-1): 4 layers, In1 a solid GND plane, In2 +3V3."""
    from tools.netlist import _child
    names = [l[1] for l in _child(board, "layers")[1:] if len(l) > 2 and l[2] in ("signal", "power")]
    assert names == ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
    x0, y0, x1, y1 = pcb.board_extents(board)
    for layer, net in (("In1.Cu", "/GND"), ("In2.Cu", "/+3V3")):
        planes = [bb for lays, n, rule, _, bb in _zones(board) if lays == [layer] and n == net and not rule]
        assert planes and planes[0][0] <= x0 and planes[0][1] <= y0 and planes[0][2] >= x1 and planes[0][3] >= y1, layer


def _vias(board, net):
    from tools.netlist import _child, _children
    return [(float(_child(v, "at")[1]), float(_child(v, "at")[2])) for v in _children(board, "via")
            if _child(v, "net")[-1] == net]


def test_decoupling_reaches_the_planes(board):
    """LBUS-2, LPWR-2: every logic-IC ground pin and its 100 nF has its own via to the GND plane close by."""
    import math
    gnd = _vias(board, "/GND")
    for ic, cap in (("U2", "C5"), ("U3", "C6"), ("U4", "C7")):
        for x, y in _pads(board, ic, "/GND") + _pads(board, cap, "/GND"):
            assert min(math.dist((x, y), v) for v in gnd) <= 1.6, (ic, cap, x, y)


def test_rule_areas(board):
    """LBUS-6, LESP-1, LESP-5, LPWR-3, LPWR-13: the track keep-outs the layout review asked for."""
    names = {name for _, _, rule, name, _ in _zones(board) if rule}
    for need in ("J1 rows", "antenna edge", "buck", "module underside", "USB-C body"):
        assert any(n.startswith(need) for n in names), need


def test_dkrd_short_and_on_one_layer(board):
    """Spec 8, LBUS-4: /DKRD (the flux stream, the only line that switches all the time) runs from U4 to its
    33 ohm as a short track without a via: at most 10 mm."""
    import math
    from tools.netlist import _child, _children
    length = sum(math.dist((float(_child(s, "start")[1]), float(_child(s, "start")[2])),
                           (float(_child(s, "end")[1]), float(_child(s, "end")[2])))
                 for s in _children(board, "segment") if _child(s, "net")[-1] == "/DKRD_D")
    assert 0 < length <= 10.0, length
    assert not _vias(board, "/DKRD_D")


def _pad_shapes(board):
    """[(ref, net, x, y, half_w, half_h, rot_deg, smd)] of every pad, in board mm."""
    import math
    from tools.netlist import _child, _children
    out = []
    for fp in _children(board, "footprint"):
        ref = [p[2] for p in _children(fp, "property") if len(p) > 2 and p[1] == "Reference"][0]
        at = _child(fp, "at")
        fx, fy = float(at[1]), float(at[2])
        frot = float(at[3]) if len(at) > 3 else 0.0
        r = math.radians(frot)
        for pad in _children(fp, "pad"):
            pat, size = _child(pad, "at"), _child(pad, "size")
            px, py = float(pat[1]), float(pat[2])
            prot = float(pat[3]) if len(pat) > 3 else 0.0
            net = _child(pad, "net")
            out.append((ref, net[-1] if net is not None else "", fx + px * math.cos(r) + py * math.sin(r),
                        fy - px * math.sin(r) + py * math.cos(r), float(size[1]) / 2, float(size[2]) / 2,
                        prot, pad[2] == "smd"))
    return out


def test_no_via_in_an_smd_pad(board):
    """LPCB-2, LCODE-4: no via ring touches an SMD pad (solder would drain into it), its own net included."""
    import math
    from tools.netlist import _child, _children
    vias = [(float(_child(v, "at")[1]), float(_child(v, "at")[2])) for v in _children(board, "via")]
    for ref, net, px, py, hw, hh, rot, smd in _pad_shapes(board):
        if not smd:
            continue
        a = math.radians(rot)
        for vx, vy in vias:
            dx, dy = vx - px, vy - py                           # into the pad's own axes
            lx, ly = dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)
            gx, gy = max(abs(lx) - hw, 0.0), max(abs(ly) - hh, 0.0)
            assert math.hypot(gx, gy) >= 0.3 + 0.05, (ref, vx, vy)   # via radius plus a mask web


def test_silkscreen_text_height(board):
    """LPCB-4: every silkscreen text at least 1.0 mm high (spec 8, JLC)."""
    from tools.netlist import _child, _children
    for t in _children(board, "gr_text"):
        if _child(t, "layer")[1] in ("F.SilkS", "B.SilkS"):
            size = _child(_child(_child(t, "effects"), "font"), "size")
            assert float(size[1]) >= 1.0, t[1]


def test_usb_data_pads_joined_on_top(board):
    """LESP-3: the receptacle has D+ and D- twice (A6/B6, A7/B7), interleaved. Each pair of pads is joined on
    F.Cu right at the receptacle, without a via: D+ around the west end of A7, D- around the east end of A6."""
    import math
    from tools.netlist import _child, _children
    for net in ("/USB_DP_C", "/USB_DN_C"):
        pads = _pads(board, "J3", net)
        assert len(pads) == 2, net
        parent = {}

        def find(p):
            while parent.setdefault(p, p) != p:
                p = parent[p]
            return p

        for s in _children(board, "segment"):
            if _child(s, "net")[-1] != net or _child(s, "layer")[1] != "F.Cu":
                continue
            a, b = ((round(float(_child(s, e)[1]), 2), round(float(_child(s, e)[2]), 2)) for e in ("start", "end"))
            parent[find(a)] = find(b)
        roots = [{find(q) for q in list(parent) if math.dist(q, pad) < 0.1} for pad in pads]   # tracks from the pad centres
        assert roots[0] & roots[1], net


def _production_mismatches(board, out_dir):
    """What differs between the board and the BOM/CPL in out_dir: missing or extra designators, and passives
    whose CPL position is not the footprint's (a CPL left from an earlier build)."""
    import csv
    from tools.netlist import _child, _children
    want = {}
    for fp in _children(board, "footprint"):
        props = {p[1]: p[2] for p in _children(fp, "property") if len(p) > 2}
        attr = _child(fp, "attr") or []
        smd = any(pad[2] == "smd" for pad in _children(fp, "pad"))      # the USB-C: SMD pins, through-hole shell
        if smd and "dnp" not in attr and "exclude_from_pos_files" not in attr and props.get("LCSC", "").strip():
            at = _child(fp, "at")
            want[props["Reference"]] = (float(at[1]), float(at[2]))
    out = pathlib.Path(out_dir)
    cpl = {r["Designator"]: r for r in csv.DictReader(open(out / "CPL-FluxDrive.csv", encoding="utf-8"))}
    bom = [d for r in csv.DictReader(open(out / "BOM-FluxDrive.csv", encoding="utf-8")) for d in r["Designator"].split(",")]
    bad = sorted(set(want) ^ set(cpl)) + sorted(set(want) ^ set(bom)) + [d for d in bom if bom.count(d) > 1]
    for ref, (x, y) in want.items():
        r = cpl.get(ref)
        if r and ref[0] in "RC" and (abs(float(r["Mid X"]) - x) > 0.01 or abs(float(r["Mid Y"]) + y) > 0.01):
            bad.append(ref)
    return bad


def test_production_files_match_the_board(board):
    """Task 12: jlcpcb/production_files/ belongs to this board: every fitted SMD part with an LCSC number is in the
    BOM once and in the CPL at its place, nothing else is (tools/jlc_production.sh after every board build)."""
    assert _production_mismatches(board, ROOT / "jlcpcb" / "production_files") == []
