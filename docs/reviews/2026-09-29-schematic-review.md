# Review of the v1 schematic (commit f2901b3)

Four specialist reviews of the generated schematic (`FluxDrive.kicad_sch`, from `hardware/design.py`), its netlist
and its tests, done by separate agents on 2026-09-29. None of them changed a file. This document lists every
finding, what was decided and where it went. The spec went to v0.3 for this review only.

| Review | Findings | Blockers |
|---|---|---|
| Amiga floppy bus (SBUS) | 4: 2 minor, 2 nits | — |
| Power and EMC (SPWR) | 5: 1 major, 3 minor, 1 nit | — |
| ESP32-S3 hardware (SESP) | 3: 1 minor, 2 nits | — |
| PCB and manufacturing at JLC (SPCB) and the generator and tests (SCODE) | 15: 1 major, 7 minor, 7 nits | — |

Reference designators below are those of the fixed schematic; the reviews quoted the numbers of f2901b3, which
shifted when parts were added.

## Sources the reviews used

- **[TPS]** TI TPS2595x datasheet SLVSE57C (eFuse: pinout, clamp, current limit, dVdt, equation 18 and the TVS note).
- **[TLV]** TI TLV62569 datasheet SLVSDG1C (absolute maximum, input capacitor, feed-forward, table 4).
- **[NXP]** Nexperia 74LVC14A datasheet (VT+ max 2.0 V and VT− min 0.8 V at VCC 3.0–3.6 V).
- **[D]**, **[W]**, **[HDG]** ESP32-S3 datasheet v2.2 (table 2-2), WROOM-1 datasheet, hardware design guidelines, as
  in the spec review.
- **[JLC]** jlcsearch mirror of JLC's parts database: stock, basic/extended, descriptions.
- The netlist (`build/FluxDrive.net`), a pin-by-pin cross-check of netlist against design file (0 mismatches), and
  ERC at every severity (0 errors, 14 `footprint_filter` warnings).

## Where the reviews disagreed

| Topic | Positions | Decision |
|---|---|---|
| AMIGA_PWR on USB alone | SPWR-4: no hardware change, the firmware reads GPIO1 with the ADC. SESP-1: make the divider ten times stiffer. | Both. The divider is 1 kΩ / 1.5 kΩ, so the pin reads low in hardware (about 0.29 V), and spec §9 names the ADC reading as the firmware's second guard against the Schottky's leakage when hot. |
| Which TE part is vertical | SPCB-1 recalled 171825-x as the right-angle one. | The JLC listing of 171826-4 says right angle, the copied footprint's own description says "Horizontal" and its outline runs 11 mm to one side of the pins. 171825-4 (C210162, 5,365 in stock) is the vertical one. |

## Findings and decisions

"Accepted" means the design or spec now does what the finding asks. A test named in the Decision column failed
before the fix and passes after it; a test marked "coverage" pins behaviour that was already right, and was checked
by breaking the design on purpose (it failed).

### Amiga floppy bus

| ID | Sev. | Finding | Decision | Where |
|---|---|---|---|---|
| SBUS-1 | minor | With the firmware halted or unflashed, the 10 kΩ pull-ups release all six outputs: `/CHNG` high reads as a disk in, so DF0 looks like a drive holding an unreadable disk, not an empty one. | Accepted as a spec correction. No pull-down on `CHNG_N`: it would assert `/CHNG` while deselected and break "release = input". Bring-up checks that the Amiga still reaches the insert-disk screen or boots its next device. | spec 11 |
| SBUS-2 | minor | The tests did not check gate pairing, output direction or the spare gate input. | Accepted: `test_gate_pairs` (coverage) checks 1→2, 3→4, 5→6, 9→8, 11→10, 13→12 on U2/U3/U4 and U3 pin 13 on GND. | tests |
| SBUS-3 | nit | GPIO15/16 carry `/SIDE` and `/DKWE` and are also the 32 kHz crystal pins. | Accepted: spec §9 keeps the RTC slow clock internal. | spec 9 |
| SBUS-4 | nit | UART TX resistor 470 Ω in the design, 499 Ω in the spec. | Accepted: 470 Ω (basic part) in both. | spec 7 |

### Power and EMC

| ID | Sev. | Finding | Decision | Where |
|---|---|---|---|---|
| SPWR-1 | major | U7 (USBLC6) pin 5 on VBUS: from boot the ESP32's D+ pull-up lifts VBUS to about 2.7 V through the ESD diodes, plus D2's leakage. A USB-C host on a C-to-C cable then may never switch VBUS on, so the console fails while the Amiga powers the board. | Accepted: U7 pin 5 on +3V3, and R58 10 kΩ from VBUS to GND. `test_usb`. | design E, spec 5, 7 |
| SPWR-2 | minor | A USB hot-plug into the 10 µF through D2 can overshoot to 6–7.5 V, and D2 holds the peak; the TLV62569's absolute maximum is 6 V. | Accepted: unfitted damper R49 1 Ω + C15 4.7 µF on V5SYS (if fitted, C13 becomes 4.7 µF so the USB limit holds), and a bring-up hot-plug test with 1 m and 2 m cables. `test_protection_pads`. | design C, spec 5, 11 |
| SPWR-3 | minor | A reversed plug pushed on while the PSU runs can ring to 22–24 V on the eFuse input (20 V abs. max) and 7.7 V on EN/UVLO. | Accepted: unfitted D4 SMAJ13A (13 V standoff) on +5V_IN; spec says "fitted with the power off". `test_protection_pads`. | design C, spec 5 |
| SPWR-4 | minor | On USB alone +3V3 feeds +5V_A through the pull-ups: AMIGA_PWR at 1.25 V (undefined for the ESP32), bus inputs at 2.1–2.2 V (just above the LVC14A's VT+ max). | Accepted, see the disagreement above: AMIGA_PWR 0.29 V, bus inputs 0.51–0.74 V or 3.3 V. `test_usb_alone_leaves_everything_defined` solves the resistor network (it gave 1.24 V before the fix, as the review computed). | design C, spec 4.2, 5, 9 |
| SPWR-5 | nit | The 6.8 pF feed-forward value was for the datasheet's 200k/100k divider; ours needs about 13–15 pF. | Accepted: the unfitted pad C16 says 15 pF; the value is chosen at bring-up. `test_buck`. | design C, spec 5 |

### ESP32-S3 hardware

| ID | Sev. | Finding | Decision | Where |
|---|---|---|---|---|
| SESP-1 | minor | Same as SPWR-4: AMIGA_PWR is not reliably low on USB alone. | Accepted: R52 1 kΩ / R53 1.5 kΩ (C25867, basic), 3.0 V at 5 V, 3.5 V at the clamp, 2 mA. | design C, spec 5 |
| SESP-2 | nit | Same as SBUS-4. | Accepted. | spec 7 |
| SESP-3 | nit | Burning `EFUSE_DIS_USB_JTAG` without `EFUSE_DIS_PAD_JTAG` moves JTAG onto GPIO39–42 (bus outputs). | Accepted: rule added to spec §9. | spec 9 |

### PCB and manufacturing at JLC

| ID | Sev. | Finding | Decision | Where |
|---|---|---|---|---|
| SPCB-1 | minor | J2 171826-4 (C590635) has 16 in stock at LCSC and is right-angle; spec §8 wants a vertical header. | Accepted: TE 171825-4, vertical, C210162. New footprint `FluxDrive:171825-4` with the same pads (2.5 mm pitch, 1.2 mm drill, 1.8 mm pad); its outline is an estimate, open item O15. The right-angle footprint and its 3D model are removed. Spec §5 names a distributor for larger runs. | design C, library, spec 5, 10, 13 |
| SPCB-2 | minor | The 100 µF on +5V_A (C15008) is 6.3 V: the 5.7 V clamp is 90 % of its rating, and at 5 V it keeps only 20–30 µF. | Accepted: 2 × 47 µF 10 V X5R 1206 (C96123, CL31A476MPHNNNE, basic). `test_bulk_capacitors_rated_above_the_clamp`. | design C, spec 5, 10 |
| SPCB-3 | minor | The unfitted pads a builder might fill by hand were 0402. | Accepted: every unfitted R and C is 0603. `test_unfitted_pads_are_hand_solderable`. | design, spec 8 |
| SPCB-4 | nit | The eFuse is single-source with about 2,000 in stock, and its WSON cannot be reworked by hand. | Accepted: reserve stock at order time, spec §10. | spec 10 |
| SPCB-5 | nit | The library symbols' default footprints still pointed to `Nano-Tek:`. | Accepted: `FluxDrive:`. `test_project_symbols_load`. | library |
| SPCB-6 | nit | Same as SBUS-4. | Accepted. | spec 7 |
| SPCB-7 | nit | Every part was marked for the position file, also unfitted parts, holes and fiducials. | Accepted: `in_pos_files` = in BOM and fitted. `test_unplaced_parts_stay_out_of_the_position_file`. | generator |
| SPCB-8 | nit | The 14 `footprint_filter` warnings come from the 74HC14 symbol (its filter lists DIP only). The 1.0 mm test pads suit a probe, not a pogo-pin fixture. | Warnings noted and allowed by the ERC test. Test-pad size deferred to the layout (task 10), where the free space is known. | — |

### Generator and tests

| ID | Sev. | Finding | Decision | Where |
|---|---|---|---|---|
| SCODE-1 | major | The netlist tests read `build/FluxDrive.net` (git-ignored) and only checked that it existed: after a design edit without a re-export, about 40 tests passed on the old circuit. | Accepted: the session fixture generates the schematic, fails if it differs from the committed `FluxDrive.kicad_sch`, and exports a fresh netlist into a temporary directory. Checked: a design edit without a re-export now fails the netlist tests with "out of date". | tests/conftest.py |
| SCODE-2 | minor | ERC only ran on the tiny design, at error severity; stacked pins with different nets would merge two nets without an ERC error. | Accepted: `test_real_schematic_erc` (coverage) runs every severity on the real schematic and allows only `footprint_filter`; the generator raises on stacked pins with different nets (`test_stacked_pins_on_different_nets_are_an_error`). | tests, generator |
| SCODE-3 | minor | A pin named by number and by name silently took the last net. | Accepted: the generator raises. `test_pin_assigned_twice_is_an_error`. | generator |
| SCODE-4 | minor | Common pins of multi-unit symbols got duplicate IDs (not triggered by this design). | Accepted: the unit is part of the pin, label and no-connect IDs. `test_common_pins_of_multi_unit_symbols_get_unique_ids`, with a two-unit test symbol. | generator |
| SCODE-5 | minor | Nothing checked that the unfitted pads exist. | Accepted: `test_unfitted_pads_exist` (coverage) for the /MTR0 pull-ups and the 220 pF pads; `test_usb` for the 10 pF pads; `test_buck` for the feed-forward pad. | tests |
| SCODE-6 | nit | The tiny test design covers little (two rotations, no unfitted part, no pin by name, no `unconnected-` check; a hard-coded `parts[1]`). | Deferred: the real design, now tested fresh at every run, exercises all of these. | — |
| SCODE-7 | nit | `netlist.py` does not unescape `\\`; `p["_numbers"]` is unused; `lib_symbol` drops parent properties the child lacks; A0 paper is awkward to print. | Deferred: none changes the netlist of this design. | — |

## What the reviews could not verify

- The TE 171825-4 body outline and where the pin row sits in it (spec O15, before the layout is frozen).
- The USB hot-plug overshoot on V5SYS with real cables (bring-up, spec §11).
- The Schottky's reverse leakage into +5V_A when hot, which lifts AMIGA_PWR above 0.29 V (the firmware's ADC reading
  covers it, spec §9).
- How each Kickstart version treats a DF0 whose outputs are all released (bring-up, spec §11, O13).
- The schematic PDF (the reviewers had no PDF renderer; the netlist was reviewed instead).
