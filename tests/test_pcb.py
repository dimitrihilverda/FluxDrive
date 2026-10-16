import pathlib

import pytest

from tools import pcb

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def board():
    return pcb.load(ROOT / "FluxDrive.kicad_pcb")


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


def _texts(board, layer):
    from tools.netlist import _child, _children
    out = []
    for t in _children(board, "gr_text"):
        lay = _child(t, "layer")
        if lay is not None and lay[1] == layer:
            out.append(t[1])
    return out


def test_pin1_marked_both_sides(board):
    """Review focus 4, LCODE-9: a "1" next to J1 pin 1 on both sides (within 6 mm of the pad)."""
    import math
    from tools.netlist import _child, _children
    (px, py), = [xy for xy in _pads(board, "J1") if xy == _pads(board, "J1")[0]]
    for layer in ("F.SilkS", "B.SilkS"):
        near = [t for t in _children(board, "gr_text") if _child(t, "layer")[1] == layer and t[1].strip() == "1"
                and math.dist((float(_child(t, "at")[1]), float(_child(t, "at")[2])), (px, py)) <= 6.0]
        assert near, layer


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
    """What differs between the board and the BOM/CPL in out_dir: missing or extra designators, and parts whose
    CPL place or rotation is not the footprint's (a CPL left from an earlier build)."""
    import csv
    from tools.assembly import HAND_PLACED
    from tools.netlist import _child, _children
    want = {}
    for fp in _children(board, "footprint"):
        props = {p[1]: p[2] for p in _children(fp, "property") if len(p) > 2}
        attr = _child(fp, "attr") or []
        smd = any(pad[2] == "smd" for pad in _children(fp, "pad"))      # the USB-C: SMD pins, through-hole shell
        if props["Reference"] in HAND_PLACED:
            continue
        if smd and "dnp" not in attr and "exclude_from_pos_files" not in attr and props.get("LCSC", "").strip():
            at = _child(fp, "at")
            want[props["Reference"]] = (float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0,
                                        fp[1].split(":")[-1])
    out = pathlib.Path(out_dir)
    cpl = {r["Designator"]: r for r in csv.DictReader(open(out / "CPL-FluxDrive.csv", encoding="utf-8"))}
    bom = [d for r in csv.DictReader(open(out / "BOM-FluxDrive.csv", encoding="utf-8")) for d in r["Designator"].split(",")]
    bad = sorted(set(want) ^ set(cpl)) + sorted(set(want) ^ set(bom)) + [d for d in bom if bom.count(d) > 1]
    bad += [ref for ref, w in want.items() if ref in cpl and _placement_mismatch(ref, w, cpl[ref])]
    return bad


def _placement_mismatch(ref, want, row):
    """True if a CPL row does not put the part where the board has it. want = (x, y, rotation, footprint name):
    the position within 0.01 mm for R and C (their pads surround the origin) and within 0.2 mm for the rest (the CPL
    takes the pads' centre: J3's is 0.16 mm off its origin); the rotation is KiCad's plus tools/jlc_rules.py's
    correction (build-rulings minor: rotations were not compared)."""
    from tools.jlc_rules import correction
    x, y, rot, name = want
    tol = 0.01 if ref[0] in "RC" else 0.2
    turn = (float(row["Rotation"]) - rot - correction(name)) % 360
    return (abs(float(row["Mid X"]) - x) > tol or abs(float(row["Mid Y"]) + y) > tol
            or min(turn, 360 - turn) > 0.01)


def test_production_files_match_the_board(board):
    """Task 12: jlcpcb/production_files/ belongs to this board: every fitted SMD part with an LCSC number that JLC
    places (not the hand-placed ones, tools/assembly.py) is in the BOM once and in the CPL at its place, nothing else
    is (tools/jlc_production.sh after every board build)."""
    assert _production_mismatches(board, ROOT / "jlcpcb" / "production_files") == []


def test_hand_placed_parts_have_no_paste(board):
    """tools/assembly.py: the parts the builder places himself (the ESP32 module) have no solder paste on any pad,
    also not the paste-only windowpane pads: JLC prints paste on every stencil opening, placed or not."""
    from tools.assembly import HAND_PLACED
    from tools.netlist import _child, _children
    for fp in _children(board, "footprint"):
        ref = [p[2] for p in _children(fp, "property") if p[1] == "Reference"][0]
        if ref in HAND_PLACED:
            pasted = [_child(pad, "at")[1:3] for pad in _children(fp, "pad")
                      if any(str(layer).endswith(".Paste") for layer in (_child(pad, "layers") or [])[1:])]
            assert pasted == [], (ref, len(pasted))


def test_production_check_sees_a_moved_or_turned_part():
    """Build-rulings minor: the production check compares rotations too, and every part's position."""
    row = {"Mid X": "120.0", "Mid Y": "-130.0", "Rotation": "90.0"}
    soic = (120.0, 130.0, 90.0, "SOIC-14_3.9x8.7mm_P1.27mm")
    assert not _placement_mismatch("U2", soic, row)
    assert _placement_mismatch("U2", soic, {**row, "Rotation": "180.0"})
    assert _placement_mismatch("U2", soic, {**row, "Mid X": "120.3"})
    sot = (120.0, 130.0, 90.0, "SOT-23-6")
    assert not _placement_mismatch("U7", sot, {**row, "Rotation": "270.0"})         # JLC adds 180 to a SOT-23
    assert _placement_mismatch("R1", (120.0, 130.0, 90.0, "R_0402_1005Metric"), {**row, "Mid X": "120.05"})


def test_rule_areas_cover_their_layers(board):
    """Build-rulings minor: every rule area is checked by its layers and its track flag, not by its name only."""
    from tools.netlist import _child, _children
    want = {"J1 rows F": ["F.Cu"], "J1 rows B": ["B.Cu"], "antenna edge": ["F.Cu", "B.Cu"],
            "module underside": ["F.Cu"], "USB-C body": ["F.Cu"], "buck F": ["F.Cu"], "buck B": ["B.Cu"],
            "J6 rows B": ["B.Cu"], "antenna sides": ["F.Cu", "B.Cu"]}
    areas = [z for z in _children(board, "zone") if _child(z, "keepout") is not None]
    for name, layers in want.items():
        hits = [z for z in areas if (_child(z, "name") or [None, ""])[1].startswith(name)]
        assert hits, name
        for z in hits:
            assert _child(_child(z, "keepout"), "tracks")[1] == "not_allowed", name
            lay = _child(z, "layers") or _child(z, "layer")
            assert list(lay[1:]) == layers, (name, lay)


def test_antenna_area_copper_free_on_every_layer(board):
    """Build-rulings minor: the antenna test also looks at zone fills and pads, not only at tracks and vias."""
    from tools.netlist import _child, _children
    fps = pcb.footprints(board)
    ux, uy = fps["U1"][0], fps["U1"][1]
    base = uy - 6.75
    for z in _children(board, "zone"):
        if _child(z, "keepout") is not None:
            continue
        for poly in _children(z, "filled_polygon"):
            for xy in _children(_child(poly, "pts"), "xy"):
                x, y = float(xy[1]), float(xy[2])
                assert not (abs(x - ux) < 23.5 and y < base - 0.3), ((_child(z, "net") or ["", ""])[-1], x, y)
    for ref, net, px, py, hw, hh, rot, smd in _pad_shapes(board):
        assert not (abs(px - ux) < 24.0 and py < base), (ref, px, py)


REV_A = (100.0, 93.5, 160.0, 148.0)          # rev A's outline (tools/pcb_place.py at 26499dc)


def _refs_between(board, net_a, net_b):
    """Refs of the two-pad parts with one pad on each of the two nets."""
    from tools.netlist import _child, _children
    out = []
    for fp in _children(board, "footprint"):
        ref = [p[2] for p in _children(fp, "property") if len(p) > 2 and p[1] == "Reference"][0]
        nets = sorted((_child(pad, "net") or [None, ""])[-1] for pad in _children(fp, "pad"))
        if len(nets) == 2 and nets == sorted((net_a, net_b)):
            out.append(ref)
    return out


def test_outline(board):
    """Rev B spec 9: 60 mm wide; the south edge 2.4 mm north of rev A's (J1 stays over CN11), the north edge at
    most 20 mm north of rev A's: at most 72.1 mm."""
    x0, y0, x1, y1 = pcb.board_extents(board)
    assert abs((x1 - x0) - 60.0) < 0.01
    assert abs(y1 - (REV_A[3] - 2.4)) < 0.01
    assert y0 >= REV_A[1] - 20.0 - 0.01 and y1 - y0 <= 72.1 + 0.01


def test_j1_stays_and_j6_beside_it(board):
    """Rev B spec 9: J1 at rev A's place over CN11; J6 17.78 mm north of it, same orientation and side."""
    fps = pcb.footprints(board)
    assert fps["J1"][:3] == (113.68, 141.55, 90.0) and fps["J1"][3] == "F.Cu"
    jx, jy, rot, layer = fps["J6"]
    assert (jx, rot, layer) == (113.68, 90.0, "F.Cu") and abs(jy - (141.55 - 17.78)) < 0.01


def test_connector_zones_free(board):
    """Review focus 5 of rev A, LCODE-9, rev B spec 9: no SMD pad in the bands J1's and J6's bodies and the iron
    need (the pin field's centre +-27 x +-5 mm); test pads and jumpers are SMD and count too."""
    fps = pcb.footprints(board)
    for conn in ("J1", "J6"):
        jx, jy = fps[conn][0] + 20.32, fps[conn][1] - 1.27
        for ref, net, x, y, hw, hh, rot, smd in _pad_shapes(board):
            if smd and ref not in ("J1", "J6"):
                assert not (abs(x - jx) < 27.0 and abs(y - jy) < 5.0), (conn, ref, x, y)


def test_filter_pads_beside_their_pull_ups(board):
    """Rev B spec 9: each unfitted 220 pF pad sits on its net after the 100 ohm, within 3 mm of that net's own
    100 kOhm pull-up (review F14: the resistor with its other pad on +3V3, not the 100 ohm)."""
    import math
    pads = _pad_shapes(board)
    pull = {ref for ref, n, *_ in pads if n == "/+3V3"}
    for sig in ("STEP", "SEL0", "SEL1", "MTR0"):
        net = f"/{sig}_B"
        caps = [(x, y) for ref, n, x, y, *_ in pads if n == net and ref.startswith("C")]
        res = [(x, y) for ref, n, x, y, *_ in pads if n == net and ref.startswith("R") and ref in pull]
        assert caps and res, sig
        assert min(math.dist(c, r) for c in caps for r in res) <= 3.0, sig


def test_placement_table_covers_the_design():
    """Review F4: the placement table names every part of hardware/design.py exactly once, found by its nets (it
    runs in the system Python: tools/placement.py has no pcbnew)."""
    import collections
    import hardware.design as D
    from tools.placement import table
    fixed, soft = table()
    refs = list(fixed) + [r for r, *_ in soft]
    assert [r for r, c in collections.Counter(refs).items() if c > 1] == []
    assert set(refs) == {p["ref"] for p in D.PARTS}


def test_placement_is_legal(board):
    """LCODE-1: every footprint where the placement table puts it (a board built by an older table shows up).
    Courtyards and parts off the board are Task 11 step 4's DRC and the legaliser's; this passes on rev A's
    board with rev A's table too."""
    import subprocess
    r = subprocess.run([r"C:/Program Files/KiCad/10.0/bin/python.exe", str(ROOT / "tools" / "pcb_place.py"),
                        "--check", str(ROOT / "FluxDrive.kicad_pcb")], capture_output=True, text=True)
    assert r.returncode == 0 and "0 footprints differ" in r.stdout, r.stdout + r.stderr


def test_connector_row_keepouts(board):
    """Review M6, rev B spec 9: the row keep-outs reach 1.75 mm past the end pins and 1.75 mm south of the GND
    row (a track centre there is 0.8 mm plus pad radius and half a track from the GND pads): J1 on both layers,
    J6 on B.Cu; the antenna's side lines stay free for the border's stitching vias."""
    from tools.placement import J1_PIN1, J6_PIN1, pin_x
    zones = {name: (lays, bb) for lays, net, rule, name, bb in _zones(board) if rule}
    for name, layer, pin1_y in (("J1 rows F 1", "F.Cu", J1_PIN1[1]), ("J1 rows B 1", "B.Cu", J1_PIN1[1]),
                                ("J6 rows B 1", "B.Cu", J6_PIN1[1])):
        lays, (x0, y0, x1, y1) = zones[name]
        assert lays == [layer], name
        want = (pin_x(1) - 1.75, pin1_y - 2.54 + 0.85, pin_x(33) + 1.75, pin1_y + 1.75)
        assert all(abs(a - b) < 0.01 for a, b in zip((x0, y0, x1, y1), want)), (name, (x0, y0, x1, y1))
    assert any(n.startswith("antenna sides") for n in zones)


def test_buck_away_from_dkrd_and_antenna(board):
    """Spec 8: the buck (switch node: U6, L1) at least 15 mm from /DKRD and from the antenna (its nearest point, not
    the board edge: build-rulings minor). Task 1's test, with the 33 ohm found by its nets (refs are not stable in
    rev B)."""
    import math
    fps = pcb.footprints(board)
    ux, uy = fps["U1"][0], fps["U1"][1]
    top, base = uy - 12.8, uy - 6.75                        # the antenna: module body top to the antenna's base line
    sw = _pads(board, "U6", "/BUCK_SW") + _pads(board, "L1", "/BUCK_SW")
    (r33,) = _refs_between(board, "/DKRD_D", "/_DKRD")
    dkrd = _pads(board, "J1", "/_DKRD") + _pads(board, r33) + _pads(board, "U4", "/DKRD_D")
    assert sw and len(dkrd) == 4
    for sx, sy in sw:
        assert min(math.dist((sx, sy), d) for d in dkrd) >= 15.0
        ax, ay = min(max(sx, ux - 9.0), ux + 9.0), min(max(sy, top), base)
        assert math.dist((sx, sy), (ax, ay)) >= 15.0


def test_credit_and_revision(board):
    texts = " ".join(_texts(board, "F.SilkS") + _texts(board, "B.SilkS"))
    assert "FluxDrive v1 rev B" in texts and "Dimmy (Dimitri Hilverda)" in texts


def test_decoupling_reaches_the_planes(board):
    """LBUS-2, LPWR-2: every buffer's ground pin and its 100 nF (the capacitor whose +3V3 pad is nearest the
    buffer's supply pin, found by net) have a via to the GND plane close by."""
    import math
    gnd = _vias(board, "/GND")
    pads = _pad_shapes(board)
    on = lambda ref, net: [(x, y) for r, n, x, y, *_ in pads if r == ref and n == net]
    caps = {r for r, n, *_ in pads if r.startswith("C") and n == "/+3V3"} & {r for r, n, *_ in pads if n == "/GND"}
    for ic in ("U2", "U3", "U4"):
        vcc = on(ic, "/+3V3")
        cap = min(caps, key=lambda c: min(math.dist(p, v) for p in on(c, "/+3V3") for v in vcc))
        for x, y in on(ic, "/GND") + on(cap, "/GND"):
            assert min(math.dist((x, y), v) for v in gnd) <= 1.6, (ic, cap, x, y)
