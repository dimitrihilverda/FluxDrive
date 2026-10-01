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
- Board 60 mm wide and 72.1 mm long, the spec's maximum (Task 11 uses all of it: the strip under the module needs
  it), J1 at rev A's position over CN11, J6 17.78 mm north of J1 with the same orientation and pin 1 on the same side
  (spec §9).
- Unfitted pads are 0603 (resistors, capacitors) or SOT (ICs); JLC does not close solder jumpers, so default-closed
  jumpers are copper-bridged 3-pad footprints (spec §4.7, §9).
- U1 (the ESP32 module) stays hand-placed (`tools/assembly.py`); its ground pad gets a 1.0 mm solder-through hole
  (spec §9).
- Board tools run with KiCad's Python; pcbnew bindings are unreliable after `board.Remove()`, so removals run in a
  process that then only saves and exits. Do not edit `tools/` while `tools/pcb_build.sh` runs (rev A LCODE-1).
- DRC reads its rules from the project file named like the board. A scratch board is therefore always
  `FluxDrive.kicad_pcb`, in a directory that holds copies of `FluxDrive.kicad_pro`, `FluxDrive.kicad_sch`,
  `FluxDrive.kicad_sym`, `fp-lib-table`, `sym-lib-table`, `FluxDrive.pretty/` and `3dmodels/`. Under any other name
  DRC runs with KiCad's defaults and reports copper-edge and hole clearances that are not there.
- Every `kicad-cli pcb drc` runs with `--refill-zones`: the zone fills saved in a board are stale after any change.
- The layout tools find R, C and TP parts by their nets, never by ref: `tools/placement.py`'s `ref_of()` reads
  `hardware.design.PARTS` (KiCad's Python imports it as the system Python does), and the tests use
  `_refs_between()`. A part added to the design after Task 11 needs a spot in `tools/placement.py`
  (`test_placement_table_covers_the_design` fails until it has one).
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
6. **The J1→J6 band and J6's own pins**: fourteen tracks cross the 7.8 mm between J1 and J6 at J1's pin columns,
   and J6's own pins (4, 6, 10, 12, 14, 16) reach their parts through the free columns (pins 4, 6 and 14) and the
   ends of J6. A part moved into a pass-through strip, or a track pulled into J6's pin gaps, cuts or crowds the bus.
   Checked by `test_placement_is_legal` (the placement table and its strips), `test_connector_row_keepouts`,
   `test_no_track_near_the_gnd_rows` and `test_j6_gaps_hold_one_centred_track` (Tasks 11, 12).
7. **The drive's power path**: J2 → U9 → J8 carries the real drive's current (up to 1.5 A) at 0.8 mm without a
   via; +12 V runs J2.4 → J8.4 on B.Cu. Checked by `test_drive_power_paths_wide` and
   `test_drive_headers_gnd_on_the_plane` (Task 12); J8's plug clearance by Task 11's O15 step and Task 13's fit test.
8. **Every IC's +3V3 on its own via**: `test_3v3_supply_pads_have_their_own_via` is a matching, so two pads never
   share one via; `tools/pcb_fanout.py` stops the build rather than letting a supply pad join a neighbour (Task 12).
9. **Routing room**: with only F.Cu and B.Cu for signals, the review's Freerouting run left 60 open connections on
   this placement, most of them in the logic north of J6 (Task 12 step 6). Task 12 step 7 closes them in rounds and
   stops at a choice for Dimitri (a routing channel in In2, six layers, fewer parts in the band) if it cannot.

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
| `tools/placement.py` | create | the rev B placement table, pcbnew-free (Task 11): outline, J1/J6 geometry, row positions, the pass-through strips, every part's spot, R/C/TP found by net (`ref_of`) |
| `tests/test_pcb.py` | modify | Task 1: rule areas by layer, antenna copper-free, production rotations, buck to the antenna; Task 11: rev B outline, J6, zones, placement table, row keep-outs, net-based lookups; Task 12: GND-row clearance, J6 gaps, _B lengths, own +3V3 vias, antenna border, drive power; Task 13: rev B labels, silk on the board |
| `tests/test_tools.py`, `tests/test_sch_gen.py`, `tests/fixtures/tiny_design.py` | modify | the deferred minors (Task 1) |
| `tools/jlc_rules.py`, `tools/netclass.py` | create | pcbnew-free helpers the tests import: BOM comment and CPL rotation; netclass track widths (Task 1) |
| `tools/jlc_export.py`, `tools/jlc_production.sh`, `tools/fit_template.sh`, `tools/pcb_maze.py`, `tools/netlist.py`, `tools/sch_gen.py` | modify | the deferred minors (Task 1) |
| `tools/pcb_place.py` | modify | reads `tools/placement.py`; the legaliser keeps SMD pads out of J1's and J6's zones and every pad out of the pass-through strips; rule areas J1 rows F/B, J6 rows B, antenna sides (Task 11) |
| `tools/pcb_prefan.py` | modify (rewritten) | hand routes found by net: +5V_A rail, U5, U9, /DKRD_D, USB pads, drive power path, J1→J6 pass-through, J6's own pins (Task 12) |
| `tools/pcb_fanout.py` | modify | an own +3V3 via for every IC supply pin and decoupling pad (two for L1 and the buck's 22 µF); no via within 0.05 mm of an SMD pad (Task 12) |
| `tools/pcb_stitch.py` | modify | GND stitching along the antenna keep-out's south, east and west borders (Task 12) |
| `tools/pcb_silk.py` | modify | rev A's texts moved onto the rev B board, J5's labels, the rev B title (Task 12); rev B labels (Task 13) |
| `tools/pcb_route.py` | modify | Freerouting's time limit stops the whole process tree (`java` on PATH is Oracle's launcher) (Task 12) |
| `FluxDrive.kicad_pro` | modify | `Drive` netclass: 0.8 mm, clearance 0.2 mm, for /+5V_IN, /+5V_DRIVE, /+12V (Task 12) |
| `FluxDrive.pretty/171825-4.kicad_mod` | modify | J2/J8 outline to TE's drawing, with the wall side marked: the header fits either way round and the wall decides where +5 V lands (Task 11 step 0, O15) |
| `README.md`, `docs/superpowers/specs/2026-09-28-fluxdrive-v1-hardware-design.md` | modify | rev B build notes, v1 spec v0.5 |
| `docs/reviews/2026-09-30-revb-schematic-review.md`, `…-revb-layout-review.md`, `…-revb-final-review.md` | create | review records (Tasks 9, 14, 16) |

## Names every task uses

Refs of R, C and TP are assigned in the order parts are added and are **not** stable across tasks: tests and tools find
them by their nets. The refs below are fixed by name in `part()` calls.

The layout (Tasks 11–13) depends on these nets and part groups, not on values: row A's 100 Ω / 33 Ω / 4k7 by the
J1 pin net they touch; the drive eFuse's ILM resistor as the R on DRV_ILM–GND (its value may change with R9); the
buck's 22 µF as the 22 µF +3V3–GND capacitor nearest L1. A net renamed in Tasks 3–8 makes `ref_of()` stop with the
nets it could not match.

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
  - **U9's input capacitor (layout review, 2026-09-30):** as written, U9 has none of its own; the nearest capacitor
    on +5V_IN is U5's 1 µF, about 20 mm away. Check the typical application in TI's TPS259531 datasheet (read the
    web page; no download). If it shows a capacitor at IN, add `C("1uF", "+5V_IN", "GND", P)` directly after U9's
    `part()` (the same value as U5's input capacitor, so no new part type), and give it a spot in Task 11's `soft()`:
    the review found the strip x 105.2–106.8, y 131–134 free, between J2.1's feed and the +5V_IN trunk (not checked
    by DRC). Record the outcome as a ruling in the ledger either way.
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
- Create: `tools/placement.py`
- Modify: `tools/pcb_place.py`, `tests/test_pcb.py`, `FluxDrive.kicad_pcb` (the placed, unrouted board),
  `FluxDrive.pretty/171825-4.kicad_mod` (its outline only, and only if step 0's drawing differs from it)

**Interfaces:**
- Consumes: `hardware.design.PARTS` (Tasks 3–8), the footprints of Task 10, Task 1's
  `test_rule_areas_cover_their_layers`.
- Produces: `tools/placement.py`, which does not import pcbnew (the tests read it in the system Python): `SHIFT`,
  `X0`, `Y0`, `X1`, `Y1`, `UY`, `J1_PIN1`, `J6_PIN1`, `BUF_Y`, `ROW_A`, `ROW_B`, `ROW_B_0603`, `ROW_M`, `BAND`,
  `CONNECTOR_ZONE`, `J6_ZONE`, `PASS_1TO1`, `PASS_THROUGH`, `pin_x(n)`, `gap_x(n)`, `corridors()`,
  `ref_of(prefix, *nets, value=None, after=None, nth=None) -> str`, `row_a_parts() -> dict[ref, (x, y, rot)]`,
  `j6_pull_ups()`, `fixed()`, `soft()`, `table() -> (fixed, soft)`. `tools/pcb_place.py`: `legal()` with `J6_ZONE`
  and the pass-through strips, `rows_keepout(pin1_y)`, the rule areas "J1 rows F", "J1 rows B", "J6 rows B",
  "antenna edge", "antenna sides", "buck B", "buck F", "module underside", "USB-C body".

Rev A's refs are not stable in rev B (61 of the 104 refs rev A's `pcb_place.py` names are other parts now, reviews F4
and B4), so the whole table is new: every R, C and TP entry names its part by nets through `ref_of()`, which reads
`hardware.design.PARTS` (KiCad's Python imports `hardware.design` as well as the system Python does). The table was
built and checked in the plan review on the design of Tasks 3–8 (`build/plan-fix/`, 2026-09-30): every part within
0.3 mm of its spot, DRC 0 violations, and with Task 12's pre-routes, fan-out and stitching on the placed board every IC
supply pin and decoupling pad on a +3V3 via of its own, the antenna border stitched, J6's own pins routed out, all
DRC-clean. It was not routed to completion in the review (Task 12 step 6). What it decides:
- **Length 72.1 mm**, the spec's maximum: the module moves 20.1 mm north (rev A: 106.75, rev B 86.65, its antenna end
  0.35 mm inside the north edge), the buffers and rows 17.78 mm. The 2.32 mm between opens the strip under the module
  (3.55 mm) that holds row M and two 74LVC1G157 with their own vias; at 69.9 mm it is about 1.3 mm and they do
  not fit.
- **J6 and the J1–J6 band:** the band (y 127.5–135.28) is crossed by the fourteen pass-through tracks at the J1 pin
  columns; `corridors()` keeps every pad 0.3 mm from them, so parts in the band sit in the pin 4–6 column (U17, U20),
  the pin 14 column (U19, J9) and the 1.94 mm gaps between the columns (jumpers, test pads, 0402s), and meet on B.Cu.
- **Where the review's zone suggestions (B4 fix 3) could not be followed** (record each as a ruling in the ledger):
  - U11 is north-east with U8 and U16, not at the west end beside U17: no TSSOP-14 fits there. Its BUSY output stays
    local to U16; CHNG_G and INDEX_G run west to U17.
  - U17 and U20 with their 33 Ω are in the band's pin 4–6 column, next to the /CHNG and /INDEX pass-through tracks;
    so row A has nothing at J1 pins 2 and 8.
  - U19 and J9 (the reset wire) are in the band's pin 14 column; U12 and U13 east of the module; U14 and U15 in the
    strip under the module; U21 in the north-east corner, U22 and U23 east of U4.
  - U4 sits 1.4 mm east of rev A's place, so that U10 fits between U2 and U4 (U10 feeds U4).
  - SW1 and SW2 stand side by side (rev A: stacked), which frees the room U8, U11 and U16 need.
  - J5 stands west of the module: its pin 3 (IO18) beside module pin 11, its pin 4 (IO3) 6.5 mm from module pin 15.
  - JP1/JP2 and U18 are west of row B (review B6): J6.10 and J6.4 reach their centre pads from the free pin-4 and
    pin-6 columns. J6.6, J6.12 and J6.14's 10 kΩ are in row A's free pin 6 and pin 14 columns.
  - J7, JP5–JP7 and flip-flop A's RCs are in the band east of J1 pin 20; flip-flop B's RC (D5 and its 1 µF) at the
    band's east end, CLR_B crossing J6 past its east end.
  - J8 (J6pwr) stands beside J6's west end, pin 1 south next to U9; J2 is 0.4 mm north of rev A's place, so that its
    courtyard ends inside the new south edge.
  - Some logic test pads are up to 20 mm from their parts (STEP, SEL_FD, DF0_STATE, MODE_CLK): no room nearer.

- [ ] **Step 0: gate — the open items due before the layout freezes (spec §11, review F17).** Task 12 does not start
  until all four are in the ledger.
  - **O15 (owner: this plan): TE 171825-4's outline, for J2 and J8, and the clearance of J8's plug to J6's body.**
    Done on 2026-10-01 with TE's two customer drawings. Dimitri allowed the two downloads; both PDFs come from the
    "Documents" section of te.com's product pages and are kept, untracked, in `build/o15/`: `ENG_CD_171825_Y4.pdf`
    (101 196 bytes) and `ENG_CD_171822_L5.pdf` (135 329 bytes).
    - The header: drawing C-171825, "Post header assy (vertical)", rev Y4 of 30 March 2023 (ECR-22-158621).
    - Its body is 10.0 ± 0.2 mm long (C, 4 positions), 4.9 mm deep and 10.4 mm high above the board.
    - Pin 1 is 1.25 mm from the body's end; pins 1 to 4 span 7.5 mm; the pitch is 2.5 ± 0.1 mm, not accumulating.
    - The pin row is 2.5 mm from the outer face of the wall (the partial shroud) and 2.4 mm from the open side.
    - The wall is about 0.9 mm thick (scaled), with a 2.4 mm locking window at its centre; the base is 2.9 mm high.
    - The drawing's board layout asks for 0.9 mm holes (+0.1/-0) in a 1.6 mm board; the footprint drills 1.2 mm.
    - The plug: drawing C-171822, "Housing, AMP EI series connector", rev L5 of 20 January 2026 (ECN-26-364653).
    - It is 11.9 mm long on its latch side (C, 4 positions) and 10.6 mm on its open side (A), 5.8 mm deep and 14.0 mm
      high.
    - Scaled from the drawing, its contact line is 2.5 mm from the latch face and 3.3 mm from the open face; the lower
      10.3 mm steps in to 2.4 mm, flush with the header.
    - The latch face has a 0.9 mm pocket that takes the header's wall, with a 2 mm locking bump at its centre: the
      plug fits only with its latch face on the wall.
    - Mated, the plug sits on the header's base: its top is 16.9 mm above the board, and the wires leave it straight
      up, along the pin row.
    - The circuit numbers are moulded on the wire face. Seen from above, with pins 1 to 4 running east (rotation 0),
      the latch face, and so the wall, is north (local -y). Then pin 1 takes circuit 1, the +5 V of a standard drive
      power cable.
    - The drawing names contacts 170262 and 170263; TE's 171822-4 page also lists 170204-2, the spec's contact.
    - Ruling: the footprint changes. Its F.Fab is 10.2 × 6.7 mm, centred on the pins; the header is 10.0 × 4.9 mm,
      1.8 mm less deep, beyond the 0.2 mm limit.
    - The new outline, pads unchanged: F.Fab x -1.25 to 8.75, y -2.5 to 2.4, with the wall from y -2.5 to -1.6;
      F.SilkS the same, with the wall side marked; F.CrtYd the body plus 0.5 mm (x -1.75 to 9.25, y -3.0 to 2.9); the
      mated plug's outline (x -2.2 to 9.7, y -2.5 to 3.3) on F.Fab. Then step 4 runs again.
    - The wall mark matters: the header fits either way round and the plug follows the wall, so a header soldered the
      other way round puts +12 V on pin 1 (+5 V), as a reversed plug does (spec §6).
    - Task 13's fit test checks the wall side on Dimitri's own cable: its +5 V (red) wire sits at the moulded "1".
  - The clearances with the drawings, on step 3's placement (J8 at 104.0, 123.5 turned 90; J2 at 104.0, 136.1 turned
    270; the wall at local -y, so J8's wall is west and J2's east):
    - J8's plug reaches 3.3 mm east of its pin row, to x 107.3; J6's body starts at x 108.58: 1.28 mm clear. The
      plan's bound (a plug up to 9.0 mm deep) holds; the test that counts is the reach on J6's side, not half the
      depth.
    - Below 13.2 mm above the board the plug's east face is at x 106.4, flush with the header: 2.18 mm clear of J6's
      body.
    - J8's plug ends 2.2 mm south of its pin 1 (y 125.7), J2's 2.2 mm north of its pin 1 (y 133.9): 8.2 mm clear. The
      plan's bound (plugs up to 19.6 mm long) holds: the plug is 11.9 mm long.
    - J2's header body ends 1.25 mm past pin 4 (y 144.85), 0.75 mm inside the south edge (y 145.6). The plan's bound
      (a housing up to 11.5 mm long) holds: the body is 10.0 mm long.
    - J2's plug overhangs the south edge by 0.2 mm (y 145.8), 2.9 mm or more above the board; Task 13's fit test
      checks it in the A500.
    - J2's plug reaches x 100.7 on its open side, 0.7 mm inside the west edge; J8's wall face is 1.5 mm inside it.
    - J2's plug reaches x 106.5 on its wall side; J1's body starts at x 108.58: 2.08 mm clear.
    - Past the header bodies the plugs are 2.9 mm or more above the board, over low SMD parts only.
    - So J8 does not move.
  - **R1, R7, R9 (owner: Dimitri):** he measures them with the guide at
    https://claude.ai/artifact/BWRmrbVaeXMhPnBMZZuhbv (R7 and R1 in one session without power, R9 in a second one).
    His entries are in that artifact's database: collection `metingen`, documents `r1`, `r7` and `r9` (read them with
    the ArtifactData tool). Record each in the ledger with its value, the date and the method.
    - R1: pins 4, 6, 10, 12, 14, 16, 18, 20 and 32, in both meter polarities. A reading of 0.90 to 1.10 kΩ is the
      nominal 1 kΩ. Stop and ask Dimitri only if a load sum breaks: 5 V/R4 + 5 V/R16 + 1.06 mA above 16 mA, or
      5 V/R10 + 1.06 mA above 16 mA (the SN74LVC2G06's VOL of 0.4 V at 16 mA and VCC 3 V; spec §4.4).
    - R7: the board revision, U36's type and the checks P1 to P13. Stop and ask on P1 open, P4 connected, P8 open, or a
      drive swapper on /SEL0 or /SEL1. On a Rev 8A board, the README gets the 74LS05 note (spec §5).
    - R9: the highest +5 V level held for at least 0.25 ms (the TPS2595's current-limit response time). Up to about
      1.05 A, DRV_ILM becomes 1K5 (C25867, Basic; 1.26 A worst case): change the Global Constraints, Names, Task 8's
      `R("1K37", ...)` line and its `RES_LCSC` entry, Task 8's test bound (to `1.3 <= ilim <= 1.6`), Task 15's README
      text and its test, and the extended-part count. From 1.05 to 1.15 A, keep 1K37 (1.37 A worst case). Above
      1.15 A, stop and ask Dimitri. A multimeter-only result counts only at 0.4 A or less, together with a +12 V
      reading that shows the motor runs on +12 V.

- [ ] **Step 1: failing tests** — in `tests/test_pcb.py` delete `test_outline`, `test_connector_zone_free`,
  `test_credit_and_revision`, `test_buck_away_from_dkrd_and_antenna` and `test_decoupling_reaches_the_planes` (the
  last two looked parts up by rev A refs: R35, C5–C7; the ones below find them by net), and append:

```python
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
```

  In `test_rule_areas_cover_their_layers` (Task 1) add two entries at the end of `want`:
  `"J6 rows B": ["B.Cu"], "antenna sides": ["F.Cu", "B.Cu"]` (both forbid tracks; "antenna sides" allows vias, for
  the border stitching of Task 12).

- [ ] **Step 2: run** `python -m pytest -q -p no:cacheprovider tests/test_pcb.py` (rev A's board, rev B's design).
  Expected, checked in the review:
  - FAIL: `test_outline` (`assert 2.4000000000000057 < 0.01`: the south edge), `test_j1_stays_and_j6_beside_it` and
    `test_connector_zones_free` (`KeyError: 'J6'`), `test_filter_pads_beside_their_pull_ups` (STEP: 7.3 mm > 3.0),
    `test_placement_table_covers_the_design` and `test_connector_row_keepouts`
    (`ModuleNotFoundError: No module named 'tools.placement'`), `test_rule_areas_cover_their_layers`
    (`AssertionError: J6 rows B`), `test_credit_and_revision` (the rev B title; it stays red until Task 12's build puts the
    silkscreen on).
  - PASS: `test_placement_is_legal` (review F25: rev A's table on rev A's board; it checks positions against the table,
    not courtyards), `test_buck_away_from_dkrd_and_antenna` and `test_decoupling_reaches_the_planes` (the same checks
    as before, by net: a refactor, not new behaviour), and rev A's other board tests. Note the passing ones in the
    ledger.

- [ ] **Step 3: implement.**
  - `tools/placement.py` (new):

```python
"""FluxDrive v1 rev B placement table, without pcbnew: the position of every footprint of hardware/design.py.

    python -c "from tools.placement import table; print(len(table()[1]))"

tools/pcb_place.py legalises and applies it; tests/test_pcb.py reads it in the system Python.
Refs of R, C and TP are not stable across design changes (plan, "Names every task uses"): every R, C and TP entry
names its part by prefix and nets (ref_of) and, where nets alone are not enough, by value or by the part it follows.
Rev A's parts keep rev A's places, moved north with the module (n) or with the buffers and rows (s).
Coordinates are KiCad board mm (x east, y south); rotation in degrees counter-clockwise.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import hardware.design as D  # noqa: E402

SHIFT = 17.78                        # J6 north of J1 (rev B spec 9)
X0, X1, Y1 = 100.0, 160.0, 145.6     # 60 mm wide; the south edge 2.4 mm north of rev A's (148.0)
Y0 = Y1 - 72.1                       # the north edge 20 mm north of rev A's (93.5): 72.1 mm, the spec's maximum
ANTENNA_IN = 0.35                    # module antenna end inside the north edge (test: 0.3-1.0 mm)
UY = Y0 + 12.8 + ANTENNA_IN          # module origin: F.Fab body top is 12.8 mm north of it
NORTH = 106.75 - UY                  # rev A -> rev B for the module side (rev A U1 at y 106.75): SHIFT + 2.32
J1_PIN1 = (113.68, 141.55)
J6_PIN1 = (J1_PIN1[0], J1_PIN1[1] - SHIFT)
BUF_Y = 125.2 - SHIFT                # the three buffers; rows B and A below them, as rev A
ROW_B, ROW_B_0603, ROW_A = 130.2 - SHIFT, 130.6 - SHIFT, 134.3 - SHIFT
ROW_M = UY + 13.47 + 1.03            # 0402s straight under the module's bottom pins 17-25
BAND = (J6_PIN1[1] + 3.73, J1_PIN1[1] - 6.27)       # y range between J6's and J1's zones
CONNECTOR_ZONE = (107.0, J1_PIN1[1] - 6.27, 161.0, J1_PIN1[1] + 3.73)   # SMD-free: J1's body and the iron
J6_ZONE = (107.0, J6_PIN1[1] - 6.27, 161.0, J6_PIN1[1] + 3.73)          # the same for J6 (LCODE-9)


PASS_1TO1 = (2, 8, 18, 20, 22, 24, 26, 28, 30, 32, 34)   # J1 pin n straight to J6 pin n on F.Cu (spec 9)
PASS_THROUGH = (10, 12, 16)                          # J1 nets that cross J6 to reach the logic


def pin_x(n):
    """x of J1 (and J6) pin n: both rows run east from pin 1/2."""
    return J1_PIN1[0] + ((n - 1) // 2) * 2.54


def gap_x(n):
    """x of the gap east of J1 pin n's column: the pass-through tracks leave these free in the band."""
    return round(pin_x(n) + 1.27, 3)


def corridors():
    """[(x0, y0, x1, y1)]: the band's strips the pass-through tracks take (0.2 mm tracks at pin_x, 0.2 mm
    clearance): no pad of another part may reach into them."""
    return [(round(pin_x(k) - 0.3, 3), BAND[0], round(pin_x(k) + 0.3, 3), BAND[1])
            for k in sorted(PASS_1TO1 + PASS_THROUGH)]


def n(y):
    """A rev A y on the module side moved to rev B."""
    return round(y - NORTH, 3)


def s(y):
    """A rev A y on the connector side (buffers, rows) moved to rev B."""
    return round(y - SHIFT, 3)


def ref_of(prefix, *nets, value=None, after=None, nth=None):
    """The ref design.py gives the part with this ref prefix and exactly these nets (and this value, if given).
    after=REF: the first such part added after REF (a decoupling capacitor follows its IC).
    nth: the nth of identical parts (the two 47 uF bulk capacitors)."""
    order = [p["ref"] for p in D.PARTS]
    start = 0 if after is None else order.index(after) + 1
    hits = [p["ref"] for p in D.PARTS[start:] if p["ref"].rstrip("0123456789") == prefix
            and sorted({x for x in p["pins"].values() if x}) == sorted(set(nets))
            and (value is None or p["value"] == value)]
    if after is not None:
        hits = hits[:1]
    if nth is None:
        assert len(hits) == 1, (prefix, nets, value, after, hits)
        return hits[0]
    assert len(hits) > nth, (prefix, nets, value, nth, hits)
    return hits[nth]


def R(*nets, **kw):
    return ref_of("R", *nets, **kw)


def C(*nets, **kw):
    return ref_of("C", *nets, **kw)


def TP(net):
    return ref_of("TP", net)


def row_a_parts():
    """{ref: (x, y, rot)} of the fitted resistors on J1's even-pin nets, found by net, in the row north of J6
    (rev A's row A, moved by SHIFT): the pull-up (other pad on a rail) at pin_x - 0.55, the 100 ohm at +0.55,
    the 33 ohm from a U4 output at 0.0 turned 270. The other 33 ohm on J1 nets are not row A parts: U17's two
    (CHNG_D, INDEX_D) sit with U17 in the J1-J6 band, U20's (VCHNG_D) with U20 (review B5/F5)."""
    rails = {"+5V_A", "+3V3", "GND"}
    j1 = next(p for p in D.PARTS if p["ref"] == "J1")["pins"]
    u4_out = {x for x in next(p for p in D.PARTS if p["ref"] == "U4")["pins"].values() if x and x.endswith("_D")}
    out = {}
    for pin in range(2, 35, 2):
        net = j1.get(str(pin))
        if not net:
            continue
        for p in D.PARTS:
            if not p["ref"].startswith("R") or p["dnp"] or net not in p["pins"].values():
                continue
            other = [x for x in p["pins"].values() if x != net][0]
            if other in rails:
                out[p["ref"]] = (round(pin_x(pin) - 0.55, 3), ROW_A, 90)
            elif p["value"] == "100":
                out[p["ref"]] = (round(pin_x(pin) + 0.55, 3), ROW_A, 90)
            elif p["value"] == "33" and other in u4_out:
                out[p["ref"]] = (round(pin_x(pin), 3), ROW_A, 270)
    return out


def j6_pull_ups():
    """J6.6, 12 and 14's 10 kOhm in row A's free columns (review B6): pins 6 and 14 carry no J1 net in rev B."""
    return {R("J6_PIN6", "+5V_A"): (round(pin_x(6) - 0.55, 3), ROW_A, 90),
            R("J6_PIN12", "+5V_A"): (round(pin_x(14) - 0.55, 3), ROW_A, 90),
            R("J6_PIN14", "+5V_A"): (round(pin_x(14) + 0.55, 3), ROW_A, 90)}


def fixed():
    """Parts that go exactly where the table says."""
    out = {
        "J1": (J1_PIN1[0], J1_PIN1[1], 90),
        "J6": (J6_PIN1[0], J6_PIN1[1], 90),          # same orientation, pin 1 on the same side (spec 9)
        "U1": (130.0, round(UY, 3), 0),
        "J2": (104.0, 136.1, 270),                   # pin 1 (+5 V) north; 0.4 mm north of rev A: its courtyard ends
                                                     # inside the new south edge
        "J8": (104.0, 123.5, 90),                    # J6pwr: pin 1 south towards U9, pin 4 north
        "J3": (104.945, n(112.5), 270),              # USB-C, opening to the west edge
        "U3": (125.0, BUF_Y, 90),                    # 74LVC14A: J1 pins 10-16 and the freed gates
        "U2": (136.5, BUF_Y, 90),                    # 74LVC14A: J1 pins 18-32, SEL_FD_N
        "U4": (151.4, BUF_Y, 90),                    # 74LVC07A, 1.4 mm east of rev A: U10 sits between U2 and U4
        "H1": (103.5, n(103.5), 0),
        "H2": (156.5, n(103.5), 0),
    }
    out.update(row_a_parts())
    out.update(j6_pull_ups())
    return out


def soft():
    """[(ref, x, y, rot)]: every other part's preferred spot, in the order they are legalised."""
    t = []
    a = t.append
    # --- west power column, moved with the module (rev A's table) ---------------------------------------------
    a(("D2", 104.0, n(118.9), 0))
    a(("D1", 104.0, n(122.55), 0))
    a((C("+5V_A", "GND", value="47uF", nth=0), 104.0, n(125.65), 0))
    a((C("+5V_A", "GND", value="47uF", nth=1), 104.0, n(128.15), 0))
    a(("U5", 111.2, n(131.9), 0))
    a((C("+5V_IN", "GND"), 110.8, n(133.95), 0))                 # U5's input capacitor at IN and the EP
    a((R("+5V_IN", "EFUSE_EN"), 108.1, n(131.0), 270))
    a((R("EFUSE_EN", "GND"), 108.1, n(132.9), 270))
    a((C("EFUSE_DVDT", "GND"), 110.0, n(129.6), 0))
    a((R("EFUSE_ILM", "GND"), 113.4, n(131.0), 90))
    a((C("+5V_A", "GND", value="100nF"), 108.8, n(127.3), 0))
    a(("U6", 112.5, n(121.3), 180))
    a(("L1", 117.2, n(121.5), 0))
    a((C("V5SYS", "GND", value="100nF"), 109.6, n(120.8), 270))
    a((C("V5SYS", "GND", value="10uF"), 112.9, n(117.9), 0))
    a((C("+3V3", "GND", after="L1"), 117.6, n(125.3), 180))      # the buck's 22 uF under L1 pin 2
    a((R("+3V3", "BUCK_FB"), 111.4, n(124.9), 0))
    a((R("BUCK_FB", "GND"), 111.4, n(126.2), 0))
    a((C("+3V3", "BUCK_FB"), 109.3, n(125.5), 90))
    a((R("V5SYS", "V5SYS_DAMP"), 102.5, n(130.8), 0))            # unfitted damper, next to D1/D2
    a((C("V5SYS_DAMP", "GND"), 105.6, n(130.8), 0))
    # --- the drive's power: J2 -> U9 -> J8 in the power strip (rev B spec 6) ----------------------------------
    a(("U9", 103.4, 129.3, 90))                                   # IN (pins 3/4) south to J2, OUT (5) north to J8
    a((C("+5V_DRIVE", "GND", value="22uF"), 105.1, 126.47, 0))    # pad 1 on the U9 -> J8 pin 1 track
    a((C("+5V_DRIVE", "GND", value="100nF"), 102.4, 126.47, 180))
    a((C("DRV_DVDT", "GND"), 101.1, 130.9, 180))
    a((R("DRV_ILM", "GND"), 101.3, 128.4, 270))
    a(("D4", 111.58, 131.4, 90))                                  # unfitted TVS on +5V_IN, between J2 and J1
    a(("FID2", gap_x(20), BAND[0] + 2.0, 0))                      # between the J1 columns of pins 20 and 22
    # --- USB, module support: rev A's, moved with the module ---------------------------------------------------
    a(("U7", 111.3, n(112.5), 0))
    a((R("GND", "USB_CC1"), 110.0, n(109.2), 0))
    a((R("GND", "USB_CC2"), 110.0, n(115.8), 0))
    a((R("GND", "VBUS"), 109.2, n(117.6), 0))
    a((R("USB_DN", "USB_DN_C"), 114.4, n(111.55), 0))
    a((R("USB_DP", "USB_DP_C"), 114.4, n(113.45), 0))
    a((C("GND", "USB_DP"), 114.6, 95.45, 90))                     # unfitted 10 pF, module side of the 22 ohm
    a((C("GND", "USB_DN"), 113.8, 84.5, 90))
    a((C("+3V3", "GND", after="U1"), 116.9, 82.0, 0))                # the module's 22 uF, clear of the border vias
    a((C("+3V3", "GND", after="U1", value="100nF"), 118.9, 83.55, 0))
    a((C("ESP_EN", "GND"), 119.1, 84.75, 0))
    a((R("+3V3", "ESP_EN"), 116.4, n(104.6), 0))
    # --- east: rev A's, moved with the module ----------------------------------------------------------------
    a(("J4", 146.5, n(102.2), 0))
    a(("SW1", 151.25, 90.8, 90))                                 # the buttons side by side (rev A: stacked)
    a(("SW2", 157.05, 90.8, 90))
    a(("D3", 150.8, n(102.0), 0))
    a((R("LED", "LED_A"), 150.8, n(104.2), 0))
    a((R("+5V_A", "AMIGA_PWR"), 141.2, n(102.4), 90))
    a((R("AMIGA_PWR", "GND"), 142.4, n(102.4), 90))
    a((R("ESP_TXD0", "UART_TX"), 142.4, n(106.2), 90))
    a((R("+3V3", "BOOT"), 141.2, n(117.4), 90))
    # --- buffer decoupling at pin 14 --------------------------------------------------------------------------
    a((C("+3V3", "GND", after="U3"), 119.8, BUF_Y - 1.4, 90))
    a((C("+3V3", "GND", after="U2"), 131.3, BUF_Y - 1.4, 90))
    a((C("+3V3", "GND", after="U4"), 147.75, BUF_Y - 4.27, 0))
    # --- row M: the GPIO-side 0402s straight under the module's bottom pins 17-25 -------------------------------
    for pin_n, x, ref, rot in (
            (17, 125.555, R("SEL1", "SEL1_IO"), 90), (18, 126.825, R("RST_REQ", "GND"), 270),
            (19, 128.095, R("MTR0", "MTR0_IO"), 90), (20, 129.365, R("DF0_FD", "DF0_STATE"), 90),
            (21, 130.635, R("DF1_EN", "DF1_REQ"), 90), (22, 131.905, R("CHNG_REQ", "GND"), 270),
            (24, 134.445, R("MODE_CLK_REQ", "GND"), 270), (25, 135.715, R("DF0_FD", "DF0_REQ"), 90)):
        a((ref, x, round(ROW_M, 3), rot))
    # the left-side GPIO 1 kOhms (GPIO17 SEL0, GPIO8 DF1_STATE, GPIO4 RST_ACT) beside their module pins
    a((R("SEL0", "SEL0_IO"), 108.2, 81.6, 0))                      # clear of the antenna border's vias
    a((R("DF1_EN", "DF1_STATE"), 108.2, 83.1, 0))
    a((R("RST_ACT", "RST_ACT_IO"), 108.2, 84.6, 0))
    # --- the steering logic under the module and around the buffers --------------------------------------------
    gy = round((UY + 13.47 + BUF_Y - 3.745) / 2, 3)               # middle of the strip between module and buffers
    a(("U14", 122.3, gy, 0))                                       # REAL_SEL, west of row M
    a(("U15", 138.4, gy, 0))                                       # REAL_MTR, east of row M
    a(("U12", 141.3, 89.3, 90))                                    # SEL1_EN, east of the module
    a(("U13", 141.3, 93.7, 90))                                    # SEL_FD, down to U2 pin 9
    a(("U10", 143.95, BUF_Y, 90))                                  # ORs for U4, between U2 and U4
    a(("U8", 146.9, 99.8, 0))                                      # the mode latch
    a((R("+3V3", "CLR_B"), 151.35, 100.0, 90))
    a((R("+3V3", "PRE_B"), 151.35, 102.1, 90))
    a(("U11", 155.8, 97.4, 180))                                   # CHNG/INDEX ORs and BUSY; pin 14 south-west
    a(("U16", 155.6, 102.2, 0))                                    # the clock gate, next to BUSY
    a((C("+3V3", "GND", after="U8"), 151.4, 97.6, 90))
    a((C("+3V3", "GND", after="U11"), 152.9, 101.5, 90))
    a((C("+3V3", "GND", after="U16"), 158.4, 102.2, 90))
    a((C("+3V3", "GND", after="U10"), 141.48, 100.25, 0))
    a((C("+3V3", "GND", after="U13"), 143.6, 93.7, 0))
    a((C("+3V3", "GND", after="U12"), 143.6, 89.3, 0))
    a((C("+3V3", "GND", after="U14"), 119.24, 98.55, 0))
    a((C("+3V3", "GND", after="U15"), 141.2, gy, 90))
    # north-west, west of row B: the real drive's drivers and the bypass jumpers (review B6)
    a(("U18", 117.2, 108.4, 0))
    a(("JP2", 115.3, 112.5, 90))                                   # J6.4/16: pad 2 reached from the pin-4 column
    a(("JP1", 118.4, 112.5, 90))                                   # J6.10: pad 2 reached from the pin-6 column
    a((C("+3V3", "GND", after="U18"), 114.2, 108.2, 90))
    a((R("J6_SEL_D", "+5V_A"), 113.2, 115.6, 0))
    a((R("J6_MTR_D", "+5V_A"), 110.9, 115.6, 0))
    # mode 4, unfitted (rev B spec 4.7): U21 in the north-east corner, U22 and U23 in the strip east of U4
    a(("U21", 157.8, 75.8, 180))
    a(("U22", 158.0, 106.0, 90))
    a((C("+3V3", "GND", after="U21"), 157.6, 78.6, 0))
    a((C("+3V3", "GND", after="U22"), 158.0, 108.8, 0))
    a((C("+3V3", "GND", after="U23"), 157.3, 112.6, 0))
    a(("U23", 157.3, 115.2, 0))
    # --- row B: rev A's 100 kOhm at the buffer inputs, spread so each 220 pF sits beside its own 100 kOhm -------
    for x, ref in ((121.2, R("+3V3", "RST_B")), (122.5, R("GND", "M4_MTR_Q")), (123.8, R("+3V3", "SEL0_B")),
                   (126.7, R("+3V3", "SEL1_B")), (129.6, R("+3V3", "MTRX_B")), (130.9, R("+3V3", "MTR0_B")),
                   (133.7, R("+3V3", "DIR_B")), (135.0, R("+3V3", "STEP_B")), (137.9, R("+3V3", "DKWD_B")),
                   (139.2, R("+3V3", "DKWE_B")), (140.5, R("+3V3", "SIDE_B")),
                   (143.3, R("+3V3", "DKRD_N")), (144.6, R("+3V3", "TRK0_N")), (145.9, R("+3V3", "WPROT_N")),
                   (147.2, R("+3V3", "RDY_N")), (148.5, R("+3V3", "CHNG_N")), (149.8, R("+3V3", "INDEX_N"))):
        a((ref, x, ROW_B, 90))
    for x, sig in ((125.25, "SEL0"), (128.15, "SEL1"), (132.35, "MTR0"), (136.45, "STEP")):
        a((C(f"{sig}_B", "GND"), x, ROW_B_0603, 90))
    a((R("_MTR0", "+5V_A"), 141.95, ROW_B_0603, 270))              # /MTR0's unfitted pull-up, +5V_A end south
    # --- the J1-J6 band: parts that meet the pass-through nets, the builder's jumpers and pads ---------------
    # Pads stay out of the pass-through tracks' strips (corridors()); parts in different gaps meet on B.Cu.
    lo, hi = BAND
    # pins 4-6 column: U17 with its 33 ohm to J1 pins 2 and 8 (rev B spec 4.3), U20 with its 33 ohm on /CHNG
    a(("U17", 117.5, lo + 1.8, 0))
    a(("U20", 117.5, hi - 1.9, 0))
    a((R("CHNG_D", "_CHNG"), 114.6, lo + 1.0, 90))
    a((C("+3V3", "GND", after="U17"), 114.6, lo + 3.1, 90))
    a((R("VCHNG_D", "_CHNG"), 114.6, lo + 5.2, 90))
    a((R("INDEX_D", "_INDEX"), 120.4, lo + 3.9, 90))
    a((C("+3V3", "GND", after="U20"), 120.4, hi - 1.9, 90))
    # gap 8-10: mode 4's select jumper, /INDEX test pad
    a(("JP3", gap_x(8), lo + 2.4, 90))
    a((TP("_INDEX"), gap_x(8), hi - 1.1, 0))
    # gap 10-12: the reset wire's 100 ohm and U19's capacitor, /SEL0 test pad
    a((R("KBRESET", "RST_B"), gap_x(10), lo + 1.0, 90))
    a((C("+3V3", "GND", after="U19"), gap_x(10), lo + 3.1, 90))
    a((TP("_SEL0"), gap_x(10), hi - 1.1, 0))
    # pin 14 column: the reset wire's driver and pad (rev B spec 4.8)
    a(("U19", pin_x(14), lo + 2.2, 90))
    a(("J9", pin_x(14), hi - 1.5, 0))
    # gap 16-18: mode 4's motor jumper, /MTR0 test pad
    a(("JP4", gap_x(16), lo + 2.4, 90))
    a((TP("_MTR0"), gap_x(16), hi - 1.1, 0))
    a((TP("_STEP"), gap_x(18), hi - 1.1, 0))                      # beside pin 20's track
    # mode 4's motor wire pad and its unfitted resistors (rev B spec 4.7)
    a((R("MTRX", "MTRX_B"), gap_x(18), lo + 1.6, 90))
    a((R("+5V_A", "MTRX"), gap_x(20) - 0.2, hi - 1.7, 90))
    # gaps 22-32: the DF0 switch pads J7 (pads in gaps 22, 24, 26), the REAL pair above them, the power-on jumper
    # and the RCs of flip-flop A (rev B spec 4.6)
    a(("J7", gap_x(22), hi - 1.9, 90))
    a(("JP6", gap_x(22), lo + 2.0, 90))
    a((R("CLR_A", "J7_REAL"), gap_x(24), lo + 1.0, 90))
    a((R("J7_FD", "PRE_A"), gap_x(24), lo + 3.0, 90))
    a(("JP7", gap_x(26), lo + 2.0, 90))
    a((C("GND", "J7_FD"), gap_x(28), lo + 1.0, 90))
    a(("JP5", gap_x(30), lo + 2.4, 90))
    a((TP("_DKRD"), gap_x(30), hi - 1.1, 0))
    a(("D6", gap_x(32), lo + 2.45, 90))
    a((C("GND", "POR_A"), gap_x(32), hi - 1.0, 90))
    # east end: the DD ID's 33 ohm on /RDY (J1 pin 34), flip-flop B's power-on RC, the other RCs, GND pad
    a((R("ID_D", "_RDY"), 155.4, lo + 1.6, 90))
    a((R("+3V3", "CLR_A"), 155.4, lo + 4.2, 90))
    a((C("GND", "J7_REAL"), 155.4, hi - 1.2, 90))
    a(("D5", 157.5, lo + 2.45, 90))
    a((C("CLR_B", "GND"), 159.3, lo + 1.0, 90))
    a((R("+3V3", "PRE_A"), 159.3, lo + 3.2, 90))
    a(("J10", 158.3, hi - 1.4, 0))                                 # mode 4's motor wire pad
    a(("FID3", 101.4, 132.9, 0))                                  # south-west, clear of the pass-through tracks
    # --- logic test pads (rev A's and rev B's) -----------------------------------------------------------------
    a((TP("MTR0"), 130.75, s(127.2), 0))
    a((TP("SEL0"), 111.3, 81.7, 0))
    a((TP("STEP"), 114.1, 105.0, 0))
    a((TP("INDEX_N"), 149.5, 95.8, 0))
    a((TP("DKRD_N"), 143.52, 95.83, 0))
    a((TP("SEL_FD"), 140.8, 85.0, 0))
    a((TP("REAL_SEL"), 112.0, 108.5, 0))
    a((TP("REAL_MTR"), 107.93, 108.85, 0))
    a((TP("DF0_STATE"), 153.2, 114.45, 0))
    a((TP("DF1_STATE"), 111.3, 83.8, 0))
    a((TP("MODE_CLK"), 153.2, 112.3, 0))
    # power and module test pads
    a((TP("+5V_A"), 101.5, 113.0, 0))
    a((TP("V5SYS"), 104.0, 113.0, 0))
    a((TP("VBUS"), 109.3, 86.9, 0))
    a((TP("+3V3"), 101.4, 78.6, 0))                               # corner beside FID1: on the plane, no track
    a((TP("ESP_EN"), 113.6, 81.7, 0))
    a((TP("GND"), 104.0, 77.4, 0))                                # its via is one of the border's west side
    a(("FID1", 101.4, 75.0, 0))
    # the spare header next to module pins 11 (IO18) and 15 (IO3), west side (rev B spec 7)
    a(("J5", 117.2, 88.6, 0))                                    # pin 3 (IO18) beside module pin 11
    return t


def table():
    """(fixed {ref: (x, y, rot)}, soft [(ref, x, y, rot)])."""
    return fixed(), soft()
```

  - `tools/pcb_place.py` (replaces the file: the tables move to `tools/placement.py`; `legal()` gets J6's zone
    (review M9) and the pass-through strips; the row keep-outs are review M6's rectangles, without rev A's test-pad
    notches; "J6 rows B" and "antenna sides" are new):

```python
"""FluxDrive v1 rev B placement: board outline, planes and pours, rule areas and the position of every footprint.

    "/c/Program Files/KiCad/10.0/bin/python.exe" tools/pcb_place.py FluxDrive.kicad_pcb
    "/c/Program Files/KiCad/10.0/bin/python.exe" tools/pcb_place.py --check FluxDrive.kicad_pcb

Coordinates are KiCad board mm (x right = east, y down = south); the board is x 100..160, y 73.5..145.6,
4 layers (In1 GND plane, In2 +3V3 plane). South edge: J1 over CN11, even (signal) row inward; 17.78 mm north of
it J6 for the real drive, same orientation; between them the J1-J6 band (the pass-through tracks, test pads, the
builder's jumpers and pads). North edge: the module, its antenna 0.35 mm inside the edge. The table itself is
tools/placement.py (no pcbnew, so the tests can read it); this script legalises and applies it.

FIXED parts go exactly where the table says. Every other part starts at its table position and, if its
courtyard would overlap one already placed, leave the board or enter J1's or J6's connector zone (no SMD in the
bands the box-header bodies and the iron need), or if one of its pads would reach into the strip of a J1-J6
pass-through track in the band, moves to the nearest free spot (spiral search, 0.1 mm steps, up to 4 mm; then the
other orientation). The script prints every part it had to move.
Positions are footprint origins; rotation in degrees (KiCad: counter-clockwise).
"""
import math
import pathlib
import sys

import pcbnew

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from tools.placement import (CONNECTOR_ZONE, J1_PIN1, J6_PIN1, J6_ZONE, SHIFT, X0, X1, Y0, Y1,  # noqa: E402
                             corridors, pin_x, table)

PLANE_MARGIN = 0.5
MODULE_BOX = (-9.75, -13.5, 9.75, 13.47)            # U1 body courtyard (without its antenna keep-out)
OVERHANG = {"J3"}                                   # may reach past the outline: the USB-C shell
CORRIDORS = corridors()                             # the pass-through tracks' strips in the J1-J6 band
assert abs(J6_PIN1[1] - (J1_PIN1[1] - SHIFT)) < 1e-9


def boxes(fp):
    """{rotation: (x0, y0, x1, y1)} of the courtyard around the origin, for 0/90/180/270 degrees."""
    out = {}
    for rot in (0, 90, 180, 270):
        fp.SetOrientationDegrees(rot)
        fp.SetPosition(pcbnew.VECTOR2I_MM(0, 0))
        fp.BuildCourtyardCaches()
        poly = fp.GetCourtyard(pcbnew.F_CrtYd)
        bb = poly.BBox() if poly.OutlineCount() else fp.GetBoundingBox(False)
        out[rot] = tuple(round(pcbnew.ToMM(v), 3) for v in (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()))
    return out


def pad_boxes(fp):
    """{rotation: [(x0, y0, x1, y1)]} of the footprint's pads (its copper) around the origin."""
    out = {}
    for rot in (0, 90, 180, 270):
        fp.SetOrientationDegrees(rot)
        fp.SetPosition(pcbnew.VECTOR2I_MM(0, 0))
        out[rot] = [tuple(round(pcbnew.ToMM(v), 3) for v in (b.GetLeft(), b.GetTop(), b.GetRight(), b.GetBottom()))
                    for b in (p.GetBoundingBox() for p in fp.Pads())]
    return out


def is_smd(fp):
    return any(p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD for p in fp.Pads())


def overlaps(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def legal(ref, box, smd, placed, pads=()):
    if any(overlaps(p, c) for p in pads for c in CORRIDORS):
        return False
    if ref not in OVERHANG and not (X0 + 0.1 <= box[0] and box[2] <= X1 - 0.1 and Y0 + 0.1 <= box[1]
                                    and box[3] <= Y1 - 0.1):
        return False
    if smd and (overlaps(box, CONNECTOR_ZONE) or overlaps(box, J6_ZONE)):
        return False
    return not any(overlaps(box, b) for b in placed.values())


def spiral(max_r=4.0, step=0.1):
    yield 0.0, 0.0
    r = step
    while r <= max_r + 1e-9:
        n = max(8, int(2 * math.pi * r / step))
        for k in range(n):
            a = 2 * math.pi * k / n
            yield r * math.cos(a), r * math.sin(a)
        r += step


def plan(fps):
    """{ref: (x, y, rot)} for every footprint, and the list of parts that were moved (ref, distance, rot)."""
    fixed, soft = table()
    shapes = {r: boxes(fp) for r, fp in fps.items()}
    coppers = {r: pad_boxes(fp) for r, fp in fps.items()}
    shapes["U1"] = {0: MODULE_BOX}
    placed, where, moved = {}, {}, []
    for ref, (x, y, rot) in fixed.items():
        b = shapes[ref][rot]
        placed[ref] = (x + b[0], y + b[1], x + b[2], y + b[3])
        where[ref] = (x, y, rot)
    for ref, x, y, rot in soft:
        smd = is_smd(fps[ref])
        for r in (rot, (rot + 90) % 360):
            b, c = shapes[ref][r], coppers[ref][r]
            spot = next(((x + dx, y + dy) for dx, dy in spiral()
                         if legal(ref, (x + dx + b[0], y + dy + b[1], x + dx + b[2], y + dy + b[3]), smd, placed,
                                  [(x + dx + q[0], y + dy + q[1], x + dx + q[2], y + dy + q[3]) for q in c])),
                        None)
            if spot:
                break
        assert spot, f"no room for {ref} near ({x}, {y})"
        sx, sy = round(spot[0], 2), round(spot[1], 2)
        placed[ref] = (sx + b[0], sy + b[1], sx + b[2], sy + b[3])
        where[ref] = (sx, sy, r)
        d = math.hypot(sx - x, sy - y)
        if d > 0.01 or r != rot:
            moved.append((ref, round(d, 2), r))
    missing = sorted(set(fps) - set(where))
    assert not missing, f"not in the placement table: {missing}"
    return where, moved


def set_outline(board):
    """A rectangle on Edge.Cuts, once: drawings are never removed (that crashes pcbnew)."""
    if any(d.GetLayer() == pcbnew.Edge_Cuts for d in board.GetDrawings()):
        return
    pts = [(X0, Y0), (X1, Y0), (X1, Y1), (X0, Y1)]
    for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
        s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pcbnew.VECTOR2I_MM(ax, ay))
        s.SetEnd(pcbnew.VECTOR2I_MM(bx, by))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(pcbnew.FromMM(0.05))
        board.Add(s)


def _rect(zone, x0, y0, x1, y1):
    poly = zone.Outline()
    poly.NewOutline()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        poly.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))


PLANES = ((pcbnew.In1_Cu, "/GND"), (pcbnew.In2_Cu, "/+3V3"), (pcbnew.F_Cu, "/GND"), (pcbnew.B_Cu, "/GND"))


def set_planes(board):
    """In1 a solid GND plane, In2 a solid +3V3 plane, GND pours on F.Cu and B.Cu, over the whole board; created
    once. Through-hole pads get thermal reliefs (hand soldering), SMD pads a solid connection. The module
    footprint's keep-out keeps every layer clear under the antenna."""
    have = {(z.GetLayer(), z.GetNetname()) for z in board.Zones() if not z.GetIsRuleArea()}
    for layer, net in PLANES:
        if (layer, net) in have:
            continue
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(board.FindNet(net))
        m = PLANE_MARGIN
        _rect(z, X0 - m, Y0 - m, X1 + m, Y1 + m)
        z.SetLocalClearance(pcbnew.FromMM(0.25))
        z.SetMinThickness(pcbnew.FromMM(0.25))
        z.SetThermalReliefGap(pcbnew.FromMM(0.3))
        z.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.4))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        board.Add(z)


def rows_keepout(pin1_y):
    """The rectangle over a 2x17 header's rows that keeps every track 0.8 mm from its GND row (rev B spec 9,
    review M6): from the even pads' south edge to 1.75 mm south of the GND row, 1.75 mm past the end pins."""
    even_y, odd_y = pin1_y - 2.54, pin1_y
    return (pin_x(1) - 1.75, even_y + 0.85, pin_x(33) + 1.75, odd_y + 1.75)


def keepout_areas(where):
    """[(name, layers, rects, no_vias)]: the track keep-outs of the layout reviews, from the placement."""
    ux, uy, _ = where["U1"]
    lx, ly, _ = where["L1"]
    sx, sy, _ = where["U6"]
    jx, jy, _ = where["J3"]
    return [
        # rev B spec 9: no track between J1's rows or within 0.8 mm of its GND row, on both layers (it is
        # hand-soldered, on either side); J6 is a top box header soldered on B.Cu: J1's rule on B.Cu only
        ("J1 rows F", (pcbnew.F_Cu,), [rows_keepout(J1_PIN1[1])], True),
        ("J1 rows B", (pcbnew.B_Cu,), [rows_keepout(J1_PIN1[1])], True),
        ("J6 rows B", (pcbnew.B_Cu,), [rows_keepout(J6_PIN1[1])], True),
        # LESP-1: nothing along the antenna's base line (the module keep-out covers the antenna itself)
        ("antenna edge", (pcbnew.F_Cu, pcbnew.B_Cu), [(ux - 26.0, uy - 6.75, ux + 26.0, uy - 5.85)], False),
        # rev B spec 9: the lines 1 mm outside the keep-out's sides stay free of tracks for the GND stitching
        # (tools/pcb_stitch.py places those vias after routing)
        ("antenna sides", (pcbnew.F_Cu, pcbnew.B_Cu), [(ux - 25.5, Y0, ux - 24.5, uy - 6.75),
                                                        (ux + 24.5, Y0, ux + 25.5, uy - 6.75)], False),
        # LPWR-3: nothing under the switch node and the inductor on B.Cu, nothing between L1 pads, and a strip
        # north of the switch node for the USB lines
        ("buck B", (pcbnew.B_Cu,), [(sx - 2.1, ly - 2.3, lx + 2.35, ly + 2.3)], False),
        ("buck F", (pcbnew.F_Cu,), [(lx - 0.85, ly - 1.9, lx + 0.85, ly + 1.9),
                                    (sx + 0.4, ly - 2.9, lx - 0.9, ly - 1.95)], True),
        # LESP-5: no F.Cu track under the module body; a band inside each pad row stays free for pad entry
        ("module underside", (pcbnew.F_Cu,), [(ux - 6.7, uy - 6.75, ux + 6.7, uy + 10.85)], False),
        # LPWR-13: nothing under the USB-C shell between its pads
        ("USB-C body", (pcbnew.F_Cu,), [(X0, jy - 3.2, jx + 1.15, jy + 3.2)], True),
    ]


def set_keepouts(board, where):
    have = {z.GetZoneName() for z in board.Zones() if z.GetIsRuleArea()}
    for name, layers, rects, no_vias in keepout_areas(where):
        for i, (x0, y0, x1, y1) in enumerate(rects):
            zname = f"{name} {i + 1}"
            if zname in have:
                continue
            z = pcbnew.ZONE(board)
            z.SetIsRuleArea(True)
            z.SetZoneName(zname)
            ls = pcbnew.LSET()
            for layer in layers:
                ls.AddLayer(layer)
            z.SetLayerSet(ls)
            z.SetDoNotAllowTracks(True)
            z.SetDoNotAllowVias(no_vias)
            z.SetDoNotAllowPads(False)
            z.SetDoNotAllowFootprints(False)
            z.SetDoNotAllowZoneFills(False)
            _rect(z, x0, y0, x1, y1)
            board.Add(z)


def place(board):
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    where, moved = plan(fps)
    for ref, (x, y, rot) in where.items():
        fp = fps[ref]
        if fp.IsFlipped():
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)
        fp.SetOrientationDegrees(rot)
        fp.SetPosition(pcbnew.VECTOR2I_MM(x, y))
    return where, moved


def check(board):
    """LCODE-1: every footprint where this table puts it (a board built by an older version shows up)."""
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    actual = {r: (round(pcbnew.ToMM(fp.GetPosition().x), 3), round(pcbnew.ToMM(fp.GetPosition().y), 3),
                  round(fp.GetOrientationDegrees()) % 360) for r, fp in fps.items()}
    where, _ = plan(fps)
    bad = [r for r, (x, y, rot) in where.items()
           if abs(actual[r][0] - x) > 0.005 or abs(actual[r][1] - y) > 0.005 or actual[r][2] != rot % 360]
    for r in bad:
        print(f"  {r}: board {actual[r]}, table {where[r]}")
    return bad


if __name__ == "__main__":
    if sys.argv[1] == "--check":
        bad = check(pcbnew.LoadBoard(sys.argv[2]))
        print(f"{len(bad)} footprints differ from the placement table")
        sys.exit(1 if bad else 0)
    b = pcbnew.LoadBoard(sys.argv[1])
    set_outline(b)
    where, moved = place(b)
    set_planes(b)
    set_keepouts(b, where)
    pcbnew.SaveBoard(sys.argv[1], b)            # zones are filled by: kicad-cli pcb drc --refill-zones --save-board
    print(f"placed {len(b.GetFootprints())} footprints; moved to make room: "
          + (", ".join(f"{r} {d} mm" + (f" rot {rot}" if rot is not None else "") for r, d, rot in moved) or "none"))
```

- [ ] **Step 4: build a placed board.** DRC reads its rules from the project file of the board's own name, so the board
  is `FluxDrive.kicad_pcb` next to copies of the project files (with any other name DRC runs with KiCad's defaults and
  reports copper-edge and hole clearances that are not there):

```bash
bash tools/export_netlist.sh
rm -rf build/place && mkdir -p build/place
cp FluxDrive.kicad_pro FluxDrive.kicad_sch FluxDrive.kicad_sym fp-lib-table sym-lib-table build/place/
cp -r FluxDrive.pretty 3dmodels build/place/
"/c/Program Files/KiCad/10.0/bin/python.exe" tools/pcb_sync.py build/FluxDrive.net build/place/FluxDrive.kicad_pcb
"/c/Program Files/KiCad/10.0/bin/python.exe" tools/pcb_place.py build/place/FluxDrive.kicad_pcb
"/c/Program Files/KiCad/10.0/bin/kicad-cli.exe" pcb drc --severity-error --refill-zones --save-board \
    -o build/place/drc.txt build/place/FluxDrive.kicad_pcb
```

  Expected (the review's run on the design of Tasks 3–8; refs in the moved list are that design's):
  - `pcb_sync.py`: `added 204 footprints; not in the schematic: none`.
  - `pcb_place.py`: `placed 204 footprints; moved to make room: R47 0.1 mm rot 270, C22 0.3 mm rot 90, C15 0.1 mm rot
    180, C6 0.3 mm rot 90, C43 0.1 mm rot 0, R18 0.1 mm rot 270, JP6 0.1 mm rot 90, TP18 0.1 mm rot 0` — eight parts,
    none more than 0.3 mm.
  - DRC: `Found 0 violations` and `Found 360 unconnected items` (the board is not routed yet).
  - If the design changed since the review, `pcb_place.py` stops with `not in the placement table: [...]` (a new part:
    give it a spot in `soft()`) or `no room for X` (move its spot), and `ref_of()` stops with the nets it could not
    match. Every part that moves more than 1.5 mm goes into the ledger with its new spot written back into `soft()`.

- [ ] **Step 5: install and test** — `cp build/place/FluxDrive.kicad_pcb FluxDrive.kicad_pcb`, then
  `"/c/Program Files/KiCad/10.0/bin/python.exe" tools/pcb_place.py --check FluxDrive.kicad_pcb` (Expected:
  `0 footprints differ from the placement table`) and `python -m pytest -q -p no:cacheprovider tests/test_pcb.py`.
  Expected, checked in the review: every test of Task 11 and Task 1's two rule-area and antenna tests PASS; still red
  on the placed board, until Task 12, and nothing else:
  - `test_pin1_marked_both_sides` (`AssertionError: F.SilkS`) and `test_credit_and_revision`: no silkscreen yet;
  - `test_dkrd_short_and_on_one_layer` (`AssertionError: 0`) and `test_usb_data_pads_joined_on_top`: no tracks yet;
  - `test_decoupling_reaches_the_planes` (`ValueError: min() iterable argument is empty`): no vias yet;
  - `test_production_files_match_the_board`, and any test of Task 1 that reads `jlcpcb/production_files/`: rev A's
    files until Task 12.
  Note these in the ledger.

- [ ] **Step 6: commit** — `git -c core.autocrlf=false add -A tools tests FluxDrive.kicad_pcb FluxDrive.pretty && git -c
  core.autocrlf=false commit -m "Rev B placement: J6 beside J1, 72.1 mm, every part found by net (unrouted)"`.

### Task 12: Hand routes, layout rules and routing

**Files:**
- Modify: `tools/pcb_prefan.py` (rewritten for rev B), `tools/pcb_fanout.py`, `tools/pcb_stitch.py`,
  `tools/pcb_silk.py` (rev A's texts moved onto the rev B board, J5's labels, the rev B title), `tools/pcb_route.py`
  (the time limit), `FluxDrive.kicad_pro` (a `Drive` netclass: track 0.8 mm, clearance 0.2 mm, patterns /+5V_IN,
  /+5V_DRIVE and /+12V; /+5V_IN leaves the Power class), `tests/test_pcb.py`, `FluxDrive.kicad_pcb`,
  `jlcpcb/production_files/*`, `mech/*`; in step 7 also `tools/placement.py` and, only with Dimitri's yes,
  `hardware/design.py`

**Interfaces:**
- Consumes: `tools/placement.py` and the placed board of Task 11.
- Produces: `tools/pcb_prefan.py`: `part_pad(fps, prefix, nets, net)`, `pullup_rail`, `efuse_u5`, `u9_routes`, `dkrd`,
  `drive_power`, `j1_to_j6`, `j6_pins`; `tools/pcb_fanout.py`: `own_via_only(fp, pad)`, `own_vias(fp)`,
  `near_smd_pad(pos)`, `SMD_BOXES`; `tools/pcb_stitch.py`: `border_candidates(fps, y_top)`.

- [ ] **Step 0:** the ledger holds O15, R1, R7 and R9 (Task 11 step 0). If one is missing, stop here.

- [ ] **Step 1: failing tests** — append to `tests/test_pcb.py`:

```python
def _segments(board, net=None):
    """[(net, layer, start, end, width, length)] of every track segment (optionally only those on `net`)."""
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


def _value(board, ref):
    from tools.netlist import _children
    fp = next(f for f in _children(board, "footprint")
              if [p[2] for p in _children(f, "property") if len(p) > 2 and p[1] == "Reference"] == [ref])
    return next(p[2] for p in _children(fp, "property") if len(p) > 2 and p[1] == "Value")


def test_no_track_near_the_gnd_rows(board):
    """Rev B spec 9: no track within 0.8 mm of J1's GND row on either layer, or of J6's GND row on B.Cu (0.8 mm
    from the track's edge to the pad's edge; the pads are 1.7 mm round)."""
    segs = _segments(board)
    assert segs
    gnd = {c: [(x, y) for ref, net, x, y, hw, hh, rot, smd in _pad_shapes(board) if ref == c and net == "/GND"]
           for c in ("J1", "J6")}
    for net, layer, a, b, w, _ in segs:
        if net == "/GND":
            continue
        for conn, layers in (("J1", ("F.Cu", "B.Cu")), ("J6", ("B.Cu",))):
            if layer in layers:
                for p in gnd[conn]:
                    assert _dist_point_segment(p, a, b) - w / 2 - 0.85 >= 0.8 - 0.01, (conn, net, layer, a, b)


def test_j6_gaps_hold_one_centred_track(board):
    """Rev B spec 9, review F21: on F.Cu a track passes between two of J6's pins only centred in the gap (within
    0.05 mm) and at most 0.2 mm wide. A point counts as "between the pins" when it lies in a row's band and more
    than 1.05 mm (pad radius plus a track width) from both neighbouring pin columns."""
    from tools.placement import J6_PIN1, pin_x
    rows = (J6_PIN1[1] - 2.54, J6_PIN1[1])
    cols = [pin_x(n) for n in range(1, 34, 2)]
    for net, layer, a, b, w, length in _segments(board):
        if layer != "F.Cu" or net == "/GND":
            continue
        for k in range(int(length / 0.05) + 1):
            t = 0.0 if length == 0 else min(1.0, k * 0.05 / length)
            x, y = a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])
            if not any(abs(y - ry) <= 0.85 for ry in rows) or not cols[0] < x < cols[-1]:
                continue
            if min(abs(x - c) for c in cols) < 1.05:
                continue                                                   # at a pin, not between two
            assert w <= 0.2 + 0.001 and min(abs(x - c - 1.27) for c in cols) <= 0.05, (net, a, b, round(x, 2))


def test_b_nets_short(board):
    """Rev B spec 9: every _B net (between a 100 ohm and its buffer) at most 1.5 x its pad-to-pad length (rev A:
    SIDE_B 111 mm)."""
    nets = {s[0] for s in _segments(board) if s[0].endswith("_B")}
    assert nets
    for net in nets:
        pads = [(x, y) for ref, n, x, y, *_ in _pad_shapes(board) if n == net]
        span = sum(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in zip(sorted(pads), sorted(pads)[1:]))
        length = sum(s[5] for s in _segments(board, net))
        assert length <= 1.5 * span, (net, round(length, 1), round(span, 1))


def test_3v3_supply_pads_have_their_own_via(board):
    """Rev B spec 9: every IC supply pin and every decoupling capacitor's +3V3 pad reaches a +3V3 via of its own by
    at most 3 mm of track (followed along the segments, not measured straight); L1's +3V3 pad and the buck's
    22 uF reach two. "Own" is a matching: each pad gets a different via (review M11)."""
    import collections
    import math
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

    l1 = _pads(board, "L1", "/+3V3")[0]
    buck = min((r for r in _refs_between(board, "/+3V3", "/GND") if _value(board, r) == "22uF"),
               key=lambda r: math.dist(_pads(board, r, "/+3V3")[0], l1))       # the buck's 22 uF, next to L1
    need = {}
    for ref, net, px, py, hw, hh, rot, smd in _pad_shapes(board):
        if net != "/+3V3" or not smd or not ref.startswith(("U", "C", "L")) or ref == "U1":
            continue
        ext = max(hw, hh) + 0.01                                     # pads may be rotated: the larger half-size
        starts = [p for p in graph if abs(p[0] - px) <= ext and abs(p[1] - py) <= ext]
        found = {v for s in starts for p in reach(s) for v in vias if math.dist(p, v) < 0.05}
        for k in range(2 if ref in ("L1", buck) else 1):
            need[(ref, px, py, k)] = found
    match = {}

    def aug(key, seen):
        for v in need[key]:
            if v not in seen:
                seen.add(v)
                if v not in match or aug(match[v], seen):
                    match[v] = key
                    return True
        return False

    assert [k for k in need if not aug(k, set())] == []


def test_antenna_border_stitched(board):
    """Rev B spec 9, reviews B8 and F11: GND vias at most 3 mm apart along the whole antenna keep-out border: its
    south side (0.55 mm south of the antenna's base line, x +-24 mm around U1) and its east and west sides
    (x +-25 mm, from the north edge to the base line)."""
    fps = pcb.footprints(board)
    ux, uy = fps["U1"][0], fps["U1"][1]
    base = uy - 6.75
    x0, y0, x1, y1 = pcb.board_extents(board)
    gnd = _vias(board, "/GND")
    xs = sorted(x for x, y in gnd if abs(y - (base + 0.55)) <= 0.3 and abs(x - ux) <= 24.0 + 0.01)
    assert xs and xs[0] <= ux - 24.0 + 3.0 and xs[-1] >= ux + 24.0 - 3.0, xs
    assert max(b - a for a, b in zip(xs, xs[1:])) <= 3.0 + 0.01, xs
    for side in (-25.0, 25.0):
        ys = sorted(y for x, y in gnd if abs(x - (ux + side)) <= 0.3 and y <= base + 0.01)
        assert ys and ys[0] <= y0 + 1.0 + 3.0 and ys[-1] >= base - 3.0, (side, ys)
        assert max(b - a for a, b in zip(ys, ys[1:])) <= 3.0 + 0.01, (side, ys)


def test_drive_power_paths_wide(board):
    """Rev B spec 6, review F15: +5V_IN, +5V_DRIVE and +12V at least 0.8 mm wide, narrower only within 1 mm of the
    eFuses' pins and the small pads on these nets (the EN divider, the 100 nF; plus 0.3 mm for the pad itself); every
    via on them has a second one beside it (at least two vias per layer change)."""
    import math
    fine = [(x, y) for ref, net, x, y, hw, hh, *_ in _pad_shapes(board) if ref in ("U5", "U9") or min(hw, hh) < 0.3]
    for net in ("/+5V_IN", "/+5V_DRIVE", "/+12V"):
        segs = _segments(board, net)
        assert segs, net
        for _, layer, a, b, w, _ in segs:
            if w < 0.8 - 0.01:
                assert min(min(math.dist(a, p), math.dist(b, p)) for p in fine) <= 1.0 + 0.3, (net, a, b, w)
        vs = _vias(board, net)
        assert all(sum(math.dist(v, u) <= 1.5 for u in vs) >= 2 for v in vs), (net, vs)


def test_drive_headers_gnd_on_the_plane(board):
    """Rev B spec 6 ("both GND pins of each header get their own vias to In1"), ruling: J2's and J8's GND pins are
    plated through-holes, and set_planes gives through-hole pads a thermal connection to the In1 GND plane, so each
    pin is its own via to In1. Checked on the filled In1 zone: plane copper within 1.4 mm of each GND pin."""
    import math
    from tools.netlist import _child, _children
    fill = [(float(xy[1]), float(xy[2])) for z in _children(board, "zone")
            if (_child(z, "layer") or [None, ""])[1] == "In1.Cu" and _child(z, "net")[-1] == "/GND"
            for poly in _children(z, "filled_polygon") for xy in _children(_child(poly, "pts"), "xy")]
    assert fill
    for ref in ("J2", "J8"):
        pins = [(x, y) for r, net, x, y, hw, hh, rot, smd in _pad_shapes(board) if r == ref and net == "/GND"]
        assert len(pins) == 2, ref
        for p in pins:
            assert min(math.dist(p, q) for q in fill) <= 1.4, (ref, p)


def test_jumpers_bridged_in_copper(board):
    """Rev B spec 4.7, 9: the jumpers delivered closed are copper-bridged 3-pad footprints (a net-tie pad group 1-2
    and a copper polygon on F.Cu); JLC does not close solder jumpers."""
    from tools.netlist import _child, _children
    found = set()
    for fp in _children(board, "footprint"):
        ref = [p[2] for p in _children(fp, "property") if len(p) > 2 and p[1] == "Reference"][0]
        if ref in ("JP1", "JP2", "JP3", "JP4", "JP5"):
            assert "Bridged12" in fp[1], (ref, fp[1])
            assert (_child(fp, "net_tie_pad_groups") or [None, ""])[1] == "1,2", ref
            assert any(_child(p, "layer")[1] == "F.Cu" for p in _children(fp, "fp_poly")), ref
            found.add(ref)
    assert found == {"JP1", "JP2", "JP3", "JP4", "JP5"}
```

- [ ] **Step 2: run** `python -m pytest -q -p no:cacheprovider tests/test_pcb.py -k "gnd_rows or gaps or b_nets or
  own_via or border or drive or jumpers"` on the placed board of Task 11. Expected, checked in the review:
  - FAIL: `test_no_track_near_the_gnd_rows` (`assert []`: no tracks), `test_b_nets_short` (`assert set()`),
    `test_3v3_supply_pads_have_their_own_via` (46 pads without a via, the first `('U18', 118.3375, 108.4, 0)`),
    `test_antenna_border_stitched` (`AssertionError: []`), `test_drive_power_paths_wide` (`AssertionError:
    /+5V_IN`).
  - PASS: `test_j6_gaps_hold_one_centred_track` (no tracks yet), `test_drive_headers_gnd_on_the_plane` (the ruling of
    step 3 holds on Task 11's planes), `test_jumpers_bridged_in_copper` (the footprints of Tasks 5–6; it guards against
    a later footprint swap). Note these three in the ledger.

- [ ] **Step 3: implement.**
  - **Ruling for the ledger (spec §6, "both GND pins of each header get their own vias to In1"; review F15):** J2's and
    J8's GND pins are plated through-holes, and `set_planes()` connects through-hole pads to the In1 GND plane with
    thermal spokes, so each pin is its own connection to In1 and gets no extra via;
    `test_drive_headers_gnd_on_the_plane` checks the plane reaches each of the four pins.
  - `FluxDrive.kicad_pro`: the Drive netclass (review F16/M8: one class, not the Power class, so +5V_A and +3V3 keep
    0.3 mm and Task 1's `width_of("/+5V_A") == 0.3` holds). Run once with the system Python:

```python
import json
import pathlib

p = pathlib.Path("FluxDrive.kicad_pro")
d = json.loads(p.read_text(encoding="utf-8"))
ns = d["net_settings"]
power = next(c for c in ns["classes"] if c["name"] == "Power")
ns["classes"].append(dict(power, name="Drive", track_width=0.8, clearance=0.2, priority=1))
ns["netclass_patterns"] = [q for q in ns["netclass_patterns"] if q["pattern"] != "/+5V_IN"]
ns["netclass_patterns"] += [{"netclass": "Drive", "pattern": n} for n in ("/+5V_IN", "/+5V_DRIVE", "/+12V")]
p.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8", newline="\n")
```

    `git diff FluxDrive.kicad_pro` then shows only the new class and the pattern changes.
  - `tools/pcb_prefan.py` (replaces the file; review M7: every passive by net, U9's EN left to the router; review B6:
    J6's own pins; spec §6: the drive's power by hand, without vias):

```python
"""Hand-made routes that go on the board before Freerouting, locked.

    "/c/Program Files/KiCad/10.0/bin/python.exe" tools/pcb_prefan.py FluxDrive.kicad_pcb

Rev A's routes, redone for the rev B placement and with every passive found by its nets (refs are not stable in
rev B), plus the routes rev B adds:
1. USB-C VBUS bridge: each VBUS pad a short stub east to a via, the two vias joined on B.Cu under the connector's
   pad row, the bridge on down to D2's anode (rev A, LESP-3).
2. The +5V_A rail to the bus pull-ups (LBUS-1): one B.Cu track along the channel between rows A and B, fed from
   U5's OUT pin, with a via and a short F.Cu stub to the +5V_A pad of every pull-up in the rows (pads closer than
   0.9 mm to another pad's via share it).
3. The eFuses' own connections (WSON-8, 0.5 mm pitch): U5 as rev A (EN to its divider, dVdt, ILM, GND to the
   exposed pad, the IN pins to their capacitor); U9's dVdt, ILM, GND and IN pins. U9's EN is left to the router.
4. The USB data pad joins (LESP-3).
5. /DKRD_D from U4's output straight down to its 33 ohm, on F.Cu without a via (LBUS-4), in the lane between
   row B's easternmost pad and the next pull-up's rail via.
6. The drive's power (rev B spec 6), at the Drive class width (0.8 mm) and 0.3 mm within 1 mm of U9's fine pads:
   J2 pin 1 -> U9 IN and -> U5 IN (+5V_IN), U9 OUT -> the 22 uF -> J8 pin 1 (+5V_DRIVE), J2 pin 4 -> J8 pin 4
   (+12V, on B.Cu along the west edge). No via on any of them, so no layer change to double.
7. J1 -> J6 pass-through (rev B spec 9): J1 pin n straight north on F.Cu, a 45-degree jog of half a pitch into the
   gap between J6's odd pins, past the odd row, then back onto J6 pin n (the eleven 1:1 nets) or on past the even
   row as a stub the router continues (J1 pins 10, 12, 16).
8. J6's own pins (review B6): J6.10 on B.Cu north and west to the free pin-6 column, a via, F.Cu north to JP1's
   centre pad; J6.12 on B.Cu north and east to its 10 kOhm in the pin-14 column; J6.4 on F.Cu north to JP2's centre
   pad and on B.Cu under row A to J6.16; J6.6 and J6.14 on F.Cu to their 10 kOhm.
Run after placement, before the fan-out. Only adds: a re-run finds the routes and places nothing.
"""
import math
import pathlib
import sys

import pcbnew

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from tools.placement import PASS_1TO1, PASS_THROUGH, ROW_A, ROW_B  # noqa: E402

STUB = 1.8              # mm, VBUS pad centre to its via, east (J3 opens to the west edge)
WIDTH = 0.3             # the Power netclass
DRIVE = 0.8             # the Drive netclass (rev B spec 6)
FINE = 0.3              # at most this wide within 1 mm of a WSON pad (spec 6)
VIA_D, VIA_DRILL = 0.6, 0.3
RAIL_Y = ROW_A - 1.6    # mm, the +5V_A rail: between row B and row A of tools/placement.py
RAIL_X = (110.0, 156.0)  # +5V_A pads of resistors in this x range and in the band of rows A and B get the rail
RAIL_BAND = (ROW_B - 1.2, ROW_A + 0.7)
RAIL_SHARE = 0.9        # mm: a pad this close to an existing rail via joins it instead of getting its own


def mm(v):
    return pcbnew.FromMM(v)


def pt(x, y):
    return pcbnew.VECTOR2I_MM(x, y)


def xy(p):
    return pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)


def track(board, net, a, b, layer, width=WIDTH):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(a)
    t.SetEnd(b)
    t.SetWidth(mm(width))
    t.SetLayer(layer)
    t.SetNet(net)
    t.SetLocked(True)
    board.Add(t)


def path(board, net, points, layer, width):
    for u, v in zip(points, points[1:]):
        if u != v:
            track(board, net, u, v, layer, width)


def via(board, net, pos):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pos)
    v.SetWidth(pcbnew.F_Cu, mm(VIA_D))
    v.SetDrill(mm(VIA_DRILL))
    v.SetNet(net)
    v.SetLocked(True)
    board.Add(v)


def pad(fps, ref, number):
    return next(p for p in fps[ref].Pads() if p.GetNumber() == number)


def part_pad(fps, prefix, nets, net):
    """The pad on `net` of the one footprint whose ref starts with `prefix` and whose pads carry exactly `nets`
    (refs of R, C and TP are not stable in rev B; nets are)."""
    want = {"/" + n for n in nets}
    hits = [fp for r, fp in fps.items() if r.rstrip("0123456789") == prefix
            and {p.GetNetname() for p in fp.Pads() if p.GetNetname()} == want]
    assert len(hits) == 1, (prefix, sorted(want), [h.GetReference() for h in hits])
    return next(p for p in hits[0].Pads() if p.GetNetname() == "/" + net)


def vbus_bridge(board, fps):
    pads = {p.GetNumber(): p for p in fps["J3"].Pads()}
    net = pads["A4B9"].GetNet()
    ends = []
    for name in ("A4B9", "B4A9"):
        p = pads[name].GetPosition()
        v = pcbnew.VECTOR2I(p.x + mm(STUB), p.y)
        via(board, net, v)
        track(board, net, p, v, pcbnew.F_Cu)
        ends.append(v)
    track(board, net, ends[0], ends[1], pcbnew.B_Cu)
    anode = pad(fps, "D2", "2").GetPosition()              # SS34: pad 2 is the anode, on VBUS
    down = pcbnew.VECTOR2I(ends[1].x, anode.y)
    track(board, net, ends[1], down, pcbnew.B_Cu)
    via(board, net, down)
    track(board, net, down, anode, pcbnew.F_Cu)


def pullup_rail(board, fps):
    out = pad(fps, "U5", "5")                                 # TPS259531 OUT
    net = out.GetNet()
    y = mm(RAIL_Y)
    src = pcbnew.VECTOR2I(out.GetPosition().x + mm(1.15), y)
    track(board, net, out.GetPosition(), src, pcbnew.F_Cu)
    via(board, net, src)
    vias = [src]
    for ref, fp in sorted(fps.items()):
        if not ref.startswith("R"):
            continue
        for p in fp.Pads():
            x, py = xy(p.GetPosition())
            if p.GetNetCode() == net.GetNetCode() and RAIL_X[0] < x < RAIL_X[1] and RAIL_BAND[0] < py < RAIL_BAND[1]:
                near = [v for v in vias if abs(v.x - p.GetPosition().x) < mm(RAIL_SHARE)]
                v = near[0] if near else pcbnew.VECTOR2I(p.GetPosition().x, y)
                if not near:
                    via(board, net, v)
                    vias.append(v)
                track(board, net, p.GetPosition(), v, pcbnew.F_Cu)
    xs = [v.x for v in vias]
    track(board, net, pcbnew.VECTOR2I(min(xs), y), pcbnew.VECTOR2I(max(xs), y), pcbnew.B_Cu)
    return len(vias) - 1


USB_W = 0.2             # mm, the Default netclass
USB_WEST = 106.42       # mm, D+ round A7: 0.21 mm from the pad row's west end (106.73), clear of the body area (106.09)
USB_EAST = 0.9          # mm east of the pad centres, D- round A6: 0.22 mm from its east end


def usb_pairs(board, fps):
    pads = {p.GetNumber(): p for p in fps["J3"].Pads()}
    for (a, b), x in ((("A6", "B6"), mm(USB_WEST)), (("A7", "B7"), pads["A7"].GetPosition().x + mm(USB_EAST))):
        pa, pb = pads[a].GetPosition(), pads[b].GetPosition()
        net = pads[a].GetNet()
        assert net.GetNetCode() == pads[b].GetNetCode(), (a, b)
        path(board, net, [pa, pcbnew.VECTOR2I(x, pa.y), pcbnew.VECTOR2I(x, pb.y), pb], pcbnew.F_Cu, USB_W)


ROW_B_BAND = (ROW_B - 1.2, ROW_B + 1.2)  # mm, the y band of row B's pads (0603 parts a little lower)
DKRD_W = 0.2
DKRD_GAP = 0.17         # mm, where the jog into the gap ends: this far above the row's pads


def mm_box(p):
    bb = p.GetBoundingBox()
    return tuple(pcbnew.ToMM(v) for v in (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()))


def dkrd(board, fps):
    """U4's output (pin 4) south, a 45-degree jog west into the lane between row B's easternmost pad and the rail via
    of the first +5V_A pull-up east of the 33 ohm, straight south across the rail channel, a jog onto the 33 ohm's
    pad. The lane keeps DKRD_W / 2 + 0.2 mm from both (asserted)."""
    src, dst = pad(fps, "U4", "4"), part_pad(fps, "R", ("DKRD_D", "_DKRD"), "DKRD_D")
    net = src.GetNet()
    sx, sy = xy(src.GetPosition())
    dx, dy = xy(dst.GetPosition())
    row = [mm_box(p) for fp in board.GetFootprints() for p in fp.Pads()
           if ROW_B_BAND[0] < pcbnew.ToMM(p.GetPosition().y) < ROW_B_BAND[1]]
    west = max(b[2] for b in row if b[2] < sx)
    rail = [xy(p.GetPosition())[0] for fp in board.GetFootprints() if fp.GetReference().startswith("R")
            for p in fp.Pads() if p.GetNetname() == "/+5V_A" and abs(pcbnew.ToMM(p.GetPosition().y) - dy) < 0.1
            and xy(p.GetPosition())[0] > dx]
    east = min(rail) - VIA_D / 2
    lane = round((west + east) / 2, 3)
    assert lane - west >= DKRD_W / 2 + 0.2 and east - lane >= DKRD_W / 2 + 0.2, (west, lane, east)
    y0 = pcbnew.ToMM(src.GetBoundingBox().GetBottom()) + 0.2
    y1 = max(b[3] for b in row) + 0.25
    pts = [(sx, sy), (sx, y0), (lane, y0 + abs(sx - lane)), (lane, y1), (dx, y1 + abs(lane - dx)), (dx, dy)]
    assert pts[4][1] <= dy, pts
    path(board, net, [pt(x, y) for x, y in pts], pcbnew.F_Cu, DKRD_W)
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def efuse_u5(fps):
    """[(pad, pad, width)]: rev A's U5 tracks, the passives found by net (rev A: EFUSE, by ref)."""
    u = {n: pad(fps, "U5", n) for n in ("1", "2", "3", "4", "7", "8", "9")}
    en = part_pad(fps, "R", ("+5V_IN", "EFUSE_EN"), "EFUSE_EN")
    return [(u["2"], en, 0.2),                                                        # EN to its divider
            (en, part_pad(fps, "R", ("EFUSE_EN", "GND"), "EFUSE_EN"), 0.2),
            (u["1"], part_pad(fps, "C", ("EFUSE_DVDT", "GND"), "EFUSE_DVDT"), 0.2),  # dVdt
            (u["7"], part_pad(fps, "R", ("EFUSE_ILM", "GND"), "EFUSE_ILM"), 0.2),   # ILM
            (u["8"], part_pad(fps, "R", ("EFUSE_ILM", "GND"), "GND"), 0.25),       # GND to the ILM resistor
            (u["8"], u["9"], 0.25),                                                 # and the exposed pad
            (u["3"], u["4"], 0.25),                                                 # IN pins
            (u["4"], part_pad(fps, "C", ("+5V_IN", "GND"), "+5V_IN"), 0.25)]        # and their capacitor


def efuse(board, fps):
    for a, b, w in efuse_u5(fps):
        assert a.GetNetCode() == b.GetNetCode(), (a.GetNetname(), b.GetNetname())
        end = b.GetPosition()
        if b.GetNumber() == "9":                     # into the exposed pad straight, clear of pin 7 (ILM)
            end = pcbnew.VECTOR2I(end.x + mm(0.3), a.GetPosition().y)
        track(board, a.GetNet(), a.GetPosition(), end, pcbnew.F_Cu, w)
    return 8


def u9_routes(board, fps):
    """U9 (turned 90 degrees: pins 1-4 west to east on its south side, 8-5 on its north side): dVdt, ILM and GND
    at 0.2-0.25 mm as U5's; the IN pins joined. Its EN is left to the router."""
    u = {n: pad(fps, "U9", n) for n in ("1", "3", "4", "7", "8", "9")}
    dvdt = part_pad(fps, "C", ("DRV_DVDT", "GND"), "DRV_DVDT")
    ilm = part_pad(fps, "R", ("DRV_ILM", "GND"), "DRV_ILM")
    (x1, y1), (dvx, dvy) = xy(u["1"].GetPosition()), xy(dvdt.GetPosition())
    path(board, u["1"].GetNet(), [pt(x1, y1), pt(x1, dvy), pt(dvx, dvy)], pcbnew.F_Cu, 0.2)
    (x7, y7), (ix, iy) = xy(u["7"].GetPosition()), xy(ilm.GetPosition())
    turn = y7 - 0.8
    path(board, u["7"].GetNet(), [pt(x7, y7), pt(x7, turn), pt(ix, turn), pt(ix, iy)], pcbnew.F_Cu, 0.2)
    (x8, y8), (ex, ey) = xy(u["8"].GetPosition()), xy(u["9"].GetPosition())
    track(board, u["8"].GetNet(), pt(x8, y8), pt(x8, ey), pcbnew.F_Cu, 0.25)     # pin 8 south into the EP
    track(board, u["3"].GetNet(), u["3"].GetPosition(), u["4"].GetPosition(), pcbnew.F_Cu, 0.25)


TRUNK_X = 107.2         # mm, +5V_IN's run north from J2 to U5, between J8's pads and J6's pin 1
EDGE_X = 101.2          # mm, +12V's run north on B.Cu, between the west edge and J2/J8's pads


def drive_power(board, fps):
    """+5V_IN from J2 to U9 and U5, +5V_DRIVE from U9 to J8, +12V from J2 to J8 (rev B spec 6)."""
    j2 = {n: pad(fps, "J2", n) for n in ("1", "4")}
    j8 = {n: pad(fps, "J8", n) for n in ("1", "4")}
    u9 = {n: pad(fps, "U9", n) for n in ("3", "4", "5")}
    (jx, jy) = xy(j2["1"].GetPosition())
    # J2.1 -> U9 IN: 0.8 mm up to 1 mm from the pins, then 0.3 mm into the gap between pins 3 and 4
    (ax, ay), (bx, by) = xy(u9["3"].GetPosition()), xy(u9["4"].GetPosition())
    mx = (ax + bx) / 2
    net = j2["1"].GetNet()
    track(board, net, pt(mx, ay), pt(mx, ay + 1.0), pcbnew.F_Cu, FINE)
    track(board, net, pt(mx, ay + 1.0), pt(jx, jy), pcbnew.F_Cu, DRIVE)
    # J2.1 -> U5 IN: east along J2's pin row, north beside J8 and under J6's west end, then to U5's input
    # capacitor (the eFuse routes join it to the IN pins) and to the top of the EN divider
    cin = part_pad(fps, "C", ("+5V_IN", "GND"), "+5V_IN")
    top = part_pad(fps, "R", ("+5V_IN", "EFUSE_EN"), "+5V_IN")
    (cx, cy), (tx, ty) = xy(cin.GetPosition()), xy(top.GetPosition())
    trunk_x, turn_y = TRUNK_X, cy + 0.75
    path(board, net, [pt(jx, jy), pt(trunk_x, jy), pt(trunk_x, turn_y), pt(cx - 0.6, turn_y), pt(cx, cy)],
         pcbnew.F_Cu, DRIVE)
    path(board, net, [pt(tx, ty), pt(trunk_x + 0.2, ty), pt(trunk_x + 0.2, turn_y)], pcbnew.F_Cu, WIDTH)
    tvs = pad(fps, "D4", "1")                                   # the unfitted TVS on +5V_IN, west to the run
    (vx, vy) = xy(tvs.GetPosition())
    track(board, net, pt(vx, vy), pt(trunk_x, vy), pcbnew.F_Cu, DRIVE)
    # U9 OUT -> its 22 uF -> J8 pin 1; the 100 nF beside it
    (ox, oy) = xy(u9["5"].GetPosition())
    caps = {fp.GetValue(): p for fp in fps.values() if fp.GetReference().startswith("C")   # the two on
            for p in fp.Pads() if p.GetNetname() == "/+5V_DRIVE"}                           # +5V_DRIVE
    (kx, ky), (sx, sy) = xy(caps["22uF"].GetPosition()), xy(caps["100nF"].GetPosition())
    dnet = u9["5"].GetNet()
    track(board, dnet, pt(ox, oy), pt(ox, oy - 1.0), pcbnew.F_Cu, FINE)
    path(board, dnet, [pt(ox, oy - 1.0), pt(kx, ky), j8["1"].GetPosition()], pcbnew.F_Cu, DRIVE)
    track(board, dnet, pt(sx, sy), pt(kx, ky), pcbnew.F_Cu, WIDTH)
    # J2.4 -> J8.4 on B.Cu along the west edge
    (fx, fy), (gx, gy) = xy(j2["4"].GetPosition()), xy(j8["4"].GetPosition())
    path(board, j2["4"].GetNet(), [pt(fx, fy), pt(EDGE_X, fy), pt(EDGE_X, gy), pt(gx, gy)], pcbnew.B_Cu, DRIVE)


def j1_to_j6(board, fps):
    """J1 pin n straight north on F.Cu, a 45-degree jog of half a pitch into the gap between J6's odd pins, past the
    odd row, then back onto J6 pin n (1:1 nets) or on past the even row as a stub the router continues."""
    j1 = {p.GetNumber(): p for p in fps["J1"].Pads()}
    j6 = {p.GetNumber(): p for p in fps["J6"].Pads()}
    odd_y, even_y = j6["1"].GetPosition().y, j6["2"].GetPosition().y      # south is +y: odd_y > even_y
    jog = mm(1.27)
    for n in map(str, PASS_1TO1 + PASS_THROUGH):
        a = j1[n].GetPosition()
        y_in = odd_y + mm(1.3)
        pts = [a, pcbnew.VECTOR2I(a.x, y_in + jog), pcbnew.VECTOR2I(a.x + jog, y_in)]
        if int(n) in PASS_1TO1:
            pts += [pcbnew.VECTOR2I(a.x + jog, odd_y - mm(1.3)), j6[n].GetPosition()]
        else:
            pts += [pcbnew.VECTOR2I(a.x + jog, even_y - mm(1.3))]
        path(board, j1[n].GetNet(), pts, pcbnew.F_Cu, 0.2)


def j6_pins(board, fps):
    """J6's own pins (review B6): see the module docstring, item 8."""
    j6 = {p.GetNumber(): p for p in fps["J6"].Pads()}
    even_y = pcbnew.ToMM(j6["2"].GetPosition().y)
    w = 0.2

    def at(n):
        return xy(j6[n].GetPosition())

    # J6.10 -> JP1 pad 2: B.Cu north and west to the free pin-6 column, a via, F.Cu north, into the pad from the east
    x10, _ = at("10")
    jp1 = pad(fps, "JP1", "2")
    (px, py) = xy(jp1.GetPosition())
    col = pcbnew.ToMM(max(q.GetBoundingBox().GetRight() for q in fps["JP1"].Pads())) + 0.3
    y_b = even_y - 2.2
    net = j6["10"].GetNet()
    path(board, net, [j6["10"].GetPosition(), pt(x10, y_b), pt(col, y_b)], pcbnew.B_Cu, w)
    via(board, net, pt(col, y_b))
    path(board, net, [pt(col, y_b), pt(col, py), pt(px, py)], pcbnew.F_Cu, w)
    # J6.12 -> its 10 kOhm: B.Cu north and east to the pin-14 column, a via, F.Cu north to the resistor
    x12, _ = at("12")
    r12 = part_pad(fps, "R", ("J6_PIN12", "+5V_A"), "J6_PIN12")
    (rx, ry) = xy(r12.GetPosition())
    y_b = even_y - 1.6
    net = j6["12"].GetNet()
    path(board, net, [j6["12"].GetPosition(), pt(x12, y_b), pt(rx, y_b)], pcbnew.B_Cu, w)
    via(board, net, pt(rx, y_b))
    track(board, net, pt(rx, y_b), pt(rx, ry), pcbnew.F_Cu, w)
    # J6.4 -> JP2 pad 2 on F.Cu, into the pad from the east; J6.4 -> J6.16 on B.Cu under row A
    x4, _ = at("4")
    jp2 = pad(fps, "JP2", "2")
    (qx, qy) = xy(jp2.GetPosition())
    col = pcbnew.ToMM(max(q.GetBoundingBox().GetRight() for q in fps["JP2"].Pads())) + 0.3
    net = j6["4"].GetNet()
    path(board, net, [j6["4"].GetPosition(), pt(col, even_y - 0.85 - 0.3), pt(col, qy), pt(qx, qy)], pcbnew.F_Cu, w)
    x16, _ = at("16")
    y_a = ROW_A
    path(board, net, [j6["4"].GetPosition(), pt(x4, y_a), pt(x16, y_a), j6["16"].GetPosition()], pcbnew.B_Cu, w)
    # J6.6 and J6.14 -> their 10 kOhm, on F.Cu
    for n, nets in (("6", ("J6_PIN6", "+5V_A")), ("14", ("J6_PIN14", "+5V_A"))):
        r = part_pad(fps, "R", nets, nets[0])
        (rx, ry) = xy(r.GetPosition())
        (x, y) = at(n)
        path(board, j6[n].GetNet(), [pt(x, y), pt(rx, y - (0.85 + 0.3)), pt(rx, ry)], pcbnew.F_Cu, w)


def main(path_):
    board = pcbnew.LoadBoard(path_)
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    vbus = pad(fps, "J3", "A4B9").GetNetCode()
    if any(t.GetClass() == "PCB_VIA" and t.GetNetCode() == vbus for t in board.GetTracks()):
        print("hand-made routes already there")
        return
    vbus_bridge(board, fps)
    n = pullup_rail(board, fps)
    e = efuse(board, fps)
    u9_routes(board, fps)
    usb_pairs(board, fps)
    d = dkrd(board, fps)
    drive_power(board, fps)
    j1_to_j6(board, fps)
    j6_pins(board, fps)
    pcbnew.SaveBoard(path_, board)
    print(f"VBUS bridge to D2; +5V_A rail on B.Cu to {n} vias; {e} U5 tracks and U9's; USB D+/D- pad joins; "
          f"/DKRD_D {d:.1f} mm; drive power; J1-J6 pass-through; J6's own pins")


if __name__ == "__main__":
    main(sys.argv[1])
```

  - `tools/pcb_fanout.py` (reviews B7, F13): in the docstring, after the line that ends "so Freerouting keeps
    them." add

```text
Rev B (spec 9): an IC supply pin or a decoupling pad on +3V3 gets a via of its own (L1 and the buck's 22 uF
two) and never joins a neighbour; if one has no room, the script stops and names it.
```

    after the line that starts `KO_TRACK, KO_VIA = [], []` add

```python
SMD_BOXES = []            # (x0, y0, x1, y1) mm of every SMD pad's rectangle (set in main)
PAD_WEB = 0.05            # via ring to an SMD pad's rectangle (test_no_via_in_an_smd_pad): rounded corners do not count


def near_smd_pad(pos):
    """True if a via at pos would come closer than PAD_WEB to the rectangle of an SMD pad (any net)."""
    x, y = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
    r = VIA_D / 2 + PAD_WEB
    return any(math.hypot(max(x0 - x, 0.0, x - x1), max(y0 - y, 0.0, y - y1)) < r for x0, y0, x1, y1 in SMD_BOXES)
```

    in `free()` replace `if any(z.Collide(circle, 0) for z in KO_VIA):` with
    `if any(z.Collide(circle, 0) for z in KO_VIA) or near_smd_pad(pos):` (a via may not come nearer than 0.05 mm to
    any SMD pad's rectangle, the rule of `test_no_via_in_an_smd_pad`: a rounded pad corner otherwise lets one in);
    before `def natural(ref):` add

```python
def own_via_only(fp, pad):
    """Rev B spec 9: every IC supply pin and every decoupling capacitor's +3V3 pad has a via of its own to In2; L1's
    +3V3 pad and the buck's 22 uF get two (own_vias)."""
    ref = fp.GetReference()
    return pad.GetNetname() == "/+3V3" and ref.startswith(("U", "C", "L")) and ref != "U1"


BUCK_CAP = None           # the buck's 22 uF on +3V3 (set in main: the one nearest L1)


def own_vias(fp):
    """How many vias of its own an own_via_only pad gets: two for L1 and the buck's 22 uF (rev B spec 9), else one."""
    return 2 if fp.GetReference() in ("L1", BUCK_CAP) else 1
```

    and replace `main()` with

```python
def main(path):
    global X0, X1, Y0, Y1
    board = pcbnew.LoadBoard(path)
    e = board.GetBoardEdgesBoundingBox()
    X0, X1, Y0, Y1 = (pcbnew.ToMM(v) for v in (e.GetLeft(), e.GetRight(), e.GetTop(), e.GetBottom()))
    for fp in board.GetFootprints():
        for q in fp.Pads():
            if q.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
                bb = q.GetBoundingBox()
                SMD_BOXES.append(tuple(pcbnew.ToMM(v)
                                       for v in (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom())))
    for z in list(board.Zones()) + [z for fp in board.GetFootprints() for z in fp.Zones()]:
        if z.GetIsRuleArea():
            if z.GetDoNotAllowTracks() and z.IsOnLayer(pcbnew.F_Cu):
                KO_TRACK.append(z.Outline())
            if z.GetDoNotAllowVias():
                KO_VIA.append(z.Outline())
    global BUCK_CAP
    l1 = next(fp for fp in board.GetFootprints() if fp.GetReference() == "L1")
    caps = [fp for fp in board.GetFootprints() if fp.GetReference().startswith("C") and fp.GetValue() == "22uF"
            and {p.GetNetname() for p in fp.Pads()} == {"/+3V3", "/GND"}]
    BUCK_CAP = min(caps, key=lambda fp: (fp.GetPosition() - l1.GetPosition()).EuclideanNorm()).GetReference()
    done, failed = 0, []
    # pass 1: a via of its own (passives may instead take a straight stub to a nearby via of the same net)
    for fp, pad in plane_pads(board):
        if has_track(board, pad):
            continue
        nc, axis, w = pad.GetNetCode(), outward_axis(fp, pad), stub_width(pad)
        cache = {pcbnew.F_Cu: obstacles(board, pcbnew.F_Cu, nc), pcbnew.B_Cu: obstacles(board, pcbnew.B_Cu, nc)}
        own = own_via_only(fp, pad)
        share = not own and not fp.GetReference().startswith("U")      # IC pins try a via of their own first
        if (share and connect_to_same_net(board, pad, cache, axis, w, False)) or place_via(board, pad, cache, axis, w):
            done += 1
            for _ in range(own_vias(fp) - 1 if own else 0):               # L1 and the buck's 22 uF: a second one
                cache = {pcbnew.F_Cu: obstacles(board, pcbnew.F_Cu, nc), pcbnew.B_Cu: obstacles(board, pcbnew.B_Cu, nc)}
                if not place_via(board, pad, cache, axis, w):
                    failed.append((fp, pad))
        else:
            failed.append((fp, pad))
    # pass 2: no room for a via, so join a neighbour of the same net that has one (straight or L-shaped); an IC
    # supply pin or decoupling pad on +3V3 never joins: the build stops, and the placement is fixed instead
    left, stuck = [], []
    for fp, pad in failed:
        if own_via_only(fp, pad):
            stuck.append(f"{fp.GetReference()}.{pad.GetNumber()}")
            continue
        nc, axis, w = pad.GetNetCode(), outward_axis(fp, pad), stub_width(pad)
        cache = {pcbnew.F_Cu: obstacles(board, pcbnew.F_Cu, nc), pcbnew.B_Cu: obstacles(board, pcbnew.B_Cu, nc)}
        if connect_to_same_net(board, pad, cache, axis, w, True):
            done += 1
        else:
            left.append(f"{fp.GetReference()}.{pad.GetNumber()}")
    if stuck:
        sys.exit("no room for an own +3V3 via: " + ", ".join(stuck))
    pcbnew.SaveBoard(path, board)
    print(f"fanned out {done} pads; no room for: {left or 'none'}")
```

    (pass 1 no longer chains an IC pin or an own-via pad to a neighbour's via: that is how a decoupling pad came to
    share its IC's via; a pad left without an own via stops the build with its ref, so the placement is fixed rather
    than the rule bent.)
  - `tools/pcb_stitch.py` (reviews B8, F11): in the docstring, after the line that ends "The outline comes from
    Edge.Cuts." add

```text
Rev B (spec 9): the antenna keep-out's border comes first, every 2.5 mm along its south side and up its east
and west sides (border_candidates); those vias are spaced only by the hole rule and may enter U1's no-go box.
```

    replace `from pcb_fanout import CLEARANCE, HOLE_GAP, VIA_D, VIA_DRILL, holes, mm` with the two lines
    `import pcb_fanout` and `from pcb_fanout import CLEARANCE, HOLE_GAP, VIA_D, VIA_DRILL, holes, mm, near_smd_pad`;
    after the line that starts `KICAD_CLI = ` add

```python
BORDER_STEP = 2.5          # mm between the antenna border's stitching candidates (rev B spec 9: at most 3 mm)
BORDER_SOUTH = 0.55        # mm south of the antenna's base line: inside the "antenna edge" strip (tracks never go
                           # there), CLEARANCE outside the module's keep-out, a mask web from module pins 1 and 40
BORDER_SIDE = 25.0         # mm east and west of the module's centre: 1 mm outside the keep-out's +-24 mm


def border_candidates(fps, y_top):
    """GND stitching along the antenna keep-out's border (rev B spec 9): its south border (the antenna's base line)
    every 2.5 mm from x -24 to +24 around U1, and up its east and west sides to the north edge."""
    ux, uy = pcbnew.ToMM(fps["U1"].GetPosition().x), pcbnew.ToMM(fps["U1"].GetPosition().y)
    base = uy - 6.75
    south = [(round(ux - 24.0 + BORDER_STEP * i, 2), round(base + BORDER_SOUTH, 2)) for i in range(20)]
    south.append((round(ux + 24.0, 2), round(base + BORDER_SOUTH, 2)))
    n = int((base - y_top - 1.0) / BORDER_STEP) + 1
    sides = [(round(ux + dx, 2), round(base - BORDER_STEP * i, 2)) for dx in (-BORDER_SIDE, BORDER_SIDE)
             for i in range(n)]
    return south + sides
```

    and replace `main()` with

```python
def main(path):
    global X0, Y0, X1, Y1
    board = pcbnew.LoadBoard(path)
    e = board.GetBoardEdgesBoundingBox()
    X0, X1, Y0, Y1 = (pcbnew.ToMM(v) for v in (e.GetLeft(), e.GetRight(), e.GetTop(), e.GetBottom()))
    gnd = board.FindNet("/GND")
    for fp in board.GetFootprints():
        for q in fp.Pads():
            if q.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
                bb = q.GetBoundingBox()
                pcb_fanout.SMD_BOXES.append(tuple(pcbnew.ToMM(v) for v in (bb.GetLeft(), bb.GetTop(), bb.GetRight(),
                                                                           bb.GetBottom())))
    own = []
    others = {layer: [] for layer in (pcbnew.F_Cu, pcbnew.B_Cu)}     # (shape, clearance in mm)
    for t in board.GetTracks():
        for layer in others:
            if t.GetNetCode() != gnd.GetNetCode() and t.IsOnLayer(layer):
                others[layer].append((t.GetEffectiveShape(layer), CLEARANCE))
    for fp in board.GetFootprints():
        for p in fp.Pads():
            for layer in others:
                if p.IsOnLayer(layer):
                    if p.GetNetCode() == gnd.GetNetCode():
                        own.append(p.GetEffectiveShape(layer))
                    else:
                        c = max(CLEARANCE, pcbnew.ToMM(p.GetOwnClearance(layer)))
                        others[layer].append((p.GetEffectiveShape(layer), c))
    for z in list(board.Zones()) + [z for fp in board.GetFootprints() for z in fp.Zones()]:
        if z.GetIsRuleArea() and z.GetDoNotAllowVias():
            for layer in others:
                others[layer].append((z.Outline(), CLEARANCE))
    no_go = []
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    for ref, hw, hh in NO_GO:
        c = fps[ref].GetPosition()
        no_go.append((pcbnew.ToMM(c.x) - hw, pcbnew.ToMM(c.y) - hh, pcbnew.ToMM(c.x) + hw, pcbnew.ToMM(c.y) + hh))
    gnd_vias = [(pcbnew.ToMM(v.GetPosition().x), pcbnew.ToMM(v.GetPosition().y)) for v in board.GetTracks()
                if v.GetClass() == "PCB_VIA" and v.GetNetCode() == gnd.GetNetCode()]
    hole_list = holes(board)
    added = 0
    nx, ny = int((X1 - X0) / GRID * 2), int((Y1 - Y0) / GRID * 2)
    border = border_candidates(fps, Y0)
    cands = sorted({(round(X0 + EDGE_MIN + i * GRID / 2, 2), round(Y0 + EDGE_MIN + j * GRID / 2, 2))
                    for i in range(nx + 1) for j in range(ny + 1)},
                   key=lambda p: min(p[0] - X0, X1 - p[0], p[1] - Y0, Y1 - p[1]))   # edges first
    for x, y in border + cands:
        on_border = (x, y) in border
        if not (X0 + EDGE_MIN <= x <= X1 - EDGE_MIN and Y0 + EDGE_MIN <= y <= Y1 - EDGE_MIN):
            continue
        if not on_border and any(a <= x <= c and b <= y <= d for a, b, c, d in no_go):
            continue
        edge = min(x - X0, X1 - x, y - Y0, Y1 - y) <= EDGE_BAND
        need = HOLE_GAP + VIA_DRILL if on_border else EDGE_SPACING if edge else SPACING
        if any((x - vx) ** 2 + (y - vy) ** 2 < need ** 2 for vx, vy in gnd_vias):
            continue
        pos = pcbnew.VECTOR2I_MM(x, y)
        if any((pos - hp).EuclideanNorm() < mm(VIA_DRILL / 2 + pcbnew.ToMM(hd) / 2 + HOLE_GAP) for hp, hd in hole_list):
            continue
        circle = pcbnew.SHAPE_CIRCLE(pos, mm(VIA_D / 2))
        if any(s.Collide(circle, mm(c)) for layer in others for s, c in others[layer]):
            continue
        if any(s.Collide(circle, mm(WEB)) for s in own) or near_smd_pad(pos):
            continue
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pos)
        via.SetWidth(pcbnew.F_Cu, mm(VIA_D))
        via.SetDrill(mm(VIA_DRILL))
        via.SetNet(gnd)
        via.SetLocked(True)
        board.Add(via)
        gnd_vias.append((x, y))
        hole_list.append((pos, mm(VIA_DRILL)))
        added += 1
    pcbnew.SaveBoard(path, board)
    print(f"added {added} ground stitching vias")
```

    (the border's candidates come first and keep every check of the grid pass except the U1 no-go box and the spacing
    between stitching vias; the south line lies in the "antenna edge" strip, where no track may go, and the side lines
    in the "antenna sides" strips of Task 11, so routing cannot take their places.)
  - `tools/pcb_silk.py` (review B9: the build must not stop in `pcb_silk.py`, whose rev A table names J5 pads 5 and 6;
    review M10: rev A's texts would land beside the module, over J6's pins or off the board): replace everything from
    `SIZE = 1.0` up to `def add_text(board` with

```python
SIZE = 1.0           # mm, text height (spec 8, JLC minimum)
# References that stay off the silkscreen: the passives, pads and jumpers in the dense rows have no room for them.
# They remain on F.Fab, i.e. in the assembly drawing.
HIDE_REFS = ("R", "C", "D", "TP", "FID", "H", "L", "SW", "JP")   # buttons: BOOT / RESET; jumpers: their texts
# obvious, or named by the texts below
HIDE_REF_EXACT = {"U1", "U5", "U6", "U7", "U9", "U12", "U13", "U14", "U15", "U16", "U17", "U18", "U19", "U20",
                  "U21", "U22", "U23", "J1", "J2", "J3", "J5", "J6", "J7", "J8", "J9", "J10"}
# references placed by hand: (dx, dy) from the footprint origin, upright; the buffers carry theirs on the body
REF_AT = {"J4": (0.0, -2.1), "U2": (0.0, 0.0), "U3": (0.0, 0.0), "U4": (0.0, 0.0), "U8": (0.0, 0.0),
          "U10": (0.0, 0.0), "U11": (0.0, 0.0)}

# (text, x, y, layer, size, rotation) at fixed places, all centred (rev B placement, tools/placement.py)
TEXTS = [
    ("FluxDrive v1 rev B", 130.0, 82.5, "B.SilkS", 1.2, 0),
    ("by Dimmy (Dimitri Hilverda)", 130.0, 84.7, "B.SilkS", 1.0, 0),
    ("JLCJLCJLCJLC", 130.0, 87.0, "B.SilkS", 1.0, 0),
    ("S/N", 124.6, 93.4, "B.SilkS", 1.0, 0),
    ("UART", 146.5, 97.3, "B.SilkS", 1.0, 0),
    # fit test (Dimitri, 2026-09-29): plugged onto CN11, pin 1 over its pin 1, the antenna edge points to the
    # A500's front (over the 8520 and Gary); on the antenna strip, which carries no copper
    ("A500 FRONT", 111.5, 76.7, "F.SilkS", 1.0, 0), ("A500 FRONT", 148.5, 76.7, "F.SilkS", 1.0, 0),
    ("A500 FRONT", 111.5, 76.7, "B.SilkS", 1.0, 0), ("A500 FRONT", 148.5, 76.7, "B.SilkS", 1.0, 0),
    ("J1 option: 2x17 female socket on this side,", 137.0, 143.05, "B.SilkS", 1.0, 0),
    ("plugs onto the A500 header. Pin 1 = square pad", 137.0, 144.45, "B.SilkS", 1.0, 0),
    ("print at 100 %: both bars must measure exactly 50 mm / 40 mm", 130.0, 154.0, "Dwgs.User", 1.5, 0),
    ("50 mm", 130.0, 152.2, "Dwgs.User", 1.5, 0),
    ("40 mm", 166.5, 120.0, "Dwgs.User", 1.5, 90),
]
# (ref, pad, text, dx, dy, layer, rotation): a label next to a pad
PAD_TEXTS = [
    ("J1", "1", "1", -5.77, 0.0, "F.SilkS", 0), ("J1", "1", "1", 0.0, 2.75, "B.SilkS", 0),
    ("J2", "1", "+5V", 3.9, 0.0, "B.SilkS", 0), ("J2", "2", "GND", 3.9, 0.0, "B.SilkS", 0),
    ("J2", "3", "GND", 3.9, 0.0, "B.SilkS", 0), ("J2", "4", "+12V", 4.2, 0.0, "B.SilkS", 0),
    ("J4", "1", "TX", 2.8, 0.0, "B.SilkS", 0), ("J4", "2", "RX", 2.8, 0.0, "B.SilkS", 0),
    ("J4", "3", "EN", 2.8, 0.0, "B.SilkS", 0), ("J4", "4", "IO0", 2.9, 0.0, "B.SilkS", 0),
    ("J4", "5", "3V3", 2.9, 0.0, "B.SilkS", 0), ("J4", "6", "GND", 2.9, 0.0, "B.SilkS", 0),
    ("J5", "1", "GND", -4.3, 0.0, "B.SilkS", 0), ("J5", "2", "3V3", -4.3, 0.0, "B.SilkS", 0),
    ("J5", "3", "SCL/IO18", -4.8, 0.0, "B.SilkS", 0), ("J5", "4", "SDA/IO3", -4.8, 0.0, "B.SilkS", 0),
]
# (ref, text, dx, dy, rotation): labels beside a footprint on F.SilkS
FP_TEXTS = [("SW1", "BOOT", 0.0, -4.4, 0), ("SW2", "RESET", 0.0, -4.4, 0)]
# (x0, y0, x1, y1, layer, width)
LINES = [
    # serial number box, 15 x 6 mm
    (122.5, 92.2, 137.5, 92.2, "B.SilkS", 0.15), (137.5, 92.2, 137.5, 98.2, "B.SilkS", 0.15),
    (137.5, 98.2, 122.5, 98.2, "B.SilkS", 0.15), (122.5, 98.2, 122.5, 92.2, "B.SilkS", 0.15),
    # scale bars for the printed fit template, outside the board outline: 50 mm across, 40 mm down
    (105.0, 150.5, 155.0, 150.5, "Dwgs.User", 0.2), (105.0, 149.5, 105.0, 151.5, "Dwgs.User", 0.2),
    (155.0, 149.5, 155.0, 151.5, "Dwgs.User", 0.2),
    (164.5, 100.0, 164.5, 140.0, "Dwgs.User", 0.2), (163.5, 100.0, 165.5, 100.0, "Dwgs.User", 0.2),
    (163.5, 140.0, 165.5, 140.0, "Dwgs.User", 0.2),
]
```

    These are rev A's texts moved onto the rev B board (with the module: title, credit, JLC's number, serial box, UART,
    A500 FRONT; south of J1: the J1 option note), the J1 pin-1 marks beside pin 1 (review M10), J2's pin 4 now "+12V"
    (review F20), BOOT and RESET above the side-by-side buttons, J5's four pins; the labels rev B adds come in Task 13,
    which only adds to these tables.

- [ ] **Step 4: check everything up to the router** on a copy of the placed board (the pre-routes, fan-out, stitching
  and silkscreen of step 3, without Freerouting), named `FluxDrive.kicad_pcb` beside the project files:

```bash
PY="/c/Program Files/KiCad/10.0/bin/python.exe"
rm -rf build/pre && mkdir -p build/pre
cp FluxDrive.kicad_pro FluxDrive.kicad_sch FluxDrive.kicad_sym fp-lib-table sym-lib-table build/pre/
cp -r FluxDrive.pretty 3dmodels build/pre/
cp FluxDrive.kicad_pcb build/pre/FluxDrive.kicad_pcb
for s in pcb_prefan pcb_fanout pcb_stitch pcb_silk; do "$PY" tools/$s.py build/pre/FluxDrive.kicad_pcb; done
"/c/Program Files/KiCad/10.0/bin/kicad-cli.exe" pcb drc --severity-error --refill-zones --save-board \
    -o build/pre/drc.txt build/pre/FluxDrive.kicad_pcb
"$PY" tools/pcb_place.py --check build/pre/FluxDrive.kicad_pcb
cp FluxDrive.kicad_pcb build/pre/placed.kicad_pcb && cp build/pre/FluxDrive.kicad_pcb FluxDrive.kicad_pcb
python -m pytest -q -p no:cacheprovider tests/test_pcb.py
cp build/pre/placed.kicad_pcb FluxDrive.kicad_pcb
```

  Expected (the review's run, 2026-09-30):
  - `pcb_prefan.py`: `VBUS bridge to D2; +5V_A rail on B.Cu to 11 vias; 8 U5 tracks and U9's; USB D+/D- pad joins;
    /DKRD_D 7.0 mm; drive power; J1-J6 pass-through; J6's own pins`.
  - `pcb_fanout.py`: `fanned out 156 pads; no room for: ['C1.2', 'C8.2', 'C41.2', 'R3.2', 'R6.2', 'R12.2', 'R16.2',
    'R20.2', 'R32.2']` — passives' GND and +3V3 pads, left to the router (refs of that design). It must not stop with
    `no room for an own +3V3 via`: if it does, move the named part in `soft()` and run step 4 again.
  - `pcb_stitch.py`: `added 71 ground stitching vias`; `pcb_silk.py`: `42 texts and lines added; references resized,
    passives hidden`.
  - DRC: `Found 0 violations`, `Found 242 unconnected items`; `--check`: `0 footprints differ from the placement table`.
  - pytest: every board test passes except `test_b_nets_short` (`assert set()`: those nets are the router's),
    `test_production_files_match_the_board` and any test of Task 1 that reads `jlcpcb/production_files/` (rev A's
    files until step 8). So the rules of Task 11 and of this task hold before routing; what fails after step 6 is
    the router's.

- [ ] **Step 5: the router's time limit** (found in the review's run): `java` on PATH is Oracle's launcher
  (`C:\Program Files\Common Files\Oracle\Java\javapath\java.exe`), which starts `jdk-17\bin\java.exe` as a child.
  `subprocess.run(..., timeout=TIMEOUT)` in `tools/pcb_route.py` kills only the launcher and then waits for the child's
  pipes, so the limit never ends a run: five of the review's six runs went on for more than 70 minutes. In
  `tools/pcb_route.py` replace the two lines

```python
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    tail = "\n".join(line for line in (r.stdout + r.stderr).strip().splitlines()[-8:] if "image handler" not in line)
```

  with

```python
    run = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        out, _ = run.communicate(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        # `java` on PATH can be Oracle's launcher, which starts the real java.exe as a child: killing only the
        # launcher leaves Freerouting running and communicate() waiting on its pipes, so kill the whole tree
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(run.pid)], capture_output=True)
        run.communicate()
        sys.exit(f"Freerouting ran longer than {TIMEOUT} s: stopped")
    tail = "\n".join(line for line in out.strip().splitlines()[-8:] if "image handler" not in line)
```

  Check it with a 25 s limit on a copy:

```bash
rm -rf build/rt && mkdir -p build/rt && cp FluxDrive.kicad_pro build/rt/ && cp build/pre/FluxDrive.kicad_pcb build/rt/
sed 's/^TIMEOUT = 3600 /TIMEOUT = 25   /' tools/pcb_route.py > build/rt/pcb_route_25s.py
time "/c/Program Files/KiCad/10.0/bin/python.exe" build/rt/pcb_route_25s.py build/rt/FluxDrive.kicad_pcb 100
tasklist //FI "IMAGENAME eq java.exe"
```

  Expected (checked in the review): `Freerouting ran longer than 25 s: stopped`, exit status 1 after about 26 s, and no
  `java.exe` left from this run (with the old two lines the same check hangs until the router is killed by hand).
  `pcb_autoroute.py` then reports such a run as `Freerouting failed` and takes the best of the others.

- [ ] **Step 6: build** — `OUT=build/pcbB bash tools/pcb_build.sh` (up to an hour and a half: six Freerouting runs of up
  to an hour side by side, then the finishing rounds; do not edit `tools/` while it runs). Expected when the board is
  routed: `build/pcbB/FluxDrive.kicad_pcb: DRC clean`, then `FluxDrive.kicad_pcb updated; run python -m pytest -q`.
  **The review's run did not get there.** With this placement and step 3's pre-routes, and rev A's `pcb_route.py`:
  - one of the six Freerouting runs finished (variant `(30, 100, 'horizontal', 'vertical', 2.5)`, 20 minutes):
    `60 open`; the other five were still running after 70 minutes (the fault step 5 fixes) and were stopped by hand;
  - the finishing rounds' maze router (one net at a time, no rip-up) brought that to 47 open; the Freerouting
    `--continue` run that follows was still going after 27 minutes and was stopped by hand;
  - where the open connections were: 12 of the 60 cross J6 (between the band's parts and the logic north of J6:
    CHNG_REQ, RST_REQ, RST_B, M4_SEL, M4_SEL_Q, M4_MTR, M4_MTR_Q, INDEX_G, CLR_A, PRE_A, CLR_B, MTRX_B); four are row
    B's +3V3 pads; the rest are in the logic north of J6: U2's and U3's outputs to row B and beyond (SEL0_B, DIR_B,
    STEP_B, DKWE_B, MTRX_B, RST_ACT, M4_MOTOR), and the nets among the module, U8 and U10–U16 (SEL0, SEL1, SEL_FD,
    SEL_FD_N, DF1_EN, DF1_REQ, BUSY, MODE_CLK, MODE_CLK_REQ, the `_G` and `_N` nets).
  So the build is expected to stop after `pcb_autoroute.py` (exit status 1; its `finishing round` lines list the
  open nets).
  Go on with step 7.

- [ ] **Step 7: close the open connections** (not done in the review; this is layout work, in rounds). Each round:
  1. Take the open nets from `pcb_autoroute.py`'s last `finishing round` line and look at them on the board
     (`build/pcbB/FluxDrive.kicad_pcb` in KiCad, or a plot per layer).
  2. Change only these, and write each change as a ruling in the ledger:
     - a `soft()` spot in `tools/placement.py` (never `fixed()`: J1, J6, the module, the rows and the buffers stay).
       Spread the cluster that holds most open connections, or move a part next to the part it talks to (for example
       the unfitted U22 and U23 nearer U3, whose M4 outputs they take);
     - a locked hand route in `tools/pcb_prefan.py`, by net, for a short connection Freerouting leaves open (a buffer
       output to its row-B pad);
     - a gate or pin swap in `hardware/design.py` only with Dimitri's yes and the netlist tests of Tasks 3–8 green.
  3. Run steps 4 and 6 again. Keep the round only if the open count falls; `git checkout` the round's changes if not.
     Freerouting gives the same result on the same input, so a count is repeatable.
  Stop and ask Dimitri with the list of open nets if three rounds leave more than 10 open, or a round gains fewer than
  5. The choices that need him change the spec: a routing channel in In2 (a split +3V3 plane, spec §9), six layers
  (spec §9 and §13: cost), or fewer parts in the J1–J6 band. Record his answer as a ruling.

- [ ] **Step 8: production files, then the whole suite** (review B10: `test_production_files_match_the_board` compares
  the board with `jlcpcb/production_files/`) — `bash tools/jlc_production.sh && python -m pytest -q -p
  no:cacheprovider`.
  Expected: PASS (every netlist and board test; the BOM and CPL are rev B's now; `test_b_nets_short` holds once the
  router has made the `_B` nets).

- [ ] **Step 9: commit** — `git -c core.autocrlf=false add -A tools tests hardware FluxDrive.kicad_pro
  FluxDrive.kicad_pcb jlcpcb mech && git -c core.autocrlf=false commit -m "Rev B routed: J1-J6 pass-through, J6's
  pins, drive power, own +3V3 vias, antenna border stitched"`.

### Task 13: Silkscreen, fit template and dummy

**Files:**
- Modify: `tools/pcb_silk.py`, `tests/test_pcb.py`, `FluxDrive.kicad_pcb`, `mech/fit_template.pdf`,
  `mech/FluxDrive.step`, `jlcpcb/production_files/*`

- [ ] **Step 1: failing tests** — append to `tests/test_pcb.py`:

```python
def test_revb_labels(board):
    """Rev B spec 9, reviews F20 and M10: the labels a builder needs; J2's pin 4 carries +12 V now."""
    texts = " ".join(_texts(board, "F.SilkS") + _texts(board, "B.SilkS"))
    for need in ("FluxDrive v1 rev B", "TO DRIVE", "TO CN11", "DRIVE POWER", "plug before J6", "CUT 1-2", "CHECK",
                 "BRIDGE 2-3", "REAL (both)", "DF0 at power-on", "mode 4", "DF0: FD", "REAL", "SCL", "SDA", "+12V",
                 "RST", "MTRX"):
        assert need in texts, need
    assert "12V nc" not in texts


def test_silk_on_the_board(board):
    """Review M10: every silkscreen text lies on the board, at least 0.5 mm inside the outline (rev A's J1 "1" would
    sit 1 mm outside the new south edge)."""
    from tools.netlist import _child, _children
    x0, y0, x1, y1 = pcb.board_extents(board)
    for t in _children(board, "gr_text"):
        if _child(t, "layer")[1] in ("F.SilkS", "B.SilkS"):
            tx, ty = float(_child(t, "at")[1]), float(_child(t, "at")[2])
            assert x0 + 0.5 <= tx <= x1 - 0.5 and y0 + 0.5 <= ty <= y1 - 0.5, (t[1], tx, ty)
```

- [ ] **Step 2: run** `python -m pytest -q -p no:cacheprovider tests/test_pcb.py -k "revb_labels or silk_on"`.
  Expected: `test_revb_labels` FAILS on `TO DRIVE` (the title came in Task 12); `test_silk_on_the_board` PASSES
  already (Task 12 moved rev A's texts onto the board; it guards the labels added now) — note that in the ledger.

- [ ] **Step 3: implement** in `tools/pcb_silk.py` (spec §9, review F20; only additions, so the step can run on the
  installed board: `pcb_silk.py` never removes a drawing) — append to `TEXTS`, before the three `Dwgs.User` entries:

```python
    # rev B spec 9: the connectors and the builder's jumpers (the bottom side of the J1-J6 band and south of J1)
    ("TO DRIVE (J6)", 113.5, 125.6, "B.SilkS", 1.0, 0),
    ("REAL (both): JP6 JP7", 143.0, 125.6, "B.SilkS", 1.0, 0),
    ("mode 4, see README: JP3 JP4 J10", 123.5, 127.3, "B.SilkS", 1.0, 0),
    ("DF0 at power-on: JP5", 150.0, 127.3, "B.SilkS", 1.0, 0),
    ("BYPASS JP1 JP2:", 121.0, 117.9, "B.SilkS", 1.0, 0),
    ("CUT 1-2, CHECK, BRIDGE 2-3", 121.0, 119.4, "B.SilkS", 1.0, 0),
    ("mode 4, see README", 158.8, 108.0, "B.SilkS", 1.0, 90),
    ("DRIVE POWER - plug before J6", 101.9, 119.75, "B.SilkS", 1.0, 90),
    ("TO CN11 (J1)", 116.0, 136.6, "B.SilkS", 1.0, 0),
```

  and append to `PAD_TEXTS`:

```python
    ("J8", "1", "+5V", 3.9, 0.0, "B.SilkS", 0), ("J8", "2", "GND", 3.9, 0.0, "B.SilkS", 0),
    ("J8", "3", "GND", 3.9, 0.0, "B.SilkS", 0), ("J8", "4", "+12V", 4.2, 0.0, "B.SilkS", 0),
    ("J7", "2", "DF0: FD / GND / REAL", 0.0, 2.0, "B.SilkS", 0),
    ("J9", "1", "RST", 0.0, 1.9, "B.SilkS", 0), ("J10", "1", "MTRX", -1.2, 1.9, "B.SilkS", 0),
```

  The builder's labels are on B.SilkS: on F.SilkS the band and the rows have no free room, and the box headers' bodies
  cover the strips beside them; the jumpers are named in the texts, since their references are hidden.

- [ ] **Step 4: apply, check and print** —
  `"/c/Program Files/KiCad/10.0/bin/python.exe" tools/pcb_silk.py FluxDrive.kicad_pcb`, then
  `"/c/Program Files/KiCad/10.0/bin/kicad-cli.exe" pcb drc --schematic-parity --severity-error --refill-zones
  --save-board --exit-code-violations -o build/drc.txt FluxDrive.kicad_pcb` (exit 0),
  `"/c/Program Files/KiCad/10.0/bin/python.exe" tools/pcb_place.py --check FluxDrive.kicad_pcb` (0 differ),
  `bash tools/jlc_production.sh`, `python -m pytest -q -p no:cacheprovider` (PASS), and `bash tools/fit_template.sh`.
  Expected from `pcb_silk.py`: `16 texts and lines added; references resized, passives hidden` (the nine texts and seven
  pad labels above). A full `tools/pcb_build.sh` gives the same board: `pcb_silk.py` adds these texts in the same run.
  Then check the PDF's scale bars (50 mm and 40 mm), print it at 100 %, and ask Dimitri for the fit test with J6, its
  plug and the drive power cable in his A500 (spec §10.4, §12). The fit test result goes into the ledger; a failed fit
  returns to Task 11 with a ruling.

- [ ] **Step 5: commit** — `git -c core.autocrlf=false add -A tools tests FluxDrive.kicad_pcb mech jlcpcb && git -c
  core.autocrlf=false commit -m "Rev B silkscreen, fit template and STEP"`.

### Task 14: Layout review

**Files:**
- Create: `docs/reviews/2026-09-30-revb-layout-review.md`
- Modify: whatever the review's accepted findings touch

- [ ] **Step 1:** the four specialist reviewers of rev A (Amiga bus, power and EMC, ESP32-S3 and USB, PCB-readiness and
  code), each a fresh agent, on the routed board (plots per layer, the DRC report, `tools/placement.py`, the tests),
  against the rev B spec, the schematic review record and the ledger's rulings of Task 11 (placement) and Task 12
  step 7 (routing). The PCB reviewer
  checks the review-focus lines of this plan on the board and in particular: the J1→J6 pass-through and the 0.8 mm to
  J1's GND row (both layers) and J6's (B.Cu); J6's own pins (Task 12's hand routes); the drive power path (J2 → U9 →
  J8, J2 → U5) at 0.8 mm without vias; the own-via matching of every IC supply pin; the antenna border stitching; the
  test pads left far from their parts.
- [ ] **Step 2:** record and decide as rev A's layout review did; fix blockers and majors with failing tests first,
  rebuild with `OUT=build/pcbB bash tools/pcb_build.sh`, `bash tools/jlc_production.sh`, suite and DRC clean.
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
