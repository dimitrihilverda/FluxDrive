# FluxDrive v1 — hardware design

**Status:** v0.4, 2026-09-29. Dimitri approved v0.2; v0.3 took in the schematic review, v0.4 the layout review and Dimitri's two decisions on it (4 layers; the antenna on the board).
**Authors:** Dimitri Hilverda (GTi co-author), with Claude
**Based on:** `docs/input/OMEGAWARE_FluxDrive_HW_Design_v0.1.md` (MES), `docs/input/FluxDrive_v0.1_review_notes.md`
(breadboard measurements), and the A500 bus research done for the Nano-Tek Rev 2.0 GTi.
**Review:** `docs/reviews/2026-09-29-spec-review.md` lists every finding (BUS-, PWR-, SI-, ESP-, PCB-numbers below)
and what was done with it; `docs/reviews/2026-09-29-schematic-review.md` does the same for the schematic (SBUS-,
SPWR-, SESP-, SPCB-, SCODE-numbers), `docs/reviews/2026-09-29-layout-review.md` for the layout (LBUS-, LPWR-,
LESP-, LPCB-, LCODE-numbers).

FluxDrive is an Amiga floppy drive emulator built around one ESP32-S3 and nothing else: no Gotek, no second
microcontroller. It plugs into the A500's internal floppy connector, holds a disk image in PSRAM and generates the
MFM flux stream itself. Disk images come from the GTi touchscreen over ESP-NOW, or from a phone over WiFi.

The goal is the cheapest emulator that still has everything the GTi offers. Target: under €10 in parts per board at
50 pieces, SMD assembled by JLCPCB, through-hole parts soldered by hand.

---

## 1. Scope of v1

| | v1 | Later |
|---|---|---|
| Host | A500 internal DF0 | A1200, A2000, external DF1 |
| Density | DD, 11 sectors per track | HD, IBM formats |
| Writes | `/WPROT` always asserted. `/DKWD` and `/DKWE` are wired to GPIO, so writing is firmware only. | Write capture and write-back |
| Images | one ADF resident | several disks, disk sets |
| Image source | GTi over ESP-NOW; WiFi upload page for use without a GTi | microSD (footprint is not on v1) |
| Radio while the motor runs | off | — |

Not in v1: pass-through to a real drive, the drive-swap switch of the Nano-Tek, an OLED or buttons for picking
disks. The GTi is the user interface.

## 2. Facts this design leans on

### 2.1 The A500 internal floppy connector

From the A500 schematic Rev 6a/7 (amigawiki `A500_R6.pdf`; sheet numbers from the title blocks), the Hardware
Reference Manual (HRM) appendix E, the Gary specification and the 8520 specification. Checked in review (BUS).

- Connector CN11, even pins: 2 `/CHNG`, 4 `/MTR0`, 6 NC, 8 `/INDEX`, 10 `/SEL0`, 12 `/SEL1`, 14 NC, 16 `/MTR0`,
  18 `/DIR`, 20 `/STEP`, 22 `/DKWD` (write data), 24 `/DKWE` (write gate), 26 `/TRK0`, 28 `/WPROT`,
  30 `/DKRD` (read data), 32 `/SIDE`, 34 `/RDY`. Odd pins are ground, except pin 3 (NC). Pins 4 and 16 are one
  net.
- **Pin 2 is `/CHNG` and pin 34 is `/RDY`.** A PC drive has disk change on pin 34. Getting this wrong cost the
  breadboard build weeks.
- **Motor.** `/MTR0` is latched for DF0 by Gary (MTRON, U5 pin 46, through U36 74LS38, sheet 4; Gary spec §2.1:
  "latched disk 0 motor on", following `/SEL0` within 50 ns). It is a plain level. The breadboard's "stream dies
  on deselect" came from the 74HCT125 run at 3.3 V (§2.2). Only the external port gets the raw motor line.
- **Who drives what.**
  - `/STEP`, `/DIR`, `/SIDE`, `/SEL0–3` come straight from CIA-B (8520 port B): internal pull-ups of 3.1–5 kΩ,
    sinks at least 13 mA at 0.4 V.
  - `/MTR0`, `/DKWD`, `/DKWE` go through a 74LS38 (open collector, 24 mA). On the A500+ it is a 74LS05 (8 mA
    maximum, 0.5 V at 8 mA).
  - `/MTR0` has R506 10 kΩ to VCC on the motherboard, plus the base of the drive-LED transistor Q503 (sheet 6).
    `/DKWD` and `/DKWE` have **no** pull-up on the motherboard.
  - Back to the Amiga: `/DKRD` has 1 kΩ (R305, sheet 4), `/INDEX` 10 kΩ (RP501, sheet 6) and goes to CIA-B /FLAG.
    `/RDY`, `/TRK0`, `/WPROT` and `/CHNG` only have CIA-A's internal pull-ups.
  - `/STEP`, `/DIR`, `/SIDE`, `/SEL1`, `/DKWD` and `/DKWE` are shared with the external DB23 port, which puts 100 pF
    filters on them (sheet 7), even with nothing plugged in.
- **Drive termination.** HRM appendix E: "Each device must provide a 1000-Ohm pull-up resistor on those outputs
  driven by an open-collector device."
- **Power** is on a separate 4-pin connector CN12: 1 = +5 V, 2 = GND, 3 = GND, 4 = +12 V (sheet 8), no fuse. The
  34-pin connector carries none. A mini-Berg forced on the wrong way round puts **+12 V on the 5 V pin**.
- **Drive ID and disk state** (HRM appendix E). With the motor on, `/RDY` means "disk in and up to speed". With the
  motor off, `/RDY` carries the drive ID, which restarts on every motor on→off transition; a DD drive's ID is all
  ones (active low), so it simply holds `/RDY` low while selected with the motor off. The change flop is "set at
  power up or when no disk is installed" and reset by a step while selected, only with a disk in. `/TRK0` reports the
  head position with or without a disk. Kickstart does not probe DF0 at boot, but FlashFloppy's HD support reads its
  ID, so v1 answers the ID on DF0 as well.

### 2.2 What the breadboard build measured

ESP32-S3 at 240 MHz, buffers in PSRAM, Arduino core 3.3.7 (details in `docs/input/FluxDrive_v0.1_review_notes.md`):

- MFM-encoding one DD track: about 3.5 ms. Converting it naively to RMT symbols: another 12–17 ms.
- The Arduino RMT layer has no stop and no TX-done callback, and mixing it with the IDF RMT driver silently
  produces no output. Firmware for this board is therefore pure ESP-IDF.
- 74HCT125 powered at 3.3 V on the input side is out of spec and caused the "weak select line" symptoms.
  This design uses 74LVC throughout.

### 2.3 The ESP32-S3 at power-up

ESP32-S3 datasheet v2.2, table 2-2: GPIO1–14, GPIO15/16 (XTAL_32K) and GPIO17 are driven **low** for about 60 µs
during chip power-up, GPIO18 low and then high, GPIO19/20 high. A driven pin overrides any pull-up. The WROOM-1
datasheet says EN low powers the chip off, so a RESET press or a brown-out very likely repeats the glitch while the
Amiga runs. GPIO21 and GPIO38–48 start as inputs without a glitch. Every output that can disturb the bus is
therefore on GPIO21 or 38–42 (ESP-1).

## 3. Block diagram

```
 A500 CN11 (34-pin) ─┬─ pull-ups to +5V_A
                     └─100 Ω──► 2× 74LVC14A (Schmitt, 3.3 V) ──────────► ESP32-S3-WROOM-1-N16R8
                     ◄──33 Ω─── 74LVC07A (open drain, 3.3 V) ◄────────────  (outputs on GPIO21, 38–42)

 A500 CN12 ──► eFuse (5.7 V clamp) ──► +5V_A ──Schottky──┐
 USB-C VBUS ──► USBLC6 ────────────────────────Schottky──┴─► V5SYS ──► buck TLV62569 ──► 3V3
 +5V_A ──► divider ──► AMIGA_PWR (GPIO1)
                  BOOT, RESET, activity LED, 6-pin UART/recovery header, spare GPIO header, test pads
```

## 4. Bus interface

### 4.1 Pin by pin

| Pin | Signal | Direction (from FluxDrive) | Buffer | ESP32-S3 GPIO | On the board |
|---|---|---|---|---|---|
| 2 | `/CHNG` | out | LVC07A | 42 | 33 Ω series |
| 4 | `/MTR0` (alt.) | in | LVC14A | 4 | no pull-up (unfitted pad) |
| 6 | NC on A500 | in | LVC14A | 8 | 10 kΩ to +3.3 V |
| 8 | `/INDEX` | out | LVC07A | 39 | 33 Ω series |
| 10 | `/SEL0` | in | LVC14A | 17 | 1 kΩ to +5V_A |
| 12 | `/SEL1` | in | LVC14A | 9 | 10 kΩ to +5V_A |
| 14 | NC on A500 | in | LVC14A | 10 | 10 kΩ to +3.3 V |
| 16 | `/MTR0` | in | LVC14A | 11 | no pull-up (unfitted pad; R506 on the motherboard) |
| 18 | `/DIR` | in | LVC14A | 7 | 1 kΩ to +5V_A |
| 20 | `/STEP` | in | LVC14A | 6 | 1 kΩ to +5V_A |
| 22 | `/DKWD` | in | LVC14A | 5 | 4.7 kΩ to +5V_A |
| 24 | `/DKWE` | in | LVC14A | 16 | 4.7 kΩ to +5V_A |
| 26 | `/TRK0` | out | LVC07A | 40 | 33 Ω series |
| 28 | `/WPROT` | out | LVC07A | 41 | 33 Ω series |
| 30 | `/DKRD` | out | LVC07A | 38 | 33 Ω series |
| 32 | `/SIDE` | in | LVC14A | 15 | 1 kΩ to +5V_A |
| 34 | `/RDY` | out | LVC07A | 21 | 33 Ω series |

Eleven inputs on twelve inverters (one spare, input tied to ground). Six outputs on the six LVC07A buffers.

- The inputs sit on GPIOs that glitch low at power-up. That is harmless: the LVC14A output is low whenever its bus
  line is idle, so the glitch only overlaps an asserted line for 60 µs. GPIO18, which also glitches high, is not
  used (ESP-2).
- On the WROOM-1 the outputs are on the right edge and the bottom-right corner; the LVC07A goes there, the LVC14As
  on the left. `/DKRD` (pin 30) gets the shortest track.

### 4.2 Inputs

- **74LVC14A** hex Schmitt inverter at 3.3 V, SOIC-14. Its inputs tolerate 5.5 V while powered at 3.3 V, and its
  hysteresis (at least 0.3 V) is what rejects ringing on the ribbon. It inverts, so the ESP sees active-high
  signals.
- **Topology per line, in this order:** connector pin → pull-up node → 100 Ω → LVC14A input, with 100 kΩ from the
  LVC14A input to +3.3 V. The pull-up must be on the connector side: on the buffer side, 4 mA through the 100 Ω
  would lift a low to 0.92 V, above the LVC14A's minimum VT− of 0.8 V (BUS-3). The 100 Ω limits current for ESD
  and when the board is unpowered. On the bench (USB only, no Amiga, no ribbon) +3V3 leaks through the 100 kΩ
  and the pull-ups into +5V_A, which the AMIGA_PWR divider (§5) holds at about 0.5 V. Every input then sits at a
  defined level: 0.5–0.75 V on the lines pulled up to +5V_A (they read as asserted), 3.3 V on the others. The
  firmware ignores them while AMIGA_PWR is low (SPWR-4).
- **Pull-up values** (to +5V_A, the Amiga side of the power OR, §5):

  | Lines | Value | Why |
  |---|---|---|
  | `/STEP`, `/DIR`, `/SIDE`, `/SEL0` | 1 kΩ | HRM termination. CIA-B load 5 mA, plus 5 mA if an external DF1 terminates too, plus 1.6 mA internal = 11.6 mA, below 13 mA. |
  | `/DKWD`, `/DKWE` | 4.7 kΩ | No host pull-up, shared with the external port: keeps an A500+ 74LS05 inside 8 mA with a DF1 attached. |
  | `/SEL1` | 10 kΩ | Not used in v1. |
  | `/MTR0` (pins 4, 16) | none | The motherboard has R506 10 kΩ and the LED driver; 2 × 1 kΩ would exceed the A500+'s 74LS05. |

- Pull-ups on +5V_A draw no current when the Amiga is off, so nothing back-powers a dead Amiga (BUS-4, PWR-2).
- Optional 100–220 pF pads (not fitted) after the 100 Ω on `/STEP`, `/SEL0`, `/SEL1` and `/MTR0`; none on `/DKWD`.
- The two NC pins (6, 14) get 10 kΩ to +3.3 V so the buffer input never floats.

### 4.3 Outputs

- **74LVC07A** hex open-drain buffer at 3.3 V, SOIC-14: sinks 24 mA (VOL ≤ 0.4 V at 12 mA), the outputs may be
  pulled to 5 V by the host, and it has Ioff (±10 µA at VO = 5.5 V, VCC = 0), so an unpowered FluxDrive does not load
  the bus.
- **33 Ω in series** on every output, against ringing and EMI into the ribbon. At 5 mA it adds 0.17 V to the low
  level.
- **Power-on safe state:** 10 kΩ pull-up to +3.3 V on every LVC07A input. The six output GPIOs (21, 38–42) have no
  power-up glitch (§2.3), so the buffers stay off until the firmware asserts a line. GPIO39 also has a weak
  pull-up at reset.
- **Releasing a line** always means switching the GPIO to input so the 10 kΩ takes over, never relying on a
  peripheral's idle level (§9).
- **Gating on select** is firmware (§9). Two drives on one bus would need it in logic; that is for external-DF1
  support (§13).

### 4.4 The connector: ribbon or plug-on

The 2×17 holes take either part:

- a **boxed male header on the top side**, for a ribbon cable like a normal drive; or
- a **female 2×17 socket on the bottom side** (8.5 mm, e.g. DS1023-2*17SF11), which plugs straight onto the A500's
  male header. The board then sits about 11 mm above the motherboard.

Both mate correctly on the same holes because the footprint uses the pin-header pattern (pin 2 at +2.54 mm);
KiCad's socket footprint is mirrored and must not be used. This was worked out on the Nano-Tek CN3 and confirmed in
review (PCB-2).

- The even (signal) row faces the board interior, so signals escape without passing between the ground pins.
- A pin-1 triangle and a "this edge to …" mark on both silkscreen layers, because a bare header accepts the socket
  rotated or shifted by a row. The plug-on variant also gets a mechanical key: a printed foot in the mounting holes
  (§8).
- The overhang direction over the motherboard follows from the fit test (O7).
- Both connectors are hand-soldered, so the buyer picks.

## 5. Power

- **Input:** polarised 4-pin floppy power header **TE 171825-4**, vertical (LCSC C210162), fed from CN12. It is the
  same Berg family as on the Gotek and the Nano-Tek; their right-angle 171826-4 has almost no stock at LCSC (SPCB-1).
  For runs of 50, buy it from a distributor; it is hand-soldered anyway.
  A bare 1×4 header is not allowed: a plug shifted by one pin shorts the PSU. Only +5 V is used; +12 V is not
  connected.
- **eFuse** on CN12 pin 1: TPS259531 (checked against datasheet SLVSE57C in the schematic review) with an over-voltage clamp at
  5.7 V, a current limit and soft-start (about 22 nF). It survives a reversed plug (+12 V on the 5 V pin) **fitted
  with the power off**, and keeps it off the bus pull-ups, the LVC14A inputs (abs. max 6.5 V) and the Amiga's own
  pins. Its output is **+5V_A**. A reversed plug pushed on while the PSU runs can ring above the eFuse's 20 V
  absolute maximum: an unfitted pad for an SMAJ13A TVS (13 V standoff) sits on its input for that (SPWR-3).
- **Power OR:** `+5V_A` → Schottky (SS34) → **V5SYS**; USB-C VBUS → USBLC6-2SC6 → Schottky (SS34) → V5SYS. There
  is no P-FET: a reverse-polarity P-FET conducts both ways and would let USB feed the whole A500 (PWR-1).
  - The Amiga cannot reach VBUS, and USB cannot power +5V_A or the Amiga (only the 100 kΩ leakage of §4.2, BUS-4).
  - The USBLC6's supply pin goes to +3V3, not to VBUS: on VBUS, the ESP32's D+ pull-up would lift VBUS to about
    2.7 V through the ESD diodes, and a USB-C host on a C-to-C cable would then not switch VBUS on. A 10 kΩ bleeder
    holds VBUS at 0 V without a cable against the leakage of the VBUS diode (SPWR-1).
  - Alternative: two LM66100 ideal diodes instead of the Schottkys (±6 V abs. max, behind the eFuse).
- **3.3 V:** buck converter **TLV62569DBVR** (2.5–5.5 V in, 2 A, 100 % duty cycle), 2.2 µH, 22 µF out plus the
  module's own 22 µF, and an unfitted 15 pF feed-forward pad across the top feedback resistor (SPWR-5). It runs
  from USB's 4.75 V minus a Schottky; the TPS562201 of the input document needs 4.5 V in
  and does not (PWR-5). The ESP32-S3 peaks at 350–500 mA while transmitting; an LDO would burn up to 0.8 W inside
  the closed case.
- **Capacitors:**
  - eFuse input: 1 µF ceramic.
  - +5V_A: 2 × 47 µF 10 V X5R ceramic (1206, LCSC C96123), no 6.3 V parts: the clamp is 5.7 V (SPCB-2). The eFuse
    soft-start separates them from the cable, so the hot-plug overshoot of a ceramic on a bare cable does not apply.
  - V5SYS (buck input, seen by USB through its diode): 10 µF + 100 nF, no more (USB allows 10 µF on VBUS). An
    unfitted 1 Ω + 4.7 µF damper pad sits next to them in case a USB hot-plug rings V5SYS towards the buck's 6 V
    absolute maximum; if it is fitted, the 10 µF becomes 4.7 µF (SPWR-2).
  - 22 µF + 100 nF at the module's 3V3 pin, 100 nF per logic IC.
- **AMIGA_PWR:** 1 kΩ / 1.5 kΩ divider from +5V_A to GPIO1 (3.0 V at 5 V, 3.5 V at the clamp, 2 mA). It is this
  stiff so that on USB alone the leakage of §4.2 leaves it at about 0.3 V, well below the ESP32's 0.83 V low
  threshold (SESP-1). While it reads low, the firmware keeps every output released and ignores the inputs, because
  with the Amiga off every input reads as asserted.
- **Unsupported:** the 34-pin cable connected without the power cable. The pull-ups then hang on a dead +5V_A and
  the bus levels are undefined. The manual says so.

## 6. ESP32-S3 module

- **ESP32-S3-WROOM-1-N16R8** (exactly this variant: 16 MB flash, 8 MB octal PSRAM, VDD_SPI 3.3 V, so GPIO47/48 are
  3.3 V pins). The whole disk pre-encoded (1.9 MB) plus the ADF (880 KB) fits with room to spare, so a head step
  becomes a pointer change and no encoding happens under the host's deadline.
- **Temperature:** the R8 modules are rated −40…65 °C ambient, 85 °C with PSRAM ECC enabled. ECC is on (7.5 MB left);
  the lid-closed temperature is measured in bring-up (§11).
- **WROOM-1U-N16R8** (U.FL, external antenna) has the same 40 pads and thermal pad (WROOM-1 datasheet figures 11-1
  and 11-2). It is the fallback if the PCB antenna does not reach the GTi from inside the A500's shielded case (O5).
  It only helps if the antenna cable can leave the shield.
- **Antenna** (Espressif hardware design guidelines, PCB layout):
  - the antenna end of the module lies at the north board edge (0.5 mm inside it, so JLC can assemble the
    board: O10), over board material that is free of copper on all four layers, with its feed point near the
    edge. An overhanging antenna would reach a little further, but JLC's economic assembly wants every part inside
    the outline (Dimitri's decision after the layout review, LPCB-1);
  - no copper on any layer, no components and no ground pour under or beside it; dense ground vias along the
    keep-out border;
  - at least 15 mm clearance from metal in the housing, in all directions. In the plug-on variant the motherboard is
    closer than that: the range test decides (O5).
- **Pins:**

  | GPIO | Use |
  |---|---|
  | 0 | BOOT button, 10 kΩ pull-up to 3.3 V, no capacitor (strapping pin) |
  | 1 | AMIGA_PWR sense (§5) |
  | 2 | activity LED |
  | 4–11, 15–17 | bus inputs (§4.1) |
  | 19, 20 | USB D−, D+ |
  | 21, 38–42 | bus outputs (§4.1) |
  | 43, 44 | UART0 TX, RX: recovery and console header (§7) |
  | 13, 14, 47, 48 | spare header; 47/48 are glitch-free for future outputs |
  | 3, 12, 18, 45, 46 | not connected. GPIO3, 45 and 46 are strapping pins; GPIO45 must stay low or floating (it selects the flash voltage). |

  GPIO26–32 (flash) and 33–37 (octal PSRAM) are taken inside the module.
- **Boot and reset:** EN with 10 kΩ pull-up and 1 µF to ground (Espressif's values); a RESET button on EN; the BOOT
  button on GPIO0.
- **Module ground pad:** windowpane paste pattern, soldered to ground with tented vias.

## 7. Other parts on the board

- **USB-C** (USB 2.0 only) on GPIO19/20 for flashing and the serial console:
  - separate 5.1 kΩ on CC1 and CC2 (sink); A6–B6 and A7–B7 tied;
  - 22 Ω series pads on D+/D− near the module (0 Ω fitted if not needed) and unfitted capacitor pads to ground;
  - USBLC6-2SC6 at the connector, its supply pin on +3V3 (§5);
  - automatic download mode over USB-Serial/JTAG needs no extra parts, but stops working if the firmware
    reconfigures GPIO19/20, switches that controller off or sleeps. Recovery is then BOOT + RESET, or the UART header.
- **Activity LED** on GPIO2.
- **Recovery/console header** (6 pins, 2.54 mm, holes only): TX (GPIO43, 470 Ω in series), RX (GPIO44), EN, IO0,
  3.3 V, GND. A USB-serial adapter can reflash the board through it even if USB is dead. The ROM prints its boot
  messages on UART0, so a wired link to the GTi uses UART1 on the spare header, not this one.
- **Spare header** (holes only): GPIO13, 14, 47, 48, 3.3 V, GND. It replaces MES's unpopulated RP2350 footprint:
  that fallback needs a crystal, flash and a second power domain, and is better as a separate board if the bench gate
  ever fails.
- **Test pads, on the top side:** `/DKRD`, `/INDEX`, `/SEL0`, `/STEP`, `/MTR0` (both sides of the buffers), +5V_A,
  V5SYS, VBUS, 3V3, EN, GND. The 34-pin connector itself is the interface for a functional test jig.

## 8. PCB

- **4 layers**, 1.6 mm, JLC standard process: F.Cu signals, In1.Cu a solid GND plane, In2.Cu a solid +3V3 plane,
  B.Cu signals (Dimitri's decision after the layout review: on 2 layers the router cut the bottom plane into
  pieces under the buffers, LBUS-1/LPWR-1). All SMD on the top side, assembled by JLC. **Hand-soldered** by the
  builder: every through-hole part (the 34-pin connector, top or bottom (§4.4), the power header, the two headers of
  §7). Unfitted pads are 0603, so the builder can fit them by hand (SPCB-3).
- **Size:** 60 × 54.5 mm: at least 56 mm along the connector axis (a 34-way boxed header body is 51–54 mm long),
  48 mm for the parts and 6.5 mm for the antenna; the fit test (O7) can still change it. A 54 × 10 mm area on the top side above the
  connector stays free of SMD parts, for the header body and for the soldering iron.
- **Floorplan** (top view):
  - south edge: the 2×17 connector, even row inward;
  - above it: the resistors, the two LVC14As (one under pins 4–16, one under pins 18–32, each gate in the
    connector's order), the LVC07A at the pin 26–34 end, so `/DKRD` is a track of about 10 mm without a via;
  - north half: the module, its antenna along the north edge;
  - west strip: the power header next to the 34-way connector (vertical, so plugging it in pushes straight down
    through the socket), eFuse, bulk capacitor, diodes, buck; USB-C on the west edge near GPIO19/20, with the ESD
    part at the connector;
  - east edge: buttons and LED, outside the antenna keep-out.
- **Mechanics:** two 3.2 mm non-plated holes at the far end for a nylon standoff or a printed foot; they are also
  tooling holes. All bottom-side vias tented, no exposed copper on the bottom (the plug-on board may rest on
  motherboard parts). Clearance under the A500's shield is part of the fit test.
- **Grounding and noise:** In1 is an unbroken ground plane under the whole board (apart from the antenna area);
  every GND and +3V3 pad has its own via to its plane, none in a pad; the odd connector pins are plated through to
  In1; the GND pours on F.Cu and B.Cu are stitched to In1 about every 5 mm, closer along the edges. No track runs
  between the rows of the 34-way connector or between its GND pins (the plug-on socket is soldered there). The buck sits at least 15 mm from `/DKRD` and the antenna.
  Buck layout per the TLV62569 datasheet: tight input capacitor loop, small switch node with nothing under it or the
  inductor (no track under it on B.Cu, none between its pads), separate feedback sense track.
- **USB pair:** full speed (12 Mbit/s) only, so the impedance is not controlled (LESP-3): D+ and D− run close
  together over the In1 plane, the 22 Ω series pads next to the ESD part, the unfitted 10 pF pads on their module
  side.
- **Rules:** tracks and spacing 0.2 / 0.2 mm (0.15 mm allowed at the module), power 0.3 mm (the eFuse's 0.5 mm
  pitch pads take no wider track; 0.3 mm carries its 0.95 A limit); vias 0.3 mm drill /
  0.6 mm pad; through-hole annular ring ≥ 0.25 mm, header holes 1.0 mm with 1.7 mm pads; copper ≥ 0.3 mm from the
  edge; thermal reliefs on the ground pins of the 34-way and the power header; silkscreen text ≥ 1.0 mm with
  0.15 mm lines, 0.15 mm clear of pads.
- **Production features:** three fiducials (1 mm copper, 2 mm mask opening); a 15 × 6 mm silkscreen box on the
  bottom for a serial number and "FluxDrive v1 rev A"; a chosen position for JLC's order number.
- **Panel:** none needed: the board is ordered as a single board (economic assembly takes 2–50 pieces). A 2-up
  panel with mouse bites is possible if a larger run wants it; tracks and parts keep at least 0.3 mm from the
  edges.
- **Test pads:** 1.0 mm, on the top side, for a probe (SPCB-8: no pogo-pin fixture in v1). The connector-side ones
  sit in the strip south of J1; a map of all sixteen is in the README.

## 9. What the firmware must do because of this hardware

Firmware is a separate design; these points follow from the board and are fixed here.

- **Pure ESP-IDF.** Flux output through RMT or I2S/LCD_CAM; the bench gate picks one.
  - RMT: one endless transmission whose encoder wraps the track pointer itself (no start/stop at the wrap); the
    channel is created from a task pinned to core 1 at the highest interrupt priority; cache-safe ISR options on.
  - I2S/LCD_CAM: a continuous DMA ring; it can output `/DKRD` and `/INDEX` in lockstep.
  - The flux interrupt only reads internal RAM: on each head step a task copies the current track (about 12 KB of
    MFM bitcells) from PSRAM to internal RAM. An ISR that is safe with the flash cache off must still not touch PSRAM
    during a flash write.
- **No flash writes while a disk is mounted.** Wi-Fi keeps its settings in RAM (`esp_wifi_set_storage(WIFI_STORAGE_RAM)`),
  because by default every Wi-Fi config call writes flash. OTA updates (two slots with rollback, the normal way to
  update a fitted board) and the 15 s BOOT wipe only run with no disk mounted.
- **Bus release** (ESP-3): the first statement in `app_main`, and a panic/shutdown hook, switch the six output GPIOs
  to input. Releasing a line always means switching it to input. RMT channels use idle and end-of-transmission level
  1 (or `invert_out`); a GPIO is set high before it is made an output; I2S `auto_clear` must not send zeros onto
  `/DKRD`.
- **AMIGA_PWR low:** every output released, inputs ignored. Reading GPIO1 with ADC1_CH0 and a threshold of about
  2.4 V (+5V_A above about 4 V), with some hysteresis, also covers the reverse leakage of the +5V_A Schottky, which grows when hot (SPWR-4).
- **RTC slow clock:** internal only, never the external 32 kHz crystal: GPIO15/16 are bus inputs, driven by the
  LVC14A (SBUS-3).
- **Spare header J5:** GPIO13, 14, 47 and 48 get their internal pull-ups until something uses them; their tracks
  are 33–48 mm long and would float (LESP-10).
- **Outputs are gated by `/SEL0` only**, not by whether an image is mounted. While deselected all six are released.
- **Selected, no disk:** `/CHNG` asserted, `/WPROT` asserted, `/TRK0` live (it follows the head), no `/DKRD`, no
  `/INDEX`.
- **`/CHNG`:** set at power-up and while no disk is mounted; cleared only by a `/STEP` pulse while selected with a
  disk mounted. An eject sets it again.
- **`/RDY`:** with the motor off and the drive selected, held low (the DD drive ID, all ones active low). With the
  motor on, asserted about 500 ms after motor-on if a disk is mounted, not asserted without a disk. The same rule is
  used on DF0 and on DF1–DF3.
- **`/MTR0`:** read as a level (Gary latches it) with a short glitch filter. If it is ever sampled on the `/SEL0`
  edge, the sample must be taken at least 100 ns after the edge.
- **`/INDEX`:** a 2 ms low pulse every 200 ms, only with the motor on, a disk mounted and the drive selected, placed
  at the track wrap.
- **`/DKRD` pulse width:** fixed in the firmware spec after measuring a real drive (O12).
- **eFuses:** never burn `EFUSE_STRAP_JTAG_SEL` (GPIO39–42 must stay GPIO); `EFUSE_DIS_PAD_JTAG` may be burnt to lock
  that in. `EFUSE_DIS_USB_JTAG` only together with `EFUSE_DIS_PAD_JTAG`: alone it moves JTAG onto GPIO39–42,
  and GPIO40 would drive the bus until `app_main` runs (SESP-3). On v1, no secure boot, no flash encryption, no `DIS_DOWNLOAD_MODE`, no `DIS_USB_SERIAL_JTAG`: each would
  remove a recovery path.
- **GTi compatibility:** from the GTi's side FluxDrive is a dongle-class device, with the same ESP-NOW protocol and
  the same pairing gesture as the GTi SuperMini dongle (hold BOOT 5 s to pair, 15 s to wipe).

## 10. Cost

Estimate from the PCB review (JLC economic assembly: $8.18 setup, $1.53 stencil, $3.07 per extended part), with
about €1 per board (5–10 boards) or €0.5 (50) for 4 layers instead of 2 (layout review; to check in JLC's
calculator at order time), plus the
eFuse added after the power review. Parts at JLC's price tier per quantity, PCB price estimated, 1 EUR = 1.15 USD,
shipping, VAT and customs excluded. LCSC numbers and prices are fixed in the plan.

- Extended parts (8): module, 74LVC14A, 74LVC07A, eFuse, buck, inductor, USB-C, USBLC6. About $24.6 per order.
- Through-hole parts (34-way header or socket, power header): hand-soldered, about $0.40 per board.

| Quantity | Per board |
|---|---|
| 5 | ≈ €15 |
| 10 | ≈ €12 |
| 50 | ≈ €8 |

The WROOM-1U variant adds about €1.5–2 per board (module plus antenna and pigtail).

Main parts (review suggestions, to be re-checked in JLC's BOM tool):

| Function | Part | LCSC |
|---|---|---|
| Module | ESP32-S3-WROOM-1-N16R8 (1U: WROOM-1U-N16R8) | C2913202 (C3013946) |
| Schmitt inverter | SN74LVC14ADR, SOIC-14 (or Nexperia) | C133541 (C6065) |
| Open-drain buffer | 74LVC07AD, SOIC-14 | C6049 (reserve stock before a 50-piece order) |
| eFuse | TPS259531DSGR | C2155674 (single source, about 2,000 in stock: reserve before an order, SPCB-4) |
| Buck | TLV62569DBVR | C141836 |
| Schottky ×2 | SS34 | C8678 |
| USB ESD | USBLC6-2SC6 | C7519 or C2687116 |
| USB-C 16-pin | TYPE-C16PIN (the Nano-Tek part and footprint, placed by JLC before) | C393939 |
| Tactile switch | TS-1187A-B-A-B | C318884 |
| LED | KT-0603R | C2286 |
| Bulk capacitor ×2 | 47 µF 10 V X5R 1206, CL31A476MPHNNNE | C96123 |
| Power header | TE 171825-4, vertical, hand-soldered | C210162 |

## 11. How the design is proven

1. **Netlist tests** on the schematic export, as on the Nano-Tek:
   - every bus pin on the right buffer and direction, with the pull-up of §4.2 on the connector side of the 100 Ω;
   - no pull-up on `/MTR0`; pull-ups on +5V_A, not on V5SYS;
   - every output GPIO in {21, 38–42}, every output buffer input with its 10 kΩ, 33 Ω in series at every output;
   - strapping pins free, GPIO0 with 10 kΩ, no 5 V on a 3.3 V pin;
   - the power path: eFuse before +5V_A, a diode between +5V_A and V5SYS and between VBUS and V5SYS;
   - every gate used in and out of the same gate; the unfitted pads present, between the right nets;
   - the DC levels on USB alone (a resistor-network solve): AMIGA_PWR low, every bus input at a defined level;
   - the tests read a netlist exported fresh from the committed schematic, and fail if that schematic is not what
     the design file generates; ERC on the real schematic at every severity.
2. **ERC and DRC clean**, with JLC's 2-layer rules.
3. **Bench gate** (MES §8), before the Amiga is involved: flux on a bare dev board for 30 minutes, with ESP-NOW
   flooding. Tight 4/6/8 µs clusters, nothing at buffer boundaries or the wrap point, no gap in the endless
   transmission.
4. **Fit test:** a 1:1 paper template and a printed dummy in the A500, in both connector variants, including the
   overhang direction and the clearance under the shield.
5. **Range test** with a real WROOM-1 board (a SuperMini has a different antenna) inside the closed A500, in both
   connector variants. If it does not reach the GTi, the board is ordered with the WROOM-1U.
6. **Bring-up** in MES's order (§7 of the input document):
   - power: a reversed plug on a lab supply with current limit; USB alone with the Amiga off (+5V_A about 0.5 V,
     AMIGA_PWR low); hot-plug a 1 m and a 2 m USB-C cable with the Amiga off and scope V5SYS: it must stay below
     6 V, otherwise fit the damper of §5;
   - scope the six outputs through power-up, a RESET press and a flash over USB: no low pulse;
   - bus with firmware halted: all outputs released, so DF0 looks like a drive holding an unreadable disk (not an
     empty drive); the Amiga must still reach the insert-disk screen or boot its next device (SBUS-1). Then inputs
     logged, static outputs, synthetic
     track, one real track, Workbench boot, GTi insert, eject;
   - one hour lid-closed at the module: air temperature below 85 °C.

**v1 is done when:** Workbench 1.3 boots from an ADF sent by the GTi. Ten trackloader games load, among them one
that needs `/RDY` (X-Copy Pro). A disk swap is seen by AmigaDOS. The Amiga boots normally with FluxDrive fitted and
powered but with the firmware halted or unflashed. Fitted without the power cable is not supported (§5).

## 12. Review

Four specialist agents reviewed draft v0.1 on 2026-09-28/29: Amiga floppy bus, power and EMC, ESP32-S3 hardware,
PCB and manufacturing at JLC. Two blockers (the P-FET back-feed, the power-up glitches on the output GPIOs), 16
major findings and the rest minor. All of them are in `docs/reviews/2026-09-29-spec-review.md` with their sources and
decisions. The same four reviews ran again on the schematic (2026-09-29, no blockers, two majors, both fixed:
`docs/reviews/2026-09-29-schematic-review.md`) and run once more on the layout.

## 13. Open items

| # | Item | Decides |
|---|---|---|
| O5 | PCB antenna or U.FL: range test with a WROOM-1 board, both connector variants | module variant |
| O7 | Board outline, overhang direction and mounting in the A500 (fit test) | layout |
| O8 | Write-back policy for v2 (RAM disk, push to GTi, microSD) | nothing in v1 |
| O9 | Licence and where the repo is published (OMEGAWARE / GTi) | publication |
| O12 | Real-drive `/DKRD` and `/INDEX` pulse widths, Paula's `/DKWD` pulse width (the 4.7 kΩ rise of 0.7 µs) | firmware, v2 |
| O13 | Kickstart 1.3/2.x/3.x with a DF0 ID; whether reset clears Gary's motor latch; the A500+ `/MTR0` network | firmware |
| O14 | External DF1 (later): outputs gated by `/SEL` in logic, a hardware motor latch for `MTRXD` | v2 hardware |
| O15 | TE 171825-4: body outline and the pin row's place in it against TE drawing 171825 (the footprint's pads are the right-angle part's, its outline an estimate) | layout |

Closed in review: O1 (Gary latches `/MTR0`), O2 (pull-up values, §4.2), O3 (output GPIOs without a power-up
glitch, §2.3), O4 (buck TLV62569, §5), O6 (GPIO allocation, §4.1 and §6). Closed in the schematic review: O11
(TPS259531 clamp, current limit, pinout and package checked against SLVSE57C; stock see §10).
Closed in the layout review: O10 (the module lies on the board with its antenna 0.5 mm inside the north edge, §6).
