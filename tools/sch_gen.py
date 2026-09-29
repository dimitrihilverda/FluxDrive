"""Draw a KiCad 10 schematic from a design module (a netlist written as data).

    python tools/sch_gen.py FluxDrive.kicad_sch [hardware.design]

Each part is placed once per unit, in rows per block. Every pin gets a local net label at its end point,
or a no-connect flag. Symbols are copied from KiCad's libraries (or FluxDrive.kicad_sym) into lib_symbols,
so the file is self-contained. It is a readable netlist, not a drawn circuit: the circuit lives in the
design module, and the tests check the exported netlist.
"""
import copy
import importlib
import math
import pathlib
import sys
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.sexpr import Q, child, children, dump, parse  # noqa: E402

KICAD_SYM = pathlib.Path(r"C:/Program Files/KiCad/10.0/share/kicad/symbols")
LOCAL_SYM = ROOT / "FluxDrive.kicad_sym"
G = 1.27
PAGE_W, MARGIN, ROW_GAP = 560.0, 20.0, 12.7
_libs = {}


def uid():
    return Q(str(uuid.uuid4()))


def snap(v):
    return round(round(v / G) * G, 4)


def _lib(name):
    if name not in _libs:
        path = LOCAL_SYM if name == "FluxDrive" else KICAD_SYM / f"{name}.kicad_sym"
        root = parse(path.read_text(encoding="utf-8"))
        _libs[name] = {s[1]: s for s in children(root, "symbol")}
    return _libs[name]


def lib_symbol(lib_id):
    """The library symbol, flattened (extends resolved) and renamed to lib_id, as lib_symbols wants it."""
    lib, name = lib_id.split(":", 1)
    syms = _lib(lib)
    sym = copy.deepcopy(syms[name])
    while child(sym, "extends"):
        parent_name = child(sym, "extends")[1]
        parent = copy.deepcopy(syms[parent_name])
        props = [c for c in sym[2:] if isinstance(c, list) and c[0] == "property"]
        head = [c for c in parent[2:] if not (isinstance(c, list) and c[0] in ("property", "symbol", "extends"))]
        subs = [c for c in parent[2:] if isinstance(c, list) and c[0] == "symbol"]
        for s in subs:
            s[1] = Q(name + s[1][len(parent_name):])
        sym = [sym[0], sym[1], *head, *props, *subs]
    sym[1] = Q(lib_id)
    return sym


def pins_of(sym):
    """{unit: [(number, name, x, y, angle)]}; unit 0 pins belong to every unit. Body style 2 is skipped."""
    base = sym[1].split(":", 1)[1]
    out = {}
    for s in children(sym, "symbol"):
        unit, style = (int(v) for v in s[1][len(base) + 1:].split("_"))
        if style == 2:
            continue
        for p in children(s, "pin"):
            at = child(p, "at")
            out.setdefault(unit, []).append((str(child(p, "number")[1]), str(child(p, "name")[1]),
                                             float(at[1]), float(at[2]), int(float(at[3])) if len(at) > 3 else 0))
    return out


def place(px, py, rot):
    """Symbol coordinates (y up) -> offset on the sheet (y down), for a rotation of rot degrees."""
    x, y = px, -py
    r = math.radians(rot)
    return (x * math.cos(r) + y * math.sin(r), -x * math.sin(r) + y * math.cos(r))


def resolve(ref, pins, allpins):
    """Map the design's keys (pin number or unique pin name) to pin numbers; every pin must be covered."""
    numbers = {n for n, *_ in allpins}
    by_name = {}
    for n, name, *_ in allpins:
        by_name.setdefault(name, set()).add(n)
    out = {}
    for key, net in pins.items():
        key = str(key)
        if key in numbers:
            out[key] = net
        elif len(by_name.get(key, ())) == 1:
            out[next(iter(by_name[key]))] = net
        else:
            raise ValueError(f"{ref}: pin {key!r} is not a pin number or a unique pin name")
    missing = sorted(numbers - set(out), key=lambda s: (len(s), s))
    if missing:
        raise ValueError(f"{ref}: pins not in the design: {', '.join(missing)}")
    return out


def prop(name, value, x, y, hide=False, angle=0):
    p = [ "property", Q(name), Q(value), ["at", snap(x), snap(y), angle],
          ["effects", ["font", ["size", 1.27, 1.27]]]]
    if hide:
        p.insert(4, ["hide", "yes"])
    return p


def label(net, x, y, pin_angle):
    ang = {0: 180, 180: 0, 90: 270, 270: 90}[pin_angle % 360]
    just = "right" if ang in (180, 270) else "left"
    return ["label", Q(net), ["at", snap(x), snap(y), ang],
            ["effects", ["font", ["size", 1.27, 1.27]], ["justify", just, "bottom"]], ["uuid", uid()]]


def instance(p, unit, pins, at, root_uuid, project):
    x, y = at
    sym = ["symbol", ["lib_id", Q(p["lib"])], ["at", x, y, p.get("rot", 0)], ["unit", unit],
           ["body_style", 1], ["exclude_from_sim", "no"], ["in_bom", "yes" if p.get("in_bom", True) else "no"],
           ["on_board", "yes" if p.get("on_board", True) else "no"], ["in_pos_files", "yes"],
           ["dnp", "yes" if p.get("dnp") else "no"], ["uuid", uid()],
           prop("Reference", p["ref"], x, y - 5.08, angle=p.get("rot", 0)),
           prop("Value", p["value"], x, y + 5.08, angle=p.get("rot", 0)),
           prop("Footprint", p.get("footprint", ""), x, y, hide=True),
           prop("Datasheet", "", x, y, hide=True)]
    if p.get("lcsc"):
        sym.append(prop("LCSC", p["lcsc"], x, y, hide=True))
    for n in sorted({pin[0] for pin in pins}, key=lambda s: (len(s), s)):     # this unit's pins only
        sym.append(["pin", Q(n), ["uuid", uid()]])
    sym.append(["instances", ["project", Q(project), ["path", Q("/" + root_uuid),
                                                       ["reference", Q(p["ref"])], ["unit", unit]]]])
    return sym


def extent(pins, rot, nets):
    """(x0, y0, x1, y1) of pins plus room for their labels, around the symbol origin."""
    xs, ys = [0.0], [0.0]
    for n, _, px, py, a in pins:
        dx, dy = place(px, py, rot)
        room = 2.0 + 1.0 * len(nets.get(n) or "")
        ang = (a + rot) % 360
        xs += [dx - room if ang == 0 else dx, dx + room if ang == 180 else dx]
        ys += [dy + room if ang == 90 else dy, dy - room if ang == 270 else dy]
    return min(xs) - 2.54, min(ys) - 6.35, max(xs) + 2.54, max(ys) + 6.35


def generate(title, blocks, parts, pwr_flags, project="FluxDrive"):
    root_uuid = str(uuid.uuid4())
    lib_syms, items = {}, []
    parts = copy.deepcopy(parts)
    for i, net in enumerate(pwr_flags, 1):
        parts.append(dict(ref=f"#FLG{i:02d}", lib="power:PWR_FLAG", value="PWR_FLAG", pins={"1": net},
                          block=blocks[-1], in_bom=False, on_board=False, rot=0))
    for p in parts:
        if p["lib"] not in lib_syms:
            lib_syms[p["lib"]] = lib_symbol(p["lib"])
        units = pins_of(lib_syms[p["lib"]])
        allpins = [pin for u in units.values() for pin in u]
        p["_nets"] = resolve(p["ref"], p["pins"], allpins)
        p["_numbers"] = sorted({n for n, *_ in allpins}, key=lambda s: (len(s), s))
        p["_units"] = {u: units.get(u, []) + units.get(0, []) for u in sorted(units) if u != 0} or {1: units.get(0, [])}
    y = MARGIN
    for block in blocks:
        items.append(["text", Q(block), ["exclude_from_sim", "no"], ["at", MARGIN, snap(y), 0],
                      ["effects", ["font", ["size", 2.54, 2.54]], ["justify", "left", "bottom"]], ["uuid", uid()]])
        y += 7.62
        x, row_h = MARGIN, 0.0
        for p in (q for q in parts if q["block"] == block):
            for unit, pins in p["_units"].items():
                x0, y0, x1, y1 = extent(pins, p.get("rot", 0), p["_nets"])
                if x + (x1 - x0) > PAGE_W - MARGIN:
                    x, y, row_h = MARGIN, y + row_h + ROW_GAP, 0.0
                ox, oy = snap(x - x0), snap(y - y0)
                items.append(instance(p, unit, pins, (ox, oy), root_uuid, project))
                for n, _, px, py, a in pins:
                    dx, dy = place(px, py, p.get("rot", 0))
                    px_, py_ = snap(ox + dx), snap(oy + dy)
                    net = p["_nets"][n]
                    if net is None:
                        items.append(["no_connect", ["at", px_, py_], ["uuid", uid()]])
                    else:
                        items.append(label(net, px_, py_, (a + p.get("rot", 0)) % 360))
                x += (x1 - x0) + 5.08
                row_h = max(row_h, y1 - y0)
        y += row_h + 2 * ROW_GAP
    paper = "A2" if y < 400 else "A1"
    sch = ["kicad_sch", ["version", 20260101], ["generator", Q("eeschema")], ["generator_version", Q("10.0")],
           ["uuid", Q(root_uuid)], ["paper", Q(paper)],
           ["title_block", ["title", Q(title)], ["comment", 1, Q("Generated by tools/sch_gen.py from hardware/design.py: edit the design, not this file")]],
           ["lib_symbols", *lib_syms.values()], *items,
           ["sheet_instances", ["path", Q("/"), ["page", Q("1")]]], ["embedded_fonts", "no"]]
    return dump(sch) + "\n"


def main(out, module="hardware.design"):
    d = importlib.import_module(module)
    text = generate(d.TITLE, d.BLOCKS, d.PARTS, d.PWR_FLAGS)
    pathlib.Path(out).write_text(text, encoding="utf-8", newline="\n")
    print(f"{out}: {len(d.PARTS)} parts")


if __name__ == "__main__":
    main(*sys.argv[1:])
