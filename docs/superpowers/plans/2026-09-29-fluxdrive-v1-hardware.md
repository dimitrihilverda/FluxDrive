# FluxDrive v1 hardware — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a KiCad 10 project for the FluxDrive v1 board (schematic, 2-layer layout, JLC production files) that meets
the approved spec v0.2, proven by netlist tests, ERC, DRC and two rounds of specialist review.

**Architecture:** the circuit is written once, as data, in `hardware/design.py` (every part, every pin, every
net). `tools/sch_gen.py` turns that into `FluxDrive.kicad_sch`: symbols from KiCad's libraries, a net label on
every pin, no hand-drawn wires. `kicad-cli` exports the netlist; pytest checks it against the spec. The board is
built from that netlist by scripts adapted from the Nano-Tek (`pcb_sync`, placement, Freerouting, a maze router
for leftovers), so it can be rebuilt after every schematic change.

**Tech stack:** KiCad 10.0.6 (`kicad-cli`, its bundled Python with `pcbnew`), Python 3.13 + pytest for the tests,
Java 17 + Freerouting 1.9 (`~/.kicad-mcp/freerouting.jar`, already installed for the Nano-Tek), git with
`core.autocrlf=false`.

**Spec:** `docs/superpowers/specs/2026-09-28-fluxdrive-v1-hardware-design.md` (v0.2, approved by Dimitri on
2026-09-29). Review record: `docs/reviews/2026-09-29-spec-review.md`.

## Global constraints

- ESP32-S3-WROOM-1-N16R8 exactly (LCSC C2913202); the WROOM-1U-N16R8 (C3013946) is the same footprint.
- Bus outputs only on GPIO21 and GPIO38–42. GPIO18, 3, 12, 45, 46 and 35–37 unconnected.
- Inputs: connector → pull-up node → 100 Ω → 74LVC14A, 100 kΩ from the LVC14A input to +3.3 V.
- Pull-ups to **+5V_A**: 1 kΩ `/STEP` `/DIR` `/SIDE` `/SEL0`; 4.7 kΩ `/DKWD` `/DKWE`; 10 kΩ `/SEL1`; none fitted on `/MTR0` (pins 4, 16).
- Outputs: 74LVC07A, 10 kΩ to +3.3 V on every buffer input, 33 Ω in series at every output.
- Power: TE 171826-4 → TPS259531 eFuse (5.7 V clamp) → +5V_A → SS34 → V5SYS; VBUS → USBLC6-2SC6 → SS34 → V5SYS; V5SYS ≤ 10 µF; TLV62569 buck, 2.2 µH, to +3V3. No P-FET.
- AMIGA_PWR: 10 kΩ / 15 kΩ from +5V_A to GPIO1.
- GPIO0: 10 kΩ pull-up, no capacitor. EN: 10 kΩ pull-up, 1 µF.
- Board: 2 layers, 1.6 mm, ≥ 56 mm along the connector, about 45 mm deep; all SMD on top, assembled by JLC; every through-hole part hand-soldered by Dimitri.
- Rules: tracks 0.2/0.2 mm (0.15 mm at the module), power 0.4 mm, vias 0.3/0.6 mm, copper ≥ 0.3 mm from the edge.
- Antenna end of the module over the north edge, keep-out on all layers, 15 mm clearance from housing metal (fit test).
- Silkscreen: pin-1 triangle and edge mark for the 34-pin connector on both sides, "FluxDrive v1 rev A", "by Dimmy (Dimitri Hilverda)".
- Git: commit with `git -c core.autocrlf=false`, never push. Commit messages end with the `Co-Authored-By` line of the session (not in Dimitri's own texts).

## Review focus

Failure modes the spec implies that no single task's main tests would catch; each has a test in the task named.

1. **A reversed power plug** (+12 V on pin 1): EN of the eFuse stays below 7 V and the eFuse is the only way from
   J2 to the board. Test `test_efuse_survives_12v` (task 5).
2. **USB alone on the bench with the Amiga off:** nothing from VBUS/V5SYS/+3V3 reaches +5V_A or a connector pin
   except through a reverse-biased diode or ≥ 100 kΩ. Test `test_no_backfeed_paths` (task 5).
3. **The ESP32 restarting while the Amiga runs:** every bus output GPIO is glitch-free and every buffer input has
   its 10 kΩ pull-up, so no output moves. Test `test_outputs_quiet_at_power_up` (task 4).
4. **A plug-on socket fitted rotated or a row off:** pin-1 marks on both silkscreen layers and the even row facing
   inward. Test `test_pin1_marked_both_sides` (task 10).
5. **Hand-soldering the connectors after JLC assembly:** no SMD part inside the 54 × 10 mm connector zone on top,
   and the power header next to the 34-pin connector. Test `test_connector_zone_free` (task 10).

---

## File structure

| Path | Responsibility |
|---|---|
| `hardware/design.py` | The circuit as data: `PARTS` (ref, symbol, value, footprint, LCSC, pin→net, block, dnp), `BLOCKS`, `PWR_FLAGS`. Single source of truth. |
| `tools/sexpr.py` | S-expression parser/writer that keeps quoted strings (KiCad files). |
| `tools/sch_gen.py` | `design.py` → `FluxDrive.kicad_sch`. |
| `tools/netlist.py` | Netlist reader (copied from Nano-Tek `2623d2f`, plus DNP awareness). |
| `tools/export_netlist.sh` | `kicad-cli` netlist export to `build/FluxDrive.net`. |
| `FluxDrive.kicad_sym`, `FluxDrive.pretty/` | Project symbols (TPS259531, TYPE-C16PIN, 171826-4) and footprints (USB-C, 171826-4). |
| `FluxDrive.kicad_pro`, `sym-lib-table`, `fp-lib-table` | KiCad project. |
| `tests/fd.py`, `tests/conftest.py` | Test helpers and the netlist fixture. |
| `tests/test_bus.py`, `test_power.py`, `test_esp.py`, `test_bom.py`, `test_sch_gen.py`, `test_pcb.py` | Spec checks. |
| `tools/pcb_sync.py`, `pcb_place.py`, `pcb_route.py`, `pcb_ripup.py`, `pcb_maze.py`, `pcb_autoroute.py`, `pcb_silk.py`, `pcb_build.sh` | Board from netlist (adapted Nano-Tek tools). |
| `tools/jlc_export.py`, `tools/jlc_production.sh` | BOM/CPL/gerbers (copied from Nano-Tek `2623d2f`). |
| `mech/fit_template.pdf` | 1:1 paper template for the fit test. |

---

### Task 1: Test tooling and project skeleton

**Files:**
- Create: `tools/__init__.py`, `tools/netlist.py`, `tools/sexpr.py`, `tools/export_netlist.sh`, `tests/__init__.py`, `tests/conftest.py`, `tests/fd.py`, `tests/test_tools.py`, `pytest.ini`, `.gitignore` (append)

**Interfaces:**
- Produces: `tools.sexpr.parse(text) -> list`, `tools.sexpr.dump(node) -> str`, class `tools.sexpr.Q(str)` (quoted atom); `tools.netlist.load(path) -> Netlist` with `.components`, `.nets`, `net_of(ref, pin)`, `net_of_function(ref, name)`, `resistors()`, and `Netlist.fitted(ref) -> bool`; `tests.fd` helpers `pulls(nl, net)`, `between(nl, ref)`, `parts_between(nl, a, b, prefix)`, `esp_net(nl, gpio)`, `RAILS`.

- [ ] **Step 1: copy the netlist reader.** `git -C "C:/Claude projecten/Nano-Tek" show 2623d2f:tools/netlist.py > tools/netlist.py`, then add to `Netlist`:

```python
    def fitted(self, ref):
        """False for parts marked DNP in the schematic (their footprint stays, JLC fits nothing)."""
        f = self.components[ref]["fields"]
        return "dnp" not in f and f.get("DNP", "") not in ("1", "yes")
```
  and make `resistors()` skip parts where `not self.fitted(ref)`.

- [ ] **Step 2: write `tools/sexpr.py`:**

```python
"""S-expressions as KiCad writes them. Quoted strings stay Q (so they are written back quoted)."""
import re

_TOKEN = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')


class Q(str):
    """A quoted atom."""


def parse(text):
    stack = [[]]
    for tok in _TOKEN.findall(text):
        if tok == "(":
            stack.append([])
        elif tok == ")":
            done = stack.pop()
            stack[-1].append(done)
        elif tok.startswith('"'):
            stack[-1].append(Q(tok[1:-1].replace('\\"', '"').replace("\\\\", "\\")))
        else:
            stack[-1].append(tok)
    return stack[0][0]


def _atom(a):
    if isinstance(a, Q):
        return '"' + a.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(a, float):
        return f"{a:.4f}".rstrip("0").rstrip(".") if a != int(a) else str(int(a))
    return str(a)


def dump(node, depth=0):
    """KiCad style: one child list per line, tab-indented; short atom lists stay on one line."""
    if not isinstance(node, list):
        return _atom(node)
    atoms = [x for x in node if not isinstance(x, list)]
    kids = [x for x in node if isinstance(x, list)]
    head = "(" + " ".join(_atom(a) for a in atoms)
    if not kids:
        return head + ")"
    inner = "\n".join("\t" * (depth + 1) + dump(k, depth + 1) for k in kids)
    return head + "\n" + inner + "\n" + "\t" * depth + ")"


def child(node, name):
    return next((c for c in node[1:] if isinstance(c, list) and c and c[0] == name), None)


def children(node, name):
    return [c for c in node[1:] if isinstance(c, list) and c and c[0] == name]
```

- [ ] **Step 3: write `tests/test_tools.py`** (fails until steps 1–2 exist):

```python
from tools import sexpr
from tools.netlist import parse_ohms


def test_sexpr_round_trip_keeps_quotes():
    text = '(kicad_sch (version 20260101) (symbol (lib_id "Device:R") (at 1.27 2.54 90)))'
    node = sexpr.parse(text)
    again = sexpr.parse(sexpr.dump(node))
    assert again == node
    assert isinstance(sexpr.child(again, "symbol")[1][1], sexpr.Q)


def test_parse_ohms():
    assert parse_ohms("4K7") == 4700 and parse_ohms("100") == 100 and parse_ohms("2K2") == 2200
```

- [ ] **Step 4:** `pytest.ini` with `[pytest]` / `pythonpath = .`; `tests/conftest.py`:

```python
import os
import pathlib

import pytest

from tools import netlist

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def nl():
    path = pathlib.Path(os.environ.get("FD_NETLIST", ROOT / "build" / "FluxDrive.net"))
    if not path.exists():
        pytest.fail(f"{path} is missing: run  bash tools/export_netlist.sh  first")
    return netlist.load(path)
```

- [ ] **Step 5: `tests/fd.py`:**

```python
"""Helpers for the FluxDrive netlist tests."""
RAILS = {"+5V_IN", "+5V_A", "V5SYS", "VBUS", "+3V3", "GND"}


def pulls(nl, net):
    """Sorted [(value, rail)] of fitted resistors between `net` and a rail."""
    out = []
    for ref, a, b, _ in nl.resistors():
        if net in (a, b):
            other = b if a == net else a
            if other in RAILS:
                out.append((nl.components[ref]["value"], other))
    return sorted(out)


def between(nl, ref):
    return {nl.net_of(ref, 1), nl.net_of(ref, 2)}


def parts_between(nl, a, b, prefix="R"):
    """Fitted two-pin parts whose pins are on nets a and b."""
    return sorted(r for r, c in nl.components.items()
                  if r.startswith(prefix) and nl.fitted(r) and between(nl, r) == {a, b})


def esp_net(nl, gpio):
    for name in (f"IO{gpio}", {19: "USB_D-", 20: "USB_D+", 43: "TXD0", 44: "RXD0"}.get(gpio, "")):
        if name:
            net = nl.net_of_function("U1", name)
            if net is not None:
                return net
    raise AssertionError(f"U1 has no pin for GPIO{gpio}")


def is_nc(net):
    return net is None or net.startswith("unconnected-")
```

- [ ] **Step 6:** `tools/export_netlist.sh`:

```bash
#!/usr/bin/env bash
# Generate the schematic from hardware/design.py and export its netlist. Needs KiCad 10.
set -euo pipefail
cd "$(dirname "$0")/.."
KICAD_CLI="${KICAD_CLI:-/c/Program Files/KiCad/10.0/bin/kicad-cli.exe}"
mkdir -p build
python tools/sch_gen.py FluxDrive.kicad_sch
"$KICAD_CLI" sch export netlist --format kicadsexpr -o build/FluxDrive.net FluxDrive.kicad_sch
echo "build/FluxDrive.net written"
```

- [ ] **Step 7:** `python -m pytest -q tests/test_tools.py` → 2 passed. Append `build/`, `*.bak`, `fp-info-cache`, `*-backups/`, `*.lck` to `.gitignore`.
- [ ] **Step 8: commit** "Tools: s-expression and netlist readers, test skeleton".

### Task 2: The schematic generator

**Files:**
- Create: `tools/sch_gen.py`, `tests/test_sch_gen.py`, `tests/fixtures/tiny_design.py`

**Interfaces:**
- Consumes: `tools.sexpr`.
- Produces: `python tools/sch_gen.py OUT.kicad_sch [module]` (default module `hardware.design`); a design module defines `TITLE`, `BLOCKS` (list of block names), `PARTS` (list of dicts: `ref, lib, value, footprint, lcsc, pins, block, dnp, rot, in_bom`), `PWR_FLAGS` (net names). `pins` maps a pin number or a unique pin name to a net name, or to `None` for a no-connect. Every pin of the symbol must appear; `generate()` raises `ValueError` naming the missing pins.

- [ ] **Step 1: tiny test design** `tests/fixtures/tiny_design.py`:

```python
TITLE = "tiny"
BLOCKS = ["A. test"]
PARTS = [
    dict(ref="R1", lib="Device:R", value="10K", footprint="Resistor_SMD:R_0402_1005Metric", lcsc="C25744",
         pins={"1": "+3V3", "2": "SIG"}, block="A. test", dnp=False, rot=90, in_bom=True),
    dict(ref="U1", lib="74xx:74HC14", value="74LVC14A", footprint="Package_SO:SOIC-14_3.9x8.7mm_P1.27mm",
         lcsc="C133541", block="A. test", dnp=False, rot=0, in_bom=True,
         pins={"1": "SIG", "2": "OUT", "3": "GND", "4": None, "5": "GND", "6": None, "9": "GND", "8": None,
               "11": "GND", "10": None, "13": "GND", "12": None, "14": "+3V3", "7": "GND"}),
    dict(ref="R2", lib="Device:R", value="1K", footprint="Resistor_SMD:R_0402_1005Metric", lcsc="C11702",
         pins={"1": "OUT", "2": "GND"}, block="A. test", dnp=False, rot=90, in_bom=True),
]
PWR_FLAGS = ["+3V3", "GND"]
```

- [ ] **Step 2: failing test** `tests/test_sch_gen.py`:

```python
import pathlib
import subprocess

import pytest

from tools import netlist, sch_gen

CLI = r"C:/Program Files/KiCad/10.0/bin/kicad-cli.exe"


def test_tiny_design_round_trips(tmp_path):
    sch = tmp_path / "tiny.kicad_sch"
    sch_gen.main(str(sch), "tests.fixtures.tiny_design")
    net = tmp_path / "tiny.net"
    subprocess.run([CLI, "sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(net), str(sch)], check=True)
    nl = netlist.load(net)
    assert nl.net_of("R1", 2) == "SIG" and nl.net_of("U1", 1) == "SIG"
    assert nl.net_of("U1", 2) == "OUT" and nl.net_of("R2", 1) == "OUT"
    assert nl.net_of("U1", 14) == "+3V3" and nl.net_of("U1", 7) == "GND"
    erc = tmp_path / "erc.txt"
    r = subprocess.run([CLI, "sch", "erc", "--severity-error", "--exit-code-violations", "-o", str(erc), str(sch)])
    assert r.returncode == 0, erc.read_text()


def test_missing_pin_is_an_error():
    import copy
    import tests.fixtures.tiny_design as d
    parts = copy.deepcopy(d.PARTS)
    del parts[1]["pins"]["12"]
    with pytest.raises(ValueError, match="U1.*12"):
        sch_gen.generate("t", ["A. test"], parts, [])
```
  Run `python -m pytest -q tests/test_sch_gen.py` → FAIL (no module `sch_gen`).

- [ ] **Step 3: write `tools/sch_gen.py`:**

```python
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
           prop("Reference", p["ref"], x, y - 5.08), prop("Value", p["value"], x, y + 5.08),
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
```

- [ ] **Step 4:** `python -m pytest -q tests/test_sch_gen.py` → 2 passed. If KiCad rejects the file, open the error, fix the generator (the Nano-Tek schematic `Nano-Tek_GTi.kicad_sch` is the format reference), and rerun. Open the tiny schematic once in KiCad 10 (`eeschema`) and check that labels sit on the pin ends.
- [ ] **Step 5: commit** "Schematic generator: design data to KiCad 10 schematic".

### Task 3: Project libraries

**Files:**
- Create: `FluxDrive.kicad_sym`, `FluxDrive.pretty/USB-C-SMD_TYPE-C16PIN.kicad_mod`, `FluxDrive.pretty/171826-4.kicad_mod`, `sym-lib-table`, `fp-lib-table`, `FluxDrive.kicad_pro`

- [ ] **Step 1:** copy `USB-C-SMD_TYPE-C16PIN.kicad_mod` and `171826-4.kicad_mod` from Nano-Tek `2623d2f:Nano-Tek.pretty/` (`git show`), and the 3D models they reference if any (`3dmodels/`), fixing the model path to `${KIPRJMOD}/3dmodels/`.
- [ ] **Step 2:** `FluxDrive.kicad_sym`: copy symbols `TYPE-C16PIN` and `171826-4` from Nano-Tek `2623d2f:Nano-Tek.kicad_sym`, and add `TPS259531`:
  - pins (TPS2595 datasheet SLVSE57C, table "Pin Functions", DSG package): 1 `dVdt` passive, 2 `EN/UVLO` input, 3 `IN` power_in, 4 `IN` power_in, 5 `OUT` power_out, 6 `~{FLT}` open_collector, 7 `ILM` passive, 8 `GND` power_in, 9 `PAD` passive (exposed pad, GND);
  - properties: Reference `U`, Value `TPS259531`, Footprint `Package_SON:Texas_DSG0008A_WSON-8-1EP_2x2mm_P0.5mm_EP0.9x1.6mm`, Datasheet `https://www.ti.com/lit/ds/symlink/tps2595.pdf`;
  - body: rectangle 15.24 × 12.7 mm, IN/EN/dVdt on the left, OUT/FLT/ILM on the right, GND/PAD at the bottom, pins on the 2.54 mm grid, length 2.54.
- [ ] **Step 3:** `sym-lib-table` and `fp-lib-table` with one `FluxDrive` entry each (`${KIPRJMOD}/FluxDrive.kicad_sym`, `${KIPRJMOD}/FluxDrive.pretty`). `FluxDrive.kicad_pro`: start from Nano-Tek's `Nano-Tek.kicad_pro`, set netclasses Default 0.2/0.2 mm and Power 0.4/0.2 mm with patterns `+5V_IN`, `+5V_A`, `V5SYS`, `VBUS`, `+3V3`, `GND`, `BUCK_SW`; board rules: min clearance 0.2 mm, min track 0.15 mm, via 0.6/0.3 mm, copper-to-edge 0.3 mm, hole-to-hole 0.5 mm.
- [ ] **Step 4:** in `tests/test_sch_gen.py` add:

```python
def test_project_symbols_load():
    for name in ("TPS259531", "TYPE-C16PIN", "171826-4"):
        sym = sch_gen.lib_symbol(f"FluxDrive:{name}")
        pins = [p for u in sch_gen.pins_of(sym).values() for p in u]
        assert pins, name
    pins = {n: name for n, name, *_ in sch_gen.pins_of(sch_gen.lib_symbol("FluxDrive:TPS259531"))[1]}
    assert pins["3"] == pins["4"] == "IN" and pins["5"] == "OUT" and pins["7"] == "ILM"
```
  Run → pass.
- [ ] **Step 5: commit** "Project libraries: TPS259531, USB-C and power header".

### Task 4: Bus interface (connector, inputs, outputs)

**Files:**
- Create: `hardware/__init__.py`, `hardware/design.py` (parts common to all blocks + blocks A, B), `tests/test_bus.py`

**Interfaces:**
- Consumes: `tools.sch_gen`, `tests.fd`.
- Produces in `hardware/design.py`: `INPUTS`, `OUTPUTS` tables (below), `PARTS`, `BLOCKS`, `PWR_FLAGS`, helpers `R()`, `C()`, `part()`. Nets: connector side `_STEP` … `_RDY`, `_MTR0_P4`, `FD_PIN6`, `FD_PIN14`; buffer side `<SIG>_B`; ESP side `<SIG>` (inputs) and `<SIG>_N` (outputs); buffer outputs `<SIG>_D`.

- [ ] **Step 1: failing tests** `tests/test_bus.py`:

```python
import pytest

from tests.fd import between, esp_net, parts_between, pulls

EVEN = {2: "_CHNG", 4: "_MTR0_P4", 6: "FD_PIN6", 8: "_INDEX", 10: "_SEL0", 12: "_SEL1", 14: "FD_PIN14",
        16: "_MTR0", 18: "_DIR", 20: "_STEP", 22: "_DKWD", 24: "_DKWE", 26: "_TRK0", 28: "_WPROT",
        30: "_DKRD", 32: "_SIDE", 34: "_RDY"}
# signal, connector net, fitted pull-up, GPIO (spec 4.1 / 4.2)
INPUTS = [("STEP", "_STEP", [("1K", "+5V_A")], 6), ("DIR", "_DIR", [("1K", "+5V_A")], 7),
          ("SIDE", "_SIDE", [("1K", "+5V_A")], 15), ("SEL0", "_SEL0", [("1K", "+5V_A")], 17),
          ("SEL1", "_SEL1", [("10K", "+5V_A")], 9), ("MTR0", "_MTR0", [], 11),
          ("DKWD", "_DKWD", [("4K7", "+5V_A")], 5), ("DKWE", "_DKWE", [("4K7", "+5V_A")], 16),
          ("MTR0_P4", "_MTR0_P4", [], 4), ("PIN6", "FD_PIN6", [("10K", "+3V3")], 8),
          ("PIN14", "FD_PIN14", [("10K", "+3V3")], 10)]
OUTPUTS = [("DKRD", "_DKRD", 38), ("INDEX", "_INDEX", 39), ("TRK0", "_TRK0", 40), ("WPROT", "_WPROT", 41),
           ("CHNG", "_CHNG", 42), ("RDY", "_RDY", 21)]
GLITCH_FREE = {21, 38, 39, 40, 41, 42, 47, 48}      # ESP32-S3 datasheet v2.2, table 2-2


def test_connector_pinout(nl):
    for pin, net in EVEN.items():
        assert nl.net_of("J1", pin) == net, pin
    for pin in range(1, 34, 2):
        assert (nl.net_of("J1", pin) or "").startswith("unconnected-") if pin == 3 else nl.net_of("J1", pin) == "GND"


@pytest.mark.parametrize("sig,conn,pull,gpio", INPUTS)
def test_input_chain(nl, sig, conn, pull, gpio):
    assert pulls(nl, conn) == pull                                 # pull-up on the connector side, fitted only
    assert len(parts_between(nl, conn, f"{sig}_B")) == 1           # the 100 ohm
    r100 = parts_between(nl, conn, f"{sig}_B")[0]
    assert nl.components[r100]["value"] == "100"
    assert pulls(nl, f"{sig}_B") == [("100K", "+3V3")]
    ins = {(r, p) for r, p, _ in nl.nets[f"{sig}_B"] if r in ("U2", "U3")}
    assert len(ins) == 1, ins
    assert esp_net(nl, gpio) == sig
    assert any(r in ("U2", "U3") for r, _, _ in nl.nets[sig])      # the inverter output drives the GPIO


@pytest.mark.parametrize("sig,conn,gpio", OUTPUTS)
def test_output_chain(nl, sig, conn, gpio):
    assert esp_net(nl, gpio) == f"{sig}_N"
    assert pulls(nl, f"{sig}_N") == [("10K", "+3V3")]
    assert any(r == "U4" for r, _, _ in nl.nets[f"{sig}_N"])
    r33 = parts_between(nl, f"{sig}_D", conn)
    assert len(r33) == 1 and nl.components[r33[0]]["value"] == "33"


def test_outputs_quiet_at_power_up(nl):
    """Review focus 3: no bus output moves when the ESP32 (re)starts."""
    for sig, _, gpio in OUTPUTS:
        assert gpio in GLITCH_FREE, sig
        assert pulls(nl, f"{sig}_N") == [("10K", "+3V3")], sig


def test_buffers_on_3v3(nl):
    for u in ("U2", "U3", "U4"):
        assert nl.net_of(u, 14) == "+3V3" and nl.net_of(u, 7) == "GND"
        assert nl.components[u]["footprint"].endswith("SOIC-14_3.9x8.7mm_P1.27mm")
    assert nl.components["U4"]["value"] == "74LVC07A"
    assert nl.components["U2"]["value"] == nl.components["U3"]["value"] == "74LVC14A"


def test_no_5v_on_the_esp(nl):
    for net, nodes in nl.nets.items():
        if any(r == "U1" for r, _, _ in nodes):
            assert net not in ("+5V_IN", "+5V_A", "V5SYS", "VBUS"), net
```

  `bash tools/export_netlist.sh` fails (no `hardware/design.py`); that is the red step.

- [ ] **Step 2: write `hardware/design.py`**, first part (helpers, blocks, bus):

```python
"""FluxDrive v1: every part and every pin (spec v0.2). tools/sch_gen.py draws FluxDrive.kicad_sch from this.
The tests read the exported netlist, not this file. Refs are numbered in the order parts are added."""
import itertools

TITLE = "FluxDrive v1 rev A"
BLOCKS = ["A. Floppy connector and bus inputs", "B. Bus outputs", "C. Power", "D. ESP32-S3 module",
          "E. USB-C", "F. Headers, buttons, LED, test pads, mechanics"]
R0402 = "Resistor_SMD:R_0402_1005Metric"
RES_LCSC = {"22": "C25092", "33": "C25105", "100": "C25076", "470": "C25117", "1K": "C11702", "2K2": "C25879",
            "4K7": "C25900", "5K1": "C25905", "10K": "C25744", "15K": "C25756", "22K": "C25768", "100K": "C25741"}
CAPS = {"100nF": ("Capacitor_SMD:C_0402_1005Metric", "C1525"), "1uF": ("Capacitor_SMD:C_0402_1005Metric", "C52923"),
        "22nF": ("Capacitor_SMD:C_0402_1005Metric", "C1532"), "10uF": ("Capacitor_SMD:C_0603_1608Metric", "C19702"),
        "22uF": ("Capacitor_SMD:C_0805_2012Metric", "C45783"), "100uF": ("Capacitor_SMD:C_1206_3216Metric", "C15008"),
        "220pF": ("Capacitor_SMD:C_0402_1005Metric", ""), "10pF": ("Capacitor_SMD:C_0402_1005Metric", "")}
PARTS = []
_n = {k: itertools.count(1) for k in ("R", "C", "D", "TP")}
SOIC14 = "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm"


def part(ref, lib, value, footprint, pins, block, lcsc="", dnp=False, rot=0, in_bom=True):
    PARTS.append(dict(ref=ref, lib=lib, value=value, footprint=footprint, pins=pins, block=block,
                      lcsc=lcsc, dnp=dnp, rot=rot, in_bom=in_bom))


def R(value, a, b, block, dnp=False):
    part(f"R{next(_n['R'])}", "Device:R", value, R0402, {"1": a, "2": b}, block,
         "" if dnp else RES_LCSC[value], dnp, rot=90, in_bom=not dnp)


def C(value, a, b, block, dnp=False):
    fp, lcsc = CAPS[value]
    part(f"C{next(_n['C'])}", "Device:C", value, fp, {"1": a, "2": b}, block, "" if dnp else lcsc, dnp,
         rot=90, in_bom=not dnp)


A, B, P, E, U, F = BLOCKS

# --- A: connector and inputs -----------------------------------------------------------------------------
EVEN = {2: "_CHNG", 4: "_MTR0_P4", 6: "FD_PIN6", 8: "_INDEX", 10: "_SEL0", 12: "_SEL1", 14: "FD_PIN14",
        16: "_MTR0", 18: "_DIR", 20: "_STEP", 22: "_DKWD", 24: "_DKWE", 26: "_TRK0", 28: "_WPROT",
        30: "_DKRD", 32: "_SIDE", 34: "_RDY"}
j1 = {str(p): ("GND" if p != 3 else None) for p in range(1, 34, 2)}
j1.update({str(p): n for p, n in EVEN.items()})
part("J1", "Connector_Generic:Conn_02x17_Odd_Even", "Amiga floppy 34", "Connector_IDC:IDC-Header_2x17_P2.54mm_Vertical",
     j1, A, lcsc="C601943")

# signal, connector net, pull-up (value, rail) or None, GPIO, buffer, input pin, output pin, optional C pad
INPUTS = [
    ("STEP", "_STEP", ("1K", "+5V_A"), 6, "U2", 1, 2, True),
    ("DIR", "_DIR", ("1K", "+5V_A"), 7, "U2", 3, 4, False),
    ("SIDE", "_SIDE", ("1K", "+5V_A"), 15, "U2", 5, 6, False),
    ("SEL0", "_SEL0", ("1K", "+5V_A"), 17, "U2", 9, 8, True),
    ("SEL1", "_SEL1", ("10K", "+5V_A"), 9, "U2", 11, 10, True),
    ("MTR0", "_MTR0", None, 11, "U2", 13, 12, True),
    ("DKWD", "_DKWD", ("4K7", "+5V_A"), 5, "U3", 1, 2, False),
    ("DKWE", "_DKWE", ("4K7", "+5V_A"), 16, "U3", 3, 4, False),
    ("MTR0_P4", "_MTR0_P4", None, 4, "U3", 5, 6, False),
    ("PIN6", "FD_PIN6", ("10K", "+3V3"), 8, "U3", 9, 8, False),
    ("PIN14", "FD_PIN14", ("10K", "+3V3"), 10, "U3", 11, 10, False),
]
buf = {"U2": {"14": "+3V3", "7": "GND"}, "U3": {"14": "+3V3", "7": "GND", "13": "GND", "12": None}}
for sig, conn, pull, gpio, u, pin_in, pin_out, cpad in INPUTS:
    if pull:
        R(pull[0], conn, pull[1], A)
    else:
        R("1K", conn, "+5V_A", A, dnp=True)                  # /MTR0: the motherboard has R506 (spec 4.2)
    R("100", conn, f"{sig}_B", A)
    R("100K", f"{sig}_B", "+3V3", A)
    if cpad:
        C("220pF", f"{sig}_B", "GND", A, dnp=True)
    buf[u].update({str(pin_in): f"{sig}_B", str(pin_out): sig})
for u in ("U2", "U3"):
    part(u, "74xx:74HC14", "74LVC14A", SOIC14, buf[u], A, lcsc="C133541")
    C("100nF", "+3V3", "GND", A)

# --- B: outputs --------------------------------------------------------------------------------------------
OUTPUTS = [("DKRD", "_DKRD", 38, 1, 2), ("INDEX", "_INDEX", 39, 3, 4), ("TRK0", "_TRK0", 40, 5, 6),
           ("WPROT", "_WPROT", 41, 9, 8), ("CHNG", "_CHNG", 42, 11, 10), ("RDY", "_RDY", 21, 13, 12)]
u4 = {"14": "+3V3", "7": "GND"}
for sig, conn, gpio, pin_in, pin_out in OUTPUTS:
    R("10K", f"{sig}_N", "+3V3", B)
    R("33", f"{sig}_D", conn, B)
    u4.update({str(pin_in): f"{sig}_N", str(pin_out): f"{sig}_D"})
part("U4", "74xx:74LS07", "74LVC07A", SOIC14, u4, B, lcsc="C6049")
C("100nF", "+3V3", "GND", B)

PWR_FLAGS = ["GND", "+3V3"]
```

  (Tasks 5 and 6 append blocks C–F; until then `U1` does not exist, so `test_input_chain`/`test_output_chain`
  fail only on `esp_net` — acceptable red state; commit this task after task 6's module is in place, or mark
  those two asserts `xfail` until then.)

- [ ] **Step 3:** `bash tools/export_netlist.sh && python -m pytest -q tests/test_bus.py -k "pinout or buffers"` → pass.
- [ ] **Step 4: commit** "Design: floppy connector, input and output buffers".

### Task 5: Power path

**Files:**
- Modify: `hardware/design.py` (append block C)
- Create: `tests/test_power.py`

- [ ] **Step 1: failing tests** `tests/test_power.py`:

```python
from tools.netlist import parse_ohms
from tests.fd import between, parts_between

BUS_NETS = {"_STEP", "_DIR", "_SIDE", "_SEL0", "_SEL1", "_MTR0", "_MTR0_P4", "_DKWD", "_DKWE", "_CHNG",
            "_INDEX", "_TRK0", "_WPROT", "_DKRD", "_RDY", "FD_PIN6", "FD_PIN14"}


def r(nl, a, b):
    refs = parts_between(nl, a, b)
    assert len(refs) == 1, (a, b, refs)
    return parse_ohms(nl.components[refs[0]]["value"])


def test_power_header_to_efuse(nl):
    assert nl.components["J2"]["footprint"].endswith(":171826-4")
    assert nl.net_of("J2", 1) == "+5V_IN" and nl.net_of("J2", 2) == nl.net_of("J2", 3) == "GND"
    assert (nl.net_of("J2", 4) or "").startswith("unconnected-")          # +12 V not used
    assert nl.net_of("U5", 3) == nl.net_of("U5", 4) == "+5V_IN"
    assert nl.net_of("U5", 5) == "+5V_A"
    assert nl.components["U5"]["value"] == "TPS259531"
    assert {r_ for r_, _, _ in nl.nets["+5V_IN"]} <= {"J2", "U5", *parts_between(nl, "+5V_IN", "GND", "C"),
                                                      *parts_between(nl, "+5V_IN", "EFUSE_EN")}


def test_efuse_survives_12v(nl):
    """Review focus 1: a reversed plug puts 12 V on IN; EN/UVLO must stay below its 7 V maximum."""
    top, bottom = r(nl, "+5V_IN", "EFUSE_EN"), r(nl, "EFUSE_EN", "GND")
    assert 12 * bottom / (top + bottom) < 6.5
    uvlo = 1.2 * (top + bottom) / bottom                                   # V_UVLO(R) = 1.2 V
    assert 3.5 <= uvlo <= 4.4, uvlo
    ilim = 2100 / r(nl, "EFUSE_ILM", "GND")                                 # table: 487R 4.17 A, 1780R 1.17 A, 4420R 0.49 A
    assert 0.8 <= ilim <= 1.3, ilim


def test_power_or(nl):
    d = {x: (nl.net_of(x, 2), nl.net_of(x, 1)) for x in ("D1", "D2")}    # SS34: pin 2 = A, pin 1 = K
    assert sorted(d.values()) == [("+5V_A", "V5SYS"), ("VBUS", "V5SYS")]
    for x in ("D1", "D2"):
        assert nl.components[x]["value"] == "SS34"
    assert not any(c.get("value", "").upper().startswith(("AO34", "SI23")) for c in nl.components.values())


def test_v5sys_capacitance_within_usb_limit(nl):
    total = 0.0
    for ref in parts_between(nl, "V5SYS", "GND", "C"):
        v = nl.components[ref]["value"].replace("uF", "e-6").replace("nF", "e-9").replace("pF", "e-12")
        total += float(v)
    assert total <= 10.2e-6, total


def test_buck(nl):
    assert nl.components["U6"]["value"].startswith("TLV62569")
    assert nl.net_of_function("U6", "VIN") == "V5SYS" and nl.net_of_function("U6", "EN") == "V5SYS"
    sw = nl.net_of_function("U6", "SW")
    assert between(nl, "L1") == {sw, "+3V3"} and nl.components["L1"]["value"] == "2.2uH"
    fb = nl.net_of_function("U6", "FB")
    vout = 0.6 * (1 + r(nl, "+3V3", fb) / r(nl, fb, "GND"))
    assert abs(vout - 3.3) < 0.05, vout


def test_amiga_pwr_sense(nl):
    top, bottom = r(nl, "+5V_A", "AMIGA_PWR"), r(nl, "AMIGA_PWR", "GND")
    assert 2.8 <= 5.0 * bottom / (top + bottom) <= 3.2
    assert 5.9 * bottom / (top + bottom) <= 3.6                            # at the eFuse clamp
    assert nl.net_of_function("U1", "IO1") == "AMIGA_PWR"


def test_pullups_on_amiga_side_only(nl):
    for ref, a, b, _ in nl.resistors():
        if {a, b} & BUS_NETS:
            assert not {a, b} & {"V5SYS", "VBUS", "+5V_IN"}, ref


def test_no_backfeed_paths(nl):
    """Review focus 2: on USB alone nothing reaches +5V_A or the bus except a reverse-biased diode or >= 100k."""
    for ref, a, b, ohms in nl.resistors():
        pair = {a, b}
        if pair & {"VBUS", "V5SYS", "+3V3"} and pair & (BUS_NETS | {"+5V_A"}):
            assert ohms is not None and ohms >= 100e3, (ref, a, b)
    feeders = {r_ for r_, _, _ in nl.nets["+5V_A"]} - {"U5", "D1"}
    for ref in feeders:
        assert ref.startswith(("R", "C", "TP", "#")), ref
```

- [ ] **Step 2: append block C** to `hardware/design.py`:

```python
# --- C: power ------------------------------------------------------------------------------------------------
part("J2", "FluxDrive:171826-4", "Floppy power", "FluxDrive:171826-4",
     {"1": "+5V_IN", "2": "GND", "3": "GND", "4": None}, P, lcsc="C590635")
part("U5", "FluxDrive:TPS259531", "TPS259531", "Package_SON:Texas_DSG0008A_WSON-8-1EP_2x2mm_P0.5mm_EP0.9x1.6mm",
     {"1": "EFUSE_DVDT", "2": "EFUSE_EN", "3": "+5V_IN", "4": "+5V_IN", "5": "+5V_A", "6": None,
      "7": "EFUSE_ILM", "8": "GND", "9": "GND"}, P, lcsc="C2155674")
C("1uF", "+5V_IN", "GND", P)
C("22nF", "EFUSE_DVDT", "GND", P)
R("10K", "+5V_IN", "EFUSE_EN", P)           # UVLO 1.2 V x 14.7/4.7 = 3.75 V; EN 3.8 V with 12 V on IN
R("4K7", "EFUSE_EN", "GND", P)
R("2K2", "EFUSE_ILM", "GND", P)             # current limit about 0.95 A
C("100uF", "+5V_A", "GND", P)
C("100nF", "+5V_A", "GND", P)
part("D1", "Diode:SS34", "SS34", "Diode_SMD:D_SMA", {"1": "V5SYS", "2": "+5V_A"}, P, lcsc="C8678")
part("D2", "Diode:SS34", "SS34", "Diode_SMD:D_SMA", {"1": "V5SYS", "2": "VBUS"}, P, lcsc="C8678")
C("10uF", "V5SYS", "GND", P)
C("100nF", "V5SYS", "GND", P)
part("U6", "Regulator_Switching:TLV62569DBV", "TLV62569DBVR", "Package_TO_SOT_SMD:SOT-23-5",
     {"EN": "V5SYS", "GND": "GND", "SW": "BUCK_SW", "VIN": "V5SYS", "FB": "BUCK_FB"}, P, lcsc="C141836")
part("L1", "Device:L", "2.2uH", "Inductor_SMD:L_Sunlord_SWPA4020S", {"1": "BUCK_SW", "2": "+3V3"}, P, lcsc="C83423")
R("100K", "+3V3", "BUCK_FB", P)             # 0.6 V x (1 + 100/22) = 3.33 V
R("22K", "BUCK_FB", "GND", P)
C("22uF", "+3V3", "GND", P)
R("10K", "+5V_A", "AMIGA_PWR", P)           # 3.0 V at 5 V, 3.5 V at the 5.7 V clamp
R("15K", "AMIGA_PWR", "GND", P)
PWR_FLAGS = ["GND", "+3V3", "+5V_IN", "+5V_A", "V5SYS", "VBUS"]
```
  Before running: check the TLV62569 datasheet's application section (https://www.ti.com/lit/ds/symlink/tlv62569.pdf) for a recommended feed-forward capacitor at 3.3 V out; if it lists one, add `C("10pF"…)` across the 100 kΩ as a DNP pad and note the page.

- [ ] **Step 3:** `bash tools/export_netlist.sh && python -m pytest -q tests/test_power.py` → all pass except `test_amiga_pwr_sense` (needs U1, task 6).
- [ ] **Step 4: commit** "Design: power path with eFuse, diode OR and buck".

### Task 6: ESP32-S3 module, USB-C, headers, buttons, LED, test pads

**Files:**
- Modify: `hardware/design.py` (blocks D, E, F)
- Create: `tests/test_esp.py`, `tests/test_bom.py`

- [ ] **Step 1: failing tests** `tests/test_esp.py`:

```python
from tests.fd import between, esp_net, is_nc, parts_between, pulls


def test_module(nl):
    assert nl.components["U1"]["value"] == "ESP32-S3-WROOM-1-N16R8"
    assert nl.components["U1"]["fields"].get("LCSC") == "C2913202"
    assert nl.net_of_function("U1", "3V3") == "+3V3"
    assert all(nl.net_of("U1", p) == "GND" for p in (1, 40, 41))


def test_left_alone(nl):
    for gpio in (3, 12, 18, 35, 36, 37, 45, 46):
        assert is_nc(esp_net(nl, gpio)), gpio


def test_boot_and_reset(nl):
    assert esp_net(nl, 0) == "BOOT" and pulls(nl, "BOOT") == [("10K", "+3V3")]
    assert not parts_between(nl, "BOOT", "GND", "C")                       # no capacitor on GPIO0
    assert between(nl, "SW1") == {"BOOT", "GND"}
    en = nl.net_of_function("U1", "EN")
    assert pulls(nl, en) == [("10K", "+3V3")]
    assert [nl.components[c]["value"] for c in parts_between(nl, en, "GND", "C")] == ["1uF"]
    assert between(nl, "SW2") == {en, "GND"}


def test_usb(nl):
    assert esp_net(nl, 19) == "USB_DN" and esp_net(nl, 20) == "USB_DP"
    for esp_side, conn_side in (("USB_DP", "USB_DP_C"), ("USB_DN", "USB_DN_C")):
        refs = parts_between(nl, esp_side, conn_side)
        assert len(refs) == 1 and nl.components[refs[0]]["value"] == "22"
    assert nl.net_of("J3", "A6") == nl.net_of("J3", "B6") == "USB_DP_C"
    assert nl.net_of("J3", "A7") == nl.net_of("J3", "B7") == "USB_DN_C"
    for cc in ("A5", "B5"):
        net = nl.net_of("J3", cc)
        assert pulls(nl, net) == [("5K1", "GND")]
    assert nl.net_of("J3", "A5") != nl.net_of("J3", "B5")                  # two separate 5.1k
    assert {nl.net_of("U7", 1), nl.net_of("U7", 3)} == {"USB_DP_C", "USB_DN_C"}
    assert nl.net_of("U7", 5) == "VBUS" and nl.net_of("U7", 2) == "GND"


def test_led_uart_spare(nl):
    assert esp_net(nl, 2) == "LED"
    assert esp_net(nl, 43) == "ESP_TXD0" and esp_net(nl, 44) == "ESP_RXD0"
    tx = parts_between(nl, "ESP_TXD0", "UART_TX")
    assert len(tx) == 1 and nl.components[tx[0]]["value"] == "470"
    en = nl.net_of_function("U1", "EN")
    assert [nl.net_of("J4", p) for p in range(1, 7)] == ["UART_TX", "ESP_RXD0", en, "BOOT", "+3V3", "GND"]
    assert [nl.net_of("J5", p) for p in range(1, 7)] == ["GPIO13", "GPIO14", "GPIO47", "GPIO48", "+3V3", "GND"]
    for g in (13, 14, 47, 48):
        assert esp_net(nl, g) == f"GPIO{g}"
```

  `tests/test_bom.py`:

```python
from tools.netlist import parse_ohms


def test_every_fitted_part_has_lcsc(nl):
    for ref, c in nl.components.items():
        if ref.startswith("#") or not nl.fitted(ref) or ref.startswith(("TP", "H", "FID", "J4", "J5")):
            continue
        assert c["fields"].get("LCSC", "").startswith("C"), ref


def test_resistor_values_parse(nl):
    for ref, c in nl.components.items():
        if ref.startswith("R"):
            parse_ohms(c["value"])


def test_test_pads(nl):
    nets = {nl.net_of(r, 1) for r in nl.components if r.startswith("TP")}
    need = {"_DKRD", "DKRD_N", "_INDEX", "INDEX_N", "_SEL0", "SEL0", "_STEP", "STEP", "_MTR0", "MTR0",
            "+5V_A", "V5SYS", "VBUS", "+3V3", "GND"}
    en = nl.net_of_function("U1", "EN")
    assert need | {en} <= nets
```

- [ ] **Step 2: append blocks D–F:**

```python
# --- D: ESP32-S3 module --------------------------------------------------------------------------------------
esp = {"1": "GND", "40": "GND", "41": "GND", "3V3": "+3V3", "EN": "ESP_EN", "IO0": "BOOT", "IO1": "AMIGA_PWR",
       "IO2": "LED", "USB_D-": "USB_DN", "USB_D+": "USB_DP", "TXD0": "ESP_TXD0", "RXD0": "ESP_RXD0",
       "IO13": "GPIO13", "IO14": "GPIO14", "IO47": "GPIO47", "IO48": "GPIO48"}
for g in (3, 12, 18, 35, 36, 37, 45, 46):
    esp[f"IO{g}"] = None
for sig, _, _, gpio, *_ in INPUTS:
    esp[f"IO{gpio}"] = sig
for sig, _, gpio, *_ in OUTPUTS:
    esp[f"IO{gpio}"] = f"{sig}_N"
part("U1", "RF_Module:ESP32-S3-WROOM-1", "ESP32-S3-WROOM-1-N16R8", "RF_Module:ESP32-S3-WROOM-1", esp, E,
     lcsc="C2913202")
C("22uF", "+3V3", "GND", E)
C("100nF", "+3V3", "GND", E)
R("10K", "+3V3", "ESP_EN", E)
C("1uF", "ESP_EN", "GND", E)
R("10K", "+3V3", "BOOT", E)
BTN = "Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A"
part("SW1", "Switch:SW_Push", "BOOT", BTN, {"1": "BOOT", "2": "GND"}, E, lcsc="C318884")
part("SW2", "Switch:SW_Push", "RESET", BTN, {"1": "ESP_EN", "2": "GND"}, E, lcsc="C318884")

# --- E: USB-C ------------------------------------------------------------------------------------------------
part("J3", "FluxDrive:TYPE-C16PIN", "USB-C", "FluxDrive:USB-C-SMD_TYPE-C16PIN",
     {"A1B12": "GND", "B1A12": "GND", "A4B9": "VBUS", "B4A9": "VBUS", "A5": "USB_CC1", "B5": "USB_CC2",
      "A6": "USB_DP_C", "B6": "USB_DP_C", "A7": "USB_DN_C", "B7": "USB_DN_C", "A8": None, "B8": None,
      "1": "GND", "2": "GND", "3": "GND", "4": "GND"}, U, lcsc="C393939")
R("5K1", "USB_CC1", "GND", U)
R("5K1", "USB_CC2", "GND", U)
part("U7", "Power_Protection:USBLC6-2SC6", "USBLC6-2SC6", "Package_TO_SOT_SMD:SOT-23-6",
     {"1": "USB_DN_C", "6": "USB_DN_C", "3": "USB_DP_C", "4": "USB_DP_C", "5": "VBUS", "2": "GND"}, U, lcsc="C2687116")
R("22", "USB_DP_C", "USB_DP", U)
R("22", "USB_DN_C", "USB_DN", U)
C("10pF", "USB_DP", "GND", U, dnp=True)
C("10pF", "USB_DN", "GND", U, dnp=True)

# --- F: headers, LED, test pads, mechanics -------------------------------------------------------------------
HDR6 = "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical"
R("470", "ESP_TXD0", "UART_TX", F)
part("J4", "Connector_Generic:Conn_01x06", "UART / recovery", HDR6,
     {"1": "UART_TX", "2": "ESP_RXD0", "3": "ESP_EN", "4": "BOOT", "5": "+3V3", "6": "GND"}, F, in_bom=False)
part("J5", "Connector_Generic:Conn_01x06", "Spare GPIO", HDR6,
     {"1": "GPIO13", "2": "GPIO14", "3": "GPIO47", "4": "GPIO48", "5": "+3V3", "6": "GND"}, F, in_bom=False)
R("1K", "LED", "LED_A", F)
part("D3", "Device:LED", "LED red", "LED_SMD:LED_0603_1608Metric", {"1": "GND", "2": "LED_A"}, F, lcsc="C2286")
for net in ("_DKRD", "DKRD_N", "_INDEX", "INDEX_N", "_SEL0", "SEL0", "_STEP", "STEP", "_MTR0", "MTR0",
            "+5V_A", "V5SYS", "VBUS", "+3V3", "ESP_EN", "GND"):
    part(f"TP{next(_n['TP'])}", "Connector:TestPoint", net, "TestPoint:TestPoint_Pad_D1.0mm", {"1": net}, F,
         in_bom=False)
for i in (1, 2):
    part(f"H{i}", "Mechanical:MountingHole", "3.2mm", "MountingHole:MountingHole_3.2mm_M3", {}, F, in_bom=False)
for i in (1, 2, 3):
    part(f"FID{i}", "Mechanical:Fiducial", "Fiducial", "Fiducial:Fiducial_1mm_Mask2mm", {}, F, in_bom=False)
```

- [ ] **Step 3:** `bash tools/export_netlist.sh && python -m pytest -q` → everything passes (tasks 1–6). A failing
  assert means the design or the test disagrees with the spec: fix the one that is wrong against the spec, never
  loosen a test to make it pass.
- [ ] **Step 4: commit** "Design: ESP32-S3 module, USB-C, headers, LED, test pads".

### Task 7: ERC clean, schematic PDF, schematic review

**Files:**
- Modify: `hardware/design.py` (fixes only), `tools/sch_gen.py` (fixes only)
- Create: `FluxDrive_Schematic.pdf`, `docs/reviews/<date>-schematic-review.md`

- [ ] **Step 1:** `"/c/Program Files/KiCad/10.0/bin/kicad-cli.exe" sch erc --severity-error --exit-code-violations -o build/erc.txt FluxDrive.kicad_sch` → exit 0. Typical fixes: a missing PWR_FLAG (add the net to `PWR_FLAGS`), a pin-type conflict from a library symbol (explain in the review record). Warnings are listed in the review record, not ignored silently.
- [ ] **Step 2:** `kicad-cli sch export pdf -o FluxDrive_Schematic.pdf FluxDrive.kicad_sch`; look at every page: labels readable, no overlaps that hide a net name.
- [ ] **Step 3: schematic review.** Four agents, the same roles as the spec review (bus, power/EMC, ESP32-S3, PCB/JLC), each given the spec, `hardware/design.py`, `build/FluxDrive.net` and the PDF. Findings with severity and source; decisions in `docs/reviews/<date>-schematic-review.md`. Blockers and majors are fixed before task 8, each with a test where one fits.
- [ ] **Step 4: commit** "Schematic: ERC clean, PDF, review".

### Task 8: Board from the netlist, outline and placement

**Files:**
- Create: `tools/pcb_sync.py`, `tools/pcb_place.py`, `tests/test_pcb.py`, `FluxDrive.kicad_pcb`

**Interfaces:**
- Consumes: `build/FluxDrive.net`.
- Produces: `FluxDrive.kicad_pcb` with every footprint, nets and the outline; `tools/pcb.py` (copied from Nano-Tek `2623d2f`) for the tests.

- [ ] **Step 1:** `tools/pcb_sync.py`: copy Nano-Tek `2623d2f:tools/pcb_sync.py` and remove everything Rev 1.2 (`DROP_TRACKS_ON`, `OLD_EDGE_STRIP`, the `first` block, the locking); `load_fp` looks in `FluxDrive.pretty` for library `FluxDrive`. If the board file does not exist, start from `pcbnew.NewBoard(path)` with 2 copper layers.
- [ ] **Step 2: failing geometry tests** `tests/test_pcb.py`:

```python
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
```
- [ ] **Step 3:** `tools/pcb_place.py`: outline 56 × 45 mm with its top-left corner at (100, 100); positions (mm, degrees):
  - J1 pin 1 at (107.68, 139.0), rotation 90, even row towards the board interior (check pin 2's position; if it lands outside, use rotation 270 with pin 1 at the other end);
  - U1 at (128.0, 106.75), rotation 0 (antenna end 6 mm past the north edge);
  - U2, U3 in the band y 124–132 under J1 pins 4–24, U4 at the pin 26–34 end (`/DKRD`, pin 30, shortest);
  - J2 vertical at the west end of J1, U5, D1, D2, U6, L1 and their capacitors in the west strip (x 100–112), J3 on the west edge next to U1's GPIO19/20 side, U7 at J3;
  - SW1, SW2, D3 on the east edge outside the keep-out; J4, J5 along the east edge; test pads where their nets pass; H1, H2 at the east and west far corners of the module half; FID1–3 in three corners;
  - resistors of each input/output next to their buffer pin; the 100 kΩ at the buffer, the pull-up and 100 Ω at the connector;
  - a rule area (keep-out, all copper layers, no footprints) under the module's antenna and 1 mm around it, per the WROOM-1 datasheet.
- [ ] **Step 4:** run `pcb_sync` then `pcb_place` with KiCad's Python; `python -m pytest -q tests/test_pcb.py` → pass; `kicad-cli pcb drc --schematic-parity` shows only unconnected items (no courtyard overlaps, no parity errors).
- [ ] **Step 5: commit** "Board: footprints from the netlist, outline and placement".

### Task 9: Routing and DRC

**Files:**
- Create: `tools/pcb_route.py`, `tools/pcb_ripup.py`, `tools/pcb_maze.py`, `tools/pcb_autoroute.py`, `tools/pcb_build.sh`

- [ ] **Step 1:** copy the four tools from Nano-Tek `2623d2f`. Changes: no In1/In2 (2 layers): `prepare()` does not set layer types; `PLANES = {"GND"}`; `pcb_maze` `POWER` = the Power netclass nets of task 3, `LAYERS = (F_Cu, B_Cu)` and no `--inner`; clearance 0.2 mm, edge 0.3 mm.
- [ ] **Step 2: ground strategy:** a GND zone on B.Cu over the whole board (not in the antenna keep-out) and on F.Cu as fill; every GND pad on F.Cu gets a via to B.Cu (the Nano-Tek `pcb_fanout` approach); Freerouting routes all other nets on both layers, with the zones left out of the DSN export.
- [ ] **Step 3:** `tools/pcb_build.sh`: export netlist → sync → place → fan-out → autoroute → dangling cleanup → silk (task 10) → `kicad-cli pcb drc --schematic-parity --refill-zones --save-board --exit-code-violations`. Run it; DRC must end with 0 errors and 0 unconnected items.
- [ ] **Step 4:** check the bottom ground plane: after refill, no GND island without a via, and the plane under the bus signals and the buck unbroken except short crossings (inspect a B.Cu plot, `kicad-cli pcb export svg --layers B.Cu`). Buck switch node ≥ 15 mm from `/DKRD` and the antenna (measure the placement).
- [ ] **Step 5: commit** "Board: routed, DRC clean".

### Task 10: Silkscreen, marks, fit template

**Files:**
- Create: `tools/pcb_silk.py`, `mech/fit_template.pdf`
- Modify: `tests/test_pcb.py`

- [ ] **Step 1: failing tests** (append to `tests/test_pcb.py`):

```python
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
```
- [ ] **Step 2:** `tools/pcb_silk.py` (add-only, idempotent, like the Nano-Tek one): a pin-1 triangle and "1" at J1 pin 1 on F.SilkS and B.SilkS; "this edge to the front of the A500" (or the direction the fit test gives) on both sides; "FluxDrive v1 rev A" and "by Dimmy (Dimitri Hilverda)" on F.SilkS; a 15 × 6 mm box on B.SilkS for the serial number; "JLCJLCJLCJLC" at a free spot on B.SilkS for JLC's order number; header pin names at J4, J5, J2.
- [ ] **Step 3:** fit template: `kicad-cli pcb export pdf --layers Edge.Cuts,F.Courtyard,F.SilkS,F.Fab --scale 1 -o mech/fit_template.pdf FluxDrive.kicad_pcb`; a 50 mm scale bar on F.SilkS to check the print scale.
- [ ] **Step 4:** `python -m pytest -q` → all pass; DRC still 0/0.
- [ ] **Step 5: commit** "Board: silkscreen, marks and fit template".
- [ ] **Step 6 [Dimitri]:** print `mech/fit_template.pdf` at 100 %, check the 50 mm bar, try it in the A500 in both connector variants, report the overhang direction and anything that touches.

### Task 11: Layout review

- [ ] **Step 1:** the same four agents review `FluxDrive.kicad_pcb` (plots per layer, the DRC report, the placement), against the spec §8 and the schematic review record. Decisions in `docs/reviews/<date>-layout-review.md`; blockers and majors fixed, `pcb_build.sh` re-run, tests and DRC clean.
- [ ] **Step 2: commit** "Layout review and fixes".

### Task 12: Production files and README

**Files:**
- Create: `tools/jlc_export.py`, `tools/jlc_production.sh` (from Nano-Tek `2623d2f`), `jlcpcb/production_files/*`, `docs/images/fluxdrive-v1-3d.png`
- Modify: `README.md`

- [ ] **Step 1:** copy the two tools; change `PCB=FluxDrive.kicad_pcb`, output names `*-FluxDrive.*`, gerber layers `F.Cu,B.Cu,F.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts`. Through-hole parts are left out automatically (all pads PTH); the module takes its F.Fab centre (the `BODY_CENTRE` rule already matches `ESP32-`).
- [ ] **Step 2:** run; check: every fitted SMD part with LCSC in the BOM, no through-hole part, CPL refs = BOM refs; the rotation table covers SOIC (`^SOIC-` 270 per the JLCPCB Tools default, to check in JLC's preview), SOT-23-5/6 (180), WSON-8, D_SMA, SW, LED.
- [ ] **Step 3:** `kicad-cli pcb render --side top/bottom` to `docs/images/`; README section "Building one": order settings (2 layers, 1.6 mm, assembly top, economic), hand-soldered parts with LCSC numbers, the parts to check in JLC's placement preview, flashing (BOOT + RESET, USB-C), the power-cable warning.
- [ ] **Step 4: commit** "Production files, render and README".
- [ ] **Step 5 [Dimitri]:** range test with a WROOM-1 dev board in the closed A500 (spec §11.5); then order at JLC.

---

## Self-review (done while writing)

- Spec coverage: §4.1–4.3 → task 4; §5 → task 5; §6, §7 → task 6; §8 → tasks 8–10; §10 costs → checked at
  task 12 against the BOM; §11 items 1–2 → tasks 4–7, 9; items 3, 5, 6 (bench gate, range test, bring-up) belong
  to the firmware plan and task 12 step 5.
- The USB-C part is C393939 with the Nano-Tek footprint (placed by JLC on the Nano-Tek), not C2765186 from the
  review table: same function, proven geometry. The spec's parts table is updated with this plan.
- Placeholders: none; values that depend on a datasheet (TLV62569 feed-forward) name the datasheet and the rule.
