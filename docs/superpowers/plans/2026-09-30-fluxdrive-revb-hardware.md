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
- The drive's +5 V comes from +5V_IN through its own TPS259531 with R_ILM = 1K37, a current limit of 1.50 A (spec §6;
  open item R9 can still change the value before the layout freezes); +12 V passes J2.4 → J6pwr.4 (spec §6).
- Board 60 mm wide, at most 72.1 mm long, J1 at rev A's position over CN11, J6 17.78 mm north of J1 with the same
  orientation and pin 1 on the same side (spec §9).
- Unfitted pads are 0603 (resistors, capacitors) or SOT (ICs); JLC does not close solder jumpers, so default-closed
  jumpers are copper-bridged 3-pad footprints (spec §4.7, §9).
- U1 (the ESP32 module) stays hand-placed (`tools/assembly.py`); its ground pad gets a 1.0 mm solder-through hole
  (spec §9).
- Board tools run with KiCad's Python; pcbnew bindings are unreliable after `board.Remove()`, so removals run in a
  process that then only saves and exits. Do not edit `tools/` while `tools/pcb_build.sh` runs (rev A LCODE-1).
- Tests run with the system Python, which has no pcbnew: whatever a test imports from `tools/` must not import pcbnew
  (Task 1 moves such helpers into `tools/jlc_rules.py` and `tools/netclass.py`).
- Net names in the netlist and on the board carry a leading "/" (local labels); `tools/netlist.py` strips it for the
  netlist tests, the board tests keep it.
- Every test is seen failing before the change that makes it pass. A test that checks work already done (coverage,
  or behaviour that earlier tasks built) passes at once: the step says so, the ledger records it, and a mutation
  shows it can fail (Task 8 Step 4).
- Scratch scripts (`build/revb/`, not committed) work on the repository they are run from (`pathlib.Path.cwd()`),
  never on a hard-coded path into the main tree, so a worktree run cannot touch the main tree.

## Review Focus

1. **A mode change during a disk access** (a GTi request, the switch, an ESP32 restart in the middle of a track
   read): no select or motor pulse reaches the real drive and FluxDrive never answers a select it does not own.
   Task 8's `test_every_order_of_events` enters every reachable state of the selects, the D inputs, the clock request
   and the switch by every single event; `test_clock_request_waits_for_the_access_to_end`,
   `test_request_dropped_inside_an_access_is_lost` and `test_switch_moved_during_an_access` step the named orders.
2. **The bypass or a mode-4 jumper converted in the wrong order** (2–3 bridged before 1–2 is cut): with both pads
   bridged the bypass latches /SEL0 and /MTR0 low and an M4 jumper shorts a push-pull output (spec §4.4). A static
   model cannot show that latch-up; the silkscreen order (Task 13) and the README (Task 15) prevent it, not a test.
   Task 8's `test_steering_logic` evaluates every legal jumper state (bypass, the REAL pair in its four states, mode
   4) and checks that one select never reaches both drives; `test_illegal_bypass_states_put_two_drives_on_sel0` shows
   why the bypass without DF0_FD held at 0 is not legal.
3. **No real drive on J6, or J6 plugged without J6pwr**: with nothing on J6, modes 1–3 must leave the bus as a
   stock A500 with FluxDrive as DF0 or no DF0; with an unpowered drive the lines read asserted — Task 6's test checks
   J6's pull-ups hold every J6-only line inactive with nothing plugged in; the README (Task 15) carries the J6pwr rule.
4. **An ESP32 that never boots** (blank flash, crash loop): the A500 must boot from the real drive as stock, with
   /CHNG, /RDY, _KBRESET and every J6 line inactive — Task 8's `test_esp32_reset_changes_nothing` leaves every control
   GPIO undriven and then with its internal pull-up, and `test_esp32_glitch_changes_nothing` drives GPIO1–17 low as
   the ESP32 does for 60 µs at every reset.
5. **A board rebuilt from the committed scripts** must be the committed board: `tools/pcb_place.py --check` and the
   production-files test (Task 1 adds rotations to it; Task 15) fail if placement or CPL drift.

---

## File structure

| File | Change | Responsibility |
|---|---|---|
| `hardware/design.py` | modify | rev B parts and nets: block A inputs, block B gated outputs, block C drive power, block F J5 and test pads, new block G |
| `FluxDrive.kicad_sym` | modify | adds the `74LVC1G157` symbol (copied from the Nano-Tek library) |
| `FluxDrive.pretty/ESP32-S3-WROOM-1.kicad_mod` | modify | ground-pad solder-through hole |
| `tests/logic.py` | create | gate-level evaluator of the exported netlist |
| `tests/test_logic_model.py` | create | tests of the evaluator itself on tiny netlists |
| `tests/test_swap.py` | create | rev B steering logic: structure, the exhaustive combinational test and the sequential tests |
| `tests/test_bus.py`, `tests/test_power.py`, `tests/test_esp.py`, `tests/test_bom.py` | modify | rev B nets, pull-ups, GPIOs, J5, BOM rules |
| `tests/test_footprints.py` | create | the module footprint's solder-through hole (Task 10) |
| `tests/test_pcb.py` | modify | Task 1: rule areas by layer, antenna copper-free, production rotations, buck to the antenna; from Task 11: rev B outline, J6, zones, clearances, via rules, stitching, silk, net-based lookups |
| `tests/test_tools.py`, `tests/test_sch_gen.py`, `tests/fixtures/tiny_design.py` | modify | the deferred minors (Task 1) |
| `tools/jlc_rules.py`, `tools/netclass.py` | create | pcbnew-free helpers the tests import: BOM comment and CPL rotation; netclass track widths (Task 1) |
| `tools/jlc_export.py`, `tools/jlc_production.sh`, `tools/fit_template.sh`, `tools/pcb_maze.py`, `tools/netlist.py`, `tools/sch_gen.py` | modify | the deferred minors (Task 1) |
| `tools/pcb_place.py` | modify | rev B outline and placement, net-based row A, J6 zones |
| `tools/pcb_prefan.py` | modify | J1→J6 pass-through routes, drive power path, redone rev A hand routes |
| `tools/pcb_fanout.py` | modify | own +3V3 via for every IC supply pin and decoupling pad |
| `tools/pcb_stitch.py` | modify | GND stitching along the antenna keep-out border |
| `tools/pcb_silk.py` | modify | rev B texts and labels |
| `README.md`, `docs/superpowers/specs/2026-09-28-fluxdrive-v1-hardware-design.md` | modify | rev B build notes, v1 spec v0.5 |
| `docs/reviews/2026-09-30-revb-schematic-review.md`, `…-revb-layout-review.md`, `…-revb-final-review.md` | create | review records (Tasks 9, 14, 16) |

## Names every task uses

Refs of R, C and TP are assigned in the order parts are added and are **not** stable across tasks: tests and tools find
them by their nets. The refs below are fixed by name in `part()` calls.

| Ref | Part (value) | Pins → nets |
|---|---|---|
| U8 | `74LVC74A` (symbol `74xx:74LS74`, TSSOP-14, C6100) | 1 CLR_A, 2 DF0_REQ, 3 MODE_CLK, 4 PRE_A, 5 DF0_FD, 6 NC; 13 CLR_B, 12 DF1_REQ, 11 MODE_CLK, 10 PRE_B, 9 DF1_EN, 8 NC; 7 GND, 14 +3V3 |
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
| U22 | `SN74LVC1G175` (`74xGxx:74LVC1G175`, SOT-23-6, C128412 = SN74LVC1G175DBVR), DNP, not in the BOM | 1 CLK SEL1, 3 D M4_MOTOR, 6 CLR DF1_EN, 4 Q M4_MTR_Q; 2 GND, 5 +3V3 |
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
| D5, D6 | 1N4148W (`Device:D`, SOD-123, C81598, JLC basic) | D5: A CLR_B, K +3V3; D6: A POR_A, K +3V3 |

- U8 uses the base symbol `74xx:74LS74` (same pins as `74HC74`, which `extends` it), as rev A's U4 uses `74LCX07`.
  Task 1 also teaches `tools/sch_gen.py` to keep a parent's properties, so a derived symbol would pass ERC too.
- D5 and D6: spec §4.9's parts row says "Schottkys … SOD-323", but §4.6 names the 1N4148W (a switching diode, JLC basic
  part C81598 in SOD-123, checked on jlcpcb.com on 2026-09-30). The plan follows §4.6: 1N4148W in SOD-123. Record this
  ruling in the ledger at Task 5.

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
+3V3–GND per new IC (DNP, 0603, for U21–U23); drive power: 22 nF DRV_DVDT–GND, 22 µF and 100 nF +5V_DRIVE–GND, and
**1K37 DRV_ILM–GND**: 2000/1370 + 0.04 = 1.50 A (spec §6, TI SLVSE57C Eq. 4).

**The R_ILM part** (looked up on 2026-09-30): UNI-ROYAL 0402WGF1371TCE, 1.37 kΩ ±1 %, 0402 (the package `R()` gives
every fitted resistor), LCSC **C423239**; 8,500 in stock at LCSC, 8,536 at JLC; a JLC **Extended** part, so one more
extended type (about $3 per order) on top of the seven of spec §13. `RES_LCSC` gets `"1K37": "C423239"`. 1K5
(C25867, JLC Basic, already in the BOM) would give 1.37 A; open item R9 (the drive's peak current, measured by Dimitri
before the layout freezes) can still change the value, and the test (`1.4 <= ilim <= 1.6`) with it.

---

### Task 1: Deferred tool and test minors

**Files:**
- Create: `tools/jlc_rules.py`, `tools/netclass.py`
- Modify: `tools/jlc_export.py`, `tools/jlc_production.sh:18`, `tools/fit_template.sh`, `tools/pcb_maze.py`,
  `tools/netlist.py:21`, `tools/sch_gen.py:49-64, 203`, `tests/fixtures/tiny_design.py`, `jlcpcb/production_files/*`
- Test: `tests/test_tools.py`, `tests/test_sch_gen.py`, `tests/test_pcb.py`

Every deferred minor of `docs/reviews/2026-09-30-build-rulings.md` ("Deferred minor findings"), before rev B changes
anything else (spec §9). Each one gets a failing test here, a written ruling here, or a named later task.
"Coverage" marks a test that tightens a check the code or board already meets: it passes at once (Step 2).

| Deferred minor | Where it is handled |
|---|---|
| SPCB-8: test pads 1.0 mm, small for pogo pins | ruling: settled by rev A's layout review (LPCB-6: 1.0 mm probe pads, no pogo fixture in v1); rev B keeps `TestPoint_Pad_D1.0mm` for all 22 pads. Cost if wrong: a later fixture needs 1.5 mm pads, a footprint change |
| SCODE-6: the tiny test design covers little (rotations, DNP, pin by name, `unconnected-`, the hard-coded `parts[1]`) | Step 1, `test_tiny_design_round_trips` and the fixture (coverage) |
| SCODE-7: `netlist.py` does not unescape `\` | Step 1, `test_netlist_strings_unescaped` |
| SCODE-7: `p["_numbers"]` is unused | ruling: the line goes (Step 3); a removal has no failing test, the suite passing is its check |
| SCODE-7: `lib_symbol` drops parent-only properties | Step 1, `test_derived_symbol_matches_its_library` |
| SCODE-7: A0 paper | ruling: stays; rev A's Task 7 ruling (the smallest of A2/A1/A0 that fits; the design needs A0). Cost if wrong: a large sheet to print |
| +3V3 own vias at U2–U4 pin 14 and C17/L1; decoupling by track path | Task 12 (`test_3v3_supply_pads_have_their_own_via`) |
| CHNG_D along the J1 GND row; 0.8 mm in rev B | Task 12 (`test_no_track_near_the_gnd_rows`) |
| `fit_template.sh` accepts any missing model and a stale STEP | Step 3; checked by running it in Step 4 |
| tests weaker than their docstrings: antenna (zones, pads) | Step 1, `test_antenna_area_copper_free_on_every_layer` (coverage) |
| … rule areas by name only | Step 1, `test_rule_areas_cover_their_layers` (coverage) |
| … production: R/C positions only, no rotations | Step 1, `test_production_check_sees_a_moved_or_turned_part` |
| … buck: measured to the board edge, not to the antenna | Step 1, `test_buck_away_from_dkrd_and_antenna` (coverage) |
| … pin-1 docstring 4 mm against a 6 mm test | Step 1, docstring |
| sparse GND vias along the antenna keep-out's east side | Task 12 (`test_antenna_border_stitched`) |
| empty `org.kicad.kicad/` entry in the gerber zip | Step 1, `test_gerber_zip_holds_files_only` |
| J3's CPL at its pad centre, 0.16 mm off its origin | ruling: harmless (JLC places by pad centre); the production check allows 0.2 mm for parts other than R and C |
| BOM comment "BOOT" for SW1 and SW2 | Step 1, `test_bom_comment_lists_every_value` |
| LCODE-8 (layout review): the maze router's widths are hard-coded | Step 1, `test_maze_router_takes_its_widths_from_the_netclasses` |

- [ ] **Step 1: failing tests.**
  - `tests/test_tools.py`: add `import pathlib` as its first line and append:

```python


ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_bom_comment_lists_every_value():
    """Build-rulings minor: parts grouped in one BOM line with different values show all of them (SW1 BOOT and SW2
    RESET gave the comment "BOOT")."""
    from tools.jlc_rules import comment
    assert comment(["BOOT", "RESET"]) == "BOOT/RESET"
    assert comment(["100K", "100K"]) == "100K"


def test_gerber_zip_holds_files_only():
    """Build-rulings minor: kicad-cli leaves an org.kicad.kicad/ directory; the zip must not carry it."""
    import zipfile
    zp = ROOT / "jlcpcb" / "production_files" / "GERBER-FluxDrive.zip"
    assert all(not n.endswith("/") for n in zipfile.ZipFile(zp).namelist())


def test_maze_router_takes_its_widths_from_the_netclasses():
    """LCODE-8: tools/pcb_maze.py reads the track widths of FluxDrive.kicad_pro's netclasses, not constants."""
    from tools.netclass import netclass_widths, width_of
    w = netclass_widths(ROOT / "FluxDrive.kicad_pro")
    assert width_of("/+5V_A", *w) == 0.3 and width_of("/STEP_B", *w) == 0.2       # Power and Default
    src = (ROOT / "tools" / "pcb_maze.py").read_text(encoding="utf-8")
    assert "width_of(" in src and "POWER = {" not in src


def test_netlist_strings_unescaped():
    """SCODE-7: KiCad escapes a backslash and a quote in netlist strings; both must come back as themselves."""
    from tools.netlist import _parse_sexpr
    assert _parse_sexpr(r'(net (name "A\\B\"C"))') == ["net", ["name", 'A\\B"C']]
```

  - `tests/fixtures/tiny_design.py`: add two parts at the end of `PARTS` (SCODE-6: a rotation of 180 and one of 270,
    an unfitted part, pins given by name):

```python
    dict(ref="R3", lib="Device:R", value="1K", footprint="Resistor_SMD:R_0603_1608Metric", lcsc="",
         pins={"1": "OUT", "2": "GND"}, block="A. test", dnp=True, rot=180, in_bom=False),
    dict(ref="D1", lib="Device:D", value="1N4148W", footprint="Diode_SMD:D_SOD-123", lcsc="C81598",
         pins={"K": "+3V3", "A": "SIG"}, block="A. test", dnp=False, rot=270, in_bom=True),
```

  - `tests/test_sch_gen.py`: in `test_tiny_design_round_trips`, after the `U1` pin-14 line, add

```python
    assert not nl.fitted("R3") and nl.fitted("R1")                                   # SCODE-6: DNP comes through
    assert (nl.net_of("R3", 1), nl.net_of("R3", 2)) == ("OUT", "GND")                # rotated 180
    assert (nl.net_of("D1", 1), nl.net_of("D1", 2)) == ("+3V3", "SIG")               # pins by name, rotated 270
    assert (nl.net_of("U1", 4) or "").startswith("unconnected-")                    # a pin left open
```

    in `test_missing_pin_is_an_error` and `test_pin_assigned_twice_is_an_error` replace `parts[1]` with
    `next(p for p in parts if p["ref"] == "U1")`, and append:

```python


def test_derived_symbol_matches_its_library(tmp_path):
    """SCODE-7: lib_symbol keeps the properties a derived symbol takes from its parent (74HC74 extends 74LS74, which
    alone has ki_locked); without them ERC reports lib_symbol_mismatch."""
    pins = {"1": "+3V3", "2": "GND", "3": "GND", "4": "+3V3", "10": "+3V3", "11": "GND", "12": "GND", "13": "+3V3",
            "5": None, "6": None, "8": None, "9": None, "7": "GND", "14": "+3V3"}
    parts = [dict(ref="U1", lib="74xx:74HC74", value="74HC74", footprint="Package_SO:TSSOP-14_4.4x5mm_P0.65mm",
                  pins=pins, block="A. test", rot=0)]
    sch = tmp_path / "ff.kicad_sch"
    sch.write_text(sch_gen.generate("t", ["A. test"], parts, ["+3V3", "GND"]), encoding="utf-8", newline="\n")
    rep = tmp_path / "erc.txt"
    subprocess.run([CLI, "sch", "erc", "--severity-all", "-o", str(rep), str(sch)], check=True, capture_output=True)
    assert "lib_symbol_mismatch" not in rep.read_text(encoding="utf-8")
```

  - `tests/test_pcb.py`: in `test_pin1_marked_both_sides` change the docstring's "within 4 mm" to "within 6 mm";
    replace `test_buck_away_from_dkrd_and_antenna` with

```python
def test_buck_away_from_dkrd_and_antenna(board):
    """Spec 8: the buck (switch node: U6, L1) at least 15 mm from /DKRD and from the antenna (its nearest point, not
    the board edge: build-rulings minor)."""
    import math
    fps = pcb.footprints(board)
    ux, uy = fps["U1"][0], fps["U1"][1]
    top, base = uy - 12.8, uy - 6.75                        # the antenna: module body top to the antenna's base line
    sw = _pads(board, "U6", "/BUCK_SW") + _pads(board, "L1", "/BUCK_SW")
    dkrd = _pads(board, "J1", "/_DKRD") + _pads(board, "R35", "/_DKRD") + _pads(board, "R35", "/DKRD_D") \
        + _pads(board, "U4", "/DKRD_D")
    assert sw and len(dkrd) == 4
    for sx, sy in sw:
        assert min(math.dist((sx, sy), d) for d in dkrd) >= 15.0
        ax, ay = min(max(sx, ux - 9.0), ux + 9.0), min(max(sy, top), base)
        assert math.dist((sx, sy), (ax, ay)) >= 15.0
```

    and append:

```python


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
            "module underside": ["F.Cu"], "USB-C body": ["F.Cu"], "buck F": ["F.Cu"], "buck B": ["B.Cu"]}
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
```

- [ ] **Step 2: run them** — `python -m pytest -q -p no:cacheprovider tests/test_tools.py tests/test_sch_gen.py
  tests/test_pcb.py`. Expected: 6 failed —
  - `test_bom_comment_lists_every_value`: `ModuleNotFoundError: No module named 'tools.jlc_rules'`;
  - `test_gerber_zip_holds_files_only`: `AssertionError` (the zip's last entry is `org.kicad.kicad/`);
  - `test_maze_router_takes_its_widths_from_the_netclasses`: `ModuleNotFoundError: No module named 'tools.netclass'`;
  - `test_netlist_strings_unescaped`: `AssertionError` (the backslash comes back doubled);
  - `test_derived_symbol_matches_its_library`: `AssertionError` (the report holds `lib_symbol_mismatch`);
  - `test_production_check_sees_a_moved_or_turned_part`: `NameError: name '_placement_mismatch' is not defined`.

  The other new or changed tests pass on rev A's board and design: `test_buck_away_from_dkrd_and_antenna` (21.6 mm to
  the antenna), `test_rule_areas_cover_their_layers`, `test_antenna_area_copper_free_on_every_layer` and the four new
  lines of `test_tiny_design_round_trips`. They are coverage, as rev A's `test_connector_zone_free` was; note that in
  the ledger.

- [ ] **Step 3: implement.**
  - Create `tools/jlc_rules.py` (the rotation table moves here from `tools/jlc_export.py`, unchanged):

```python
"""The JLC BOM and CPL rules of tools/jlc_export.py that need no pcbnew, so the tests (system Python) can import them.

Rotation: KiCad's plus a correction per footprint for JLC's package orientation. The corrections are the ones the
Nano-Tek Rev 1.2 CPL (made by the JLCPCB Tools plugin, assembled by JLC) used; SOIC follows TSSOP, the same KiCad
pin-1 orientation.
"""
import re

# footprint name regex -> degrees added to KiCad's rotation, first match wins
ROTATION = [
    (r"^LQFP-", 270),                 # U1 in Rev 1.2
    (r"^SOT-23", 180),                # U3 (SOT-23-5) and Q1 (SOT-23) in Rev 1.2; also SOT-23-6
    (r"^SOT-363", 180),               # SC-70-6: the same orientation as the SOT-23 family
    (r"^TSSOP-", 0),                  # U2 in Rev 1.2
    (r"^SOIC-", 0),                   # same pin-1 orientation as TSSOP in KiCad (check in JLC's preview)
    (r"^(MSOP|VSSOP)-", 0),           # the same pin-1 orientation as TSSOP in KiCad
    (r"^IDC-Header_2x", 270),         # CN3 in Rev 1.2
    (r"^Pin(Header|Socket)_", 270),   # J1-J4 in Rev 1.2
]


def correction(fp_name):
    """Degrees JLC's CPL adds to KiCad's rotation for this footprint name (the library item, no library prefix)."""
    for pattern, deg in ROTATION:
        if re.search(pattern, fp_name):
            return deg
    return 0


def comment(values):
    """BOM comment for a group of parts: every distinct value, in order of first appearance, joined by "/"."""
    seen = []
    for v in values:
        if v not in seen:
            seen.append(v)
    return "/".join(seen)
```

  - `tools/jlc_export.py`: delete the `ROTATION` list with its comment line (lines 26–36) and `def correction()`
    (lines 43–47; `BODY_CENTRE` between them stays), and below the `tools.assembly` import add
    `from tools.jlc_rules import comment, correction  # noqa: E402`. In `main()` replace the comment expression of
    `rows.append([...])` (the whole `ps[0]["value"] if len({...}) == 1 else sorted(...)[0]["value"]` line) with
    `comment([p["value"] for p in sorted(ps, key=lambda p: natural(p["ref"]))]),`.
  - `tools/jlc_production.sh` line 18: zip only regular files — replace `[z.write(f, f.name) for f in
    sorted(src.iterdir())]` with `[z.write(f, f.name) for f in sorted(src.iterdir()) if f.is_file()]`.
  - `tools/fit_template.sh`: replace the `if ! out=$(…); then … fi` block and the comment above it with the block
    below: it deletes the old STEP first and accepts exit 2 only when every error line names a known model gap.

```bash
# kicad-cli exits 2 when a model is missing. Known gaps: the USB-C has a VRML model only (3dmodels/), and KiCad 10
# has no STEP model for the buttons (SW1, SW2) or the eFuses (U5, U9). None of them is taller than 3.3 mm.
# Any other error fails, and so does an empty STEP; the old STEP goes first, so a failed export cannot leave it.
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

  - Create `tools/netclass.py`:

```python
"""Track widths from a KiCad 10 project's netclasses (LCODE-8). No pcbnew, so the tests can import it."""
import fnmatch
import json
import pathlib


def netclass_widths(pro_path):
    """({class: track width mm}, [(net pattern, class)]) from a KiCad 10 project file."""
    ns = json.loads(pathlib.Path(pro_path).read_text(encoding="utf-8"))["net_settings"]
    widths = {c["name"]: c["track_width"] for c in ns["classes"]}
    return widths, [(p["pattern"], p["netclass"]) for p in ns.get("netclass_patterns", [])]


def width_of(net, widths, patterns):
    """The track width of `net`: the class of its first matching pattern, else Default."""
    for pat, cls in patterns:
        if fnmatch.fnmatchcase(net, pat):
            return widths.get(cls, widths["Default"])
    return widths["Default"]
```

  - `tools/pcb_maze.py` (LCODE-8): below `import pcbnew` add

```python

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.netclass import netclass_widths, width_of  # noqa: E402
```

    replace the line `POWER = {"/+5V_IN", …}   # the "Power" netclass: 0.3 mm` with
    `WIDTHS = netclass_widths(ROOT / "FluxDrive.kicad_pro")      # LCODE-8: track widths from the netclasses`; in
    `Obstacles.__init__` replace `(SOFT_POWER if it.GetNetname() in POWER else SOFT)` with
    `(SOFT_POWER if width_of(it.GetNetname(), *WIDTHS) > WIDTHS[0]["Default"] else SOFT)`; in `route_in_window`
    replace `w = 0.3 if net.GetNetname() in POWER else 0.2` with `w = width_of(net.GetNetname(), *WIDTHS)`.
  - `tools/netlist.py` line 21 (SCODE-7): replace `stack[-1].append(tok[1:-1].replace('\\"', '"'))` with
    `stack[-1].append(re.sub(r"\\(.)", r"\1", tok[1:-1]))`.
  - `tools/sch_gen.py` (SCODE-7): delete the unused line `p["_numbers"] = sorted(…)` in `generate()`, and in
    `lib_symbol()` replace the `props = …` line with these three lines, so a parent's property the child does not
    override (such as 74LS74's `ki_locked`) stays, in the parent's order:

```python
        own = {c[1]: c for c in sym[2:] if isinstance(c, list) and c[0] == "property"}
        inherited = [c for c in parent[2:] if isinstance(c, list) and c[0] == "property"]
        props = [own.pop(c[1], c) for c in inherited] + list(own.values())    # SCODE-7: parent-only ones stay
```

  - `tests/test_pcb.py`: in `_production_mismatches` replace `want[props["Reference"]] = (float(at[1]), float(at[2]))`
    with

```python
            want[props["Reference"]] = (float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0,
                                        fp[1].split(":")[-1])
```

    replace its position loop (from `for ref, (x, y) in want.items():` to `return bad`) with

```python
    bad += [ref for ref, w in want.items() if ref in cpl and _placement_mismatch(ref, w, cpl[ref])]
    return bad
```

    replace its docstring with

```python
    """What differs between the board and the BOM/CPL in out_dir: missing or extra designators, and parts whose
    CPL place or rotation is not the footprint's (a CPL left from an earlier build)."""
```

    and append the helper:

```python


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
```

  The rev A schematic does not change: its derived symbols (SS34, SMAJ13A, TLV62569DBV, USBLC6-2SC6) already carry
  every parent property, so `python tools/sch_gen.py FluxDrive.kicad_sch` gives the committed file byte for byte.
- [ ] **Step 4: run** —
  - `bash tools/jlc_production.sh` → exit 0; `git diff --stat jlcpcb` shows `BOM-FluxDrive.csv` (one line: `BOOT/RESET`)
    and the gerber zip; the CPL is unchanged.
  - `bash tools/fit_template.sh` → exit 0 with the "note: no STEP model …" line; then `git checkout -- mech` (the
    board did not change; Task 13 makes the rev B files).
  - `"C:/Program Files/KiCad/10.0/bin/python.exe" -c "import sys; sys.path.insert(0, 'tools'); import pcb_maze;
    print(pcb_maze.WIDTHS[0])"` → `{'Default': 0.2, 'Power': 0.3}` (the maze router still imports under KiCad's
    Python).
  - `python -m pytest -q -p no:cacheprovider` → all pass: 81 passed (rev A's 73 and the 8 new tests).
- [ ] **Step 5: commit** — `git -c core.autocrlf=false add -A tools tests jlcpcb && git -c core.autocrlf=false commit
  -m "Tools and tests: the deferred minors of rev A"`. Record the four rulings of the table above in the ledger.

### Task 2: Logic evaluator and the 1G157 symbol

**Files:**
- Create: `tests/logic.py`, `tests/test_logic_model.py`
- Modify: `FluxDrive.kicad_sym` (add `74LVC1G157`), `tests/test_sch_gen.py`

**Interfaces:**
- Produces: `tests.logic.evaluate(nl, sources, state=None, bridged=None, fit=()) -> dict[str, int | None]`;
  `tests.logic.STRONG, OD, PULL, WEAK` (3, 2, 1, 0.5); `tests.logic.Conflict`; `tests.logic.NoFixedPoint`;
  `tests.logic.GATES` (value → gate list), `tests.logic.FLIPFLOPS` (value → flip-flop list);
  `tests.logic.pin_map(nl) -> {ref: {pin: net}}`.
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


def test_divider_between_rails_is_no_logic_level():
    """AMIGA_PWR, EFUSE_EN and BUCK_FB are dividers between two rails: an analog level (None), not a Conflict."""
    nl = nl_of([("R1", "1K", {"1": "+5V_A", "2": "MID"}, True), ("R2", "1K5", {"1": "MID", "2": "GND"}, True)])
    assert evaluate(nl, {})["MID"] is None


def test_released_open_drain_does_not_hold_its_bus_low():
    """A 33 ohm series resistor must not hand a net's own low back to it once its driver has released."""
    nl = nl_of([("U1", "74LVC14A", {"1": "A", "2": "B", "7": "GND", "14": "+3V3"}, True),
                ("R1", "10K", {"1": "B", "2": "GND"}, True),
                ("U2", "SN74LVC2G07", {"1": "B", "6": "OUT", "3": "GND", "4": "X", "2": "GND", "5": "+3V3"}, True),
                ("R2", "33", {"1": "OUT", "2": "BUS"}, True)])
    v = evaluate(nl, {"A": (0, STRONG), "BUS": (1, PULL)})
    assert v["OUT"] == v["BUS"] == 1
```

- [ ] **Step 2: run** `python -m pytest -q -p no:cacheprovider tests/test_logic_model.py`. Expected: FAIL,
  `ModuleNotFoundError: No module named 'tests.logic'`.

- [ ] **Step 3: implement** `tests/logic.py`. Two rules the last two model tests need: equal-strength drivers with
  different values at PULL or below give no logic level (a divider), not a Conflict; and a resistor passes on only
  what drives its far net apart from that resistor itself, so a released open-drain output does not keep its bus low
  by its own echo through the 33 Ω (without that rule the four-part case oscillates and raises `NoFixedPoint`).

```python
"""Gate-level model of FluxDrive's logic, evaluated on the exported netlist (rev B spec §10.1).

Every net settles to 0, 1 or None (no logic level) from its drivers; the strongest driver wins:
  4    a rail (+3V3, +5V_A, +5V_IN, +5V_DRIVE, +12V, V5SYS -> 1; GND -> 0), and every net a bridged jumper
       joins to it
  3    STRONG: a push-pull gate output, a flip-flop Q, or an external push-pull source (a GPIO that drives)
  2    OD: an open-drain output that pulls low, an external open-collector source (the Amiga's CIA, Gary, a drive),
       or the far side of a resistor of at most 1 kOhm whose near side is at OD or stronger
  1    PULL: a resistor to a rail, or a resistor of more than 1 kOhm to a net at OD or stronger
  0.5  WEAK: an ESP32 internal pull-up (about 45 kOhm)
Drivers of the same top strength with different values: above PULL they are a Conflict; at PULL or below the net has
no logic level (None), as a divider between two rails has (AMIGA_PWR, EFUSE_EN, BUCK_FB). A resistor passes on only
what drives its far net apart from that resistor itself, so a net never holds its own level by its own echo through a
series resistor (a released open-drain output does not keep its bus low). Capacitors and diodes are open (the settled
state). Parts marked DNP are left out unless their ref is in `fit`.
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


def pin_map(nl):
    """{ref: {pin: net}} of the netlist."""
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
    pins = pin_map(nl)
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
    logic = [(ref, comp["value"], pins[ref]) for ref, comp in nl.components.items()   # the live gates, once
             if _live(nl, ref, fit) and (comp["value"] in GATES or comp["value"] in FLIPFLOPS)]
    val = {find(n): None for n in nl.nets}
    stren = {k: 0 for k in val}
    prev = {}

    def settle(cands):
        """(value, strength): the strongest candidates win; different values at PULL or weaker are an analog level
        (a divider such as AMIGA_PWR), None; different values above PULL are "X", a Conflict."""
        if not cands:
            return None, 0
        top = max(c[0] for c in cands)
        vals = {c[1] for c in cands if c[0] == top}
        if len(vals) > 1:
            return (None, 0) if top <= PULL else ("X", top)
        return vals.pop(), top

    for _ in range(max_iter):
        drv = defaultdict(list)                     # net -> [(strength, value, resistor index or -1)]
        for n in nl.nets:
            if n in RAIL:
                drv[find(n)].append((4, RAIL[n], -1))
        for n, (v, s) in sources.items():
            if n in parent:
                drv[find(n)].append((s, v, -1))
        for i, (ra, rb, a, b, ohms) in enumerate(resistors):
            for x, y, yn in ((ra, rb, b), (rb, ra, a)):
                if yn in RAIL:
                    drv[x].append((PULL, RAIL[yn], i))
                    continue
                # what drives y apart from this resistor: a net never pulls itself up by its own echo
                vy, sy = settle([c for c in prev.get(y, []) if c[2] != i])
                if vy is None or vy == "X":
                    continue
                if ohms <= 1000:
                    if min(sy, OD) >= PULL:
                        drv[x].append((min(sy, OD), vy, i))
                elif sy >= OD:
                    drv[x].append((PULL, vy, i))
        for ref, value, p in logic:
            for kind, ins, out in GATES.get(value, []):
                if out not in p:
                    continue
                iv = [val[find(p[i])] if i in p else None for i in ins]
                if None in iv:
                    continue
                o = find(p[out])
                if kind == "inv":
                    drv[o].append((STRONG, 1 - iv[0], -1))
                elif kind == "or":
                    drv[o].append((STRONG, iv[0] | iv[1], -1))
                elif kind == "mux":
                    drv[o].append((STRONG, iv[2] if iv[0] else iv[1], -1))
                elif kind == "odbuf" and iv[0] == 0:
                    drv[o].append((OD, 0, -1))
                elif kind == "odinv" and iv[0] == 1:
                    drv[o].append((OD, 0, -1))
                elif kind == "odnand" and iv[0] == 1 and iv[1] == 1:
                    drv[o].append((OD, 0, -1))
            for name, clr, pre, d, clk, q in FLIPFLOPS.get(value, []):
                if q not in p:
                    continue
                c = val[find(p[clr])] if clr in p else 1
                s = val[find(p[pre])] if pre and pre in p else 1
                if c is None or s is None:
                    continue
                qv = 1 if s == 0 else (0 if c == 0 else state.get((ref, name), 0))
                drv[find(p[q])].append((STRONG, qv, -1))
        new, news = {}, {}
        for k in val:
            new[k], news[k] = settle(drv.get(k, []))
            if new[k] == "X":
                raise Conflict((k, sorted((c[0], c[1]) for c in drv[k])))
        drv = {k: sorted(v) for k, v in drv.items()}
        if new == val and news == stren and drv == prev:
            return {n: val[find(n)] for n in nl.nets}
        val, stren, prev = new, news, drv
    raise NoFixedPoint(sorted(k for k in val if val[k] is None)[:10])
```

- [ ] **Step 4: run** `python -m pytest -q -p no:cacheprovider tests/test_logic_model.py`. Expected: 10 passed.
- [ ] **Step 5: failing test for the symbol** — in `tests/test_sch_gen.py::test_project_symbols_load` add
  `"74LVC1G157"` to the name tuple of the first loop, and append to the test:

```python
    pins = {n: name for n, name, *_ in sch_gen.pins_of(sch_gen.lib_symbol("FluxDrive:74LVC1G157"))[1]}
    assert pins == {"1": "I1", "2": "GND", "3": "I0", "4": "Y", "5": "VCC", "6": "S"}
```

  Run `python -m pytest -q -p no:cacheprovider tests/test_sch_gen.py -k symbols_load`. Expected: FAIL,
  `KeyError: '74LVC1G157'`.
- [ ] **Step 6: copy the 1G157 symbol** — a script `build/revb/copy_1g157.py` (scratch, not committed), run from the
  repository root with `python build/revb/copy_1g157.py`:

```python
import pathlib
import sys

ROOT = pathlib.Path.cwd()                          # the repository (or worktree) it is run from
sys.path.insert(0, str(ROOT))
from tools.sexpr import children, dump, parse  # noqa: E402

nt = parse(pathlib.Path(r"C:\Claude projecten\Nano-Tek\Nano-Tek.kicad_sym").read_text(encoding="utf-8"))
sym = next(s for s in children(nt, "symbol") if s[1] == "74LVC1G157")
path = ROOT / "FluxDrive.kicad_sym"
lib = parse(path.read_text(encoding="utf-8"))
assert not any(s[1] == "74LVC1G157" for s in children(lib, "symbol"))
lib.append(sym)
path.write_text(dump(lib) + "\n", encoding="utf-8", newline="\n")
```

  Expected: `git diff --stat FluxDrive.kicad_sym` → `1 file changed, 180 insertions(+)` (no deletions: `dump` leaves
  the other symbols byte-identical, and the `+ "\n"` keeps the file's last newline). The copied symbol's `Footprint`
  (`Package_TO_SOT_SMD:SOT-363_SC-70-6`) and `Datasheet` (Nexperia 74LVC1G157) are already right.
- [ ] **Step 7: run** `python -m pytest -q -p no:cacheprovider tests/test_logic_model.py tests/test_sch_gen.py`.
  Expected: PASS (10 + 11).
- [ ] **Step 8: commit** — "Logic evaluator for the netlist tests; 74LVC1G157 symbol".

### Task 3: Bus inputs for rev B

**Files:**
- Modify: `hardware/design.py:40-78`, `tests/test_bus.py`, `tests/test_power.py`, `tests/test_esp.py`

**Interfaces:**
- Produces nets: `SEL0`, `SEL1`, `MTR0` (U3 outputs, feed logic), `SEL0_IO`, `SEL1_IO`, `MTR0_IO` (GPIO side);
  `RST_B`, `RST_ACT`, `MTRX_B`, `M4_MOTOR`, `M4_MTR_Q`, `M4_MTR_N` on U3's freed gates; `SEL_FD` → U2.9, `SEL_FD_N`
  ← U2.8.

- [ ] **Step 1: failing tests** — in `tests/test_bus.py` delete `test_connector_pinout`, `test_input_chain`,
  `test_buffers_follow_the_connector` and `test_unfitted_pads_exist`, and put the block below where the old `EVEN`
  and `INPUTS` were (it holds the new `EVEN`, `NC_PINS`, `INPUTS`, those four tests and the new
  `test_freed_gates_reused`):

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

  In `test_gate_pairs` keep the input loop as it is and delete the two U2 spare-inverter asserts at its end
  (`nl.net_of("U2", 9) == "GND"` and the `unconnected-` check of U2 pin 8: U2.9 is now SEL_FD, checked in
  `test_freed_gates_reused`); its output loop stays until Task 4. In `tests/test_power.py` set
  `BUS_NETS = {"_STEP", "_DIR", "_SIDE", "_SEL0", "_SEL1", "_MTR0", "_DKWD", "_DKWE", "_CHNG", "_INDEX", "_TRK0",
  "_WPROT", "_DKRD", "_RDY"}`, `amiga_nets = BUS_NETS` in `test_no_backfeed_paths` (its comment about pins 6 and 14
  goes), and the signal list of `test_usb_alone_leaves_everything_defined` to
  `("STEP", "DIR", "SIDE", "SEL0", "SEL1", "MTR0", "DKWD", "DKWE")`. In `tests/test_esp.py::test_left_alone` use
  `(35, 36, 37, 45, 46)`.
- [ ] **Step 2: run** `python -m pytest -q -p no:cacheprovider tests/test_bus.py tests/test_power.py tests/test_esp.py`.
  Expected: 8 failed, 30 passed — `test_connector_pinout` (`AssertionError: 4`: J1 pin 4 is still `_MTR0_P4`), six
  `test_input_chain` cases (STEP, DIR, SIDE and SEL1 on their rev A pull-ups; SEL0 and MTR0 with their GPIO still on
  `SEL0`, `MTR0` instead of the `_IO` nets) and `test_freed_gates_reused` (U3 pin 1 is still `MTR0_P4_B`).
- [ ] **Step 3: implement** in `hardware/design.py`: `TITLE = "FluxDrive v1 rev B"`, block G name added to `BLOCKS`
  (`"G. Drive pass-through and DF0/DF1 swap"`) and `A, B, P, E, U, F, G = BLOCKS`; then replace block A (from
  `EVEN = {` to the `for u in ("U2", "U3"):` loop, lines 40–78) with:

```python
EVEN = {2: "_CHNG", 4: None, 6: None, 8: "_INDEX", 10: "_SEL0", 12: "_SEL1", 14: None,
        16: "_MTR0", 18: "_DIR", 20: "_STEP", 22: "_DKWD", 24: "_DKWE", 26: "_TRK0", 28: "_WPROT",
        30: "_DKRD", 32: "_SIDE", 34: "_RDY"}          # rev B spec §7: pins 4, 6, 14 are not used on the A500
j1 = {str(p): ("GND" if p != 3 else None) for p in range(1, 34, 2)}
j1.update({str(p): n for p, n in EVEN.items()})
part("J1", "Connector_Generic:Conn_02x17_Odd_Even", "Amiga floppy 34", "Connector_IDC:IDC-Header_2x17_P2.54mm_Vertical",
     j1, A, lcsc="C601943")

# signal, connector net, pull-up, GPIO, buffer, input pin, output pin, C pad, 1 kOhm to the GPIO (rev B §4.1).
# U3 (west) takes the lines on J1 pins 10-16, U2 (east) the ones on pins 18-32, each in the connector's west-to-east
# order over the gates (input pins 1, 13, 3, 11, 5, 9 with the SOIC turned 90 degrees; layout review LBUS-3).
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

  and in block D replace the INPUTS loop over `esp` (`for sig, _, _, gpio, *_ in INPUTS: esp[f"IO{gpio}"] = sig`) with
  `for gpio, net in GPIO_NET.items(): esp[f"IO{gpio}"] = net` (two lines), and the unused list with
  `for g in (3, 4, 8, 10, 12, 18, 35, 36, 37, 45, 46): esp[f"IO{g}"] = None`, above the new loop (every module pin must
  be assigned or `sch_gen` refuses the schematic; Tasks 5 and 7 give IO3, 4, 8, 10, 12 and 18 their rev B nets).
  Leave the OUTPUTS loop, `IO13/14/47/48` and J5 as rev A until Tasks 4 and 5. RST_ACT's 1 kΩ to `RST_ACT_IO` and
  J9/J10 come in Task 7; until then `KBRESET` and `MTRX` are nets with only these resistors.
- [ ] **Step 4: regenerate and run** — `bash tools/export_netlist.sh && python -m pytest -q -p no:cacheprovider
  tests/test_bus.py tests/test_power.py tests/test_esp.py`. Expected: PASS (all of them: the output tests still read
  rev A's outputs, which Task 3 does not touch).
- [ ] **Step 5: commit** — "Rev B inputs: 4k7 and 1k pull-ups, 1 kOhm to the GPIOs, U3/U2 gates reused".

### Task 4: Gated outputs and the second output buffer

**Files:**
- Modify: `hardware/design.py:80-92` (block B), `tests/test_bus.py`

**Interfaces:**
- Consumes: `SEL_FD_N` (U2.8, Task 3), `SEL_FD` (Task 5 drives it), `SEL0`, `SEL1`.
- Produces: `DKRD_G`, `TRK0_G`, `WPROT_G`, `RDY_G`, `CHNG_G`, `INDEX_G`, `BUSY`; U10, U11, U17 as in "Names".

- [ ] **Step 1: failing tests** — in `tests/test_bus.py` replace `OUTPUTS`, `test_output_chain` and
  `test_buffers_on_3v3` with the block below, delete the output loop of `test_gate_pairs` (covered by
  `test_output_chain` now), and in `test_outputs_quiet_at_power_up` change the loop header to
  `for sig, _, gpio, _ in OUTPUTS:` (the new `OUTPUTS` has four fields):

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

- [ ] **Step 2: run** `python -m pytest -q -p no:cacheprovider tests/test_bus.py`. Expected: FAIL — the six
  `test_output_chain` cases (no 74LVC32A on the `_N` nets yet) and `test_buffers_on_3v3` (`U10` has no pin 14 net);
  the rest pass.
- [ ] **Step 3: implement** block B: replace everything below its `# --- B: outputs` header line, down to and with
  U4's `C("100nF", "+3V3", "GND", B)`, with:

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

  and in block D delete the OUTPUTS loop over `esp` (`for sig, _, gpio, *_ in OUTPUTS: …`; the `GPIO_NET` loop covers
  the outputs now). `SEL_FD` has no driver until Task 5; ERC is run only from Task 8 on.
- [ ] **Step 4: run** `bash tools/export_netlist.sh && python -m pytest -q -p no:cacheprovider tests/test_bus.py`.
  Expected: PASS.
- [ ] **Step 5: commit** — "Rev B outputs: gated by SEL_FD_N, /CHNG and /INDEX from a west-end buffer".

### Task 5: Mode latch, clock, switch pads, J5 and the GPIO map

**Files:**
- Modify: `hardware/design.py` (new block G part 1; block F J5; block D GPIOs), `tests/test_esp.py`,
  `tests/test_bom.py`
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

  In `tests/test_esp.py::test_led_uart_spare` replace the J5 line and the loop after it
  (`for g in (13, 14, 47, 48): assert esp_net(nl, g) == f"GPIO{g}"`, now in `test_control_gpios`) with
  `assert [nl.net_of("J5", p) for p in range(1, 5)] == ["GND", "+3V3", "GPIO18", "GPIO3"]`. In
  `tests/test_bom.py::test_every_fitted_part_has_lcsc` extend the skipped prefixes to
  `("TP", "H", "FID", "J4", "J5", "J7", "JP")` (J7 and the jumpers are fitted parts without an LCSC number: wire pads
  and copper).
- [ ] **Step 2: run** `python -m pytest -q -p no:cacheprovider tests/test_swap.py tests/test_esp.py`. Expected: 6
  failed, 4 passed —
  `test_mode_latch` and `test_select_and_clock_gates` with `KeyError: 'U8'` / `'U12'`, `test_power_on_rcs`,
  `test_switch_pads` and `test_control_gpios` with `AssertionError`, `test_led_uart_spare` with `AssertionError`
  (J5 still has 6 pins).
- [ ] **Step 3: implement.** Block F: J5 becomes

```python
HDR4 = "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical"
part("J5", "Connector_Generic:Conn_01x04", "Spare / OLED", HDR4,              # rev B §7: GND 3V3 SCL SDA order
     {"1": "GND", "2": "+3V3", "3": "GPIO18", "4": "GPIO3"}, F, in_bom=False)
```

  Block D: in the `esp = {…}` dict delete the four entries `"IO13": "GPIO13", "IO14": "GPIO14", "IO47": "GPIO47",
  "IO48": "GPIO48"`, and after the `GPIO_NET` loop add

```python
esp.update({"IO47": "MODE_CLK_REQ", "IO48": "DF0_REQ", "IO13": "DF1_REQ", "IO14": "CHNG_REQ",
            "IO10": "RST_REQ", "IO12": "DF0_STATE", "IO8": "DF1_STATE", "IO4": "RST_ACT_IO", "IO18": "GPIO18",
            "IO3": "GPIO3"})
```

  New block G, appended after block F:

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
part("U8", "74xx:74LS74", "74LVC74A", TSSOP14,                 # the base symbol: 74HC74 only extends it
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

  `Device:D` pin 1 is the cathode (K), pin 2 the anode (A) (`test_power_on_rcs` checks D5.1 and D6.1 on +3V3). The
  jumper values ("DF0 at power-on", "REAL clear", …) are labels; the model of Task 2 recognises bridged jumpers by the
  footprint name. Record the 1N4148W/SOD-123 ruling of "Names" in the ledger.
- [ ] **Step 4: run** `bash tools/export_netlist.sh && python -m pytest -q -p no:cacheprovider tests/test_swap.py
  tests/test_esp.py tests/test_bom.py`. Expected: PASS.
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

- [ ] **Step 2: run** `python -m pytest -q -p no:cacheprovider tests/test_swap.py`. Expected: 5 failed —
  `test_j6_pinout` (`AssertionError: 2`: `net_of` gives None for a missing J6), `test_real_drive_drivers` and
  `test_bypass_and_mode4_jumpers` (`AssertionError`), `test_virtual_disk_change` (`KeyError: 'U20'`),
  `test_nothing_on_j6_leaves_its_lines_inactive` (`KeyError: 'J6_SEL'`); Task 5's five pass.
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
  Expected: PASS (10 passed).
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
    assert nl.components["U22"]["fields"].get("LCSC") == "C128412"          # spec §4.9: the kit's number
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

  In `tests/test_bom.py::test_every_fitted_part_has_lcsc` add `"J9", "J10"` to the skipped prefixes (the two wire
  pads).
- [ ] **Step 2: run** `python -m pytest -q -p no:cacheprovider tests/test_swap.py tests/test_bom.py`. Expected: 2
  failed — `test_mode4_parts_prepared_not_fitted` (`KeyError: 'U21'`) and `test_reset_wire` (`AssertionError`: J9
  missing).
- [ ] **Step 3: implement** in block G (U22 carries its LCSC number for the mode-4 kit, spec §4.9, and stays out of
  the BOM):

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
part("U22", "74xGxx:74LVC1G175", "SN74LVC1G175", "Package_TO_SOT_SMD:SOT-23-6",   # SN74LVC1G175DBVR
     {"1": "SEL1", "3": "M4_MOTOR", "6": "DF1_EN", "4": "M4_MTR_Q", "2": "GND", "5": "+3V3"}, G, lcsc="C128412",
     dnp=True, in_bom=False)
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
- Modify: `hardware/design.py` (`RES_LCSC`, block C, block F test pads), `tests/test_power.py`, `tests/test_bom.py`,
  `tests/test_swap.py`, `FluxDrive_Schematic.pdf`

**Interfaces:**
- Consumes: `tests.logic.evaluate`, `FLIPFLOPS`, `pin_map` (Task 2); the nets of Tasks 3–7.
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
    assert 1.4 <= ilim <= 1.6, ilim                                                         # R9 may move it
    caps = [nl.components[c]["value"] for c in parts_between(nl, "+5V_DRIVE", "GND", "C")]
    assert sorted(caps) == ["100nF", "22uF"]
    assert [nl.components[c]["value"] for c in parts_between(nl, "DRV_DVDT", "GND", "C")] == ["22nF"]
```

- [ ] **Step 2: failing tests — behaviour** — append to `tests/test_swap.py` the block below. What it covers, and
  where the product of spec §10.1 is cut:
  - `test_steering_logic`: every legal combination of the stored mode bits (4), J7 (3), the REAL pair in its four
    states (none, clear only, preset only, both), the bypass (2) and mode 4 fitted or not (2); each case loops over
    SEL0, SEL1, MTR0 and the mode-4 latch output. Checked: DF0_FD, DF1_EN, SEL_FD, REAL_SEL, REAL_MTR, J6.10, J6.4/16,
    the six `_G` buffer inputs, the six bus outputs (J1.2 and J1.34 among them), KBRESET (RST) and MODE_CLK, and that
    one active select never reaches both drives.
  - The cut: there, the six X_N lines are all asserted or all released, not 64 patterns, because each line is its own
    OR gate and buffer; all 64 patterns run in `test_outputs_follow_the_firmware_only_when_selected`, in every mode and
    select state. CHNG_REQ, RST_REQ and MODE_CLK_REQ take five patterns with "X_N asserted" (`CONTROLS`, a pairwise
    covering array), not all 16: every pair of the four lines still takes all four pairs of values, so a request wired
    to another request's gate, or /CHNG's two drivers mixed up, still fails. The full product (64 X_N patterns times 8
    request patterns) would take about 50 minutes; this one takes 35–50 s.
  - JP5 moves only the power-on RC, so `test_power_on_defaults` varies it, not the combinational test.
  - `Board` steps the flip-flops as the netlist wires them (preset, clear, clock and D pins read from U8 and U22), so
    a wrong CLR or clock wire shows. Each sequential test sets D before it raises the clock request, as spec §8 has
    the firmware do (with both in one step a clock during an access would latch the old D and pass for the wrong
    reason).

```python


# --- behaviour on the netlist (rev B spec §10.1) -----------------------------------------------------------------
import copy
import itertools

import pytest

from tests.logic import FLIPFLOPS, OD, PULL, STRONG, WEAK, evaluate, pin_map

BUS_OUT = ("_CHNG", "_INDEX", "_TRK0", "_WPROT", "_DKRD", "_RDY")
OUTS = {"CHNG": "_CHNG", "INDEX": "_INDEX", "TRK0": "_TRK0", "WPROT": "_WPROT", "DKRD": "_DKRD", "RDY": "_RDY"}
SWITCH = {"GTi": None, "FD": [("1", "2")], "REAL": [("3", "2")]}          # J7: centre, FD throw, REAL throw
REAL_PAIRS = ("none", "clear", "preset", "both")                          # JP6 (clear to GND), JP7 (preset to +3V3)
# (the six X_N asserted, CHNG_REQ, RST_REQ, MODE_CLK_REQ): a pairwise covering array. Every pair of these four takes
# all four pairs of values, so a request wired to another request's gate, or /CHNG's two drivers mixed up, shows.
CONTROLS = ((0, 0, 0, 0), (0, 1, 1, 1), (1, 0, 1, 1), (1, 1, 0, 1), (1, 1, 1, 0))


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
    """Rev B §4.4, §10.1: the bypass needs DF0_FD held at 0, by the REAL pair (both jumpers) or by J7 on REAL."""
    return not bypass or real_pair == "both" or switch == "REAL"


def df0_of(stored, real_pair, switch):
    """Rev B §3, §4.4: J7's FD throw pulls the preset low unless JP7 holds it high; its REAL throw and JP6 pull the
    clear low; with both low the 74LVC74A gives Q = 1; with neither, the latch keeps what it stored."""
    pre_low = switch == "FD" and real_pair not in ("preset", "both")
    clr_low = switch == "REAL" or real_pair in ("clear", "both")
    return 1 if pre_low else 0 if clr_low else stored


def jumpers(switch, real_pair, bypass, m4):
    """The `bridged` argument of evaluate() for one state of J7 and the jumpers."""
    bridged = {}
    if bypass:
        bridged.update({"JP1": [("2", "3")], "JP2": [("2", "3")]})
    if m4:
        bridged.update({"JP3": [("2", "3")], "JP4": [("2", "3")]})
    if real_pair in ("clear", "both"):
        bridged["JP6"] = [("1", "2")]
    if real_pair in ("preset", "both"):
        bridged["JP7"] = [("1", "2")]
    if SWITCH[switch]:
        bridged["J7"] = SWITCH[switch]
    return bridged


@pytest.mark.parametrize("m4", (0, 1))
@pytest.mark.parametrize("bypass", (0, 1))
@pytest.mark.parametrize("real_pair", REAL_PAIRS)
@pytest.mark.parametrize("switch", tuple(SWITCH))
@pytest.mark.parametrize("stored0,stored1", ((0, 0), (0, 1), (1, 0), (1, 1)))
def test_steering_logic(nl, stored0, stored1, switch, real_pair, bypass, m4):
    """Rev B spec §10.1: every legal state of the stored mode bits, J7, the REAL pair, the bypass and mode 4, with
    every SEL0, SEL1, MTR0 and mode-4 latch output under the five CONTROLS patterns; every output §10.1 lists."""
    if not legal(bypass, real_pair, switch):
        pytest.skip("illegal: see test_illegal_bypass_states_put_two_drives_on_sel0")
    bridged = jumpers(switch, real_pair, bypass, m4)
    fit = fit_mode4(nl) if m4 else ()
    df0 = df0_of(stored0, real_pair, switch)
    for m4_q, sel0, sel1, mtr0, (asserted, chng_req, rst_req, clk_req) in itertools.product(
            (0, 1) if m4 else (0,), (0, 1), (0, 1), (0, 1), CONTROLS):
        case = dict(m4_q=m4_q, sel0=sel0, sel1=sel1, mtr0=mtr0, asserted=asserted, chng_req=chng_req,
                    rst_req=rst_req, clk_req=clk_req)
        src = amiga(sel0, sel1, mtr0)
        if asserted:                                             # released: the GPIO is an input, the 10k pulls up
            src.update({f"{s}_N": (0, STRONG) for s in OUTS})
        src.update({"CHNG_REQ": (chng_req, STRONG), "RST_REQ": (rst_req, STRONG), "MODE_CLK_REQ": (clk_req, STRONG)})
        state = {("U8", "A"): stored0, ("U8", "B"): stored1, ("U22", "A"): m4_q}
        v = evaluate(nl, src, state=state, bridged=bridged, fit=fit)
        e = expected(df0, stored1, sel0, sel1, mtr0, m4, m4_q)
        assert (v["DF0_FD"], v["DF1_EN"]) == (df0, stored1), case
        assert (v["SEL_FD"], v["REAL_SEL"], v["REAL_MTR"]) == (e["SEL_FD"], e["REAL_SEL"], e["REAL_MTR"]), case
        if bypass:
            assert (v["J6_SEL"], v["J6_MTR"]) == (1 - sel0, 1 - mtr0), case
        else:
            assert (v["J6_SEL"], v["J6_MTR"]) == (1 - e["REAL_SEL"], 1 - e["REAL_MTR"]), case
        for sig, conn in OUTS.items():
            mine = asserted and e["SEL_FD"]
            assert v[f"{sig}_G"] == (0 if mine else 1), (sig, case)                    # the buffer inputs
            low = mine or (sig == "CHNG" and chng_req and sel0) or (sig == "RDY" and e["ID"])
            assert v[conn] == (0 if low else 1), (sig, case)
        assert v["MODE_CLK"] == (1 if clk_req and not (sel0 or sel1) else 0), case
        assert v["KBRESET"] == 1 - rst_req, case
        if sel0 != sel1:                                         # one select active: one drive answers it at most
            assert not (v["SEL_FD"] and v["J6_SEL"] == 0), ("two drives selected", case)


def test_illegal_bypass_states_put_two_drives_on_sel0(nl):
    """Review focus 2: the bypass states test_steering_logic skips are illegal for a reason: with DF0_FD not held at
    0, FluxDrive and the real drive both answer /SEL0."""
    for bridged, stored in (({"J7": [("1", "2")]}, 0), ({}, 1)):          # J7 on FD; or the GTi chose FD
        bridged = {**bridged, "JP1": [("2", "3")], "JP2": [("2", "3")]}
        v = evaluate(nl, amiga(1, 0, 0), state={("U8", "A"): stored, ("U8", "B"): 0}, bridged=bridged)
        assert v["SEL_FD"] == 1 and v["J6_SEL"] == 0


@pytest.mark.parametrize("pattern", range(64))
def test_outputs_follow_the_firmware_only_when_selected(nl, pattern):
    """Rev B §4.3: each of the six X_N lines reaches the bus only while FluxDrive is selected, for all 64 patterns
    and every mode and select state (test_steering_logic takes all six asserted or all six released)."""
    for df0, df1, sel0, sel1 in itertools.product((0, 1), repeat=4):
        src = amiga(sel0, sel1, 0)
        src.update({f"{s}_N": (0, STRONG) for i, s in enumerate(OUTS) if pattern >> i & 1})
        v = evaluate(nl, src, state={("U8", "A"): df0, ("U8", "B"): df1})
        sel_fd = sel0 if df0 else sel1 & df1
        for i, (sig, conn) in enumerate(OUTS.items()):
            assert v[conn] == (0 if pattern >> i & 1 and sel_fd else 1), (sig, df0, df1, sel0, sel1)


class Board:
    """Steps the flip-flops through events (rev B spec §10.1, second test). Their pins are read from the netlist:
    after each event a low preset sets Q, a low clear clears it, and otherwise a rising clock takes D as it was just
    before the event, so a wrong clock, clear or preset wire on U8 or U22 shows."""

    def __init__(self, nl, m4=False, stored=(0, 0), m4_q=0, bridged=None):
        self.nl, self.fit = nl, fit_mode4(nl) if m4 else ()
        self.state = {("U8", "A"): stored[0], ("U8", "B"): stored[1], ("U22", "A"): m4_q}
        self.bridged = dict(bridged or {})
        if m4:
            self.bridged.update({"JP3": [("2", "3")], "JP4": [("2", "3")]})
        pins = pin_map(nl)
        self.ffs = [(ref, name, pins[ref].get(clr), pins[ref].get(pre) if pre else None, pins[ref].get(d),
                     pins[ref].get(clk))
                    for ref, comp in nl.components.items() if nl.fitted(ref) or ref in self.fit
                    for name, clr, pre, d, clk, _ in FLIPFLOPS.get(comp["value"], [])]
        self.src = amiga(0, 0, 0)
        self.v = self.eval()

    def eval(self):
        return evaluate(self.nl, self.src, state=self.state, bridged=self.bridged, fit=self.fit)

    def set(self, **nets):
        """Change the sources (None removes one), settle, then update the flip-flops."""
        for net, val in nets.items():
            if val is None:
                self.src.pop(net, None)
            else:
                self.src[net] = val
        before, after = self.v, self.eval()
        old = dict(self.state)
        for ref, name, clr, pre, d, clk in self.ffs:
            if pre and after[pre] == 0:
                self.state[(ref, name)] = 1
            elif clr and after[clr] == 0:
                self.state[(ref, name)] = 0
            elif clk and before[clk] == 0 and after[clk] == 1:
                self.state[(ref, name)] = before[d]
        self.v = self.eval() if self.state != old else after
        return self.v

    def copy(self):
        """An independent Board in the same state (the search of test_every_order_of_events branches from it)."""
        b = copy.copy(self)
        b.state, b.src, b.bridged = dict(self.state), dict(self.src), dict(self.bridged)
        return b

    def throw(self, position):
        """Move J7 to "GTi" (centre), "FD" or "REAL"."""
        self.bridged.pop("J7", None)
        if SWITCH[position]:
            self.bridged["J7"] = SWITCH[position]
        return self.set()


def test_clock_request_waits_for_the_access_to_end(nl):
    """Review focus 1: a DF0 request during a /SEL0 access takes effect when the access ends, not before."""
    b = Board(nl, stored=(0, 0))
    b.set(_SEL0=(0, OD))                                   # real drive DF0, being read
    b.set(DF0_REQ=(1, STRONG))                             # D first, then the clock request (spec §8)
    b.set(MODE_CLK_REQ=(1, STRONG))
    assert b.v["DF0_FD"] == 0 and b.v["REAL_SEL"] == 1 and b.v["MODE_CLK"] == 0
    b.set(_SEL0=None)                                      # access over: the clock arrives
    assert b.v["DF0_FD"] == 1 and b.v["REAL_SEL"] == 0
    b.set(MODE_CLK_REQ=(0, STRONG))
    assert b.v["DF0_FD"] == 1


def test_request_dropped_inside_an_access_is_lost(nl):
    b = Board(nl, stored=(0, 1))
    b.set(_SEL1=(0, OD))                                   # FluxDrive DF1 in use (mode 3)
    b.set(DF0_REQ=(1, STRONG))                             # D first, then the clock request (spec §8)
    b.set(MODE_CLK_REQ=(1, STRONG))
    b.set(MODE_CLK_REQ=(0, STRONG))
    b.set(_SEL1=None)
    assert b.v["DF0_FD"] == 0 and b.v["DF1_EN"] == 1


def test_switch_moved_during_an_access(nl):
    """Spec §3, §10.1: J7 acts at once, also during an access; the latch keeps a throw after the switch returns to
    the centre; it never touches DF1_EN."""
    b = Board(nl, stored=(0, 1))                           # mode 3
    b.set(_SEL0=(0, OD))                                   # the real drive, DF0, is being read
    assert b.v["REAL_SEL"] == 1 and b.v["SEL_FD"] == 0
    b.throw("FD")
    assert (b.v["DF0_FD"], b.v["DF1_EN"], b.v["REAL_SEL"], b.v["SEL_FD"]) == (1, 1, 0, 1)
    b.throw("GTi")
    b.set(_SEL0=None)
    assert (b.v["DF0_FD"], b.v["DF1_EN"]) == (1, 1)
    b.throw("REAL")
    assert (b.v["DF0_FD"], b.v["DF1_EN"]) == (0, 1)


def test_esp32_reset_changes_nothing(nl):
    """Review focus 4: control GPIOs undriven, with their internal pull-ups on: no clock, no /CHNG, no reset, and
    /RDY and the J6 lines idle."""
    for stored in ((0, 0), (1, 0), (0, 1)):
        b = Board(nl, stored=stored)
        b.set(_SEL0=(0, OD))
        b.set(**{n: (1, WEAK) for n in ("MODE_CLK_REQ", "DF0_REQ", "DF1_REQ", "CHNG_REQ", "RST_REQ")})
        b.set(_SEL0=None)
        assert (b.v["DF0_FD"], b.v["DF1_EN"]) == stored
        assert b.v["_CHNG"] == 1 and b.v["KBRESET"] == 1 and b.v["MODE_CLK"] == 0
        assert b.v["_RDY"] == 1 and b.v["J6_SEL"] == 1 and b.v["J6_MTR"] == 1


def test_esp32_glitch_changes_nothing(nl):
    """Rev B §4.1, §10.1: GPIO1-17 driven low for 60 us at an ESP32 reset, in every mode, with and without an
    access: no clock, no /CHNG, no reset pulse, the mode kept, the real drive's select follows the bus."""
    glitch = ("RST_ACT_IO", "DF1_STATE", "SEL1_IO", "RST_REQ", "MTR0_IO", "DF0_STATE", "DF1_REQ", "CHNG_REQ",
              "SEL0_IO")                                  # GPIO 4, 8, 9, 10, 11, 12, 13, 14, 17
    for stored in ((0, 0), (1, 0), (0, 1)):
        for sel0 in (0, 1):
            b = Board(nl, stored=stored)
            b.set(_SEL0=(0, OD) if sel0 else None)
            b.set(**{n: (0, STRONG) for n in glitch})
            b.set(**{n: None for n in glitch})
            assert (b.v["DF0_FD"], b.v["DF1_EN"]) == stored
            assert b.v["_CHNG"] == 1 and b.v["KBRESET"] == 1 and b.v["MODE_CLK"] == 0 and b.v["_RDY"] == 1
            assert b.v["J6_SEL"] == (0 if sel0 and not stored[0] else 1) and b.v["J6_MTR"] == 1


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
    """Rev B §3, §4.6: the power-on RCs give DF1 off and the real drive as DF0, or FluxDrive with JP5 on 2-3."""
    for jp5, want in ((None, 0), ([("2", "3")], 1)):
        bridged = {"JP5": jp5} if jp5 else {}
        b = Board(nl, stored=(1, 1), bridged=bridged)
        b.set(POR_A=(0, OD), CLR_B=(0, OD))                # capacitors still discharged
        b.set(POR_A=None, CLR_B=None)
        assert b.v["DF1_EN"] == 0 and b.v["DF0_FD"] == want


def test_every_order_of_events(nl):
    """Rev B spec §10.1 (second test), review focus 1: every state reachable by the Amiga's selects, the firmware's
    D inputs and clock request, and J7, entered by every single event from every state. After each event: FluxDrive
    answers only the unit it owns and the real drive only its own select; the mode bits change only on a clock edge
    or by the switch; MODE_CLK is never high during an access."""
    from collections import deque
    order = tuple(SWITCH)                                  # GTi -> FD -> REAL -> GTi

    def board(node):
        s0, s1, sel0, sel1, req0, req1, clk, sw = node
        b = Board(nl, stored=(s0, s1), bridged={"J7": SWITCH[sw]} if SWITCH[sw] else {})
        b.set(_SEL0=(0, OD) if sel0 else None, _SEL1=(0, OD) if sel1 else None,
              DF0_REQ=(req0, STRONG), DF1_REQ=(req1, STRONG), MODE_CLK_REQ=(clk, STRONG))
        return b

    starts = [(s0, s1, 0, 0, s0, s1, 0, "GTi") for s0, s1 in ((0, 0), (1, 0), (0, 1))]
    seen, todo = set(starts), deque(starts)
    while todo:
        node = todo.popleft()
        s0, s1, sel0, sel1, req0, req1, clk, sw = node
        start = board(node)
        for ev in ("sel0", "sel1", "req0", "req1", "clk", "sw"):
            b = start.copy()
            before = dict(b.v)
            n = dict(sel0=sel0, sel1=sel1, req0=req0, req1=req1, clk=clk)
            nsw = sw
            if ev == "sw":
                nsw = order[(order.index(sw) + 1) % 3]
                b.throw(nsw)
            else:
                n[ev] ^= 1
                net = {"sel0": "_SEL0", "sel1": "_SEL1", "req0": "DF0_REQ", "req1": "DF1_REQ",
                       "clk": "MODE_CLK_REQ"}[ev]
                b.set(**{net: ((0, OD) if n[ev] else None) if ev.startswith("sel") else (n[ev], STRONG)})
            v = b.v
            e = expected(v["DF0_FD"], v["DF1_EN"], n["sel0"], n["sel1"], 0, False, 0)
            assert v["SEL_FD"] == e["SEL_FD"] and v["J6_SEL"] == 1 - e["REAL_SEL"], (node, ev)
            assert not (v["MODE_CLK"] and (n["sel0"] or n["sel1"])), (node, ev)
            moved = (v["DF0_FD"], v["DF1_EN"]) != (before["DF0_FD"], before["DF1_EN"])
            clocked = before["MODE_CLK"] == 0 and v["MODE_CLK"] == 1
            assert not moved or ev == "sw" or clocked, (node, ev)
            nxt = (b.state[("U8", "A")], b.state[("U8", "B")], n["sel0"], n["sel1"], n["req0"], n["req1"],
                   n["clk"], nsw)
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    assert len(seen) > 100, len(seen)
```

- [ ] **Step 3: run** `python -m pytest -q -p no:cacheprovider tests/test_power.py tests/test_swap.py`. Expected:
  2 failed, 239 passed, 48 skipped — the failures are `test_power_header_to_efuse` (`AssertionError`: J2 pin 4 is
  still unconnected) and `test_drive_behind_its_own_efuse` (`KeyError: 'U9'`). Every test in `tests/test_swap.py`
  passes at once (229 passed; the 48 skipped are the illegal bypass states): the behaviour tests verify the circuit
  of Tasks 5–7, and U9 is not part of it. Note that in the ledger; Step 4 shows they can fail.
- [ ] **Step 4: prove the behaviour tests can fail** — a scratch script `build/revb/mutate.py` (not committed), run
  from the repository root with `python build/revb/mutate.py` (4 to 7 minutes). It wires six parts wrong in
  `hardware/design.py`, one at a time, regenerates the schematic, runs the behaviour tests, and restores both files:

```python
"""Mutation check of the rev B behaviour tests (scratch, not committed): each mutant must fail them, the design as
committed must pass them. Run from the repository root; hardware/design.py and the schematic are restored at the end.

    python build/revb/mutate.py
"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path.cwd()
DESIGN = ROOT / "hardware" / "design.py"
BEHAVIOUR = ("steering or illegal_bypass or follow_the_firmware or waits_for or dropped_inside or switch_moved "
             "or changes_nothing or keeps_the_real_drive or power_on_defaults or every_order or nothing_on_j6")
MUTANTS = {                                           # name: (text in design.py, wrong text)
    "U13 mux inputs swapped": ('mux("U13", "DF0_FD", "SEL1_EN", "SEL0", "SEL_FD")',
                               'mux("U13", "DF0_FD", "SEL0", "SEL1_EN", "SEL_FD")'),
    "U16 S = SEL0": ('mux("U16", "BUSY", "MODE_CLK_REQ", "GND", "MODE_CLK")',
                     'mux("U16", "SEL0", "MODE_CLK_REQ", "GND", "MODE_CLK")'),
    "U11 9/10 = SEL0": ('"9": "SEL0", "10": "SEL1", "8": "BUSY"', '"9": "SEL0", "10": "SEL0", "8": "BUSY"'),
    "U22 CLR = +3V3": ('"6": "DF1_EN", "4": "M4_MTR_Q"', '"6": "+3V3", "4": "M4_MTR_Q"'),
    "U19 input on CHNG_REQ": ('{"2": "RST_REQ", "4": "KBRESET"', '{"2": "CHNG_REQ", "4": "KBRESET"'),
    "U8-B clock on MODE_CLK_REQ": ('"11": "MODE_CLK", "10": "PRE_B"', '"11": "MODE_CLK_REQ", "10": "PRE_B"'),
}


def run(label):
    subprocess.run([sys.executable, "tools/sch_gen.py", "FluxDrive.kicad_sch"], cwd=ROOT, check=True,
                   capture_output=True)
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_swap.py",
                        "-k", BEHAVIOUR], cwd=ROOT, capture_output=True, text=True)
    failed = sorted({line.split("::")[1].split("[")[0].split(" ")[0] for line in r.stdout.splitlines()
                     if line.startswith("FAILED")})
    print(f"{label}: {r.stdout.strip().splitlines()[-1]}  {', '.join(failed)}", flush=True)


good = DESIGN.read_text(encoding="utf-8")
try:
    run("design as committed")
    for name, (a, b) in MUTANTS.items():
        assert good.count(a) == 1, name
        DESIGN.write_text(good.replace(a, b), encoding="utf-8", newline="\n")
        run(name)
finally:
    DESIGN.write_text(good, encoding="utf-8", newline="\n")
    subprocess.run([sys.executable, "tools/sch_gen.py", "FluxDrive.kicad_sch"], cwd=ROOT, check=True,
                   capture_output=True)
```

  Expected (the failed counts can vary a little; the failing tests do not):

| Mutant | Behaviour tests | Failing tests |
|---|---|---|
| design as committed | 218 passed, 48 skipped, 11 deselected | none |
| U13 mux inputs swapped | about 210 failed | `test_steering_logic`, `test_outputs_follow_the_firmware_only_when_selected`, `test_illegal_bypass_states_put_two_drives_on_sel0`, `test_switch_moved_during_an_access`, `test_every_order_of_events` |
| U16 S = SEL0 | about 146 failed | `test_steering_logic`, `test_request_dropped_inside_an_access_is_lost`, `test_every_order_of_events` |
| U11 9/10 = SEL0 | about 146 failed | the same three |
| U22 CLR = +3V3 | about 8 failed | `test_steering_logic`, `test_mode1_with_mode4_fitted_keeps_the_real_drive_still` |
| U19 input on CHNG_REQ | about 144 failed | `test_steering_logic` |
| U8-B clock on MODE_CLK_REQ | 1 failed | `test_every_order_of_events` |

  Then `git status --short` shows only `tests/test_power.py` and `tests/test_swap.py` changed. A mutant that passes
  is a gap in the tests: add the check that catches it before going on.
- [ ] **Step 5: implement.** In `RES_LCSC` add `"1K37": "C423239"` (UNI-ROYAL 0402WGF1371TCE, see "Names"). Block C,
  after U5's parts (after `R("2K2", "EFUSE_ILM", "GND", P)`):

```python
part("U9", "FluxDrive:TPS259531", "TPS259531", "Package_SON:Texas_DSG0008A_WSON-8-1EP_2x2mm_P0.5mm_EP0.9x1.6mm",
     {"1": "DRV_DVDT", "2": "EFUSE_EN", "3": "+5V_IN", "4": "+5V_IN", "5": "+5V_DRIVE", "6": None,
      "7": "DRV_ILM", "8": "GND", "9": "GND"}, P, lcsc="C2155674")     # the real drive's eFuse (rev B §6)
C("22nF", "DRV_DVDT", "GND", P)
R("1K37", "DRV_ILM", "GND", P)                 # 2000/1370 + 0.04 = 1.50 A (rev B §6); R9 may change it
C("22uF", "+5V_DRIVE", "GND", P)
C("100nF", "+5V_DRIVE", "GND", P)
part("J8", "FluxDrive:171825-4", "Drive power", "FluxDrive:171825-4",
     {"1": "+5V_DRIVE", "2": "GND", "3": "GND", "4": "+12V"}, P, lcsc="C210162")
```

  Change J2's pins to `{"1": "+5V_IN", "2": "GND", "3": "GND", "4": "+12V"}`, and extend the test-pad list in block F
  with `"SEL_FD", "REAL_SEL", "REAL_MTR", "DF0_STATE", "DF1_STATE", "MODE_CLK"` (after `"GND"`). In
  `tests/test_bom.py::test_test_pads` add those six nets to `need`.
- [ ] **Step 6: run the whole suite** — `bash tools/export_netlist.sh && python -m pytest -q -p no:cacheprovider`.
  Expected: 319 passed, 48 skipped — the board tests included (they still read rev A's board, which nothing here
  changes), in 50–110 s. `tests/test_swap.py` takes 50–80 s of it: `test_steering_logic` 35–50 s,
  `test_every_order_of_events` about 10 s (the upper figures measured with Freerouting runs going on the same
  machine). These are wall times: another build on the same machine can double them, so judge the time on an idle
  machine; the product is cut as Step 2 says, and no case is dropped for speed.
- [ ] **Step 7: ERC and PDF** — `"C:/Program Files/KiCad/10.0/bin/kicad-cli.exe" sch erc --severity-error
  --exit-code-violations -o build/erc.txt FluxDrive.kicad_sch` → exit 0, 0 errors. At `--severity-all` only
  `footprint_filter` warnings remain (the 74HC14, 74LS74 and 74LS32 symbols' filters list DIP only), which
  `tests/test_sch_gen.py::test_real_schematic_erc` checks too. Then `"C:/Program Files/KiCad/10.0/bin/kicad-cli.exe"
  sch export pdf -o FluxDrive_Schematic.pdf FluxDrive.kicad_sch`; open the PDF and check that block G is on the sheet
  with readable labels (`test_everything_fits_on_the_sheet` guards the size; the sheet is A0, as rev A's).
- [ ] **Step 8: commit** — "Rev B drive power behind its own eFuse, test pads; the steering logic proven on the
  netlist".

### Task 9: Schematic review

**Files:**
- Create: `docs/reviews/2026-09-30-revb-schematic-review.md`
- Modify: whatever the review's accepted findings touch

- [ ] **Step 1:** the four specialist reviews of rev A (Amiga bus, power and EMC, ESP32-S3 and USB, PCB-readiness and
  code), each by a fresh agent, on `FluxDrive_Schematic.pdf`, the exported netlist, `hardware/design.py` and the rev B
  spec; the bus reviewer also re-runs `tests/test_swap.py` and `build/revb/mutate.py` and tries to break them (a state
  the oracle does not cover, a wrong wire the tests miss).
- [ ] **Step 2:** write the record (finding, severity, decision) as rev A's `docs/reviews/2026-09-29-schematic-review.md`
  does; fix blockers and majors, each with a failing test first; re-run the suite, the ERC of Task 8 Step 7 and
  `build/revb/mutate.py`.
- [ ] **Step 3: commit** — "Rev B schematic review and fixes".

### Task 10: Footprints: module ground-pad hole

**Files:**
- Modify: `FluxDrive.pretty/ESP32-S3-WROOM-1.kicad_mod`
- Create: `tests/test_footprints.py`

The jumpers need no footprint work: JP1–JP5 use KiCad's `SolderJumper-3_P1.3mm_Bridged12_RoundedPad1.0x1.5mm`, which
is copper-bridged 1–2 already (`net_tie_pad_groups "1,2"`); Task 12 checks the bridge on the board.

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

- [ ] **Step 2: run** `python -m pytest -q -p no:cacheprovider tests/test_footprints.py`. Expected: FAIL,
  `assert 0 == 1` (`len(big)`: no 1.0 mm hole yet).
- [ ] **Step 3: implement** with a scratch script `build/revb/ground_pad_hole.py` (not committed), run from the
  repository root with `python build/revb/ground_pad_hole.py`. It removes the four `pad "41" thru_hole` whose centre
  is within 1.0 mm of the ground pad's centre (the four inner thermal vias; the nearest others are 1.57 mm away and
  stay), adds the 1.0 mm hole right after the ground pad, and puts one sentence in front of the footprint's `descr`:

```python
"""Rev B §9: a 1.0 mm solder-through hole in the module's ground pad (scratch, not committed). Run from the
repository root. It edits the file as text, so every other line stays as KiCad wrote it."""
import math
import pathlib
import sys
import uuid

ROOT = pathlib.Path.cwd()
sys.path.insert(0, str(ROOT))
from tools.sexpr import Q, child, dump, parse  # noqa: E402

path = ROOT / "FluxDrive.pretty" / "ESP32-S3-WROOM-1.kicad_mod"
lines = path.read_text(encoding="utf-8").split("\n")
starts = [i for i, line in enumerate(lines) if line.startswith("\t(")] + [len(lines) - 2]   # top-level items
items = [(a, b, parse("\n".join(lines[a:b]))) for a, b in zip(starts, starts[1:])]
pads = [(a, b, n) for a, b, n in items if n[0] == "pad" and n[1] == "41"]
ep = next(n for a, b, n in pads if n[2] == "smd")
cx, cy = float(child(ep, "at")[1]), float(child(ep, "at")[2])


def dist(n):
    return math.dist((float(child(n, "at")[1]), float(child(n, "at")[2])), (cx, cy))


inner = [(a, b) for a, b, n in pads if n[2] == "thru_hole" and dist(n) < 1.0]
assert len(inner) == 4, inner                           # the four thermal vias the hole would overlap
hole = ["pad", Q("41"), "thru_hole", "circle", ["at", cx, cy], ["size", 1.6, 1.6], ["drill", 1.0],
        ["property", "pad_prop_heatsink"], ["layers", Q("*.Cu"), Q("F.Mask"), Q("B.Mask")],
        ["remove_unused_layers", "no"], ["zone_connect", 2],
        ["uuid", Q(str(uuid.uuid5(uuid.NAMESPACE_URL, "FluxDrive rev B module ground-pad hole")))]]
ep_end = next(b for a, b, n in pads if n is ep)
out = []
for i, line in enumerate(lines):
    if i == ep_end:                                     # the hole goes right after the ground pad
        out.append("\t" + dump(hole, 1))
    if not any(a <= i < b for a, b in inner):
        out.append(line)
text = "\n".join(out)
old = '(descr "FluxDrive copy: '
assert text.count(old) == 1
text = text.replace(old, old + "1.0 mm solder-through hole in the ground pad for hand soldering, rev B spec §9; ")
path.write_text(text, encoding="utf-8", newline="\n")
```

  Expected: `git diff --stat` → `1 file changed, 6 insertions(+), 36 deletions(-)`; KiCad loads the footprint:
  `"C:/Program Files/KiCad/10.0/bin/python.exe" -c "import pcbnew; fp = pcbnew.FootprintLoad('FluxDrive.pretty',
  'ESP32-S3-WROOM-1'); print(sum(p.GetNumber() == '41' for p in fp.Pads()))"` → `10` (the ground pad, eight thermal
  vias and the hole).
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
  `docs/superpowers/specs/2026-09-28-fluxdrive-v1-hardware-design.md`
- Create: `tests/test_readme.py`

- [ ] **Step 1:** `bash tools/jlc_production.sh`; `python -m pytest -q -p no:cacheprovider tests/test_pcb.py -k
  production` → PASS (U1 and the DNP parts out, every fitted SMD part in, at its place and rotation). Check the BOM
  for the new parts and their LCSC numbers and stock (spec §4.9, R10) and record the stock in the ledger; count the
  new JLC extended part types (spec §13 says seven; C423239, the 1K37, makes eight) and record the fee.
- [ ] **Step 2:** renders `kicad-cli pcb render --side top/bottom` and a 3D view to `docs/images/fluxdrive-v1b-*.png`.
- [ ] **Step 3: failing test** — `tests/test_readme.py`, a checklist of what the README's rev B section must carry
  (spec §3–§6, §9, §12; review finding F24):

```python
"""The README carries what a rev B builder needs (rev B spec §3-§6, §9, §12)."""
import pathlib

README = (pathlib.Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")


def test_readme_rev_b_build_notes():
    for need in (
        "## Rev B",
        "J6pwr",                                   # §6: J6 never without J6pwr
        "TE 171822-4", "170204-2", "AWG 20",       # §6: the drive power cable
        "continuity",                              # §6: +5 V on pin 1, +12 V on pin 4 before the drive is plugged
        "CUT 1-2, CHECK, BRIDGE 2-3",              # §4.4: the jumper order
        "REAL (both)",                             # §4.4: the bypass needs the pair
        "17.7 mA",                                 # §5: two external drives next to the real drive
        "DF2",                                     # §3: external drives
        "C135822", "C128412", "C2867613",          # §4.7: the mode-4 kit (U21, U22, U23)
        "WROOM-1U-N16R8", "C3013946", "U.FL",      # §9: the other module, its cable out of the shield
        "nothing on J6",                           # §6: the reversed-plug bench test
        "1K37",                                    # §6: the drive eFuse's limit, and R9
    ):
        assert need in README, need
```

  Run it: FAIL on `## Rev B`.
- [ ] **Step 4:** README: a "## Rev B" section —
  - what rev B adds: the original drive next to FluxDrive, the four modes (§3's table), the GTi and switch control,
    the power-on default and JP5;
  - J6 and J8 (J6pwr) with the drive power cable: 2 × TE 171822-4 housings with 170204-2 contacts, AWG 20–22, pin 1
    to pin 1, its length taken from the fit dummy; a continuity check (+5 V on pin 1, +12 V on pin 4) before the drive
    is plugged in; never J6 without J6pwr (an unpowered drive pulls the shared lines to about 0.9 V, which reads as
    asserted);
  - the jumper table with the delivered states (JP1/JP2 1–2, JP3/JP4 to GND, JP5 to clear, JP6/JP7 open) and the
    order "CUT 1-2, CHECK, BRIDGE 2-3"; the bypass procedure with "REAL (both)" or J7 on REAL;
  - mode 4 and its wire (MTRX to CIA-B pin 17, or DB23 pin 8), with the kit list: U21 74LVC1G157GW (C135822),
    U22 SN74LVC1G175DBVR (C128412), U23 SN74LVC1G38DBVR (C2867613), three 100 nF 0603, the MTRX 4k7 and 100 Ω and
    the ID 33 Ω (0603), moving JP3/JP4 in the order above, and "mode 4 fitted" in the firmware; R5 before relying on it;
  - the reset wire (RST to `_KBRESET`, CN13 pin 3 or Gary pin 5);
  - external drives: with DF1 on, a drive with a DF2/DF3 switch or a select-shifting adapter; two external drives
    next to the real drive draw 17.7 mA on /STEP, /DIR and /SIDE, outside the 8520's guaranteed VOL, as a stock A500
    with two external drives (16.6 mA) already does (§5);
  - the drive eFuse: R_ILM 1K37 for 1.50 A; if R9 (the drive's measured peak) says otherwise, the value to fit;
  - soldering the module through its ground-pad hole; the footprint also takes the WROOM-1U-N16R8 (C3013946), whose
    U.FL cable must leave the shield (§9);
  - the new test pads (the map of all 22) and the order settings (4 layers, rev B BOM/CPL);
  - the reversed-plug bench test of the v1 spec §11 runs with nothing on J6 or J6pwr (§6);
  - the checks before ordering (spec §12): O5, O7, R1, R7, R9, the C601943 body length for J1 and J6, and the fit
    dummy with J6, its plug and the drive power cable (the shield may need a cut-out).

  Run `tests/test_readme.py` → PASS.
- [ ] **Step 5:** the v1 spec gets v0.5 with every change of the rev B spec §13 (§1 scope, §2.1, §2.3, §3 block
  diagram, §4.1–§4.4, §5, §6 GPIO table and J5, §7, §8 with "twenty-two" test pads and the module hole, §9 firmware,
  §10: the extended part types (eight with the 1K37) and the under-€10 target re-checked against the rev B BOM, with
  the result written into §10; §11 verification; §13 open items), and a pointer to the rev B spec.
- [ ] **Step 6: run** the whole suite → PASS; **commit** — "Rev B production files, render, README; v1 spec v0.5".

### Task 16: Final whole-branch review

**Files:**
- Create: `docs/reviews/2026-09-30-revb-final-review.md`
- Modify: whatever the review's accepted findings touch

Spec §10.3: the four specialist reviews run on the schematic (Task 9) and on the layout (Task 14), "then a final
whole-branch review".

- [ ] **Step 1:** a fresh reviewer (one agent that saw none of the earlier work) reads the whole branch —
  `git diff main...feature/rev-b`, the rev B spec, `docs/reviews/2026-09-30-revb-schematic-review.md`,
  `docs/reviews/2026-09-30-revb-layout-review.md`, the ledger and this plan's review focus — and checks:
  - every done criterion of spec §10.5 is covered by a test, by the README's bring-up list, or by an open item of
    spec §11;
  - every ruling in the ledger holds, and every test that passed at once has its mutation or coverage note;
  - the committed board, production files, schematic PDF, fit template and STEP belong together (the suite, DRC with
    zone refill and parity, `tools/pcb_place.py --check`);
  - no AI attribution in the branch: `git log main..feature/rev-b --format=%B | grep -i -e "co-authored" -e
    "generated with"` prints nothing.
- [ ] **Step 2:** write the record (finding, severity, decision) as rev A's final review did; fix blockers and majors,
  each with a failing test first. If the board changes: `tools/pcb_build.sh`, then Task 15 Step 1 again; re-run the
  suite, ERC and DRC.
- [ ] **Step 3: commit** — "Rev B final review". Do not push; tell Dimitri the branch is ready and list what stays
  open for him (spec §12: O5, O7, R1, R7, R9, the C601943 body length, the fit test).
