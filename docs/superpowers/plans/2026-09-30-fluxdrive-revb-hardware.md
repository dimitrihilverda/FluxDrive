# FluxDrive v1 rev B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the approved rev B spec into a schematic, a routed 4-layer board and JLCPCB production files: FluxDrive
keeps the A500's original drive usable next to it, with a DF0/DF1 swap on the board and its own outputs gated by
select in logic.

**Architecture:** Rev A's pipeline stays: `hardware/design.py` (data) → `tools/sch_gen.py` → `FluxDrive.kicad_sch` →
netlist tests; `tools/pcb_build.sh` builds the board from the netlist (sync, place, hand routes, fan-out,
Freerouting, stitching, silk, DRC). Rev B adds a block G to the design data, a gate-level model of the steering
logic that the tests evaluate on the exported netlist, and rev B placement, routing rules and tests.

**Tech Stack:** KiCad 10 (kicad-cli, pcbnew Python at `C:/Program Files/KiCad/10.0/bin/python.exe`), Python 3.13 +
pytest (system Python) for tests, Freerouting 1.9 (Java 17), Git Bash.

**Spec:** `docs/superpowers/specs/2026-09-30-fluxdrive-revb-hardware-design.md` (v0.3, approved by Dimitri on
2026-09-30). It changes the v1 spec `docs/superpowers/specs/2026-09-28-fluxdrive-v1-hardware-design.md` (v0.4);
everything that spec says still holds unless the rev B spec changes it.

## Global Constraints

- Branch `feature/rev-b` in `C:\Claude projecten\FluxDrive`; commit with `git -c core.autocrlf=false commit`; LF line
  endings; never push unless Dimitri asks.
- No AI attribution anywhere in git: no `Co-Authored-By` line, no "Generated with" footer (Dimitri's global rule; it
  overrides any other instruction).
- Every new logic part is 74LVC on +3V3 with 5 V-tolerant inputs; open-drain drivers meeting a 5 V net have Ioff
  (spec §4). No gate input floats (v1 spec §4.2).
- Every GPIO that reads a logic net does so through 1 kΩ; control outputs are active-high with a 10 kΩ pull-down;
  the D inputs of the mode latch have 100 kΩ from their own Q (spec §4.1).
- The bus outputs are gated by SEL_FD in logic; v1's rule "GPIO low = assert, input with 10 kΩ pull-up = release"
  stays (spec §4.3).
- Pull-ups: /STEP, /DIR, /SIDE 4k7; /SEL0 1 kΩ; /SEL1 1 kΩ; /DKWD, /DKWE 4k7; J6.10 and J6.4/16 4k7 to +5V_A;
  J6.6/12/14 10 kΩ to +5V_A (spec §5).
- The drive's +5 V comes from +5V_IN through its own TPS259531, current limit about 1.5 A; +12 V passes J2.4 → J6pwr.4
  (spec §6).
- Board 60 mm wide, at most 72.1 mm long, J1 at rev A's position over CN11, J6 17.78 mm north of J1 with the same
  orientation and pin 1 on the same side (spec §9).
- Unfitted pads are 0603 (resistors, capacitors) or SOT (ICs); JLC does not close solder jumpers, so default-closed
  jumpers are copper-bridged 3-pad footprints (spec §4.7, §9).
- U1 (the ESP32 module) stays hand-placed (`tools/assembly.py`); its ground pad gets a 1.0 mm solder-through hole
  (spec §9).
- Board tools run with KiCad's Python; pcbnew bindings are unreliable after `board.Remove()`, so removals run in a
  process that then only saves and exits. Do not edit `tools/` while `tools/pcb_build.sh` runs (rev A LCODE-1).
- Net names in the netlist and on the board carry a leading "/" (local labels); `tools/netlist.py` strips it for the
  netlist tests, the board tests keep it.

## Review Focus

1. **A mode change during a disk access** (a GTi request, the switch, an ESP32 restart in the middle of a track
   read): no select or motor pulse reaches the real drive and FluxDrive never answers a select it does not own — the
   sequential logic test of Task 8 steps these orders.
2. **The bypass or a mode-4 jumper converted in the wrong order** (2–3 bridged before 1–2 is cut): the board must
   refuse to reach a state where two drives answer /SEL0 in any legal configuration — Task 8's combinational test
   evaluates every jumper state and flags illegal ones; Task 13 puts the order on the silkscreen.
3. **No real drive on J6, or J6 plugged without J6pwr**: with nothing on J6, modes 1–3 must leave the bus as a
   stock A500 with FluxDrive as DF0 or no DF0; with an unpowered drive the lines read asserted — Task 6's test checks
   J6's pull-ups hold every J6-only line inactive with nothing plugged in; the README (Task 15) carries the J6pwr rule.
4. **An ESP32 that never boots** (blank flash, crash loop): the A500 must boot from the real drive as stock, with
   /CHNG, /RDY, _KBRESET and every J6 line inactive — Task 8's reset-state test drives every control GPIO undriven
   and with its internal pull-up.
5. **A board rebuilt from the committed scripts** must be the committed board: `tools/pcb_place.py --check` and the
   production-files test (Task 15) fail if placement or CPL drift.

---

## File structure

| File | Change | Responsibility |
|---|---|---|
| `hardware/design.py` | modify | rev B parts and nets: block A inputs, block B gated outputs, block C drive power, block F J5 and test pads, new block G |
| `FluxDrive.kicad_sym` | modify | adds the `74LVC1G157` symbol (copied from the Nano-Tek library) |
| `FluxDrive.pretty/ESP32-S3-WROOM-1.kicad_mod` | modify | ground-pad solder-through hole |
| `tests/logic.py` | create | gate-level evaluator of the exported netlist |
| `tests/test_logic_model.py` | create | tests of the evaluator itself on tiny netlists |
| `tests/test_swap.py` | create | rev B steering logic: exhaustive combinational test and sequential scenarios |
| `tests/test_bus.py`, `tests/test_power.py`, `tests/test_esp.py`, `tests/test_bom.py` | modify | rev B nets, pull-ups, GPIOs, J5, BOM rules |
| `tests/test_pcb.py` | modify | rev B outline, J6, zones, clearances, via rules, stitching, silk, net-based lookups |
| `tools/pcb_place.py` | modify | rev B outline and placement, net-based row A, J6 zones |
| `tools/pcb_prefan.py` | modify | J1→J6 pass-through routes, drive power path, redone rev A hand routes |
| `tools/pcb_fanout.py` | modify | own +3V3 via for every IC supply pin and decoupling pad |
| `tools/pcb_stitch.py` | modify | GND stitching along the antenna keep-out border |
| `tools/pcb_silk.py` | modify | rev B texts and labels |
| `tools/fit_template.sh`, `tools/jlc_export.py`, `tools/jlc_production.sh`, `tools/pcb_maze.py` | modify | the deferred minors (Task 1) |
| `README.md`, `docs/superpowers/specs/2026-09-28-fluxdrive-v1-hardware-design.md`, `docs/reviews/*` | modify/create | rev B build notes, v1 spec v0.5, review records |

## Names every task uses

Refs of R, C and TP are assigned in the order parts are added and are **not** stable across tasks: tests and tools find
them by their nets. The refs below are fixed by name in `part()` calls.

| Ref | Part (value) | Pins → nets |
|---|---|---|
| U8 | `74LVC74A` (symbol `74xx:74HC74`, TSSOP-14, C6100) | 1 CLR_A, 2 DF0_REQ, 3 MODE_CLK, 4 PRE_A, 5 DF0_FD, 6 NC; 13 CLR_B, 12 DF1_REQ, 11 MODE_CLK, 10 PRE_B, 9 DF1_EN, 8 NC; 7 GND, 14 +3V3 |
| U9 | `TPS259531` (C2155674) | 1 DRV_DVDT, 2 EFUSE_EN, 3/4 +5V_IN, 5 +5V_DRIVE, 6 NC, 7 DRV_ILM, 8/9 GND |
| U10 | `74LVC32A` (`74xx:74LS32`, TSSOP-14, C6087) | (1,2→3) DKRD_N, SEL_FD_N → DKRD_G; (4,5→6) TRK0_N, SEL_FD_N → TRK0_G; (9,10→8) WPROT_N, SEL_FD_N → WPROT_G; (12,13→11) RDY_N, SEL_FD_N → RDY_G |
| U11 | `74LVC32A` | (1,2→3) CHNG_N, SEL_FD_N → CHNG_G; (4,5→6) INDEX_N, SEL_FD_N → INDEX_G; (9,10→8) SEL0, SEL1 → BUSY; (12,13→11) GND, GND → NC |
| U12 | `74LVC1G157` (`FluxDrive:74LVC1G157`, SOT-363, C135822; pins 1 I1, 2 GND, 3 I0, 4 Y, 5 VCC, 6 S) | S DF1_EN, I1 SEL1, I0 GND, Y SEL1_EN |
| U13 | `74LVC1G157` | S DF0_FD, I1 SEL0, I0 SEL1_EN, Y SEL_FD |
| U14 | `74LVC1G157` | S DF0_FD, I0 SEL0, I1 M4_SEL, Y REAL_SEL |
| U15 | `74LVC1G157` | S DF0_FD, I0 MTR0, I1 M4_MTR, Y REAL_MTR |
| U16 | `74LVC1G157` | S BUSY, I0 MODE_CLK_REQ, I1 GND, Y MODE_CLK |
| U17 | `SN74LVC2G07` (`74xGxx:74LVC2G07`, SOT-23-6, C37708) | 1 CHNG_G → 6 CHNG_D; 3 INDEX_G → 4 INDEX_D; 2 GND, 5 +3V3 |
| U18 | `SN74LVC2G06` (`74xGxx:74LVC2G06`, SOT-23-6, C402162) | 1 REAL_SEL → 6 J6_SEL_D; 3 REAL_MTR → 4 J6_MTR_D; 2 GND, 5 +3V3 |
| U19 | `SN74LVC1G06` (`74xGxx:74LVC1G06`, SOT-23-5, C840103) | 2 RST_REQ → 4 KBRESET; 3 GND, 5 +3V3 |
| U20 | `SN74LVC1G38` (`74xGxx:74LVC1G38`, SOT-23-5, C2867613) | 1 CHNG_REQ, 2 SEL0 → 4 VCHNG_D; 3 GND, 5 +3V3 |
| U21 | `74LVC1G157`, DNP | S DF0_FD, I1 SEL1_EN, I0 GND, Y M4_SEL_Q |
| U22 | `SN74LVC1G175` (`74xGxx:74LVC1G175`, SOT-23-6), DNP | 1 CLK SEL1, 3 D M4_MOTOR, 6 CLR DF1_EN, 4 Q M4_MTR_Q; 2 GND, 5 +3V3 |
| U23 | `SN74LVC1G38`, DNP | 1 M4_SEL_Q, 2 M4_MTR_N → 4 ID_D |
| U2 | (rev A) | pins 9 → 8 now SEL_FD → SEL_FD_N |
| U3 | (rev A) | 1 RST_B → 2 RST_ACT; 5 MTRX_B → 6 M4_MOTOR; 13 M4_MTR_Q → 12 M4_MTR_N (rev A's J1 pin 4/14/6 gates); 3→4 SEL0, 11→10 SEL1, 9→8 MTR0 as rev A |
| U4 | (rev A) | 3→4 DKRD, 13→12 TRK0, 1→2 WPROT, 5→6 RDY (inputs now the `_G` nets); 9, 11 → +3V3; 8, 10 NC |
| J5 | `Conn_01x04`, 1×4 2.54 mm | 1 GND, 2 +3V3, 3 GPIO18, 4 GPIO3 |
| J6 | 2×17 box header (C601943) | odd GND, 3 NC; 2 _CHNG, 4 J6_MTR, 6 J6_PIN6, 8 _INDEX, 10 J6_SEL, 12 J6_PIN12, 14 J6_PIN14, 16 J6_MTR, 18 _DIR, 20 _STEP, 22 _DKWD, 24 _DKWE, 26 _TRK0, 28 _WPROT, 30 _DKRD, 32 _SIDE, 34 _RDY |
| J7 | `Conn_01x03`, 1×3 2.54 mm THT pads | 1 J7_FD, 2 GND, 3 J7_REAL |
| J8 | `FluxDrive:171825-4` (J6pwr, C210162) | 1 +5V_DRIVE, 2/3 GND, 4 +12V |
| J9 | `Connector:TestPoint`, THT pad | 1 KBRESET (the reset wire) |
| J10 | `Connector:TestPoint`, THT pad | 1 MTRX (the mode-4 motor wire) |
| JP1 | `SolderJumper_3_Bridged12` (pins 1 A, 2 C, 3 B) | 1 J6_SEL_D, 2 J6_SEL, 3 _SEL0 (bypass) |
| JP2 | `SolderJumper_3_Bridged12` | 1 J6_MTR_D, 2 J6_MTR, 3 _MTR0 (bypass) |
| JP3 | `SolderJumper_3_Bridged12` | 1 GND, 2 M4_SEL, 3 M4_SEL_Q (mode 4) |
| JP4 | `SolderJumper_3_Bridged12` | 1 GND, 2 M4_MTR, 3 M4_MTR_Q (mode 4) |
| JP5 | `SolderJumper_3_Bridged12` | 1 CLR_A, 2 POR_A, 3 PRE_A (DF0 at power-on) |
| JP6 | `SolderJumper_2_Open` | CLR_A – GND (REAL, clear) |
| JP7 | `SolderJumper_2_Open` | PRE_A – +3V3 (REAL, preset) |
| D5, D6 | 1N4148W (`Device:D`, SOD-123, C81598) | D5: A CLR_B, K +3V3; D6: A POR_A, K +3V3 |

**GPIOs (rev B):** IO47 MODE_CLK_REQ, IO48 DF0_REQ, IO13 DF1_REQ, IO14 CHNG_REQ, IO10 RST_REQ, IO12 DF0_STATE,
IO8 DF1_STATE, IO4 RST_ACT_IO, IO17 SEL0_IO, IO9 SEL1_IO, IO11 MTR0_IO, IO18 GPIO18, IO3 GPIO3; rev A's inputs STEP 6,
DIR 7, SIDE 15, DKWD 5, DKWE 16 and outputs DKRD_N 38, INDEX_N 39, TRK0_N 40, WPROT_N 41, CHNG_N 42, RDY_N 21 unchanged;
IO35, 36, 37, 45, 46 left alone.

**Resistors and capacitors of block G** (found by net in tests):
1 kΩ SEL0–SEL0_IO, SEL1–SEL1_IO, MTR0–MTR0_IO, DF0_FD–DF0_STATE, DF1_EN–DF1_STATE, RST_ACT–RST_ACT_IO, J7_FD–PRE_A,
J7_REAL–CLR_A; 10 kΩ pull-ups CLR_A, PRE_A, CLR_B, PRE_B (+3V3); 10 kΩ pull-downs MODE_CLK_REQ, CHNG_REQ, RST_REQ;
100 kΩ DF0_FD–DF0_REQ, DF1_EN–DF1_REQ; 1 µF CLR_B–GND, POR_A–GND; 100 nF J7_FD–GND, J7_REAL–GND; 4k7 J6_SEL_D and
J6_MTR_D to +5V_A; 10 kΩ J6_PIN6/12/14 to +5V_A; 33 Ω VCHNG_D–_CHNG; 100 Ω KBRESET–RST_B, 100 kΩ RST_B–+3V3;
DNP: 4k7 MTRX–+5V_A, 100 Ω MTRX–MTRX_B, 33 Ω ID_D–_RDY; fitted 100 kΩ MTRX_B–+3V3 and M4_MTR_Q–GND; one 100 nF
+3V3–GND per new IC (DNP, 0603, for U21–U23); drive power: 22 nF DRV_DVDT–GND, 1K5 DRV_ILM–GND (2000/1500 + 0.04 =
1.37 A, "about 1.5 A" in spec §6, a value already in the BOM), 22 µF and 100 nF +5V_DRIVE–GND.

---

### Task 1: Deferred tool and test minors

**Files:**
- Modify: `tools/fit_template.sh`, `tools/jlc_export.py:88-95`, `tools/jlc_production.sh:18`, `tools/pcb_maze.py`
  (widths), `tests/test_pcb.py`
- Test: `tests/test_tools.py`, `tests/test_pcb.py`

The minors of `docs/reviews/2026-09-30-build-rulings.md` ("Deferred minor findings") and Mez's cosmetic items, before
rev B changes anything else (spec §9).

- [ ] **Step 1: failing tests** — append to `tests/test_tools.py`:

```python
def test_bom_comment_lists_every_value(tmp_path):
    """Build-rulings minor: parts grouped in one BOM line with different values show all of them (SW1 BOOT and SW2
    RESET gave the comment "BOOT")."""
    from tools.jlc_export import comment
    assert comment(["BOOT", "RESET"]) == "BOOT/RESET"
    assert comment(["100K", "100K"]) == "100K"


def test_gerber_zip_holds_files_only():
    """Build-rulings minor: kicad-cli leaves an org.kicad.kicad/ directory; the zip must not carry it."""
    import pathlib
    import zipfile
    zp = pathlib.Path(__file__).resolve().parents[1] / "jlcpcb" / "production_files" / "GERBER-FluxDrive.zip"
    assert all(not n.endswith("/") for n in zipfile.ZipFile(zp).namelist())
```

and to `tests/test_pcb.py` (replacing the docstring of `test_pin1_marked_both_sides` "within 4 mm" with "within 6 mm"):

```python
def test_rule_areas_cover_their_layers(board):
    """Build-rulings minor: the rule areas are checked by layer and flag, not by name only."""
    want = {"J1 rows F": (["F.Cu"], "tracks"), "J1 rows B": (["B.Cu"], "tracks"),
            "antenna edge": (None, "tracks"), "module underside": (["F.Cu"], "tracks"),
            "USB-C body": (["F.Cu"], "tracks")}
    from tools.netlist import _child, _children
    zones = {(_child(z, "name") or [None, ""])[1]: z for z in _children(board, "zone") if _child(z, "keepout")}
    for name, (layers, what) in want.items():
        z = next(v for k, v in zones.items() if k.startswith(name))
        ko = _child(z, "keepout")
        assert _child(ko, what)[1] == "not_allowed", name
        if layers:
            lay = _child(z, "layers") or _child(z, "layer")
            assert list(lay[1:]) == layers, (name, lay)


def test_antenna_area_copper_free_on_every_layer(board):
    """Build-rulings minor: the antenna test also looks at zone fills and pads, not only tracks and vias."""
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
```

- [ ] **Step 2: run them** — `python -m pytest -q -p no:cacheprovider tests/test_tools.py tests/test_pcb.py -k
  "comment or zip or rule_areas_cover or copper_free"`. Expected: `test_bom_comment_lists_every_value` fails with
  `ImportError: cannot import name 'comment'`; `test_gerber_zip_holds_files_only` fails on `org.kicad.kicad/`; the two
  board tests pass on rev A's board (they are coverage, as rev A's `test_connector_zone_free` was) — note that in the
  ledger.

- [ ] **Step 3: implement.**
  - `tools/jlc_export.py`: add near the top

```python
def comment(values):
    """BOM comment for a group of parts: every distinct value, in order of first appearance, joined by "/"."""
    seen = []
    for v in values:
        if v not in seen:
            seen.append(v)
    return "/".join(seen)
```

    and in `main()` replace the comment expression in `rows.append(...)` with
    `comment([p["value"] for p in sorted(ps, key=lambda p: natural(p["ref"]))])`.
  - `tools/jlc_production.sh` line 18: zip only regular files —
    `[z.write(f, f.name) for f in sorted(src.iterdir()) if f.is_file()]`.
  - `tools/fit_template.sh`: delete the old STEP first and accept exit 2 only when every error line is one of the
    known models:

```bash
rm -f mech/FluxDrive.step
if ! out=$("$CLI" pcb export step --subst-models --force -o mech/FluxDrive.step "$PCB" 2>&1); then
    unknown=$(grep -i "error\|cannot\|could not\|not found" <<< "$out" \
        | grep -v -e "Cannot use VRML models" -e "for SW1" -e "for SW2" -e "for U5" -e "for U9" \
                  -e "SW_Push_1P1T_XKB_TS-1187A" -e "Texas_DSG0008A_WSON-8" || true)
    if [ -n "$unknown" ] || [ ! -s mech/FluxDrive.step ]; then
        echo "$out"
        exit 1
    fi
    echo "note: no STEP model for the USB-C (3.3 mm), the buttons and the eFuses; the STEP leaves them out"
fi
```

  - `tools/pcb_maze.py` (LCODE-8): read the track widths from `FluxDrive.kicad_pro`'s netclasses instead of the
    hard-coded constants, and use `width_of(net)` wherever the maze router now picks a width:

```python
import fnmatch
import json


def netclass_widths(pro_path):
    """({class: track width mm}, [(net pattern, class)]) from a KiCad 10 project file."""
    ns = json.loads(pathlib.Path(pro_path).read_text(encoding="utf-8"))["net_settings"]
    widths = {c["name"]: c["track_width"] for c in ns["classes"]}
    return widths, [(p["pattern"], p["netclass"]) for p in ns.get("netclass_patterns", [])]


def width_of(net, widths, patterns):
    for pat, cls in patterns:
        if fnmatch.fnmatch(net, pat):
            return widths.get(cls, widths["Default"])
    return widths["Default"]
```

    A test in `tests/test_tools.py`: `width_of("/+5V_A", *netclass_widths(ROOT / "FluxDrive.kicad_pro")) == 0.3` and
    `width_of("/STEP_B", ...) == 0.2` (the Power and Default classes).
- [ ] **Step 4: run** `bash tools/jlc_production.sh` and `python -m pytest -q -p no:cacheprovider`. Expected: all pass
  (the BOM line for SW1/SW2 now reads `BOOT/RESET`).
- [ ] **Step 5: commit** — `git -c core.autocrlf=false add -A tools tests jlcpcb && git -c core.autocrlf=false commit
  -m "Tools and tests: the deferred minors of rev A"`.

### Task 2: Logic evaluator and the 1G157 symbol

**Files:**
- Create: `tests/logic.py`, `tests/test_logic_model.py`
- Modify: `FluxDrive.kicad_sym` (add `74LVC1G157`)

**Interfaces:**
- Produces: `tests.logic.evaluate(nl, sources, state=None, bridged=None, fit=()) -> dict[str, int | None]`;
  `tests.logic.STRONG, OD, PULL, WEAK` (3, 2, 1, 0.5); `tests.logic.Conflict`; `tests.logic.NoFixedPoint`;
  `tests.logic.GATES` (value → gate list), `tests.logic.FLIPFLOPS`.
- Consumes: `tools.netlist.Netlist` (`components`, `nets`, `fitted()`), `tools.netlist.parse_ohms`.

- [ ] **Step 1: failing tests** — `tests/test_logic_model.py`:

```python
"""The evaluator of tests/logic.py on tiny hand-made netlists."""
import pytest

from tests.logic import OD, PULL, STRONG, WEAK, Conflict, evaluate
from tools.netlist import Netlist


def nl_of(parts):
    """parts: [(ref, value, {pin: net}, fitted)] -> Netlist."""
    nl = Netlist()
    for ref, value, pins, fitted in parts:
        nl.components[ref] = {"value": value, "footprint": "", "fields": {} if fitted else {"dnp": ""}}
        for pin, net in pins.items():
            nl.nets.setdefault(net, []).append((ref, pin, ""))
    return nl


def test_inverter_and_pull_up():
    nl = nl_of([("U1", "74LVC14A", {"1": "A", "2": "Y", "7": "GND", "14": "+3V3"}, True),
                ("R1", "10K", {"1": "A", "2": "+3V3"}, True)])
    assert evaluate(nl, {})["Y"] == 0                       # pulled-up input, inverted
    assert evaluate(nl, {"A": (0, STRONG)})["Y"] == 1


def test_open_drain_wired_and_through_series_resistor():
    nl = nl_of([("U1", "SN74LVC2G06", {"1": "IN", "6": "OUT", "3": "GND", "4": "X", "2": "GND", "5": "+3V3"}, True),
                ("R1", "4K7", {"1": "OUT", "2": "+5V_A"}, True),
                ("R2", "100", {"1": "OUT", "2": "FAR"}, True),
                ("R3", "100K", {"1": "FAR", "2": "+3V3"}, True)])
    assert evaluate(nl, {"IN": (0, STRONG)})["FAR"] == 1
    v = evaluate(nl, {"IN": (1, STRONG)})
    assert v["OUT"] == 0 and v["FAR"] == 0                  # the 100 ohm carries the low past the 100k


def test_mux_and_or():
    nl = nl_of([("U1", "74LVC1G157", {"6": "S", "3": "I0", "1": "I1", "4": "Y", "2": "GND", "5": "+3V3"}, True),
                ("U2", "74LVC32A", {"1": "Y", "2": "B", "3": "Z", "7": "GND", "14": "+3V3"}, True)])
    v = evaluate(nl, {"S": (1, STRONG), "I0": (0, STRONG), "I1": (1, STRONG), "B": (0, STRONG)})
    assert v["Y"] == 1 and v["Z"] == 1


def test_flip_flop_preset_clear_and_state():
    ff = {"1": "CLR", "2": "D", "3": "CLK", "4": "PRE", "5": "Q", "7": "GND", "14": "+3V3",
          "13": "+3V3", "12": "GND", "11": "GND", "10": "+3V3", "9": "Q2"}
    nl = nl_of([("U1", "74LVC74A", ff, True), ("R1", "10K", {"1": "CLR", "2": "+3V3"}, True),
                ("R2", "10K", {"1": "PRE", "2": "+3V3"}, True)])
    assert evaluate(nl, {}, state={("U1", "A"): 1})["Q"] == 1
    assert evaluate(nl, {"CLR": (0, OD)}, state={("U1", "A"): 1})["Q"] == 0
    assert evaluate(nl, {"PRE": (0, OD), "CLR": (0, OD)}, state={("U1", "A"): 0})["Q"] == 1   # both low: Q high


def test_bridged_jumper_joins_nets_and_rail_wins():
    nl = nl_of([("JP1", "SolderJumper_2_Open", {"1": "PRE", "2": "+3V3"}, True),
                ("R1", "1K", {"1": "SW", "2": "PRE"}, True)])
    assert evaluate(nl, {"SW": (0, STRONG)})["PRE"] == 0
    assert evaluate(nl, {"SW": (0, STRONG)}, bridged={"JP1": [("1", "2")]})["PRE"] == 1


def test_weak_pull_up_loses_to_10k_pull_down():
    nl = nl_of([("R1", "10K", {"1": "REQ", "2": "GND"}, True)])
    assert evaluate(nl, {"REQ": (1, WEAK)})["REQ"] == 0


def test_conflict_is_reported():
    nl = nl_of([("U1", "74LVC14A", {"1": "A", "2": "Y", "7": "GND", "14": "+3V3"}, True)])
    with pytest.raises(Conflict):
        evaluate(nl, {"A": (0, STRONG), "Y": (0, STRONG)})


def test_dnp_parts_are_open_unless_fitted():
    nl = nl_of([("U1", "74LVC14A", {"1": "A", "2": "Y", "7": "GND", "14": "+3V3"}, False),
                ("R1", "10K", {"1": "Y", "2": "GND"}, True)])
    assert evaluate(nl, {"A": (1, STRONG)})["Y"] == 0                     # DNP inverter: only the pull-down
    assert evaluate(nl, {"A": (0, STRONG)}, fit={"U1"})["Y"] == 1
```

- [ ] **Step 2: run** `python -m pytest -q -p no:cacheprovider tests/test_logic_model.py`. Expected: FAIL,
  `ModuleNotFoundError: No module named 'tests.logic'`.

- [ ] **Step 3: implement** `tests/logic.py`:

```python
"""Gate-level model of FluxDrive's logic, evaluated on the exported netlist (rev B spec §10.1).

Every net settles to 0 or 1 from its drivers; the strongest driver wins:
  4    a rail (+3V3, +5V_A, +5V_IN, +5V_DRIVE, +12V -> 1; GND -> 0), and every net joined to it by a bridged jumper
  3    STRONG: a push-pull gate output, a flip-flop Q, or an external push-pull source (a GPIO that drives)
  2    OD: an open-drain output that pulls low, an external open-collector source (the Amiga's CIA, Gary, a drive),
       or the far side of a resistor of at most 1 kOhm whose near side is at OD or stronger
  1    PULL: a resistor to a rail, or a resistor of more than 1 kOhm to a net at OD or stronger
  0.5  WEAK: an ESP32 internal pull-up (about 45 kOhm)
Two drivers of the same top strength with different values are a Conflict. Capacitors and diodes are open (the
settled state). Parts marked DNP are left out unless their ref is in `fit`.
"""
from collections import defaultdict

from tools.netlist import parse_ohms

STRONG, OD, PULL, WEAK = 3, 2, 1, 0.5
RAIL = {"+3V3": 1, "+5V_A": 1, "+5V_IN": 1, "+5V_DRIVE": 1, "+12V": 1, "V5SYS": 1, "GND": 0}
# value -> [(kind, input pins, output pin)]; mux inputs are (S, I0, I1)
GATES = {
    "74LVC14A": [("inv", ("1",), "2"), ("inv", ("3",), "4"), ("inv", ("5",), "6"), ("inv", ("9",), "8"),
                 ("inv", ("11",), "10"), ("inv", ("13",), "12")],
    "74LVC07A": [("odbuf", ("1",), "2"), ("odbuf", ("3",), "4"), ("odbuf", ("5",), "6"), ("odbuf", ("9",), "8"),
                 ("odbuf", ("11",), "10"), ("odbuf", ("13",), "12")],
    "SN74LVC2G07": [("odbuf", ("1",), "6"), ("odbuf", ("3",), "4")],
    "74LVC32A": [("or", ("1", "2"), "3"), ("or", ("4", "5"), "6"), ("or", ("9", "10"), "8"),
                 ("or", ("12", "13"), "11")],
    "74LVC1G157": [("mux", ("6", "3", "1"), "4")],
    "SN74LVC2G06": [("odinv", ("1",), "6"), ("odinv", ("3",), "4")],
    "SN74LVC1G06": [("odinv", ("2",), "4")],
    "SN74LVC1G38": [("odnand", ("1", "2"), "4")],
}
# value -> [(name, CLR pin, PRE pin or None, D pin, CLK pin, Q pin)]
FLIPFLOPS = {"74LVC74A": [("A", "1", "4", "2", "3", "5"), ("B", "13", "10", "12", "11", "9")],
             "SN74LVC1G175": [("A", "6", None, "3", "1", "4")]}


class Conflict(Exception):
    pass


class NoFixedPoint(Exception):
    pass


def _pins(nl):
    out = defaultdict(dict)
    for net, nodes in nl.nets.items():
        for ref, pin, _ in nodes:
            out[ref][pin] = net
    return out


def _live(nl, ref, fit):
    return nl.fitted(ref) or ref in fit


def evaluate(nl, sources, state=None, bridged=None, fit=(), max_iter=80):
    """{net: 0, 1 or None} after settling. sources: {net: (value, strength)}; state: {(ref, "A"/"B"): q} for the
    flip-flops (missing = 0); bridged: {ref: [(pin, pin), ...]} for jumpers and switch pads that are joined — every
    footprint whose value or footprint names "Bridged12" is joined on pins 1-2 unless its ref is given here."""
    state = state or {}
    pins = _pins(nl)
    parent = {n: n for n in nl.nets}

    def find(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    joins = dict(bridged or {})
    for ref, comp in nl.components.items():
        if ref not in joins and "Bridged12" in comp["value"] + comp["footprint"]:
            joins[ref] = [("1", "2")]
    for ref, pairs in joins.items():
        for a, b in pairs:
            na, nb = pins[ref].get(a), pins[ref].get(b)
            if na and nb:
                parent[find(na)] = find(nb)
    resistors = []
    for ref, comp in nl.components.items():
        if ref.startswith("R") and ref[1:].isdigit() and _live(nl, ref, fit):
            a, b = pins[ref].get("1"), pins[ref].get("2")
            if a and b:
                resistors.append((find(a), find(b), a, b, parse_ohms(comp["value"])))
    val = {find(n): None for n in nl.nets}
    stren = {k: 0 for k in val}
    for _ in range(max_iter):
        drv = defaultdict(list)
        for n in nl.nets:
            if n in RAIL:
                drv[find(n)].append((4, RAIL[n]))
        for n, (v, s) in sources.items():
            if n in parent:
                drv[find(n)].append((s, v))
        for ra, rb, a, b, ohms in resistors:
            for x, y, yn in ((ra, rb, b), (rb, ra, a)):
                if yn in RAIL:
                    drv[x].append((PULL, RAIL[yn]))
                elif val[y] is not None:
                    if ohms <= 1000:
                        s = min(stren[y], OD)
                        if s >= PULL:
                            drv[x].append((s, val[y]))
                    elif stren[y] >= OD:
                        drv[x].append((PULL, val[y]))
        for ref, comp in nl.components.items():
            if not _live(nl, ref, fit):
                continue
            p = pins[ref]
            for kind, ins, out in GATES.get(comp["value"], []):
                if out not in p:
                    continue
                iv = [val[find(p[i])] if i in p else None for i in ins]
                if None in iv:
                    continue
                o = find(p[out])
                if kind == "inv":
                    drv[o].append((STRONG, 1 - iv[0]))
                elif kind == "or":
                    drv[o].append((STRONG, iv[0] | iv[1]))
                elif kind == "mux":
                    drv[o].append((STRONG, iv[2] if iv[0] else iv[1]))
                elif kind == "odbuf" and iv[0] == 0:
                    drv[o].append((OD, 0))
                elif kind == "odinv" and iv[0] == 1:
                    drv[o].append((OD, 0))
                elif kind == "odnand" and iv[0] == 1 and iv[1] == 1:
                    drv[o].append((OD, 0))
            for name, clr, pre, d, clk, q in FLIPFLOPS.get(comp["value"], []):
                if q not in p:
                    continue
                c = val[find(p[clr])] if clr in p else 1
                s = val[find(p[pre])] if pre and pre in p else 1
                if c is None or s is None:
                    continue
                qv = 1 if s == 0 else (0 if c == 0 else state.get((ref, name), 0))
                drv[find(p[q])].append((STRONG, qv))
        new, news = {}, {}
        for k in val:
            cands = drv.get(k, [])
            if not cands:
                new[k], news[k] = None, 0
                continue
            top = max(s for s, _ in cands)
            vals = {v for s, v in cands if s == top}
            if len(vals) > 1:
                raise Conflict((k, sorted(cands)))
            new[k], news[k] = vals.pop(), top
        if new == val and news == stren:
            return {n: val[find(n)] for n in nl.nets}
        val, stren = new, news
    raise NoFixedPoint(sorted(k for k in val if val[k] is None)[:10])
```

- [ ] **Step 4: copy the 1G157 symbol** — a script `build/revb/copy_1g157.py` (scratch, not committed):

```python
import pathlib
import sys
sys.path.insert(0, r"C:\Claude projecten\FluxDrive")
from tools.sexpr import children, dump, parse

nt = parse(pathlib.Path(r"C:\Claude projecten\Nano-Tek\Nano-Tek.kicad_sym").read_text(encoding="utf-8"))
sym = next(s for s in children(nt, "symbol") if s[1] == "74LVC1G157")
path = pathlib.Path(r"C:\Claude projecten\FluxDrive\FluxDrive.kicad_sym")
lib = parse(path.read_text(encoding="utf-8"))
assert not any(s[1] == "74LVC1G157" for s in children(lib, "symbol"))
lib.append(sym)
path.write_text(dump(lib), encoding="utf-8", newline="\n")
```

  Then set the symbol's `Footprint` property to `Package_TO_SOT_SMD:SOT-363_SC-70-6` and its `Datasheet` to the
  Nexperia 74LVC1G157 page if they differ, and check that `tools.sexpr.dump` leaves the other symbols byte-identical
  (`git diff --stat FluxDrive.kicad_sym` shows only added lines). Extend `tests/test_sch_gen.py::test_project_symbols_load`
  with `assert pins_of("FluxDrive:74LVC1G157") == {"1": "I1", "2": "GND", "3": "I0", "4": "Y", "5": "VCC", "6": "S"}`
  (use the same helper the test already uses for TPS259531).
- [ ] **Step 5: run** `python -m pytest -q -p no:cacheprovider tests/test_logic_model.py tests/test_sch_gen.py`.
  Expected: PASS.
- [ ] **Step 6: commit** — "Logic evaluator for the netlist tests; 74LVC1G157 symbol".

### Task 3: Bus inputs for rev B

**Files:**
- Modify: `hardware/design.py:40-78`, `tests/test_bus.py`, `tests/test_power.py`, `tests/test_esp.py`

**Interfaces:**
- Produces nets: `SEL0`, `SEL1`, `MTR0` (U3 outputs, feed logic), `SEL0_IO`, `SEL1_IO`, `MTR0_IO` (GPIO side);
  `RST_B`, `RST_ACT`, `MTRX_B`, `M4_MOTOR`, `M4_MTR_Q`, `M4_MTR_N` on U3's freed gates; `SEL_FD` → U2.9, `SEL_FD_N`
  ← U2.8.

- [ ] **Step 1: failing tests** — in `tests/test_bus.py` replace `EVEN`, `INPUTS`, `test_connector_pinout`,
  `test_input_chain`, `test_buffers_follow_the_connector`, `test_unfitted_pads_exist` and the U2 spare-gate lines of
  `test_gate_pairs` with:

```python
EVEN = {2: "_CHNG", 8: "_INDEX", 10: "_SEL0", 12: "_SEL1", 16: "_MTR0", 18: "_DIR", 20: "_STEP", 22: "_DKWD",
        24: "_DKWE", 26: "_TRK0", 28: "_WPROT", 30: "_DKRD", 32: "_SIDE", 34: "_RDY"}
NC_PINS = (3, 4, 6, 14)                  # rev B spec §7: pins 4, 6 and 14 have no use on the A500
# signal, connector net, fitted pull-up, GPIO, GPIO net (rev B spec §5, §7)
INPUTS = [("STEP", "_STEP", [("4K7", "+5V_A")], 6, "STEP"), ("DIR", "_DIR", [("4K7", "+5V_A")], 7, "DIR"),
          ("SIDE", "_SIDE", [("4K7", "+5V_A")], 15, "SIDE"), ("SEL0", "_SEL0", [("1K", "+5V_A")], 17, "SEL0_IO"),
          ("SEL1", "_SEL1", [("1K", "+5V_A")], 9, "SEL1_IO"), ("MTR0", "_MTR0", [], 11, "MTR0_IO"),
          ("DKWD", "_DKWD", [("4K7", "+5V_A")], 5, "DKWD"), ("DKWE", "_DKWE", [("4K7", "+5V_A")], 16, "DKWE")]


def test_connector_pinout(nl):
    for pin, net in EVEN.items():
        assert nl.net_of("J1", pin) == net, pin
    for pin in range(1, 35):
        if pin in NC_PINS:
            assert (nl.net_of("J1", pin) or "").startswith("unconnected-"), pin
        elif pin % 2:
            assert nl.net_of("J1", pin) == "GND", pin


@pytest.mark.parametrize("sig,conn,pull,gpio,gnet", INPUTS)
def test_input_chain(nl, sig, conn, pull, gpio, gnet):
    assert pulls(nl, conn) == pull
    r100 = parts_between(nl, conn, f"{sig}_B")
    assert len(r100) == 1 and nl.components[r100[0]]["value"] == "100"
    assert pulls(nl, f"{sig}_B") == [("100K", "+3V3")]
    assert esp_net(nl, gpio) == gnet
    if gnet != sig:                                              # rev B spec §4.1: 1 kOhm to the GPIO
        iso = parts_between(nl, sig, gnet)
        assert len(iso) == 1 and nl.components[iso[0]]["value"] == "1K"


def test_buffers_follow_the_connector(nl):
    """LBUS-3 kept: U3 takes J1 pins 10-16, U2 pins 18-32, each buffer's gates in the connector's west-to-east order
    (input pins 1, 13, 3, 11, 5, 9 with the SOIC turned 90 degrees)."""
    pin_of = {net: pin for pin, net in EVEN.items()}
    order = [1, 13, 3, 11, 5, 9]
    used = {"U2": [], "U3": []}
    for sig, conn, *_ in INPUTS:
        (u, pin_in), = [(r, int(p)) for r, p, _ in nl.nets[f"{sig}_B"] if r in ("U2", "U3")]
        assert u == ("U3" if pin_of[conn] <= 16 else "U2"), sig
        used[u].append((pin_of[conn], order.index(pin_in)))
    for u, pairs in used.items():
        ranks = [r for _, r in sorted(pairs)]
        assert ranks == sorted(ranks), u


def test_freed_gates_reused(nl):
    """Rev B spec §7: U3's gates for rev A's J1 pins 4, 6, 14 serve the reset wire and mode 4; U2's spare makes
    SEL_FD_N; none of their inputs floats."""
    assert (nl.net_of("U3", 1), nl.net_of("U3", 2)) == ("RST_B", "RST_ACT")
    assert (nl.net_of("U3", 5), nl.net_of("U3", 6)) == ("MTRX_B", "M4_MOTOR")
    assert (nl.net_of("U3", 13), nl.net_of("U3", 12)) == ("M4_MTR_Q", "M4_MTR_N")
    assert (nl.net_of("U2", 9), nl.net_of("U2", 8)) == ("SEL_FD", "SEL_FD_N")
    assert pulls(nl, "RST_B") == [("100K", "+3V3")] and pulls(nl, "MTRX_B") == [("100K", "+3V3")]
    assert pulls(nl, "M4_MTR_Q") == [("100K", "GND")]


def test_unfitted_pads_exist(nl):
    """SCODE-5, spec 4.2: the optional parts exist, between the right nets, unfitted."""
    from tests.fd import dnp_between
    assert len(dnp_between(nl, "_MTR0", "+5V_A", "R")) == 1
    for sig in ("STEP", "SEL0", "SEL1", "MTR0"):
        assert len(dnp_between(nl, f"{sig}_B", "GND", "C")) == 1, sig
```

  In `test_gate_pairs` replace the loop header `for sig, *_ in INPUTS:` (unchanged shape) and the two U2 spare lines
  with nothing (Task 4 rewrites the output half). In `tests/test_power.py` set
  `BUS_NETS = {"_STEP", "_DIR", "_SIDE", "_SEL0", "_SEL1", "_MTR0", "_DKWD", "_DKWE", "_CHNG", "_INDEX", "_TRK0",
  "_WPROT", "_DKRD", "_RDY"}`, `amiga_nets = BUS_NETS` in `test_no_backfeed_paths`, and the signal list of
  `test_usb_alone_leaves_everything_defined` to `("STEP", "DIR", "SIDE", "SEL0", "SEL1", "MTR0", "DKWD", "DKWE")`.
  In `tests/test_esp.py::test_left_alone` use `(35, 36, 37, 45, 46)`.
- [ ] **Step 2: run** `python -m pytest -q -p no:cacheprovider tests/test_bus.py tests/test_power.py tests/test_esp.py`.
  Expected: FAIL (pull-up values, `SEL0_IO` not found, J1 pin 4 still `_MTR0_P4`, U3 pin 1 still `MTR0_P4_B`).
- [ ] **Step 3: implement** in `hardware/design.py`: `TITLE = "FluxDrive v1 rev B"`, block G name added to `BLOCKS`
  (`"G. Drive pass-through and DF0/DF1 swap"`) and `A, B, P, E, U, F, G = BLOCKS`; then block A:

```python
EVEN = {2: "_CHNG", 4: None, 6: None, 8: "_INDEX", 10: "_SEL0", 12: "_SEL1", 14: None,
        16: "_MTR0", 18: "_DIR", 20: "_STEP", 22: "_DKWD", 24: "_DKWE", 26: "_TRK0", 28: "_WPROT",
        30: "_DKRD", 32: "_SIDE", 34: "_RDY"}          # rev B spec §7: pins 4, 6, 14 are not used on the A500
...
# signal, connector net, pull-up, GPIO, buffer, input pin, output pin, C pad, 1 kOhm to the GPIO (rev B §4.1)
INPUTS = [
    ("STEP", "_STEP", ("4K7", "+5V_A"), 6, "U2", 13, 12, True, False),      # J1 pin 20
    ("DIR", "_DIR", ("4K7", "+5V_A"), 7, "U2", 1, 2, False, False),         # 18
    ("SIDE", "_SIDE", ("4K7", "+5V_A"), 15, "U2", 5, 6, False, False),      # 32
    ("SEL0", "_SEL0", ("1K", "+5V_A"), 17, "U3", 3, 4, True, True),         # 10
    ("SEL1", "_SEL1", ("1K", "+5V_A"), 9, "U3", 11, 10, True, True),        # 12
    ("MTR0", "_MTR0", None, 11, "U3", 9, 8, True, True),                    # 16
    ("DKWD", "_DKWD", ("4K7", "+5V_A"), 5, "U2", 3, 4, False, False),       # 22
    ("DKWE", "_DKWE", ("4K7", "+5V_A"), 16, "U2", 11, 10, False, False),    # 24
]
GPIO_NET = {}
buf = {"U2": {"14": "+3V3", "7": "GND", "9": "SEL_FD", "8": "SEL_FD_N"},   # U2's spare makes SEL_FD_N (§4.2)
       "U3": {"14": "+3V3", "7": "GND",
              "1": "RST_B", "2": "RST_ACT",              # rev A's J1 pin 4 gate: the reset wire (§4.8)
              "5": "MTRX_B", "6": "M4_MOTOR",            # rev A's pin 14 gate: mode 4's motor line (§4.7)
              "13": "M4_MTR_Q", "12": "M4_MTR_N"}}       # rev A's pin 6 gate: NOT M4_MTR for the DF1 ID (§4.7)
for sig, conn, pull, gpio, u, pin_in, pin_out, cpad, iso in INPUTS:
    if pull:
        R(pull[0], conn, pull[1], A)
    else:
        R("1K", conn, "+5V_A", A, dnp=True)                  # /MTR0: the motherboard has R506 (spec 4.2)
    R("100", conn, f"{sig}_B", A)
    R("100K", f"{sig}_B", "+3V3", A)
    if cpad:
        C("220pF", f"{sig}_B", "GND", A, dnp=True)
    if iso:
        R("1K", sig, f"{sig}_IO", A)
    GPIO_NET[gpio] = f"{sig}_IO" if iso else sig
    buf[u].update({str(pin_in): f"{sig}_B", str(pin_out): sig})
R("100", "KBRESET", "RST_B", A)                               # the reset wire's input (§4.8)
R("100K", "RST_B", "+3V3", A)
R("4K7", "MTRX", "+5V_A", A, dnp=True)                        # mode 4's motor wire (§4.7)
R("100", "MTRX", "MTRX_B", A, dnp=True)
R("100K", "MTRX_B", "+3V3", A)
R("100K", "M4_MTR_Q", "GND", A)
for u in ("U2", "U3"):
    part(u, "74xx:74HC14", "74LVC14A", SOIC14, buf[u], A, lcsc="C133541")
    C("100nF", "+3V3", "GND", A)
```

  and in block D replace the INPUTS loop over `esp` with `for gpio, net in GPIO_NET.items(): esp[f"IO{gpio}"] = net`
  and the unused list with `for g in (3, 4, 8, 10, 12, 18, 35, 36, 37, 45, 46): esp[f"IO{g}"] = None` (every module
  pin must be assigned or `sch_gen` refuses the schematic; Tasks 5 and 7 give IO3, 4, 8, 10, 12 and 18 their rev B
  nets). Leave `IO13/14/47/48` and J5 as rev A until Task 5. RST_ACT's 1 kΩ to `RST_ACT_IO` and J9/J10 come in Task 7;
  until then `KBRESET` and `MTRX` are nets with only these resistors.
- [ ] **Step 4: regenerate and run** — `bash tools/export_netlist.sh && python -m pytest -q -p no:cacheprovider
  tests/test_bus.py tests/test_power.py tests/test_esp.py -k "not gate_pairs and not output"`. Expected: PASS.
  `test_gate_pairs` and the output tests stay red until Task 4 (note it in the ledger).
- [ ] **Step 5: commit** — "Rev B inputs: 4k7 and 1k pull-ups, 1 kOhm to the GPIOs, U3/U2 gates reused".

### Task 4: Gated outputs and the second output buffer

**Files:**
- Modify: `hardware/design.py:80-92` (block B), `tests/test_bus.py`

**Interfaces:**
- Consumes: `SEL_FD_N` (U2.8, Task 3), `SEL_FD` (Task 5 drives it), `SEL0`, `SEL1`.
- Produces: `DKRD_G`, `TRK0_G`, `WPROT_G`, `RDY_G`, `CHNG_G`, `INDEX_G`, `BUSY`; U10, U11, U17 as in "Names".

- [ ] **Step 1: failing tests** — in `tests/test_bus.py` replace `OUTPUTS`, `test_output_chain`, the output half of
  `test_gate_pairs` and `test_buffers_on_3v3` with:

```python
# signal, connector net, GPIO, buffer (rev B spec §4.3)
OUTPUTS = [("DKRD", "_DKRD", 38, "U4"), ("TRK0", "_TRK0", 40, "U4"), ("WPROT", "_WPROT", 41, "U4"),
           ("RDY", "_RDY", 21, "U4"), ("CHNG", "_CHNG", 42, "U17"), ("INDEX", "_INDEX", 39, "U17")]
BUF_GATES = {"U4": {1: 2, 3: 4, 5: 6, 9: 8, 11: 10, 13: 12}, "U17": {1: 6, 3: 4}}


@pytest.mark.parametrize("sig,conn,gpio,buffer", OUTPUTS)
def test_output_chain(nl, sig, conn, gpio, buffer):
    assert esp_net(nl, gpio) == f"{sig}_N"
    assert pulls(nl, f"{sig}_N") == [("10K", "+3V3")]              # the release pull-up, on the OR input
    ors = [(r, p) for r, p, _ in nl.nets[f"{sig}_N"] if nl.components[r]["value"] == "74LVC32A"]
    assert len(ors) == 1
    (u_or, pin), = ors
    pair = {1: 2, 2: 1, 4: 5, 5: 4, 9: 10, 10: 9, 12: 13, 13: 12}[int(pin)]
    assert nl.net_of(u_or, pair) == "SEL_FD_N"
    ins = [int(p) for r, p, _ in nl.nets[f"{sig}_G"] if r == buffer]
    assert len(ins) == 1 and nl.net_of(buffer, BUF_GATES[buffer][ins[0]]) == f"{sig}_D"
    r33 = parts_between(nl, f"{sig}_D", conn)
    assert len(r33) == 1 and nl.components[r33[0]]["value"] == "33"


def test_buffers_on_3v3(nl):
    for u in ("U2", "U3", "U4", "U10", "U11"):
        assert nl.net_of(u, 14) == "+3V3" and nl.net_of(u, 7) == "GND", u
    assert nl.net_of("U17", 5) == "+3V3" and nl.net_of("U17", 2) == "GND"
    assert nl.components["U4"]["value"] == "74LVC07A" and nl.components["U17"]["value"] == "SN74LVC2G07"
    assert nl.net_of("U4", 9) == nl.net_of("U4", 11) == "+3V3"                        # spare inputs tied
    assert nl.net_of("U11", 12) == nl.net_of("U11", 13) == "GND"                     # spare OR tied
    assert {nl.net_of("U11", 9), nl.net_of("U11", 10)} == {"SEL0", "SEL1"} and nl.net_of("U11", 8) == "BUSY"
```

  and in `test_gate_pairs` delete the output loop (covered above).
- [ ] **Step 2: run** `python -m pytest -q -p no:cacheprovider tests/test_bus.py`. Expected: FAIL (`U17` missing,
  `DKRD_N` still on U4).
- [ ] **Step 3: implement** block B:

```python
# signal, connector net, GPIO, buffer, buffer in/out pins, OR chip and its (a, b, y) pins (rev B spec §4.3):
# U4 keeps the east-end outputs, the SN74LVC2G07 U17 drives /CHNG and /INDEX at the west end
OUTPUTS = [("DKRD", "_DKRD", 38, "U4", 3, 4, "U10", (1, 2, 3)), ("TRK0", "_TRK0", 40, "U4", 13, 12, "U10", (4, 5, 6)),
           ("WPROT", "_WPROT", 41, "U4", 1, 2, "U10", (9, 10, 8)), ("RDY", "_RDY", 21, "U4", 5, 6, "U10", (12, 13, 11)),
           ("CHNG", "_CHNG", 42, "U17", 1, 6, "U11", (1, 2, 3)), ("INDEX", "_INDEX", 39, "U17", 3, 4, "U11", (4, 5, 6))]
pins_of = {"U4": {"14": "+3V3", "7": "GND", "9": "+3V3", "11": "+3V3", "8": None, "10": None},
           "U17": {"2": "GND", "5": "+3V3"},
           "U10": {"14": "+3V3", "7": "GND"},
           "U11": {"14": "+3V3", "7": "GND", "9": "SEL0", "10": "SEL1", "8": "BUSY", "12": "GND", "13": "GND",
                   "11": None}}
for sig, conn, gpio, bufr, pin_in, pin_out, orc, (a, b, y) in OUTPUTS:
    R("10K", f"{sig}_N", "+3V3", B)                 # release pull-up, on the OR input (rev B §4.3)
    R("33", f"{sig}_D", conn, B)
    pins_of[orc].update({str(a): f"{sig}_N", str(b): "SEL_FD_N", str(y): f"{sig}_G"})
    pins_of[bufr].update({str(pin_in): f"{sig}_G", str(pin_out): f"{sig}_D"})
    GPIO_NET[gpio] = f"{sig}_N"
part("U4", "74xx:74LCX07", "74LVC07A", SOIC14, pins_of["U4"], B, lcsc="C6049")
C("100nF", "+3V3", "GND", B)
part("U17", "74xGxx:74LVC2G07", "SN74LVC2G07", "Package_TO_SOT_SMD:SOT-23-6", pins_of["U17"], B, lcsc="C37708")
C("100nF", "+3V3", "GND", B)
TSSOP14 = "Package_SO:TSSOP-14_4.4x5mm_P0.65mm"
for u in ("U10", "U11"):
    part(u, "74xx:74LS32", "74LVC32A", TSSOP14, pins_of[u], B, lcsc="C6087")
    C("100nF", "+3V3", "GND", B)
```

  and in block D delete the OUTPUTS loop over `esp` (the `GPIO_NET` loop covers outputs now). `SEL_FD` has no driver
  until Task 5; ERC is run only from Task 8 on.
- [ ] **Step 4: run** `bash tools/export_netlist.sh && python -m pytest -q -p no:cacheprovider tests/test_bus.py`.
  Expected: PASS.
- [ ] **Step 5: commit** — "Rev B outputs: gated by SEL_FD_N, /CHNG and /INDEX from a west-end buffer".

### Task 5: Mode latch, clock, switch pads, J5 and the GPIO map

**Files:**
- Modify: `hardware/design.py` (new block G part 1; block F J5; block D GPIOs), `tests/test_esp.py`
- Create: `tests/test_swap.py` (structural part)

**Interfaces:**
- Produces: U8, U12, U13, U16, JP5, JP6, JP7, J7, D5, D6 and nets `DF0_FD`, `DF1_EN`, `SEL1_EN`, `SEL_FD`,
  `MODE_CLK`, `MODE_CLK_REQ`, `DF0_REQ`, `DF1_REQ`, `DF0_STATE`, `DF1_STATE`, `CLR_A`, `PRE_A`, `CLR_B`, `PRE_B`,
  `POR_A`, `J7_FD`, `J7_REAL`.

- [ ] **Step 1: failing tests** — `tests/test_swap.py`:

```python
"""Rev B steering logic (spec §3, §4): structure here, behaviour in Task 8's tests below."""
from tests.fd import between, esp_net, parts_between, pulls


def value(nl, ref):
    return nl.components[ref]["value"]


def test_mode_latch(nl):
    assert value(nl, "U8") == "74LVC74A"
    a = {p: nl.net_of("U8", p) for p in (1, 2, 3, 4, 5)}
    b = {p: nl.net_of("U8", p) for p in (13, 12, 11, 10, 9)}
    assert a == {1: "CLR_A", 2: "DF0_REQ", 3: "MODE_CLK", 4: "PRE_A", 5: "DF0_FD"}
    assert b == {13: "CLR_B", 12: "DF1_REQ", 11: "MODE_CLK", 10: "PRE_B", 9: "DF1_EN"}
    for net in ("CLR_A", "PRE_A", "CLR_B", "PRE_B"):
        assert ("10K", "+3V3") in pulls(nl, net), net
    assert [value(nl, r) for r in parts_between(nl, "DF0_FD", "DF0_REQ")] == ["100K"]      # D holds Q (§4.1)
    assert [value(nl, r) for r in parts_between(nl, "DF1_EN", "DF1_REQ")] == ["100K"]
    assert [value(nl, r) for r in parts_between(nl, "DF0_FD", "DF0_STATE")] == ["1K"]
    assert [value(nl, r) for r in parts_between(nl, "DF1_EN", "DF1_STATE")] == ["1K"]


def test_power_on_rcs(nl):
    assert parts_between(nl, "CLR_B", "GND", "C") and parts_between(nl, "POR_A", "GND", "C")
    assert {nl.net_of("D5", 2), nl.net_of("D5", 1)} == {"CLR_B", "+3V3"} and nl.net_of("D5", 1) == "+3V3"
    assert {nl.net_of("D6", 2), nl.net_of("D6", 1)} == {"POR_A", "+3V3"} and nl.net_of("D6", 1) == "+3V3"
    assert [nl.net_of("JP5", p) for p in (1, 2, 3)] == ["CLR_A", "POR_A", "PRE_A"]
    assert "Bridged12" in nl.components["JP5"]["footprint"]
    assert between(nl, "JP6") == {"CLR_A", "GND"} and between(nl, "JP7") == {"PRE_A", "+3V3"}
    assert "Open" in nl.components["JP6"]["footprint"] and "Open" in nl.components["JP7"]["footprint"]


def test_switch_pads(nl):
    assert [nl.net_of("J7", p) for p in (1, 2, 3)] == ["J7_FD", "GND", "J7_REAL"]
    assert [value(nl, r) for r in parts_between(nl, "J7_FD", "PRE_A")] == ["1K"]
    assert [value(nl, r) for r in parts_between(nl, "J7_REAL", "CLR_A")] == ["1K"]
    for net in ("J7_FD", "J7_REAL"):
        assert [value(nl, c) for c in parts_between(nl, net, "GND", "C")] == ["100nF"], net


def test_select_and_clock_gates(nl):
    mux = {"U12": ("DF1_EN", "GND", "SEL1", "SEL1_EN"), "U13": ("DF0_FD", "SEL1_EN", "SEL0", "SEL_FD"),
           "U16": ("BUSY", "MODE_CLK_REQ", "GND", "MODE_CLK")}                # S, I0, I1, Y
    for u, (s, i0, i1, y) in mux.items():
        assert value(nl, u) == "74LVC1G157"
        assert (nl.net_of(u, 6), nl.net_of(u, 3), nl.net_of(u, 1), nl.net_of(u, 4)) == (s, i0, i1, y), u


def test_control_gpios(nl):
    """Rev B spec §7: the GPIO map; outputs active-high with 10k pull-downs, read-backs through 1k."""
    want = {47: "MODE_CLK_REQ", 48: "DF0_REQ", 13: "DF1_REQ", 14: "CHNG_REQ", 12: "DF0_STATE", 8: "DF1_STATE",
            18: "GPIO18", 3: "GPIO3"}
    for gpio, net in want.items():
        assert esp_net(nl, gpio) == net, gpio
    for net in ("MODE_CLK_REQ", "CHNG_REQ"):
        assert pulls(nl, net) == [("10K", "GND")], net
```

  In `tests/test_esp.py::test_led_uart_spare` replace the J5 lines with
  `assert [nl.net_of("J5", p) for p in range(1, 5)] == ["GND", "+3V3", "GPIO18", "GPIO3"]`.
- [ ] **Step 2: run** `python -m pytest -q -p no:cacheprovider tests/test_swap.py tests/test_esp.py`. Expected: FAIL
  (`KeyError: 'U8'`, J5 still 6 pins).
- [ ] **Step 3: implement.** Block F: J5 becomes

```python
HDR4 = "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical"
part("J5", "Connector_Generic:Conn_01x04", "Spare / OLED", HDR4,              # rev B §7: GND 3V3 SCL SDA order
     {"1": "GND", "2": "+3V3", "3": "GPIO18", "4": "GPIO3"}, F, in_bom=False)
```

  Block D: `esp.update({"IO47": "MODE_CLK_REQ", "IO48": "DF0_REQ", "IO13": "DF1_REQ", "IO14": "CHNG_REQ",
  "IO10": "RST_REQ", "IO12": "DF0_STATE", "IO8": "DF1_STATE", "IO4": "RST_ACT_IO", "IO18": "GPIO18", "IO3": "GPIO3"})`
  after the `GPIO_NET` loop. New block G, appended after block F:

```python
# --- G: drive pass-through and DF0/DF1 swap (rev B spec §3, §4) ------------------------------------------------
G1157 = ("FluxDrive:74LVC1G157", "74LVC1G157", "Package_TO_SOT_SMD:SOT-363_SC-70-6")


def mux(ref, s, i0, i1, y, dnp=False):
    part(ref, G1157[0], G1157[1], G1157[2], {"6": s, "3": i0, "1": i1, "4": y, "2": "GND", "5": "+3V3"}, G,
         lcsc="" if dnp else "C135822", dnp=dnp, in_bom=not dnp)
    C("100nF", "+3V3", "GND", G, dnp=dnp)


mux("U12", "DF1_EN", "GND", "SEL1", "SEL1_EN")                 # SEL1_EN = SEL1 AND DF1_EN
mux("U13", "DF0_FD", "SEL1_EN", "SEL0", "SEL_FD")              # FluxDrive's own select
mux("U16", "BUSY", "MODE_CLK_REQ", "GND", "MODE_CLK")          # the clock only while both selects are idle
part("U8", "74xx:74HC74", "74LVC74A", TSSOP14,
     {"1": "CLR_A", "2": "DF0_REQ", "3": "MODE_CLK", "4": "PRE_A", "5": "DF0_FD", "6": None,
      "13": "CLR_B", "12": "DF1_REQ", "11": "MODE_CLK", "10": "PRE_B", "9": "DF1_EN", "8": None,
      "7": "GND", "14": "+3V3"}, G, lcsc="C6100")
C("100nF", "+3V3", "GND", G)
for net in ("CLR_A", "PRE_A", "CLR_B", "PRE_B"):
    R("10K", net, "+3V3", G)
R("100K", "DF0_FD", "DF0_REQ", G)                              # an undriven D holds the present state (§4.1)
R("100K", "DF1_EN", "DF1_REQ", G)
R("1K", "DF0_FD", "DF0_STATE", G)
R("1K", "DF1_EN", "DF1_STATE", G)
R("10K", "MODE_CLK_REQ", "GND", G)
R("10K", "CHNG_REQ", "GND", G)
DIODE = ("Device:D", "1N4148W", "Diode_SMD:D_SOD-123", "C81598")
C("1uF", "CLR_B", "GND", G)                                   # power-on: DF1 off (§4.6)
part("D5", DIODE[0], DIODE[1], DIODE[2], {"1": "+3V3", "2": "CLR_B"}, G, lcsc=DIODE[3])
C("1uF", "POR_A", "GND", G)                                   # power-on: real drive DF0 via JP5 1-2
part("D6", DIODE[0], DIODE[1], DIODE[2], {"1": "+3V3", "2": "POR_A"}, G, lcsc=DIODE[3])
JP3B = ("Jumper:SolderJumper_3_Bridged12", "Bridged12", "Jumper:SolderJumper-3_P1.3mm_Bridged12_RoundedPad1.0x1.5mm")
JP2O = ("Jumper:SolderJumper_2_Open", "Open", "Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm")
part("JP5", JP3B[0], "DF0 at power-on", JP3B[2], {"1": "CLR_A", "2": "POR_A", "3": "PRE_A"}, G, in_bom=False)
part("JP6", JP2O[0], "REAL clear", JP2O[2], {"1": "CLR_A", "2": "GND"}, G, in_bom=False)
part("JP7", JP2O[0], "REAL preset", JP2O[2], {"1": "PRE_A", "2": "+3V3"}, G, in_bom=False)
part("J7", "Connector_Generic:Conn_01x03", "DF0 switch", "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
     {"1": "J7_FD", "2": "GND", "3": "J7_REAL"}, G, in_bom=False)
R("1K", "J7_FD", "PRE_A", G)
R("1K", "J7_REAL", "CLR_A", G)
C("100nF", "J7_FD", "GND", G)
C("100nF", "J7_REAL", "GND", G)
```

  `Device:D` pin 1 is the cathode (K), pin 2 the anode (A); check with `tools/sch_gen.py`'s pin table before
  committing. The jumper values ("DF0 at power-on", "REAL clear", …) are labels; the model of Task 2 recognises
  bridged jumpers by the footprint name.
- [ ] **Step 4: run** `bash tools/export_netlist.sh && python -m pytest -q -p no:cacheprovider tests/test_swap.py
  tests/test_esp.py`. Expected: PASS.
- [ ] **Step 5: commit** — "Rev B mode latch, select and clock gates, switch pads, J5 as a 4-pin header".

### Task 6: The real drive's connector J6, its drivers, bypass and virtual disk change

**Files:**
- Modify: `hardware/design.py` (block G part 2), `tests/test_swap.py`

**Interfaces:**
- Produces: U14, U15, U18, U20, J6, JP1–JP4; nets `REAL_SEL`, `REAL_MTR`, `J6_SEL_D`, `J6_MTR_D`, `J6_SEL`, `J6_MTR`,
  `J6_PIN6`, `J6_PIN12`, `J6_PIN14`, `M4_SEL`, `M4_MTR`, `VCHNG_D`.

- [ ] **Step 1: failing tests** — append to `tests/test_swap.py`:

```python
J6_1TO1 = (2, 8, 18, 20, 22, 24, 26, 28, 30, 32, 34)


def test_j6_pinout(nl):
    for p in J6_1TO1:
        assert nl.net_of("J6", p) == nl.net_of("J1", p), p
    assert nl.net_of("J6", 10) == "J6_SEL" and nl.net_of("J6", 4) == nl.net_of("J6", 16) == "J6_MTR"
    for p, net in ((6, "J6_PIN6"), (12, "J6_PIN12"), (14, "J6_PIN14")):
        assert nl.net_of("J6", p) == net and pulls(nl, net) == [("10K", "+5V_A")], p
    for p in range(1, 35, 2):
        assert (nl.net_of("J6", p) or "").startswith("unconnected-") if p == 3 else nl.net_of("J6", p) == "GND"


def test_real_drive_drivers(nl):
    for u, (s, i0, i1, y) in {"U14": ("DF0_FD", "SEL0", "M4_SEL", "REAL_SEL"),
                              "U15": ("DF0_FD", "MTR0", "M4_MTR", "REAL_MTR")}.items():
        assert (nl.net_of(u, 6), nl.net_of(u, 3), nl.net_of(u, 1), nl.net_of(u, 4)) == (s, i0, i1, y), u
    assert value(nl, "U18") == "SN74LVC2G06"
    assert (nl.net_of("U18", 1), nl.net_of("U18", 6)) == ("REAL_SEL", "J6_SEL_D")
    assert (nl.net_of("U18", 3), nl.net_of("U18", 4)) == ("REAL_MTR", "J6_MTR_D")
    for net in ("J6_SEL_D", "J6_MTR_D"):
        assert pulls(nl, net) == [("4K7", "+5V_A")], net


def test_bypass_and_mode4_jumpers(nl):
    want = {"JP1": ("J6_SEL_D", "J6_SEL", "_SEL0"), "JP2": ("J6_MTR_D", "J6_MTR", "_MTR0"),
            "JP3": ("GND", "M4_SEL", "M4_SEL_Q"), "JP4": ("GND", "M4_MTR", "M4_MTR_Q")}
    for jp, nets in want.items():
        assert tuple(nl.net_of(jp, p) for p in (1, 2, 3)) == nets, jp
        assert "Bridged12" in nl.components[jp]["footprint"], jp


def test_virtual_disk_change(nl):
    assert value(nl, "U20") == "SN74LVC1G38"
    assert {nl.net_of("U20", 1), nl.net_of("U20", 2)} == {"CHNG_REQ", "SEL0"} and nl.net_of("U20", 4) == "VCHNG_D"
    r33 = parts_between(nl, "VCHNG_D", "_CHNG")
    assert len(r33) == 1 and value(nl, r33[0]) == "33"


def test_nothing_on_j6_leaves_its_lines_inactive(nl):
    """Review focus 3: with nothing plugged into J6, every J6-only line is pulled to its inactive high level."""
    from tests.logic import evaluate
    v = evaluate(nl, {"_CHNG": (1, 1), "_INDEX": (1, 1), "_TRK0": (1, 1), "_WPROT": (1, 1), "_DKRD": (1, 1),
                      "_RDY": (1, 1), "KBRESET": (1, 1)})
    for net in ("J6_SEL", "J6_MTR", "J6_PIN6", "J6_PIN12", "J6_PIN14"):
        assert v[net] == 1, net
```

- [ ] **Step 2: run** `python -m pytest -q -p no:cacheprovider tests/test_swap.py`. Expected: FAIL (`KeyError:
  'J6'`).
- [ ] **Step 3: implement** in block G:

```python
mux("U14", "DF0_FD", "SEL0", "M4_SEL", "REAL_SEL")             # the real drive's select (§4.4)
mux("U15", "DF0_FD", "MTR0", "M4_MTR", "REAL_MTR")             # and its motor
part("U18", "74xGxx:74LVC2G06", "SN74LVC2G06", "Package_TO_SOT_SMD:SOT-23-6",
     {"1": "REAL_SEL", "6": "J6_SEL_D", "3": "REAL_MTR", "4": "J6_MTR_D", "2": "GND", "5": "+3V3"}, G, lcsc="C402162")
C("100nF", "+3V3", "GND", G)
R("4K7", "J6_SEL_D", "+5V_A", G)
R("4K7", "J6_MTR_D", "+5V_A", G)
part("JP1", JP3B[0], "bypass SEL", JP3B[2], {"1": "J6_SEL_D", "2": "J6_SEL", "3": "_SEL0"}, G, in_bom=False)
part("JP2", JP3B[0], "bypass MTR", JP3B[2], {"1": "J6_MTR_D", "2": "J6_MTR", "3": "_MTR0"}, G, in_bom=False)
part("JP3", JP3B[0], "mode 4 SEL", JP3B[2], {"1": "GND", "2": "M4_SEL", "3": "M4_SEL_Q"}, G, in_bom=False)
part("JP4", JP3B[0], "mode 4 MTR", JP3B[2], {"1": "GND", "2": "M4_MTR", "3": "M4_MTR_Q"}, G, in_bom=False)
j6 = {str(p): ("GND" if p != 3 else None) for p in range(1, 34, 2)}
j6.update({str(p): EVEN[p] for p in (2, 8, 18, 20, 22, 24, 26, 28, 30, 32, 34)})
j6.update({"4": "J6_MTR", "16": "J6_MTR", "10": "J6_SEL", "6": "J6_PIN6", "12": "J6_PIN12", "14": "J6_PIN14"})
part("J6", "Connector_Generic:Conn_02x17_Odd_Even", "Original drive", "Connector_IDC:IDC-Header_2x17_P2.54mm_Vertical",
     j6, G, lcsc="C601943")
for net in ("J6_PIN6", "J6_PIN12", "J6_PIN14"):
    R("10K", net, "+5V_A", G)
part("U20", "74xGxx:74LVC1G38", "SN74LVC1G38", "Package_TO_SOT_SMD:SOT-23-5",
     {"1": "CHNG_REQ", "2": "SEL0", "4": "VCHNG_D", "3": "GND", "5": "+3V3"}, G, lcsc="C2867613")
C("100nF", "+3V3", "GND", G)
R("33", "VCHNG_D", "_CHNG", G)                                # virtual disk change on bus DF0 (§4.5)
```

- [ ] **Step 4: run** `bash tools/export_netlist.sh && python -m pytest -q -p no:cacheprovider tests/test_swap.py`.
  Expected: PASS.
- [ ] **Step 5: commit** — "Rev B J6 pass-through, real-drive drivers, bypass and mode-4 jumpers, virtual disk change".

### Task 7: Mode 4 (unfitted) and the reset wire

**Files:**
- Modify: `hardware/design.py` (block G part 3), `tests/test_swap.py`, `tests/test_bom.py`

**Interfaces:**
- Produces: U19, U21, U22, U23, J9, J10; nets `RST_REQ`, `KBRESET`, `RST_ACT_IO`, `MTRX`, `M4_SEL_Q`, `ID_D`.

- [ ] **Step 1: failing tests** — append to `tests/test_swap.py`:

```python
def test_mode4_parts_prepared_not_fitted(nl):
    assert not nl.fitted("U21") and not nl.fitted("U22") and not nl.fitted("U23")
    assert (nl.net_of("U21", 6), nl.net_of("U21", 3), nl.net_of("U21", 1), nl.net_of("U21", 4)) == \
        ("DF0_FD", "GND", "SEL1_EN", "M4_SEL_Q")
    assert value(nl, "U22") == "SN74LVC1G175"
    assert [nl.net_of("U22", p) for p in (1, 3, 6, 4)] == ["SEL1", "M4_MOTOR", "DF1_EN", "M4_MTR_Q"]
    assert {nl.net_of("U23", 1), nl.net_of("U23", 2)} == {"M4_SEL_Q", "M4_MTR_N"} and nl.net_of("U23", 4) == "ID_D"
    from tests.fd import dnp_between
    assert len(dnp_between(nl, "ID_D", "_RDY", "R")) == 1
    assert nl.net_of("J10", 1) == "MTRX"


def test_reset_wire(nl):
    assert nl.net_of("J9", 1) == "KBRESET"
    assert not pulls(nl, "KBRESET")                              # no pull-up on the pad: RP501 on the motherboard
    assert value(nl, "U19") == "SN74LVC1G06"
    assert (nl.net_of("U19", 2), nl.net_of("U19", 4)) == ("RST_REQ", "KBRESET")
    assert pulls(nl, "RST_REQ") == [("10K", "GND")]
    assert [value(nl, r) for r in parts_between(nl, "RST_ACT", "RST_ACT_IO")] == ["1K"]
    assert esp_net(nl, 4) == "RST_ACT_IO" and esp_net(nl, 10) == "RST_REQ"
```

  In `tests/test_bom.py::test_every_fitted_part_has_lcsc` extend the skipped prefixes to
  `("TP", "H", "FID", "J4", "J5", "J7", "J9", "J10", "JP")`.
- [ ] **Step 2: run** `python -m pytest -q -p no:cacheprovider tests/test_swap.py tests/test_bom.py`. Expected: FAIL
  (`KeyError: 'U21'`).
- [ ] **Step 3: implement** in block G:

```python
part("U19", "74xGxx:74LVC1G06", "SN74LVC1G06", "Package_TO_SOT_SMD:SOT-23-5",
     {"2": "RST_REQ", "4": "KBRESET", "3": "GND", "5": "+3V3"}, G, lcsc="C840103")
C("100nF", "+3V3", "GND", G)
R("10K", "RST_REQ", "GND", G)
R("1K", "RST_ACT", "RST_ACT_IO", G)
TP_THT = "TestPoint:TestPoint_THTPad_D1.5mm_Drill0.7mm"
part("J9", "Connector:TestPoint", "RST wire", TP_THT, {"1": "KBRESET"}, G, in_bom=False)   # to _KBRESET (§4.8)
part("J10", "Connector:TestPoint", "MTRX wire", TP_THT, {"1": "MTRX"}, G, in_bom=False)   # to CIA-B pin 17 (§4.7)
mux("U21", "DF0_FD", "GND", "SEL1_EN", "M4_SEL_Q", dnp=True)   # M4_SEL = DF0_FD AND SEL1_EN
part("U22", "74xGxx:74LVC1G175", "SN74LVC1G175", "Package_TO_SOT_SMD:SOT-23-6",
     {"1": "SEL1", "3": "M4_MOTOR", "6": "DF1_EN", "4": "M4_MTR_Q", "2": "GND", "5": "+3V3"}, G, dnp=True, in_bom=False)
C("100nF", "+3V3", "GND", G, dnp=True)
part("U23", "74xGxx:74LVC1G38", "SN74LVC1G38", "Package_TO_SOT_SMD:SOT-23-5",
     {"1": "M4_SEL_Q", "2": "M4_MTR_N", "4": "ID_D", "3": "GND", "5": "+3V3"}, G, dnp=True, in_bom=False)
C("100nF", "+3V3", "GND", G, dnp=True)
R("33", "ID_D", "_RDY", G, dnp=True)                            # the DD ID for the real drive as DF1
```

- [ ] **Step 4: run** `bash tools/export_netlist.sh && python -m pytest -q -p no:cacheprovider tests/test_swap.py
  tests/test_bom.py`. Expected: PASS.
- [ ] **Step 5: commit** — "Rev B mode 4 as unfitted pads, the optional reset wire".

### Task 8: Drive power, test pads, and the logic proven on the netlist

**Files:**
- Modify: `hardware/design.py` (block C, block F test pads), `tests/test_power.py`, `tests/test_bom.py`,
  `tests/test_swap.py`, `FluxDrive_Schematic.pdf`

**Interfaces:**
- Produces: U9, J8, nets `+5V_DRIVE`, `+12V`, `DRV_DVDT`, `DRV_ILM`; the behavioural tests of spec §10.1.

- [ ] **Step 1: failing tests — power** — in `tests/test_power.py` replace the J2 pin-4 line and the `+5V_IN` subset
  in `test_power_header_to_efuse` with:

```python
    assert nl.net_of("J2", 4) == "+12V" and nl.net_of("J8", 4) == "+12V"                   # rev B §6
    assert set(nl.refs_on("+12V")) == {"J2", "J8"}
    assert {r_ for r_, _, _ in nl.nets["+5V_IN"]} <= {"J2", "U5", "U9", "D4", *parts_between(nl, "+5V_IN", "GND", "C"),
                                                      *parts_between(nl, "+5V_IN", "EFUSE_EN")}
```

  and append:

```python
def test_drive_behind_its_own_efuse(nl):
    """Rev B §6: the drive's +5 V never passes U5; U9 limits it at about 1.5 A and clamps a reversed J2."""
    assert nl.components["U9"]["value"] == "TPS259531"
    assert nl.net_of("U9", 3) == nl.net_of("U9", 4) == "+5V_IN" and nl.net_of("U9", 5) == "+5V_DRIVE"
    assert nl.net_of("U9", 2) == nl.net_of("U5", 2) == "EFUSE_EN"                           # one UVLO divider
    assert [nl.net_of("J8", p) for p in (1, 2, 3, 4)] == ["+5V_DRIVE", "GND", "GND", "+12V"]
    ilim = 2000 / r(nl, "DRV_ILM", "GND") + 0.04                                            # TI SLVSE57C Eq. 4
    assert 1.2 <= ilim <= 1.7, ilim
    caps = [nl.components[c]["value"] for c in parts_between(nl, "+5V_DRIVE", "GND", "C")]
    assert sorted(caps) == ["100nF", "22uF"]
    assert [nl.components[c]["value"] for c in parts_between(nl, "DRV_DVDT", "GND", "C")] == ["22nF"]
```

- [ ] **Step 2: failing tests — behaviour** — append to `tests/test_swap.py`:

```python
import itertools

import pytest

from tests.logic import OD, PULL, STRONG, WEAK, evaluate

BUS_OUT = ("_CHNG", "_INDEX", "_TRK0", "_WPROT", "_DKRD", "_RDY")
OUTS = {"CHNG": "_CHNG", "INDEX": "_INDEX", "TRK0": "_TRK0", "WPROT": "_WPROT", "DKRD": "_DKRD", "RDY": "_RDY"}


def fit_mode4(nl):
    """The unfitted parts a builder fits for mode 4: U21-U23 and the MTRX and ID resistors (found by net)."""
    from tests.fd import dnp_between
    refs = {"U21", "U22", "U23"}
    refs |= set(dnp_between(nl, "MTRX", "+5V_A", "R")) | set(dnp_between(nl, "MTRX", "MTRX_B", "R"))
    refs |= set(dnp_between(nl, "ID_D", "_RDY", "R"))
    return refs


def amiga(sel0, sel1, mtr0, motor_raw=0):
    """The Amiga side: CIA-B and Gary pull the active-low selects and /MTR0 low; the motherboard pulls the drive
    outputs and _KBRESET up; the raw motor line (mode 4) is low when a DF1-3 motor is on."""
    src = {n: (1, PULL) for n in BUS_OUT + ("KBRESET",)}
    for net, on in (("_SEL0", sel0), ("_SEL1", sel1), ("_MTR0", mtr0), ("MTRX", motor_raw)):
        if on:
            src[net] = (0, OD)
    src.setdefault("MTRX", (1, PULL))
    return src


def expected(df0_fd, df1_en, sel0, sel1, mtr0, m4, m4_q):
    """Rev B spec §3 table and §4 equations, written independently of the netlist."""
    sel1_en = sel1 & df1_en
    sel_fd = sel0 if df0_fd else sel1_en
    m4_sel = (df0_fd & sel1_en) if m4 else 0
    m4_mtr = (m4_q & df1_en) if m4 else 0
    return {"SEL_FD": sel_fd, "REAL_SEL": m4_sel if df0_fd else sel0, "REAL_MTR": m4_mtr if df0_fd else mtr0,
            "ID": m4_sel & (1 - m4_mtr)}


def legal(bypass, real_pair, switch):
    """Rev B §4.4: the bypass needs DF0_FD held at 0 by the REAL pair or by J7 on its real-drive throw."""
    return not bypass or real_pair or switch == "REAL"


def df0_of(stored, real_pair, switch):
    if real_pair:
        return 0
    return {"FD": 1, "REAL": 0, "GTi": stored}[switch]


CASES = list(itertools.product((0, 1), (0, 1), ("GTi", "FD", "REAL"), (0, 1), (0, 1), (0, 1), (0, 1),
                               (0, 1), (0, 1), (0, 1), (0, 1)))


@pytest.mark.parametrize("stored0,stored1,switch,real_pair,bypass,m4,m4_q,sel0,sel1,mtr0,chng_req", CASES)
def test_steering_logic(nl, stored0, stored1, switch, real_pair, bypass, m4, m4_q, sel0, sel1, mtr0, chng_req):
    """Rev B spec §10.1: every legal state, with the six outputs asserted by the firmware."""
    if not legal(bypass, real_pair, switch) or (m4_q and not m4):
        pytest.skip("not a legal state")
    bridged = {}
    if bypass:
        bridged["JP1"] = [("2", "3")]
        bridged["JP2"] = [("2", "3")]
    if m4:
        bridged["JP3"] = [("2", "3")]
        bridged["JP4"] = [("2", "3")]
    if real_pair:
        bridged["JP6"] = [("1", "2")]
        bridged["JP7"] = [("1", "2")]
    if switch != "GTi":
        bridged["J7"] = [("1", "2")] if switch == "FD" else [("3", "2")]
    src = amiga(sel0, sel1, mtr0)
    src.update({f"{s}_N": (0, STRONG) for s in OUTS})                  # the firmware asserts all six
    src["CHNG_REQ"] = (chng_req, STRONG)
    state = {("U8", "A"): stored0, ("U8", "B"): stored1, ("U22", "A"): m4_q}
    v = evaluate(nl, src, state=state, bridged=bridged, fit=fit_mode4(nl) if m4 else ())
    df0 = df0_of(stored0, real_pair, switch)
    assert v["DF0_FD"] == df0 and v["DF1_EN"] == stored1
    e = expected(df0, stored1, sel0, sel1, mtr0, m4, m4_q)
    assert v["SEL_FD"] == e["SEL_FD"]
    if bypass:
        assert v["J6_SEL"] == 1 - sel0 and v["J6_MTR"] == 1 - mtr0
    else:
        assert v["J6_SEL"] == 1 - e["REAL_SEL"] and v["J6_MTR"] == 1 - e["REAL_MTR"]
    for sig, conn in OUTS.items():
        low = e["SEL_FD"] or (sig == "CHNG" and chng_req and sel0) or (sig == "RDY" and e["ID"])
        assert v[conn] == (0 if low else 1), (sig, v[conn])
    # at most one drive on /SEL0 (review focus 2); with /SEL1 idle, a low J6_SEL can only come from /SEL0
    if sel0 and not sel1:
        assert not (v["J6_SEL"] == 0 and v["SEL_FD"] == 1 and df0 == 1), "two drives on /SEL0"


@pytest.mark.parametrize("pattern", range(64))
def test_outputs_follow_the_firmware_only_when_selected(nl, pattern):
    for df0, sel0 in ((1, 1), (1, 0), (0, 1)):
        src = amiga(sel0, 0, 0)
        src.update({f"{s}_N": (0, STRONG) for i, s in enumerate(OUTS) if pattern >> i & 1})
        v = evaluate(nl, src, state={("U8", "A"): df0, ("U8", "B"): 0})
        for i, (sig, conn) in enumerate(OUTS.items()):
            assert v[conn] == (0 if (pattern >> i & 1) and df0 and sel0 else 1), (sig, df0, sel0)


def rising(before, after, net):
    return before[net] == 0 and after[net] == 1


class Board:
    """Steps the latches through events (rev B spec §10.1, second test)."""

    def __init__(self, nl, m4=False, stored=(0, 0), m4_q=0, bridged=None):
        self.nl, self.fit = nl, fit_mode4(nl) if m4 else ()
        self.state = {("U8", "A"): stored[0], ("U8", "B"): stored[1], ("U22", "A"): m4_q}
        self.bridged = dict(bridged or {})
        if m4:
            self.bridged.update({"JP3": [("2", "3")], "JP4": [("2", "3")]})
        self.src = amiga(0, 0, 0)
        self.v = self.eval()

    def eval(self):
        return evaluate(self.nl, self.src, state=self.state, bridged=self.bridged, fit=self.fit)

    def set(self, **nets):
        for net, val in nets.items():
            if val is None:
                self.src.pop(net, None)
            else:
                self.src[net] = val
        before, after = self.v, self.eval()
        if rising(before, after, "MODE_CLK"):
            self.state[("U8", "A")] = before["DF0_REQ"]
            self.state[("U8", "B")] = before["DF1_REQ"]
        if self.fit and rising(before, after, "SEL1") and after["DF1_EN"]:
            self.state[("U22", "A")] = before["M4_MOTOR"]
        if not after["DF1_EN"]:
            self.state[("U22", "A")] = 0
        self.v = self.eval()
        return self.v


def test_clock_request_waits_for_the_access_to_end(nl):
    """Review focus 1: a DF0 request during a /SEL0 access takes effect when the access ends, not before."""
    b = Board(nl, stored=(0, 0))
    b.set(_SEL0=(0, OD))                                   # real drive DF0, being read
    b.set(DF0_REQ=(1, STRONG), MODE_CLK_REQ=(1, STRONG))
    assert b.v["DF0_FD"] == 0 and b.v["REAL_SEL"] == 1
    b.set(_SEL0=None)                                      # access over: the clock arrives
    assert b.v["DF0_FD"] == 1 and b.v["REAL_SEL"] == 0
    b.set(MODE_CLK_REQ=(0, STRONG))
    assert b.v["DF0_FD"] == 1


def test_request_dropped_inside_an_access_is_lost(nl):
    b = Board(nl, stored=(0, 1))
    b.set(_SEL1=(0, OD))                                   # FluxDrive DF1 in use (mode 3)
    b.set(DF0_REQ=(1, STRONG), MODE_CLK_REQ=(1, STRONG))
    b.set(MODE_CLK_REQ=(0, STRONG))
    b.set(_SEL1=None)
    assert b.v["DF0_FD"] == 0 and b.v["DF1_EN"] == 1


def test_esp32_reset_changes_nothing(nl):
    """Review focus 4: control GPIOs undriven, with their internal pull-ups on: no clock, no /CHNG, no reset."""
    for stored in ((0, 0), (1, 0), (0, 1)):
        b = Board(nl, stored=stored)
        b.set(_SEL0=(0, OD))
        b.set(**{n: (1, WEAK) for n in ("MODE_CLK_REQ", "DF0_REQ", "DF1_REQ", "CHNG_REQ", "RST_REQ")})
        b.set(_SEL0=None)
        assert (b.v["DF0_FD"], b.v["DF1_EN"]) == stored
        assert b.v["_CHNG"] == 1 and b.v["KBRESET"] == 1 and b.v["MODE_CLK"] == 0


def test_mode1_with_mode4_fitted_keeps_the_real_drive_still(nl):
    """v0.1's finding I3: an external DF1's motor must not spin the real drive in mode 1."""
    b = Board(nl, m4=True, stored=(1, 0))
    for _ in range(3):
        b.set(MTRX=(0, OD))
        b.set(_SEL1=(0, OD))
        assert b.v["J6_MTR"] == 1 and b.v["J6_SEL"] == 1 and b.v["_RDY"] == 1
        b.set(_SEL1=None)
        b.set(MTRX=None)


def test_power_on_defaults(nl):
    for jp5, want in ((None, 0), ([("2", "3")], 1)):
        bridged = {"JP5": jp5} if jp5 else {}
        b = Board(nl, stored=(1, 1), bridged=bridged)
        b.set(POR_A=(0, OD), CLR_B=(0, OD))                # capacitors still discharged
        b.set(POR_A=None, CLR_B=None)
        assert b.v["DF1_EN"] == 0 and b.v["DF0_FD"] == want
```

  The power-on test models the RC as a source on the capacitor node; the flip-flop states it checks come from the
  preset or clear while those are low — so, before `evaluate` returns the settled state after release, `Board.set`
  must also latch Q from an asserted preset or clear: add to `Board.set`, before `self.v = self.eval()`:

```python
        for ff, (clr, pre) in {("U8", "A"): ("CLR_A", "PRE_A"), ("U8", "B"): ("CLR_B", "PRE_B")}.items():
            if after[pre] == 0:
                self.state[ff] = 1
            elif after[clr] == 0:
                self.state[ff] = 0
```

- [ ] **Step 3: run** `python -m pytest -q -p no:cacheprovider tests/test_power.py tests/test_swap.py -x -q`.
  Expected: FAIL (`KeyError: 'U9'`; `+12V` missing).
- [ ] **Step 4: implement** block C additions after U5's parts:

```python
part("U9", "FluxDrive:TPS259531", "TPS259531", "Package_SON:Texas_DSG0008A_WSON-8-1EP_2x2mm_P0.5mm_EP0.9x1.6mm",
     {"1": "DRV_DVDT", "2": "EFUSE_EN", "3": "+5V_IN", "4": "+5V_IN", "5": "+5V_DRIVE", "6": None,
      "7": "DRV_ILM", "8": "GND", "9": "GND"}, P, lcsc="C2155674")     # the real drive's eFuse (rev B §6)
C("22nF", "DRV_DVDT", "GND", P)
R("1K5", "DRV_ILM", "GND", P)                  # 2000/1500 + 0.04 = 1.37 A
C("22uF", "+5V_DRIVE", "GND", P)
C("100nF", "+5V_DRIVE", "GND", P)
part("J8", "FluxDrive:171825-4", "Drive power", "FluxDrive:171825-4",
     {"1": "+5V_DRIVE", "2": "GND", "3": "GND", "4": "+12V"}, P, lcsc="C210162")
```

  change J2's pins to `{"1": "+5V_IN", "2": "GND", "3": "GND", "4": "+12V"}`, and extend the test-pad list in block F
  with `"SEL_FD", "REAL_SEL", "REAL_MTR", "DF0_STATE", "DF1_STATE", "MODE_CLK"`. In `tests/test_bom.py::test_test_pads`
  add those six nets to `need`.
- [ ] **Step 5: run the whole suite** — `bash tools/export_netlist.sh && python -m pytest -q -p no:cacheprovider`.
  Expected: PASS, apart from the board tests in `tests/test_pcb.py` that read rev A's board (they are rewritten from
  Task 11 on; run the netlist tests with `--deselect` of `tests/test_pcb.py` and record that in the ledger). The
  exhaustive test takes about a minute; if it takes more than five, cache the pin map in `tests/logic.py`
  (`functools.lru_cache` on `id(nl)`) and re-run.
- [ ] **Step 6: ERC and PDF** — `"C:/Program Files/KiCad/10.0/bin/kicad-cli.exe" sch erc --severity-error
  --exit-code-violations -o build/erc.txt FluxDrive.kicad_sch` → exit 0 (`tests/test_sch_gen.py::test_real_schematic_erc`
  allows only `footprint_filter`); `kicad-cli sch export pdf -o FluxDrive_Schematic.pdf FluxDrive.kicad_sch`; open the
  PDF and check that block G is on the sheet with readable labels (`test_everything_fits_on_the_sheet` guards the size).
- [ ] **Step 7: commit** — "Rev B drive power behind its own eFuse, test pads; the steering logic proven on the
  netlist".

### Task 9: Schematic review

**Files:**
- Create: `docs/reviews/2026-09-30-revb-schematic-review.md`
- Modify: whatever the review's accepted findings touch

- [ ] **Step 1:** the four specialist reviews of rev A (Amiga bus, power and EMC, ESP32-S3 and USB, PCB-readiness and
  code), each by a fresh agent, on `FluxDrive_Schematic.pdf`, the exported netlist, `hardware/design.py` and the rev B
  spec; the bus reviewer also re-runs `tests/test_swap.py` and tries to break it (a state the oracle does not cover).
- [ ] **Step 2:** write the record (finding, severity, decision) as rev A's `docs/reviews/2026-09-29-schematic-review.md`
  does; fix blockers and majors, each with a failing test first; re-run the suite and ERC.
- [ ] **Step 3: commit** — "Rev B schematic review and fixes".

### Task 10: Footprints: module ground-pad hole and jumpers

**Files:**
- Modify: `FluxDrive.pretty/ESP32-S3-WROOM-1.kicad_mod`, `tests/test_sch_gen.py` (or a new `tests/test_footprints.py`)

- [ ] **Step 1: failing test** — `tests/test_footprints.py`:

```python
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
```

- [ ] **Step 2: run** `python -m pytest -q -p no:cacheprovider tests/test_footprints.py`. Expected: FAIL
  (`len(big) == 0`).
- [ ] **Step 3: implement** with a scratch script that parses the footprint with `tools.sexpr`, removes the four
  `pad "41" thru_hole` whose centre is within 1.0 mm of the ground pad's centre, and adds
  `(pad "41" thru_hole circle (at <cx> <cy>) (size 1.6 1.6) (drill 1.0) (layers "*.Cu" "F.Mask" "B.Mask")
  (zone_connect 2))`; update the footprint's `descr` with one sentence ("1.0 mm solder-through hole in the ground pad
  for hand soldering, rev B spec §9").
- [ ] **Step 4: run** the test → PASS; `python -m pytest -q -p no:cacheprovider tests/test_sch_gen.py` → PASS.
- [ ] **Step 5: commit** — "Module footprint: ground-pad solder-through hole".

### Task 11: Placement and outline

**Files:**
- Modify: `tools/pcb_place.py`, `tools/pcb_sync.py` (only if new footprints need library paths), `tests/test_pcb.py`

**Interfaces:**
- Consumes: the rev B netlist (Task 8), the footprints of Task 10.
- Produces: `tools/pcb_place.py` with `J6_PIN1`, `SHIFT = 17.78`, `row_a_parts(board) -> dict[ref, (x, y, rot)]`,
  outline `X0, Y0, X1, Y1`; the rule areas "J1 rows F", "J1 rows B", "J6 rows B", "J6 zone" (SMD-free, like rev A's
  connector zone), "antenna edge", "buck", "module underside", "USB-C body".

- [ ] **Step 1: failing tests** — in `tests/test_pcb.py` replace `test_outline`, `test_connector_zone_free`,
  `test_credit_and_revision` (text "FluxDrive v1 rev B"), the ref-based lookups (`R35`, `C5`–`C7`) with net-based
  helpers, and add:

```python
REV_A = (100.0, 93.5, 160.0, 148.0)          # rev A's outline (tools/pcb_place.py at c095b6c)


def _refs_on(board, net):
    from tools.netlist import _child, _children
    out = set()
    for fp in _children(board, "footprint"):
        ref = [p[2] for p in _children(fp, "property") if len(p) > 2 and p[1] == "Reference"][0]
        if any((_child(pad, "net") or [None, ""])[-1] == net for pad in _children(fp, "pad")):
            out.add(ref)
    return out


def test_outline(board):
    """Rev B §9: 60 mm wide; the south edge 2.4 mm north of rev A's (J1 stays over CN11), the north edge at most 20 mm
    north of rev A's: at most 72.1 mm."""
    x0, y0, x1, y1 = pcb.board_extents(board)
    assert abs((x1 - x0) - 60.0) < 0.1
    assert abs(y1 - (REV_A[3] - 2.4)) < 0.1
    assert y0 >= REV_A[1] - 20.0 - 0.01 and y1 - y0 <= 72.1 + 0.01


def test_j1_stays_and_j6_beside_it(board):
    fps = pcb.footprints(board)
    assert fps["J1"][:3] == (113.68, 141.55, 90.0)
    jx, jy, rot, layer = fps["J6"]
    assert (jx, rot, layer) == (113.68, 90.0, "F.Cu") and abs(jy - (141.55 - 17.78)) < 0.01


def test_connector_zones_free(board):
    """Review focus 5 of rev A, LCODE-9: no SMD courtyard in the bands J1's and J6's bodies and the iron need."""
    fps = pcb.footprints(board)
    for conn in ("J1", "J6"):
        jx, jy = fps[conn][0] + 20.32, fps[conn][1] - 1.27
        for ref, (x, y, rot, layer) in fps.items():
            if ref in ("J1", "J6", "J2", "J8") or ref.startswith(("H", "FID", "TP", "JP", "J7")) or layer != "F.Cu":
                continue
            assert not (abs(x - jx) < 27.0 and abs(y - jy) < 5.0), (conn, ref)


def test_filter_pads_beside_their_pull_ups(board):
    """Rev B §9: each unfitted 220 pF pad sits on its net after the 100 ohm, within 3 mm of that net's 100k."""
    import math
    pads = _pad_shapes(board)
    for sig in ("STEP", "SEL0", "SEL1", "MTR0"):
        net = f"/{sig}_B"
        caps = [(x, y) for ref, n, x, y, *_ in pads if n == net and ref.startswith("C")]
        res = [(x, y) for ref, n, x, y, *_ in pads if n == net and ref.startswith("R")]
        assert caps and res, sig
        assert min(math.dist(c, r) for c in caps for r in res) <= 3.0, sig


def test_placement_is_legal(board):
    """No two courtyards overlap (the legaliser's job, checked on the saved board)."""
    import subprocess
    r = subprocess.run([r"C:/Program Files/KiCad/10.0/bin/python.exe", str(ROOT / "tools" / "pcb_place.py"),
                        "--check", str(ROOT / "FluxDrive.kicad_pcb")], capture_output=True, text=True)
    assert r.returncode == 0 and "0 footprints differ" in r.stdout, r.stdout + r.stderr
```

- [ ] **Step 2: run** `python -m pytest -q -p no:cacheprovider tests/test_pcb.py -k "outline or j6 or zones or
  legal"` on the rev A board. Expected: FAIL (no J6, rev A outline).
- [ ] **Step 3: implement** in `tools/pcb_place.py`:
  - `SHIFT = 17.78`; `J6_PIN1 = (J1_PIN1[0], J1_PIN1[1] - SHIFT)`; outline `X0, Y0, X1, Y1 = 100.0, 93.5 - SHIFT - 0.1,
    160.0, 145.6` (69.9 mm; if Step 5 cannot legalise every part, grow `Y0` northwards in 0.5 mm steps, never past
    `73.5`);
  - every rev A `FIXED` and `SOFT` position north of J1 (`y < 135.0`) moves north by `SHIFT`; J1 and J2 stay; rev A's
    south strip (`SOUTH_STRIP`) goes: its test pads and FID3 get preferred spots in the band between J1's and J6's
    courtyards (`y` between `J6_PIN1[1] + 3.8` and `J1_PIN1[1] - 6.3`), each between two of J1's even-row pins;
  - `row_a_parts(board)` replaces `ROW_A_PARTS`: for each J1 even pin `n` with a net, the fitted resistors with one pad
    on that net — the pull-up (other pad on a rail) at `pin_x(n) - 0.55`, the 100 Ω at `+0.55`, the 33 Ω at `0.0`
    rotated 270 — placed at `ROW_A - SHIFT` (north of J6's courtyard); written as

```python
def row_a_parts(board):
    """{ref: (x, y, rot)} of the resistors on J1's even-pin nets, found by net (rev A used fixed refs)."""
    rails = {"/+5V_A", "/+3V3", "/GND"}
    j1 = {pad.GetNumber(): pad.GetNetname() for pad in board.FindFootprintByReference("J1").Pads()}
    out = {}
    for n in range(2, 35, 2):
        net = j1.get(str(n), "")
        if not net or net.startswith("unconnected"):
            continue
        for fp in board.GetFootprints():
            ref = fp.GetReference()
            if not ref.startswith("R") or fp.IsDNP():
                continue
            nets = [p.GetNetname() for p in fp.Pads()]
            if net not in nets:
                continue
            other = [x for x in nets if x != net][0]
            value = fp.GetValue()
            if other in rails:
                out[ref] = (round(pin_x(n) - 0.55, 3), ROW_A - SHIFT, 90)
            elif value == "100":
                out[ref] = (round(pin_x(n) + 0.55, 3), ROW_A - SHIFT, 90)
            elif value == "33":
                out[ref] = (round(pin_x(n), 3), ROW_A - SHIFT, 270)
    return out
```

    (J1 pin 30's 33 Ω, pin 34's, 26's, 28's, 2's and 8's; for pins with two resistors both offsets apply; check that
    the result has one entry per resistor that rev A's table had, minus the pin 4/6/14 ones);
  - new parts' preferred spots (`SOFT`, legalised in this order): U8, U12, U13, U16 and the latch resistors next to
    U2/U3 at the buffer row's west end; U10 and U11 between U4 and U2/U3 so each OR sits beside the buffer it feeds;
    U17 at the west end next to J1 pins 2/8's 33 Ω; U14, U15, U18 and the J6 4k7s north of J6 pins 4–16; U20 next to
    the _CHNG 33 Ω; JP1–JP4 and J7 in the J1–J6 band under J6 pins 10 and 16; JP5–JP7, D5, D6 and the RCs next to U8;
    U19, J9, J10 and U21–U23 at the east end of the J1–J6 band; U9, J8 and the drive capacitors in the west power strip
    north of J2 (J8 courtyard clear of J6's); J5 west of the module next to module pins 11 and 15;
  - rule areas: rev A's "J1 rows F" without the test-pad notches, "J1 rows B"; new "J6 rows B" (B.Cu, tracks not
    allowed, J6's pin field plus 1.2 mm) and "J6 zone" (the SMD-free band, as rev A's `CONNECTOR_ZONE`); the others as
    rev A, moved with the module.
- [ ] **Step 4: build a placed board** — `OUT=build/pcbB1 INSTALL=0` is not enough (the build routes); run the first
  steps by hand: `bash tools/export_netlist.sh`, `pcb_sync.py build/FluxDrive.net build/place/FluxDrive.kicad_pcb`,
  `pcb_place.py build/place/FluxDrive.kicad_pcb`, then `kicad-cli pcb drc --severity-error` on it: only
  `unconnected_items`, no courtyard overlaps. Every part the legaliser moves more than 1.5 mm is listed in the ledger.
- [ ] **Step 5:** copy the placed board to `FluxDrive.kicad_pcb` only for the test run (`git stash` afterwards is not
  needed: Task 12 overwrites it), run `python -m pytest -q -p no:cacheprovider tests/test_pcb.py -k "outline or j6 or
  zones or legal"` → PASS.
- [ ] **Step 6: commit** — "Rev B placement: J6 beside J1, the board 17.8 mm longer, row A found by net" (with the
  placed board as `FluxDrive.kicad_pcb`, marked unrouted in the commit message).

### Task 12: Hand routes, layout rules and routing

**Files:**
- Modify: `tools/pcb_prefan.py`, `tools/pcb_fanout.py`, `tools/pcb_stitch.py`, `tools/pcb_build.sh` (only if a
  step is added), `FluxDrive.kicad_pro` (a `Power` netclass pattern for `/+5V_DRIVE` and `/+12V` at 0.8 mm),
  `tests/test_pcb.py`

- [ ] **Step 1: failing tests** — append to `tests/test_pcb.py`:

```python
def _segments(board, net=None):
    import math
    from tools.netlist import _child, _children
    out = []
    for s in _children(board, "segment"):
        n = _child(s, "net")[-1]
        if net and n != net:
            continue
        a = (float(_child(s, "start")[1]), float(_child(s, "start")[2]))
        b = (float(_child(s, "end")[1]), float(_child(s, "end")[2]))
        out.append((n, _child(s, "layer")[1], a, b, float(_child(s, "width")[1]), math.dist(a, b)))
    return out


def _dist_point_segment(p, a, b):
    import math
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.dist(p, (ax + t * dx, ay + t * dy))


def test_no_track_near_the_gnd_rows(board):
    """Rev B §9: no track within 0.8 mm of J1's GND row on either layer, or of J6's GND row on B.Cu (0.8 mm edge to
    pad centre minus the pad radius)."""
    gnd = {c: [(x, y) for ref, net, x, y, hw, hh, rot, smd in _pad_shapes(board) if ref == c and net == "/GND"]
           for c in ("J1", "J6")}
    for net, layer, a, b, w, _ in _segments(board):
        if net == "/GND":
            continue
        for conn, layers in (("J1", ("F.Cu", "B.Cu")), ("J6", ("B.Cu",))):
            if layer in layers:
                for p in gnd[conn]:
                    assert _dist_point_segment(p, a, b) - w / 2 - 0.85 >= 0.8 - 0.01, (conn, net, layer, a, b)


def test_b_nets_short(board):
    """Rev B §9: every _B net at most 1.5 x its pad-to-pad length plus 5 mm (rev A: SIDE_B 111 mm)."""
    import math
    nets = {s[0] for s in _segments(board) if s[0].endswith("_B")}
    assert nets
    for net in nets:
        pads = [(x, y) for ref, n, x, y, *_ in _pad_shapes(board) if n == net]
        span = sum(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in zip(sorted(pads), sorted(pads)[1:]))
        length = sum(s[5] for s in _segments(board, net))
        assert length <= 1.5 * span + 5.0, (net, round(length, 1), round(span, 1))


def test_3v3_supply_pads_have_their_own_via(board):
    """Rev B §9: every IC supply pin and every decoupling capacitor's +3V3 pad reaches a +3V3 via of its own by at
    most 3 mm of track (followed along the segments, not measured straight)."""
    import math
    import collections
    segs = _segments(board, "/+3V3")
    vias = _vias(board, "/+3V3")
    graph = collections.defaultdict(list)
    for _, layer, a, b, w, length in segs:
        graph[a].append((b, length))
        graph[b].append((a, length))
    def reach(start):
        best, todo = {start: 0.0}, [start]
        while todo:
            p = todo.pop()
            for q, l in graph[p]:
                d = best[p] + l
                if d < best.get(q, 1e9) and d <= 3.0:
                    best[q] = d
                    todo.append(q)
        return best
    owners = collections.Counter()
    for ref, net, px, py, hw, hh, rot, smd in _pad_shapes(board):
        if net != "/+3V3" or not smd or not ref.startswith(("U", "C")) or ref == "U1":
            continue
        ext = max(hw, hh) + 0.01                                     # pads may be rotated: the larger half-size
        starts = [p for p in graph if abs(p[0] - px) <= ext and abs(p[1] - py) <= ext]
        found = sorted({v for s in starts for p in reach(s) for v in vias if math.dist(p, v) < 0.05})
        assert found, (ref, px, py)
        owners[found[0]] += 1
    assert max(owners.values()) == 1, owners.most_common(3)          # every pad its own via


def test_antenna_border_stitched(board):
    """Rev B §9: GND vias at most 3 mm apart along the antenna keep-out's south border."""
    fps = pcb.footprints(board)
    ux, uy = fps["U1"][0], fps["U1"][1]
    base = uy - 6.75
    xs = sorted(x for x, y in _vias(board, "/GND") if abs(y - (base + 1.0)) <= 1.5 and abs(x - ux) <= 24.0)
    assert xs and xs[0] <= ux - 24.0 + 3.0 and xs[-1] >= ux + 24.0 - 3.0
    assert max(b - a for a, b in zip(xs, xs[1:])) <= 3.0 + 0.01


def test_drive_power_paths_wide(board):
    """Rev B §6: +5V_DRIVE and +12V at least 0.8 mm, narrower only within 1 mm of U9's pads."""
    import math
    u9 = [(x, y) for ref, net, x, y, *_ in _pad_shapes(board) if ref == "U9"]
    for net in ("/+5V_DRIVE", "/+12V"):
        segs = _segments(board, net)
        assert segs, net
        for _, layer, a, b, w, _ in segs:
            if w < 0.8 - 0.01:
                assert min(min(math.dist(a, p), math.dist(b, p)) for p in u9) <= 1.0 + 0.3, (net, a, b, w)


def test_jumpers_bridged_in_copper(board):
    from tools.netlist import _children
    for fp in _children(board, "footprint"):
        ref = [p[2] for p in _children(fp, "property") if len(p) > 2 and p[1] == "Reference"][0]
        if ref in ("JP1", "JP2", "JP3", "JP4", "JP5"):
            assert "Bridged12" in fp[1], (ref, fp[1])
```

- [ ] **Step 2: run** these on the placed, unrouted board of Task 11. Expected: FAIL (no segments).
- [ ] **Step 3: implement.**
  - `tools/pcb_prefan.py`: redo rev A's hand routes for the new positions (VBUS bridge, +5V_A rail between the rows,
    the USB pad joins, `/DKRD_D` through its row-B gap); rev A's `EFUSE` list names refs, so find the parts by net
    now (`pad_on(fps, net, prefix)` below) and use it for U5 and U9 alike; and add the J1→J6 pass-through:

```python
def pad_on(fps, net, prefix):
    """The one pad on `net` of a footprint whose ref starts with `prefix` (refs are not stable in rev B)."""
    hits = [p for ref, fp in fps.items() if ref.startswith(prefix) for p in fp.Pads() if p.GetNetname() == net]
    assert len(hits) == 1, (net, prefix, len(hits))
    return hits[0]


PASS_1TO1 = ("2", "8", "18", "20", "22", "24", "26", "28", "30", "32", "34")
PASS_THROUGH = ("10", "12", "16")           # J1 nets that cross J6 to reach the logic (rev B §9)


def j1_to_j6(board, fps):
    """J1 pin n straight north on F.Cu, a 45-degree jog of half a pitch into the gap between J6's odd pins, past the
    odd row, then back onto J6 pin n (1:1 nets) or on past the even row as a stub the router continues."""
    j1 = {p.GetNumber(): p for p in fps["J1"].Pads()}
    j6 = {p.GetNumber(): p for p in fps["J6"].Pads()}
    odd_y, even_y = j6["1"].GetPosition().y, j6["2"].GetPosition().y      # south is +y: odd_y > even_y
    jog = mm(1.27)
    for n in PASS_1TO1 + PASS_THROUGH:
        a = j1[n].GetPosition()
        y_in = odd_y + mm(1.3)
        pts = [a, pcbnew.VECTOR2I(a.x, y_in + jog), pcbnew.VECTOR2I(a.x + jog, y_in)]
        if n in PASS_1TO1:
            pts += [pcbnew.VECTOR2I(a.x + jog, odd_y - mm(1.3)), j6[n].GetPosition()]
        else:
            pts += [pcbnew.VECTOR2I(a.x + jog, even_y - mm(1.3))]
        for u, v in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(u)
            t.SetEnd(v)
            t.SetWidth(mm(0.2))
            t.SetLayer(pcbnew.F_Cu)
            t.SetNet(j1[n].GetNet())
            t.SetLocked(True)
            board.Add(t)
```

    and a U9 entry in the eFuse routes: DRV_DVDT to its 22 nF, DRV_ILM to its 1K5, EN to U5's EN pad, pins 3/4 joined,
    each 0.2–0.3 mm as rev A's U5 tracks, plus 0.3 mm, 1 mm long stubs out of pins 3/4 and 5 that the router continues
    at the Drive class width. `main()` runs each group only when the board has none of its tracks yet (re-run safe).
  - `tools/pcb_fanout.py`: IC supply pins and decoupling pads on +3V3 never chain; a pad that gets no via in pass 1
    stops the build with its ref, so the placement is fixed rather than the rule bent:

```python
def own_via_only(fp, pad):
    """Rev B §9: IC supply pins and decoupling capacitors' +3V3 pads get a via of their own."""
    ref = fp.GetReference()
    return pad.GetNetname() == "/+3V3" and ref.startswith(("U", "C")) and ref != "U1"
```

    and in pass 2: `if own_via_only(fp, pad): stuck.append(ref)` instead of joining it; after pass 2
    `if stuck: sys.exit(f"no room for an own +3V3 via: {', '.join(sorted(stuck))}")`.
  - `tools/pcb_stitch.py`: before the grid pass, candidates along the antenna keep-out's border, taken first:

```python
def border_candidates(fps, y_top):
    """GND stitching every 2.5 mm, 1.0 mm outside the antenna keep-out (x +-24 mm around U1, south border at the
    antenna's base line): along its south border and up its east and west sides (rev B §9)."""
    ux, uy = pcbnew.ToMM(fps["U1"].GetPosition().x), pcbnew.ToMM(fps["U1"].GetPosition().y)
    base = uy - 6.75
    south = [(round(ux - 24.0 + 2.5 * i, 2), round(base + 1.0, 2)) for i in range(20)]
    sides = [(round(ux + dx, 2), round(y, 2)) for dx in (-25.0, 25.0)
             for y in [y_top + 1.0 + 2.5 * i for i in range(int((base - y_top) / 2.5))]]
    return south + sides
```

    Each border candidate still has to pass the clearance, hole and pad checks of the grid pass; the spacing rule
    between stitching vias does not apply to them.
  - `FluxDrive.kicad_pro`: `/+5V_DRIVE` and `/+12V` in a `Drive` netclass, track 0.8 mm, clearance 0.2 mm.
- [ ] **Step 4: build** — `OUT=build/pcbB bash tools/pcb_build.sh` (Freerouting; 15–60 min; do not edit `tools/`
  while it runs). Expected: DRC 0 errors, 0 unconnected, 0 parity; `pcb_place.py --check` 0 differences; the board
  installed as `FluxDrive.kicad_pcb`. If routes remain open, fix the cause (placement, a rule) as rev A's rulings did
  (hand route in `pcb_prefan.py`, ledger ruling) — never bend the tests.
- [ ] **Step 5: run** `python -m pytest -q -p no:cacheprovider`. Expected: PASS (all netlist and board tests).
- [ ] **Step 6: commit** — "Rev B routed: J1-J6 pass-through, drive power, own +3V3 vias, antenna border stitching".

### Task 13: Silkscreen, fit template and dummy

**Files:**
- Modify: `tools/pcb_silk.py`, `tests/test_pcb.py`, `mech/fit_template.pdf`, `mech/FluxDrive.step`

- [ ] **Step 1: failing test** — append to `tests/test_pcb.py`:

```python
def test_revb_labels(board):
    """Rev B §9: the labels a builder needs."""
    texts = " ".join(_texts(board, "F.SilkS") + _texts(board, "B.SilkS"))
    for need in ("FluxDrive v1 rev B", "TO DRIVE", "TO CN11", "DRIVE POWER", "plug before J6", "CUT 1-2", "CHECK",
                 "BRIDGE 2-3", "REAL (both)", "DF0 at power-on", "mode 4", "FD", "REAL", "SCL", "SDA"):
        assert need in texts, need
```

- [ ] **Step 2: run** → FAIL on "TO DRIVE".
- [ ] **Step 3: implement** in `tools/pcb_silk.py`: rev B text instead of rev A; J6 "TO DRIVE" and J1 "TO CN11" next to
  their pin 1; J8 "DRIVE POWER – plug before J6"; J7's three pads "FD / GND / REAL" and "DF0 switch"; the bypass pair
  "BYPASS: CUT 1-2, CHECK, BRIDGE 2-3" and "REAL (both)" at JP6/JP7; JP5 "DF0 at power-on"; JP3/JP4 and U21–U23
  "mode 4, see README"; J5's pins "GND 3V3 SCL/IO18 SDA/IO3"; the test pads moved from the south strip keep their
  labels; every text 1.0 mm high (`test_silkscreen_text_height`), placed from its pads as rev A's `PAD_TEXTS`.
- [ ] **Step 4: run** `bash tools/pcb_build.sh` again (the silk step is part of the build) or `pcb_silk.py` on the
  installed board followed by DRC; `bash tools/fit_template.sh`; check the PDF scale bars (50 mm and 40 mm), print it,
  and ask Dimitri for the fit test with J6, its plug and the drive power cable (spec §12). The fit test result goes
  into the ledger; a failed fit returns to Task 11 with a ruling.
- [ ] **Step 5: commit** — "Rev B silkscreen, fit template and STEP".

### Task 14: Layout review

**Files:**
- Create: `docs/reviews/2026-09-30-revb-layout-review.md`

- [ ] **Step 1:** the same four reviewers on the routed board (plots per layer, DRC report, placement, the tests),
  against the rev B spec and the schematic review record; the PCB reviewer checks the review-focus lines of this plan
  on the board.
- [ ] **Step 2:** record and decide as rev A's layout review did; fix blockers and majors with failing tests first,
  rebuild with `tools/pcb_build.sh`, suite and DRC clean.
- [ ] **Step 3: commit** — "Rev B layout review and fixes".

### Task 15: Production files, README and the v1 spec v0.5

**Files:**
- Modify: `jlcpcb/production_files/*`, `docs/images/*`, `README.md`,
  `docs/superpowers/specs/2026-09-28-fluxdrive-v1-hardware-design.md`, `tests/test_pcb.py`

- [ ] **Step 1:** `bash tools/jlc_production.sh`; `python -m pytest -q -p no:cacheprovider tests/test_pcb.py -k
  production` → PASS (U1 and the DNP parts out, every fitted SMD part in); check the BOM for the new parts and their
  LCSC numbers and stock (spec §4.9, R10) and record the stock in the ledger.
- [ ] **Step 2:** renders `kicad-cli pcb render --side top/bottom` and a 3D view to `docs/images/fluxdrive-v1b-*.png`.
- [ ] **Step 3:** README: a "Rev B" section — what it adds (the original drive next to FluxDrive, the four modes, the
  GTi and switch control), J6 and J8 with the drive power cable (TE 171822-4 + 170204-2, pin 1 to pin 1, continuity
  check, never J6 without J8), the jumper table with delivered states and the "cut, check, bridge" order, the bypass
  procedure, mode 4 and its wire, the reset wire, external drives (DF2/DF3 switch or a select-shifting adapter),
  soldering the module through its ground-pad hole, the new test pads, the order settings (4 layers, rev B BOM/CPL),
  and the checks before ordering (spec §12).
- [ ] **Step 4:** the v1 spec gets v0.5 with the changes of the rev B spec §13, and a pointer to the rev B spec.
- [ ] **Step 5: run** the whole suite → PASS; **commit** — "Rev B production files, render, README; v1 spec v0.5".
