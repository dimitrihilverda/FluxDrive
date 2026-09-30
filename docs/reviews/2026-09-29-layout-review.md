# Review of the v1 layout (commit 0e820ad)

Four specialist reviews of `FluxDrive.kicad_pcb` as it stood after plan task 10 (2 layers, 60 × 48 mm, the module's
antenna 6 mm past the north edge), its build scripts and its tests, done by separate agents on 2026-09-29. None of
them changed a file. This document lists every finding, what was decided and where it went.

| Review | Findings | Blockers |
|---|---|---|
| Amiga floppy bus (LBUS) | 8: 3 major, 4 minor, 1 nit | — |
| Power and EMC (LPWR) | 14: 4 major, 6 minor, 4 nits | — |
| ESP32-S3 and USB (LESP) | 11: 1 major, 4 minor, 6 nits | — |
| Manufacturing at JLC (LPCB) and build scripts (LCODE) | 22: 5 major, 11 minor, 6 nits | — |

Two decisions went to Dimitri, both on 2026-09-29:

1. **4 layers instead of 2.** The bus and power reviews measured the same thing independently: on 2 layers the
   router cut the bottom ground plane into 48 pieces under the buffers and the resistor rows (27 % GND coverage in
   the signal area), and the decoupling capacitors reached their IC's ground pin only over 20–70 mm of copper. The
   board now has In1.Cu as a solid GND plane and In2.Cu as a solid +3V3 plane; F.Cu and B.Cu carry the signals and
   GND pours stitched to In1. Cost: about €1 per board more at 5–10 boards (spec §10).
2. **The antenna on the board.** JLC's economic assembly wants every part inside the outline (LPCB-1). The board
   grows 6.5 mm to the north; the module lies with its antenna end 0.5 mm inside the north edge, over board material
   that is copper-free on all four layers (the module footprint's own keep-out). The envelope in the A500 does not
   change: the fit test (below) was done with the antenna drawn past the old edge.

Fit test (Dimitri, 2026-09-29, paper template on an A500): CN11's pin 1 is on the right when looking from the front;
the template's pin 1 sits over it with the board running towards the front, over the 8520 and Gary. The board's east
edge ends at the motherboard's CN12, its west edge next to an electrolytic capacitor: 60 mm is the width there is.
The Berg header J2 and its plug stay inside the outline. A "A500 FRONT" mark now sits on both sides of the antenna
edge. Answered on 2026-09-30: the room under the shield is enough, and the drive's power cable reaches J2 from CN12.

## The rebuilt board

`tools/pcb_build.sh` built the board from the committed scripts (build 12, 2026-09-30) and installed it:

- 4 layers, 60 × 54.5 mm. DRC with zone refill and schematic parity: **0 errors, 0 unconnected, 0 parity issues**;
  `pcb_place.py --check`: the board is the placement table. Warnings: 12 `lib_footprint_mismatch` (the 12 unfitted
  parts, whose paste `pcb_sync.py` takes off, LPCB-10); 12 `silk_overlap`, 3 `silk_over_copper`, 3
  `silk_edge_clearance` (library outlines: SW1 and SW2 touch, D2 and D4 against J3 and R46, J4's reference on its
  outline, J3's outline past the edge; JLC clips silk on pads and off the board); 2 `footprint_filters_mismatch`
  (the 74HC14 symbol's filters, known from ERC).
- Tracks: F.Cu 996 mm, B.Cu 955 mm; 192 vias, 58 of them GND (32 stitching) and 14 +3V3.
- `/DKRD_D` 6.4 mm, no via: `pcb_prefan.py` routes it by hand through the gap in row B (the fan-out had chained
  row B's +3V3 pads across that gap, and the router took it 20 mm round the row with two vias).
- USB: each pair of receptacle pads joined on F.Cu without a via (`pcb_prefan.py`; build 9 left D− open); D+
  9.4 mm, D− 11.3 mm to the ESD part, D− with one layer change round U7.
- **The `_B` nets (the 11 bus inputs): 420 mm, 34 vias, against 398 mm and 39 vias before (LBUS-3).** The gate
  order no longer crosses them at the buffers, and eight of them run close to their pad-to-pad distance (STEP_B
  35 mm against 23), but three take long ways round: SIDE_B 111 mm (on B.Cu under the module), PIN14_B 71 mm and
  DKWD_B 67 mm with 7 vias. The channel between rows A and B is full: the +5V_A rail and INDEX_D (U4 in the
  east serves J1 pins 2 and 8 in the west: INDEX_D 43 mm, CHNG_D 81 mm) run along it on B.Cu, and SIDE (pin 32)
  has to cross U4's three outputs to reach U2. With the rest in place neither Freerouting `--continue` nor the
  maze router found a shorter path for them. Every one of them runs over a plane and switches at most at the
  MFM rate with the Amiga's open-collector edges, so the detours are kept for rev A; the cure for rev B is a
  placement change (INDEX and CHNG from a buffer at the west end, the unfitted 220 pF pads beside their
  pull-ups). Bring-up looks at DKWD with a scope.
- Tests: 71 passed, among them `test_usb_data_pads_joined_on_top` (new) and `test_dkrd_short_and_on_one_layer`,
  both red on the builds before their pre-route.

## Final review (2026-09-30)

A fresh reviewer checked tasks 8–12 against the board itself (DRC, pcbnew, regenerated gerbers, renders): no
critical or important finding; "order it". It reproduced every number above, found the gerbers identical to a fresh
export, BOM and CPL consistent with the board, the JLC rules met (narrowest track 0.2 mm, vias 0.3/0.6 mm tented,
closest hole-to-hole 0.544 mm, copper to edge ≥ 0.3 mm) and the README's test-pad table, pin-1 and cathode
directions right. Its judgements:

- The hand routes are sound; USB D+ in front of the receptacle runs under its plastic, not under the metal shell.
- The three long `_B` routes cost nothing on rev A: PIN14 is static (not connected on the A500, held high), DKWD is
  unused in v1 (/WPROT is always asserted), and SIDE_B's worst neighbour (SEL0, 23.7 mm side by side) couples an
  estimated 0.15–0.5 V against more than 1 V of margin.
- The antenna area is free of copper on all four layers; SIDE_B passes 2.1 mm and SEL0 1.7 mm south of its base
  line, on B.Cu behind In1 and In2.

Taken in: LBUS-2 and LBUS-6 above (the +3V3 vias and `/CHNG_D` along the J1 GND row), LPCB-12, spec §8's
grounding text, and three README lines (the `/CHNG_D` check after soldering J1, J3's shell legs, the keep-out
outline on the fit template). Left for rev B or later, with the rest of the minor points in the ledger: the sparse
ground vias along the east side of the antenna keep-out (spec §6 asks for dense ones), the +3V3 vias, the
`/CHNG_D` route.

## Findings and decisions

"Accepted" means the design, the scripts or the spec now do what the finding asks. A test named in the Decision
column failed before the fix and passes on the rebuilt board.

### Amiga floppy bus

| ID | Sev. | Finding | Decision |
|---|---|---|---|
| LBUS-1 | major | No ground plane under the buffers and resistor rows: B.Cu GND 15–20 % under U2–U4, 30 % between the rows; 43 of 48 B.Cu pieces floating. | 4 layers (Dimitri): In1 is the plane. `test_four_copper_layers_with_planes`. |
| LBUS-2 | major | Buffer decoupling and ground returns over 60–70 mm; U3's and U4's ground vias on islands. | Every GND pad of U2–U4 and their 100 nF has its own via to In1 within 1.6 mm. `test_decoupling_reaches_the_planes`. The +3V3 side does not meet that everywhere (final review): U2/U4 pin 14 reach In2 over 3.7 mm through their capacitor's via, U3 pin 14 over 8.6 mm through L1's output pad and C17, the 17 row B pull-ups share 4 vias, and the buck output enters In2 through one via. Small at these loads and edges; rev B gives each pin 14 and C17/L1 their own vias. |
| LBUS-3 | major | The input gate assignment made the `_B` nets cross (398 mm, 39 vias for 11 nets). | Accepted: U3 takes J1 pins 4–16, U2 pins 18–32, each over its gates in connector order; row B follows the buffer inputs; the spare gate moved to U2. `test_buffers_follow_the_connector`, `test_gate_pairs`. Measured on the rebuilt board: 420 mm, 34 vias, three detours (see above). |
| LBUS-4 | minor | `/DKRD` 16.7 mm with 2 vias, no plane under its B.Cu part. | Accepted: U4's connector-facing gates take /WPROT, /DKRD and /RDY in connector order, so /DKRD runs straight down, routed by hand (6.4 mm). `test_dkrd_short_and_on_one_layer` (≤ 10 mm, no via). The six U4 pull-ups stay in row B: with In1 under every route their wrap-around costs nothing. |
| LBUS-5 | minor | `/INDEX_D` 88 mm (under the module and the buck inductor), `/CHNG_D` 81 mm into the J1 pin field. | With In1 both have a reference plane their whole length; the "module underside" and "buck" rule areas keep them from under U1's body and L1, the "J1 rows" rule area out of the pin field. No hand route. |
| LBUS-6 | minor | F.Cu tracks between the J1 rows and between its GND pins (+5V_A, /SEL0_B, /TRK0_D, /CHNG_D), 0.22 mm from where the plug-on socket is soldered. | Accepted: "J1 rows" track keep-out on F.Cu and B.Cu from the even row's pads to past the odd row, with notches on F.Cu only for the five test-pad stubs. `test_rule_areas`. Left (final review): `/CHNG_D` runs along the outside of the GND pin row, 0.25–0.30 mm from the pads (B.Cu x 121.9–156, F.Cu past pins 1–7); the README asks for a continuity check after soldering J1, rev B keeps 0.8 mm. |
| LBUS-7 | minor | In the plug-on variant J1's orientation fixes which way the board lies. | Fit test done: the board lies towards the A500's front; "A500 FRONT" on both sides. |
| LBUS-8 | nit | A box header longer than 52 mm would overhang the east edge. | The IDC footprint's body is 50.84 mm (DIN 41651); the part's drawing (C601943) is to be checked when ordering (README). |

### Power and EMC

| ID | Sev. | Finding | Decision |
|---|---|---|---|
| LPWR-1 | major | The B.Cu "plane" was a ring with a hole in the middle. | 4 layers (Dimitri). |
| LPWR-2 | major | The logic-IC decoupling capacitors did not decouple (20–70 mm GND path). | As LBUS-2. |
| LPWR-3 | major | INDEX_D, DKWD_B and USB D+ under and next to the switch node and L1. | Accepted: "buck B" (no B.Cu track under U6 and L1) and "buck F" (none between L1's pads, a strip north of the switch node) rule areas; C21/C22 moved (LESP-4). `test_rule_areas`. |
| LPWR-4 | major | Buck input loop: C13 returned through 2 vias, C14's loop about 3× TI's layout. | Accepted: C14 (100 nF) turned 270° 1.8 mm from VIN with its GND pad in line with U6's GND pin under the body (TI Fig. 20); C13 (10 µF) next to it; both GND pads with their own via to In1. |
| LPWR-5 | minor | C17's return to U6 GND over 16 mm with 2 vias. | Accepted: C17 turned 180° (+ under L1 pin 2, − towards U6), GND via to In1. |
| LPWR-6 | minor | The eFuse input capacitor C8 reached IN over 15 mm. | Accepted: C8 right under pins 3/4, its GND pad at the exposed pad. |
| LPWR-7 | minor | TVS D4 on a stub with a 13.6 mm return. | Accepted: D4 turned 180° (cathode on the J2–eFuse path, anode to the GND pour), GND via to In1. |
| LPWR-8 | minor | USB return paths: pair routed apart, VBUS bridge slot. | In1 under the whole pair; the VBUS bridge on B.Cu no longer cuts a plane. |
| LPWR-9 | minor | The FB node reached within 1.07 mm of SW through the unfitted C16. | Accepted: C16 moved west of R50/R51, away from L1. |
| LPWR-10 | minor | Stitching gaps of 9–12.5 mm on the edges. | The outer pours are stitched to In1; with a solid In1 the gaps matter far less. |
| LPWR-11 | nit | The eFuse exposed pad has no vias. | Accepted as is: at most 48 mW at the 0.95 A limit; the pad connects to pin 8 and the F.Cu pour, which is stitched to In1. |
| LPWR-12 | nit | EN/UVLO trace 7.4 mm with 2 vias. | R46/R47 placed beside EN. |
| LPWR-13 | nit | VBUS track and via under the USB-C body. | Accepted: "USB-C body" rule area (no F.Cu track or via under the shell between its pads). |
| LPWR-14 | nit | +3V3 feed 22.8 mm with 2 vias; 0.3 mm everywhere. | +3V3 is the In2 plane. The 0.3 mm Power class stays (ruling in the ledger). |

### ESP32-S3 and USB

| ID | Sev. | Finding | Decision |
|---|---|---|---|
| LESP-1 | major | The EN (reset) net ran 29 mm along the antenna's base line; C20 20.8 mm of track from pin 3. | Accepted: C20 2.6 mm from pin 3; "antenna edge" track keep-out along the antenna's base line (vias allowed); the antenna itself is copper-free on all layers. |
| LESP-2 | minor | The module is centred on the north edge; Espressif prefers the feed-point corner. | Kept for rev A: the range test (O5) decides, with the WROOM-1U as fallback; moving the module to a corner would redo the whole placement. |
| LESP-3 | minor | USB D+/D− not routed as a pair, about 190–260 Ω differential against spec §8's 90 Ω. | Spec §8 changed: USB is full speed only, the impedance is not controlled; the pair runs over In1. The receptacle's pad joins are routed by hand. `test_usb_data_pads_joined_on_top`. |
| LESP-4 | minor | The unfitted C21/C22 sat on the wrong side of R59/R60, with long stubs under L1. | Accepted: R59/R60 next to U7, C21/C22 against their module-side pads. |
| LESP-5 | minor | 215 mm of signal track and 20 vias under the module. | Accepted: "module underside" F.Cu track keep-out (a 1.3 mm band inside each pad row stays for pad entry; vias allowed). |
| LESP-6 | nit | No stitching vias along the north edge under the module. | The north edge now carries the antenna and no copper; In1 ends at the antenna's base. |
| LESP-7 | nit | J4 and the UART lines 7.8 mm from the antenna feed. | Kept: J4 is holes only, used for recovery. |
| LESP-8 | nit | The ground-pad thermal vias can wick solder. | Accepted as is (the footprint's windowpane paste); their pads are now 0.7 mm (LPCB-9). |
| LESP-9 | nit | The 6 mm overhang needed room in a panel. | Gone with the antenna on the board. |
| LESP-10 | nit | The spare-header lines float when unused. | Firmware: internal pull-ups on GPIO13/14/47/48 until they are used (spec §9). |
| LESP-11 | nit | Tracks at 0.2 mm next to the PSRAM and strapping pads. | Visual check after assembly (README). |

### Manufacturing at JLC

| ID | Sev. | Finding | Decision |
|---|---|---|---|
| LPCB-1 | major | The module overhang (O10) and the flush USB-C were open; JLC's economic assembly wants parts inside the outline. | The antenna on the board (Dimitri); O10 closed. The USB-C shell keeps its 0.18 mm past the edge (a receptacle has to reach the edge for the plug; the Nano-Tek has the same placement); to be confirmed in JLC's preview. |
| LPCB-2 | major | Open via holes in SMD pads (U3 pin 13, module pads). | Accepted: see LCODE-4. `test_no_via_in_an_smd_pad`. |
| LPCB-3 | minor | A 2-up panel needs a framed panel. | Not needed: the board is ordered single (economic assembly takes 2–50 pieces); spec §8. |
| LPCB-4 | minor | 28 texts at 0.8–0.9 mm. | Accepted: every silkscreen text 1.0 mm, `min_text_height` 1.0. `test_silkscreen_text_height`. The library footprints keep their 0.12 mm silk lines. |
| LPCB-5 | minor | Silk over pads and off the board unchecked. | Accepted: silk clearance 0.15 mm, silk-over-copper and silk-to-edge checked (warnings); J3/J4 references placed or hidden. |
| LPCB-6 | minor | Test pads unlabelled; SPCB-8 undecided. | 1.0 mm probe pads kept (no pogo fixture in v1); a map of all sixteen in the README. |
| LPCB-7 | minor | The fit template had one scale bar, no note, no heights. | Accepted: bars across and down, "print at 100 %" on the sheet, a STEP model for a printed dummy; `pcb_build.sh` makes both again. |
| LPCB-8 | nit | FID1/FID3 closer than 3.85 mm to the edge. | Only a panel needs that; the board is ordered single. |
| LPCB-9 | nit | The module's thermal vias had a 0.15 mm ring. | Accepted: 0.7 mm pads, 0.2 mm ring. |
| LPCB-10 | nit | Paste on the unfitted parts' pads. | Accepted: `pcb_sync.py` takes the paste off unfitted parts. |
| LPCB-11 | nit | Bottom texts over tented vias print bumpy. | Accepted as is. |
| LPCB-12 | nit | J3's peg-to-slot hole gap 0.34 mm, below JLC's 0.45 mm. | Kept: the Nano-Tek's footprint. The final review measured 0.805 mm from the drill file's slot geometry, so no remark is expected. |

### Build scripts

| ID | Sev. | Finding | Decision |
|---|---|---|---|
| LCODE-1 | major | The committed board was not what the committed scripts produce (two values changed during a build). | The board is rebuilt from the committed scripts; `pcb_build.sh` ends with `pcb_place.py --check` and installs the board itself. |
| LCODE-2 | major | The fan-out was non-deterministic (random footprint IDs set the file order). | Accepted: fixed footprint IDs in `pcb_sync.py`, pads in reference order in `pcb_fanout.py`; two runs gave identical vias. |
| LCODE-3 | minor | The six parallel Freerouting runs were identical. | Accepted: each run gets its own settings (via cost, rip-up cost, preferred directions). |
| LCODE-4 | major | The fan-out put vias into their own pads. | Accepted: the search starts outside the pad, every pad of the net is an obstacle with a mask web, rule areas are respected, a pad with its own plated holes gets nothing. |
| LCODE-5 | minor | Stitching vias could touch GND through-hole pads. | Accepted: every pad is an obstacle, with its own clearance where it asks for more (the fiducials). |
| LCODE-6 | minor | Freerouting routed GND after all. | On 4 layers GND and +3V3 are planes in the DSN (the Nano-Tek method). |
| LCODE-7 | minor | Hard-coded outline; silk labels at table coordinates. | Accepted: fan-out and stitching read Edge.Cuts; pin labels follow their pads. |
| LCODE-8 | minor | Widths hard-coded; hole-to-hole on the rule. | The fat-via trick is back (0.58 mm between holes); the maze router's widths stay hard-coded (deferred minor). |
| LCODE-9 | minor | The board tests would catch none of the above. | Accepted: tests for the planes, decoupling vias, via in pad, rule areas, antenna, silk height, pin-1 mark near pin 1, /DKRD. The connector-zone test on courtyards is deferred. |
| LCODE-10 | nit | Build-script loose ends. | The build installs the board, makes the fit template and checks the placement; the rest deferred. |

## What the reviews could not verify

- The radio range with the antenna over board material inside the closed A500 (O5).
- The ground-bounce and coupling figures (estimates), and the buck's VIN ringing: bring-up measurements.
- JLC's own design check on the USB-C at the edge and on the module's thermal vias.
- The C601943 box-header length and the TE 171825-4 body outline (O15).
