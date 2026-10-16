# Review of the rev B schematic (commit 329c6e9)

Four specialist reviews of the generated rev B schematic (`FluxDrive.kicad_sch`, from `hardware/design.py`), its
netlist, its PDF, the rev B spec v0.3 and its tests, done by separate agents on 2026-10-14. None of them changed a
file. This document lists every finding, what was decided and where it went. The rev B spec went to v0.4 for this
review (header and change note). The reviewers' severities are advice; the decisions grade by effect on the person
using the board, so a minor can be fixed and a minor can be declined.

| Review | Findings | Blockers |
|---|---|---|
| Amiga floppy bus (RBUS) | 8: 6 minor, 2 nits | — |
| Power and EMC (RPWR) | 8: 1 major, 2 minor, 5 nits | — |
| ESP32-S3 and USB (RESP) | 8: 4 minor, 4 nits | — |
| PCB-readiness (RPCB) and code (RCODE) | 18: 1 major, 6 minor, 11 nits | — |

42 findings in all, 2 majors (RPWR-1, RPCB-1), no blockers. What became of them:

| Outcome | Findings |
|---|---|
| Fixed (16: 14 with a test, the tidy-ups RCODE-5 and RCODE-6 by the suite staying green) | RPCB-1, RPWR-1, RBUS-1, RBUS-2, RBUS-3, RBUS-4, RBUS-7, RBUS-8, RESP-1, RPCB-6, RCODE-1, RCODE-4, RCODE-5, RCODE-6, RCODE-7, RPWR-6 |
| Spec v0.4 or plan text only (13) | RBUS-5, RBUS-6, RPWR-2, RPWR-4, RPWR-5, RPWR-7, RPWR-8, RESP-3, RESP-4, RESP-6, RESP-7, RPCB-2, RPCB-7 |
| README only (2) | RESP-8, RPCB-9 |
| Declined (5) | RPWR-3, RPCB-3, RPCB-4, RPCB-5, RPCB-8 |
| Deferred (6) | RESP-2 (a, b; its rule c is in spec §8), RESP-5, RCODE-2, RCODE-3, RCODE-8, RCODE-9 |

Reference designators below are those of the fixed schematic. The fix adds one part, R85 (100 kΩ, M4_SEL_Q to GND),
as the last part of `design.py`, so no existing R, C or TP ref moved; the reviews' refs are unchanged.

## Sources the reviews used

- **[TPS]** TI TPS2595x datasheet SLVSE57C (U5, U9: pinout, clamp, Eq. 3 and 4, retry, FLT).
- **[LVC]** TI SN74LVC2G06/2G07/1G06/1G38/1G175 datasheets (SCES307J, SCES308K, SCES560G: pinout, VOL, Ioff, setup),
  Nexperia 74LVC1G157, 74LVC74A, 74LVC32A, Diodes 74LVC07A (C176925).
- **[ESP]** ESP32-S3 datasheet v2.2 (tables 2-1, 2-2, 3-3 to 3-5, 5-4) and ESP32-S3-WROOM-1/1U datasheet v1.8, the
  ESP-IDF GPIO API (`gpio_reset_pin`) and the ESP32-S3 errata.
- **[TEAC]**, **[CHI]** TEAC FD-235HF (§7.1, §9.1, §9.2(2)) and Chinon F-354C (§3-2, §5-1, §5-4) specifications.
- **[SCH]**, **[HRM]** the A500 Rev 6a/7 schematic (CN11, via `build/revb-research/a500.md`) and the Amiga Hardware
  Reference Manual appendix H.
- **[JLC]**, **[LCSC]** JLC's parts API and LCSC's product API (stock, basic or extended, package), 2026-10-14.
- The netlist (`build/FluxDrive.net`), a pin-by-pin cross-check of netlist against design file (0 mismatches over 205
  parts), the whole committed suite, `tests/test_swap.py` and `build/revb/mutate.py` re-run, 8 own mutants of the bus
  reviewer, and ERC at every severity (0 errors, 27 `footprint_filter` warnings).

## Where the reviews and the decisions differ

| Topic | Positions | Decision |
|---|---|---|
| Series resistor on J6.10 and the reset output (RPWR-3) | RPWR: 22 Ω on U18.6 and 33 Ω on U19.4, none on J6.4/16, exception written down. | Declined. The A500's own open-collector drivers (74LS38, 74LS05) have none; J6.4/16 cannot take one (33 Ω adds 0.37 V to the 2G06's 0.4 V at 11.1 mA, against the drive's 0.40 V input-low); one rule for all three is simpler than two. The exception is in spec §4.4 and §13. Cost if wrong: some ringing on J6.10 on a long ribbon. |
| Remove JP3 and JP4 (RPCB-3) | RPCB: one 100 kΩ replaces both jumpers; the layout gets simpler. | Declined. Spec §4.7's conversion step stays and the verified placement has the jumpers. RBUS-1's 100 kΩ on M4_SEL_Q makes them harmless. Cost if wrong: two small pads and one conversion step more. |
| U4's replacement (RPCB-1) | RPCB: (a) C176925 in SO-14, (b) C7809 in TSSOP-14, (c) two more SN74LVC2G07. | (a): the same footprint, only the LCSC field changes, and the verified placement keeps U4 where it is. Checked on lcsc.com and jlcpcb.com (see RPCB-1). |
| R1's pass rule for pin 10 (RPWR-7) | RPWR and the decision: 330 Ω. | 335 Ω. At 330 Ω the 2G06 sinks 5 V / 330 Ω + 1.06 mA = 16.2 mA, above the 16 mA the rule is made from (the plan's load sum 5 V/R10 + 1.06 mA ≤ 16 mA). Pins 4 and 16: 680 Ω as reviewed. Cost if wrong: a drive with a 330–334 Ω termination on pin 10 is sent to the bypass or another drive for nothing. |

## Findings and decisions

"Fixed" means the design, tests or generator now do what the finding asks. A test named in the Decision column failed
before the fix and passes after it ("RED at 329c6e9"), or, where the finding was a gap in the tests, it passes on the
design and fails on the named mutant ("coverage"; the mutants are in "How the fixes were proven" below). Items marked
"spec" are in the rev B spec v0.4 and have no test (firmware, bring-up or wording).

### Amiga floppy bus

| ID | Sev. | Finding | Decision | Where |
|---|---|---|---|---|
| RBUS-1 | minor | M4_SEL_Q floats if JP3 is moved to the mode-4 side before U21 is fitted or with its output unsoldered; U14's I1 is then undefined, and the real drive can answer DF0 next to FluxDrive (also a write on DF0 can reach it). The evaluator read the open-drain output as released (RBUS-8). | Fixed (A3): fitted 100 kΩ R85 from M4_SEL_Q to GND, as R33 on M4_MTR_Q. `test_partial_mode4_fit_keeps_the_real_drive_off`: RED at 329c6e9 (REAL_SEL None), GREEN. | design G, spec §4.7, `tests/test_swap.py` |
| RBUS-2 | minor | No test clocks mode 4's motor latch (U22); three wrong U22 wires pass every behaviour test. | Fixed (A4): `test_mode4_latch_sequence` (motor on, kept between accesses, off latched with the DD ID on /RDY, J7 to REAL hands J6 back). Coverage: fails on all three U22 mutants. | `tests/test_swap.py` |
| RBUS-3 | minor | R84 (ID gate's 33 Ω) is not asserted; the evaluator takes any series R up to 1 kΩ as a path (R84 = 1 kΩ passes). Also the deferred Task 3 minor for R30 and R31. | Fixed (A4): `test_mode4_kit_values` (R84 33, R30 4K7, R31 100). Coverage: fails on the R84 and R30 mutants. Closes the Task 3 minor. | `tests/test_swap.py` |
| RBUS-4 | minor | No test drives the reset wire's input; R28 = 100 kΩ passes everything. | Fixed (A4): `test_reset_wire_input` (_KBRESET low gives RST_ACT high, high gives low, no wire gives low); `test_reset_wire` also pins R28 = 100 Ω. Coverage: fails on the R28 mutant. | `tests/test_swap.py` |
| RBUS-5 | minor | A drive that trips U9 (auto-retry, FLT unconnected) is an unpowered load on the shared lines; /DKWE then reads as a write gate. | Spec §8: unpowered-drive detection and a write guard (write only on a /DKWE falling edge while selected with flux on /DKWD; /DKWE low while deselected or longer than a revolution is a bus fault). §6 notes U9's FLT. README item. No FLT pad (no free GPIO). | spec §6, §8 |
| RBUS-6 | minor | The reset wire has no filter and §8 sets no minimum RST_ACT width. | Spec §8: RST_ACT counts only after reading high continuously for at least 10 ms. No hardware change. | spec §8 |
| RBUS-7 | nit | J6.6, 12 and 14 are checked only at power-on; a stray path from /SEL1 to J6.12 passes. | Fixed (A4): `test_strap_pins_never_active` (every mode bit × SEL0, SEL1, MTR0). Coverage: fails on both strap-pin mutants. | `tests/test_swap.py` |
| RBUS-8 | nit | The evaluator reads a floating input in front of an open-drain gate as "released". | Fixed (A5, in two steps). A live gate with an input of no level gives its output no level at its own strength (U18 and U19 drive their pin directly, so the pin reads None); `test_floating_gate_input_gives_no_level`: RED at 329c6e9 (the output read 1). The task review found that U20 and U23 reach /CHNG and /RDY through 33 Ω, where the evaluator dropped the no level and the bus still read 1 (released): in fix round 1 the no level goes on across a series resistor of at most 1 kΩ (across a larger one the near net keeps its own pull); `test_no_level_passes_across_a_series_resistor`: RED before that change (the bus read 1). On scratch copies of the netlist (R85 removed and U21 not fitted; R73 removed with CHNG_REQ undriven and /SEL0 asserted) /RDY and /CHNG read 1 before round 1 and None after. No existing test failed under the stricter evaluator, so none hides a floating input. | `tests/logic.py`, `tests/test_logic_model.py` |

### Power and EMC

| ID | Sev. | Finding | Decision | Where |
|---|---|---|---|---|
| RPWR-1 | major | U9's limit is sized from the 1.0 A of TEAC Table 7.1-1; the same document (§9.2(2)) adds 0.55 A when a seek overlaps the spindle start: 1.25 A, about 9 % under U9's minimum with a lower limit, 0.6 % at 1K5. R9 measures Dimitri's +12 V-spindle drive and cannot settle it. | Fixed (A2): R_ILM stays 1K37 (worst-case minimum 1.37 A). Test: `(2000 / (R_ILM × 1.01) + 0.04) × 0.925 >= 1.30` in `test_drive_behind_its_own_efuse`, plus `ilim <= 1.6`. Coverage: passes at 1K37 (1.374), fails at 1K5 (1.258). Spec §2 and §6 carry the 1.25 A case and J2's 0.4 + 1.25 = 1.65 A against 2 A; the R9 rule is "may raise the limit (a lower R_ILM), never lower it; above 1.15 A measured, stop and ask" (spec §11, plan Global Constraints, Names, Task 11 step 0); the "switch to 1K5" path is removed. | design B/C comment, spec §2, §6, §11, plan, `tests/test_power.py` |
| RPWR-2 | minor | A drive that loses power with J6 plugged (J8 forgotten, or U9 tripped) stalls FluxDrive in every mode and nothing says why. | Spec §8: with AMIGA_PWR high, a shared line asserted while neither select was active for about 100 ms means "real drive: no power". README item. | spec §8 |
| RPWR-3 | minor | No series resistor on J6.10 and `_KBRESET`, against v1's "33 Ω on every output"; J6.4/16 cannot take one. | Declined (see above); the exception is written into spec §4.4 and §13. | spec §4.4, §13 |
| RPWR-4 | nit | RST_ACT gates every DF1 removal but has no debounce. | Spec §8: the 10 ms rule (as RBUS-6). | spec §8 |
| RPWR-5 | nit | The bypass criterion "boots with FluxDrive unpowered" cannot hold as written: the drive's +5 V comes from J2 through U9. | Spec §10.5: "with FluxDrive's logic unpowered (+3V3 absent, J2 powered)", and how (the buck's L1 removed). README item: a dead U9 also takes the drive's power; the fallback is the drive's cable back on CN12. | spec §10.5 |
| RPWR-6 | nit | No test pins U9's input capacitor C13. | Fixed (A10): the +5V_IN–GND capacitors are exactly ["1uF", "1uF"] in `test_drive_behind_its_own_efuse`. Coverage: fails when C13 is dropped. | `tests/test_power.py` |
| RPWR-7 | nit | R1 sets no acceptance bound, but the 2G06 meets 0.40 V only up to 16 mA. | Spec §11 R1: pins 4 and 16 each at least 680 Ω, pin 10 at least 335 Ω (ruling above: the reviewer's 330 Ω gives 16.2 mA); otherwise bypass or another drive. | spec §11 |
| RPWR-8 | nit | "The motor's return current stays in the power strip" cannot hold. | Spec §6 reworded: the GND vias per header stay; about three quarters of the return runs back over the ribbon and the J1–J6 band, harmless (about 1 mV at 1.25 A). | spec §6 |

### ESP32-S3 and USB

| ID | Sev. | Finding | Decision | Where |
|---|---|---|---|---|
| RESP-1 | minor | TP20 and TP21 sit on the GPIO side of R70/R71, so they show the 60 µs reset glitch of GPIO12/GPIO8, not the mode bits; §10.5's scoped check would show a false drop. | Fixed (A6): the two pads moved to DF0_FD and DF1_EN. `test_test_pads` (equality with spec §9's 22 nets): RED at 329c6e9 (DF0_STATE where DF0_FD is expected). Spec §9, §4.6 and §10.5 say where the pads are. TP20/TP21 keep their numbers. | design F, spec §9, `tests/test_bom.py` |
| RESP-2 | minor | The evaluator ranks an internal pull-up below a 100 kΩ from a driven net (a) and the test does not show that the clock gate saves the mode (b); spec §8 forbids internal pull-ups but not pull-downs on GPIO13/48, and `gpio_reset_pin()` enables the pull-up (c). | (a) and (b) deferred (final review). (c) in spec §8: no internal pull-up or pull-down on GPIO13 and GPIO48 while inputs; never `gpio_reset_pin()` on GPIO10, 13, 14, 47, 48. | spec §8 |
| RESP-3 | minor | No GPIO reads J7: the drive page cannot show the switch state. | Spec §8: shown "as last seen by a request". No J5 pins given up. | spec §8 |
| RESP-4 | minor | After the firmware has applied a stored non-default mode, the latch keeps it through a crash loop; Review Focus 4's "boots as stock" holds only before that. | Spec §8: apply a stored non-default mode at power-on only from an app image marked valid, and stop after N panic or watchdog restarts in a row. Plan Review Focus 4: "until the firmware has applied a stored mode" (plan and controller's Global Constraints). README item: J7 pins 2–3 give the real drive back without firmware. | spec §8, plan |
| RESP-5 | nit | The glitch test drives 9 nets; STEP, DIR, DKWD, SIDE, DKWE are read without 1 kΩ and no test pins that structure. | Deferred (final review): a structural GPIO-isolation test. | — |
| RESP-6 | nit | GPIO47/48 run at 1.8 V on a -N16R16VA module, under the 2.0 V input-high of U16 and U8. | Spec §8: refuse mode writes when VDD_SPI is 1.8 V; §8 and §9 name the N16R8. README item. | spec §8 |
| RESP-7 | nit | After a RESET press a stored DF0 request would replay by the power-on rule and skip §3's quiet-bus wait; the firmware cannot read JP5. | Spec §8: a DF0 change is written to flash only once applied. README item: JP5 and the "power-on default" setting go together. | spec §8 |
| RESP-8 | nit | J5's GND/3V3/SCL/SDA is one of two common OLED pin orders. | README item: check the module's order against the silkscreen. | — |

### PCB-readiness and code

| ID | Sev. | Finding | Decision | Where |
|---|---|---|---|---|
| RPCB-1 | major | U4's 74LVC07AD,118 (C6049) has 0 stock at JLC and LCSC; R10 checked stock only for new parts. | Fixed (A1): U4 is C176925, the Diodes 74LVC07AS14-13, SO-14, the same footprint. Read on lcsc.com (stock 1,640) and jlcpcb.com (Extended): a hex buffer with open-drain outputs, 1.65–5.5 V, inputs and outputs accept up to 5.5 V, power-off isolation. Test (`test_buffers_on_3v3` pins U4's LCSC and footprint): RED at 329c6e9 (C6049). Spec §4.3, §4.9 and §13 name it (v1 §10's row becomes C176925); R10 now covers every LCSC number in the BOM. | design B, spec §4.3, §4.9, §11, §13, `tests/test_bus.py` |
| RPCB-2 | minor | The box header C601943 (J1 and J6) has 0 in stock. | Spec §11, §12: a second source, checked against the 52 mm body limit and the band; candidate C20920 (its length is not checked). README item. | spec §11, §12 |
| RPCB-3 | minor | JP3 and JP4 are not needed. | Declined (see above). | — |
| RPCB-4 | nit | +5V_DRIVE has no test pad. | Declined: J8 pin 1 is probe-able; no new spot in the verified placement. Cost if wrong: a probe on a header pin. | — |
| RPCB-5 | nit | D5/D6 are SOD-123; a basic SOD-323 1N4148WS exists. | Declined: the Task 5 ruling stands (§4.6 names the 1N4148W). | — |
| RPCB-6 | nit | Only U22 carries an LCSC number among the mode-4 parts. | Fixed (A7): U21 C135822, U23 C2867613 (`mux()` keeps the field for a DNP part; still DNP, out of the BOM and of JLC's files). `test_mode4_parts_prepared_not_fitted`: RED at 329c6e9 (None). | design G, `tests/test_swap.py` |
| RPCB-7 | nit | Spec §13 says seven new extended types; the design adds eight (the 1K37). | Spec §13: eight, about $24 per order; the plan's Task 15 step 1 agrees. | spec §13, plan |
| RPCB-8 | nit | /CHNG has two 33 Ω taps (R43 and R81). | Declined: two open-drain taps are correct; the verified placement has both. | — |
| RPCB-9 | nit | The JLC preview needs a note for D5/D6 and the SOT-363 muxes. | README item. | — |
| RCODE-1 | minor | A repeated ref in `design.py` merges two parts in the netlist and ERC says nothing. | Fixed (A8): `sch_gen.generate()` raises on a repeated ref. `test_duplicate_ref_is_an_error`: RED at 329c6e9 (DID NOT RAISE). | `tools/sch_gen.py`, `tests/test_sch_gen.py` |
| RCODE-2 | minor | No test compares the board with the netlist; the suite is green while the board is rev A. | Deferred: Task 11/12's DRC with schematic parity covers it. | — |
| RCODE-3 | minor | The steering tests are slow (the evaluator rebuilds its setup per call). | Deferred. The full suite takes about two minutes. | — |
| RCODE-4 | minor | No test pins which fitted parts are left out of the BOM. | Fixed (A9): `test_parts_left_out_of_the_bom` (the set written out by ref: J4, J5, J7, J9, J10, JP1–JP7, TP1–TP22, H1, H2, FID1–FID3), and `test_every_fitted_part_has_lcsc` skips only that set. Coverage: fails when a fitted SMD part (U17) gets `in_bom=False`. Closes the deferred Task 7 minor. | `tests/test_bom.py` |
| RCODE-5 | nit | design.py's docstring is stale (spec v0.2, "tests read the netlist, not this file"). | Fixed (A11): rewritten for spec v0.4, says that tests and the layout import `PARTS`, and states the "decoupling C directly after its IC" rule `ref_of(after=IC)` relies on. | `hardware/design.py` |
| RCODE-6 | nit | Dead `_n["D"]` counter and `RES_LCSC["15K"]`. | Fixed (A11): removed (nothing uses them; the schematic is unchanged by it). | `hardware/design.py` |
| RCODE-7 | nit | `test_test_pads` checks a subset. | Fixed (A10): the sorted pad nets equal spec §9's 22, and every pad is `TestPoint_Pad_D1.0mm`. Coverage: fails on a 23rd pad and on a 1.5 mm pad. | `tests/test_bom.py` |
| RCODE-8 | nit | `test_outputs_quiet_at_power_up` cannot fail on its own. | Deferred (a rev A test). | — |
| RCODE-9 | nit | The A0 sheet is nearly full. | Deferred, watched: R85 sits on block G's last row and the sheet did not grow (largest y 769.6 mm against the test's 831 mm); the paper size is unchanged. | — |

## For the README (Task 15)

From this review:
- **RESP-4:** J7 pins 2–3 (REAL) joined by a jumper give the real drive back without firmware, also if the firmware
  crash-loops after it applied a stored mode.
- **RESP-6:** exactly the N16R8 module, and why (on a -N16R16VA module GPIO47/48 run at 1.8 V and the mode writes fail);
  the WROOM-1U-N16R8 (C3013946) is the only fallback.
- **RESP-7:** JP5 and the firmware's "power-on default" setting go together.
- **RESP-8:** check the OLED module's pin order against the silkscreen before plugging it into J5 (GND, 3V3, SCL, SDA;
  some modules are VCC, GND, SCL, SDA).
- **RPWR-2 and RBUS-5:** a drive that trips its fuse (or runs without J6pwr) disturbs the bus until it is unplugged.
- **RPWR-5:** a dead U9 also takes the drive's power; the fallback is the drive's own cable back on CN12.
- **RPCB-9:** the JLC-preview list gets D5 and D6 (CPL correction 0, no `D_SOD-123` entry in `tools/jlc_rules.py`) and
  the five SOT-363 muxes U12–U16 (correction 180).

From this fix round:
- U4 is the Diodes 74LVC07AS14-13 (C176925), not C6049; the BOM and the part list say so.
- The box header C601943 has a second source before ordering (spec §12), checked against the 52 mm body limit.
- R_ILM is 1K37 (1.50 A typical, 1.37 A minimum) for a +5 V-only drive's 1.25 A; R9 can only lower it. J2's budget is
  0.4 + 1.25 = 1.65 A against 2 A.
- R1's pass rule: pins 4 and 16 each at least 680 Ω, pin 10 at least 335 Ω.
- The test-pad map: the mode bits are probed on DF0_FD and DF1_EN (TP20, TP21), not on the GPIO side.
- J6.10, J6.4/16 and the reset wire leave the board without a series resistor, as the A500's own drivers (spec §4.4).

## How the fixes were proven

RED: in a worktree at 329c6e9, only the new tests of the fixes (`tests/test_*.py`; the evaluator and generator
unchanged). Six fail, each for the stated reason:

| Test | Failure at 329c6e9 |
|---|---|
| `test_bus.py::test_buffers_on_3v3` | `'C6049' == 'C176925'` |
| `test_swap.py::test_partial_mode4_fit_keeps_the_real_drive_off` | `REAL_SEL` is None (floating) |
| `test_swap.py::test_mode4_parts_prepared_not_fitted` | LCSC of U21 and U23 is None |
| `test_bom.py::test_test_pads` | the pad on `DF0_STATE` where `DF0_FD` is expected |
| `test_logic_model.py::test_floating_gate_input_gives_no_level` | the output reads 1, not None |
| `test_sch_gen.py::test_duplicate_ref_is_an_error` | DID NOT RAISE ValueError |

The tests that cover a gap pass at once at 329c6e9 (`test_mode4_latch_sequence`, `test_mode4_kit_values`,
`test_reset_wire_input`, `test_strap_pins_never_active`, `test_parts_left_out_of_the_bom`, the new asserts of
`test_drive_behind_its_own_efuse`). Their proof is the mutants below, each run on the fixed design in a worktree
(the design file and schematic are restored after each); the other tests of those files stay green on every mutant but
the one named.

| Mutant (design.py) | Fails |
|---|---|
| R84 (ID gate) = 1K | `test_mode4_kit_values` |
| R28 (KBRESET to RST_B) = 100K | `test_reset_wire_input` |
| R30 (MTRX pull-up) to GND | `test_mode4_kit_values` |
| U22 D = MTRX_B (motor polarity) | `test_mode4_latch_sequence` |
| U22 CLK = SEL0 | `test_mode4_latch_sequence` |
| U22 D = M4_MTR_N (the latch toggles) | `test_mode4_latch_sequence` |
| 100 Ω from /SEL1 to J6.12 | `test_strap_pins_never_active` |
| 100 Ω from /MTR0 to J6.14 | `test_strap_pins_never_active` |
| R85 (100 kΩ on M4_SEL_Q) taken out again | `test_partial_mode4_fit_keeps_the_real_drive_off` |
| R_ILM = 1K5 | `test_drive_behind_its_own_efuse` |
| C13 (U9's 1 µF) dropped | `test_drive_behind_its_own_efuse` |
| a 23rd test pad | `test_test_pads` (and the two BOM-set tests, which name TP1–TP22) |
| test pads 1.5 mm | `test_test_pads` |
| U17 with `in_bom=False` | `test_parts_left_out_of_the_bom` |

GREEN, with every fix in the tree:
- The whole suite: 334 passed, 48 skipped (325 at 329c6e9 plus the 9 new tests, the last one from fix round 1; the 48
  skips are the illegal bypass states, as before).
- ERC (Task 8 Step 7): `--severity-error --exit-code-violations` exits 0 with 0 violations; at `--severity-all` 27
  violations, all `footprint_filter` (as at 329c6e9). `FluxDrive_Schematic.pdf` is exported again (block G on the
  sheet, R85 on its last row, labels readable); the netlist is exported (206 components).
- `build/revb/mutate.py` (the steering and mode tests against its six design mutants): the design passes (219 passed,
  48 skipped, one more than before for `test_partial_mode4_fit_keeps_the_real_drive_off`), and all six mutants are
  still caught, with the failure counts of Task 8's record (the same counts after fix round 1's evaluator change):

| Mutant | Failed |
|---|---|
| U13 inputs swapped | 210 |
| U16 S = SEL0 | 146 |
| U11 9/10 = SEL0 | 146 |
| U22 CLR = +3V3 | 8 |
| U19 input on CHNG_REQ | 144 |
| U8-B clock on MODE_CLK_REQ | 1 |

## What the reviews could not verify

- C20920's body length and its width against the J1–J6 band (spec §11).
- The flux, write and bus behaviour of a drive without power or with a tripping U9 (a firmware bench case, spec §8).
- The R1 terminations and R9 current of Dimitri's drive (before the layout freezes).
- The sequential behaviour of mode 4's latch on the real motherboard (R5, logic analyser).
