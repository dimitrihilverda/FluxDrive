# FluxDrive v1 — hardware design

**Status:** draft for review, 2026-09-28
**Authors:** Dimitri Hilverda (GTi co-author), with Claude
**Based on:** `docs/input/OMEGAWARE_FluxDrive_HW_Design_v0.1.md` (MES), `docs/input/FluxDrive_v0.1_review_notes.md`
(breadboard measurements), and the A500 bus research done for the Nano-Tek Rev 2.0 GTi.

FluxDrive is an Amiga floppy drive emulator built around one ESP32-S3 and nothing else: no Gotek, no second
microcontroller. It plugs into the A500's internal floppy connector, holds a disk image in PSRAM and generates the
MFM flux stream itself. Disk images come from the GTi touchscreen over ESP-NOW, or from a phone over WiFi.

The goal is the cheapest emulator that still has everything the GTi offers. Target: about €10 in parts per board
at 50 pieces, fully assembled by JLCPCB.

---

## 1. Scope of v1

| | v1 | Later |
|---|---|---|
| Host | A500 internal DF0 | A1200, A2000, external DF1 |
| Density | DD, 11 sectors per track | HD, IBM formats |
| Writes | `/WPRO` always asserted. `/WDATA` and `/WGATE` are wired to GPIO, so writing is firmware only. | Write capture and write-back |
| Images | one ADF resident | several disks, disk sets |
| Image source | GTi over ESP-NOW; WiFi upload page for use without a GTi | microSD (footprint is not on v1) |
| Radio while the motor runs | off | — |

Not in v1: pass-through to a real drive, the drive-swap switch of the Nano-Tek, an OLED or buttons for picking
disks. The GTi is the user interface.

## 2. Facts this design leans on

### 2.1 The A500 internal floppy connector

From the A500 schematic Rev 6a/7 (amigawiki `A500_R6.pdf`, sheets 4, 6, 7, 8) and the Hardware Reference Manual,
chapter 8. These were collected for the Nano-Tek Rev 2.0 GTi and are to be re-checked in review (§12).

- Connector CN11, even pins: 2 `/CHNG`, 4 `/MTR0`, 6 NC, 8 `/INDEX`, 10 `/SEL0`, 12 `/SEL1`, 14 NC, 16 `/MTR0`,
  18 `/DIR`, 20 `/STEP`, 22 `/DKWD` (write data), 24 `/DKWE` (write gate), 26 `/TRK0`, 28 `/WPROT`,
  30 `/DKRD` (read data), 32 `/SIDE`, 34 `/RDY`. Odd pins are ground, except pin 3 (NC).
- **Pin 2 is `/CHNG` and pin 34 is `/RDY`.** A PC drive has disk change on pin 34. Getting this wrong cost the
  breadboard build weeks.
- **Motor.** On the A500, `/MTR0` on pins 4 and 16 is reported to be already latched for DF0 by Gary on the
  `/SEL0` edge, so it is a plain level. The breadboard build, however, found that reading pin 16 as a level
  killed the stream on every deselect. The firmware rule in §9 works in both cases; the review must settle
  which is true (open item O1).
- **Who drives what.**
  - `/STEP`, `/DIR`, `/SIDE`, `/SEL0–3` come straight from CIA-B (8520 port B): passive pull-ups, sinks 13 mA
    at 0.4 V.
  - `/MTR0`, `/DKWD`, `/DKWE` go through a 74LS38 (open collector, 24 mA). On the A500+ it is a 74LS05
    (about 8 mA). The motherboard has **no pull-ups** on these three; a real drive terminates them.
  - Back to the Amiga: `/DKRD` has 1 kΩ on the motherboard, `/INDEX` 10 kΩ. `/RDY`, `/TRK0`, `/WPROT` and
    `/CHNG` only have CIA-A's internal pull-ups.
- **Drive termination.** Common 3.5" drives have a fixed 1 kΩ pull-up on every input (confirmed for the TEAC
  FD-235HF, not for the Chinon or Matsushita drives fitted in the A500).
- **Power** is on a separate 4-pin connector CN12: 1 = +5 V, 2 = GND, 3 = GND, 4 = +12 V. The 34-pin connector
  carries none.
- **Kickstart never probes DF0** ("DF0 is always there"). DF1–DF3 are probed at boot through a serial ID on
  `/RDY`.

### 2.2 What the breadboard build measured

ESP32-S3 at 240 MHz, buffers in PSRAM, Arduino core 3.3.7 (details in `docs/input/FluxDrive_v0.1_review_notes.md`):

- MFM-encoding one DD track: about 3.5 ms. Converting it naively to RMT symbols: another 12–17 ms.
- The Arduino RMT layer has no stop and no TX-done callback, and mixing it with the IDF RMT driver silently
  produces no output. Firmware for this board is therefore pure ESP-IDF.
- 74HCT125 powered at 3.3 V on the input side is out of spec and caused the "weak select line" symptoms.
  This design uses 74LVC throughout.

## 3. Block diagram

```
 A500 CN11 (34-pin) ──100 Ω──► 2× 74LVC14A (Schmitt, 3.3 V) ──► ESP32-S3-WROOM-1-N16R8
          ▲                                                        │  ▲
          └──────────── 74LVC07A (open drain, 3.3 V) ◄─────────────┘  │
                                                                      │
 A500 CN12 (Berg +5 V) ──P-FET──┬── buck 3.3 V ───────────────────────┤
 USB-C (bench, flashing) ──Schottky──┘                                │
                                    BOOT, RESET, activity LED, UART header, spare GPIO header, test pads
```

## 4. Bus interface

### 4.1 Pin by pin

| Pin | Signal | Direction (from FluxDrive) | Buffer | ESP32-S3 GPIO | Pull-up on the board |
|---|---|---|---|---|---|
| 2 | `/CHNG` | out | LVC07A | 11 | — (host) |
| 4 | `/MTR0` (alt.) | in | LVC14A | 21 | 1 kΩ to +5 V |
| 6 | NC on A500 | in | LVC14A | 38 | 10 kΩ to +3.3 V (keeps an open pin defined) |
| 8 | `/INDEX` | out | LVC07A | 8 | — (host, 10 kΩ) |
| 10 | `/SEL0` | in | LVC14A | 17 | 1 kΩ to +5 V |
| 12 | `/SEL1` | in | LVC14A | 39 | 1 kΩ to +5 V |
| 14 | NC on A500 | in | LVC14A | 40 | 10 kΩ to +3.3 V |
| 16 | `/MTR0` | in | LVC14A | 18 | 1 kΩ to +5 V |
| 18 | `/DIR` | in | LVC14A | 7 | 1 kΩ to +5 V |
| 20 | `/STEP` | in | LVC14A | 6 | 1 kΩ to +5 V |
| 22 | `/DKWD` | in | LVC14A | 5 | 1 kΩ to +5 V |
| 24 | `/DKWE` | in | LVC14A | 16 | 1 kΩ to +5 V |
| 26 | `/TRK0` | out | LVC07A | 9 | — (host) |
| 28 | `/WPROT` | out | LVC07A | 10 | — (host) |
| 30 | `/DKRD` | out | LVC07A | 4 | — (host, 1 kΩ) |
| 32 | `/SIDE` | in | LVC14A | 15 | 1 kΩ to +5 V |
| 34 | `/RDY` | out | LVC07A | 12 | — (host) |

Eleven inputs on twelve inverters (one spare, input tied to ground). Six outputs on the six LVC07A buffers.
The GPIO numbers follow MES's allocation (§5 of the input document) so the breadboard notes stay comparable;
the review may move them (open item O6).

### 4.2 Inputs

- **74LVC14A** hex Schmitt inverter at 3.3 V. Its inputs tolerate 5 V while powered at 3.3 V, and the hysteresis
  keeps ringing on a ribbon cable from causing phantom steps. It inverts, so the ESP sees active-high signals.
- **100 Ω in series** at the connector on every input, against ringing and ESD.
- **1 kΩ pull-up to +5 V** on every line the A500 drives, like a real drive's termination. Without it the three
  74LS38 lines (`/MTR0`, `/DKWD`, `/DKWE`) float. Load: 5 mA per line, within CIA-B's 13 mA, the 74LS38's
  24 mA and the A500+'s 74LS05 (about 8 mA). If an external DF1 is also connected, its termination adds
  another 5 mA: 10 mA total, still inside CIA-B's rating but not the 74LS05's (open item O2).
- The two NC pins (6, 14) get 10 kΩ to +3.3 V so the buffer input never floats.

### 4.3 Outputs

- **74LVC07A** hex open-drain buffer at 3.3 V: sinks 24 mA, the outputs may be pulled to 5 V by the host, and it is
  specified with power off (Ioff), so an unpowered FluxDrive does not load the bus. To be confirmed in review.
- **Power-on safe state:** 10 kΩ pull-up to +3.3 V on every LVC07A input. While the ESP32 boots its GPIOs are
  high impedance, the buffers stay off, and the Amiga sees an idle bus. No enable logic, no firmware involvement.
  The review must check that none of these six GPIOs glitches low during boot or flashing (open item O3).
- **Bus release on deselect** is firmware: on `/SEL` going inactive all six outputs go high (released) within
  microseconds. It only matters with two drives, but costs nothing.

### 4.4 The connector: ribbon or plug-on

The 2×17 holes take either part:

- a **boxed male header on the top side**, for a ribbon cable like a normal drive; or
- a **female 2×17 socket on the bottom side**, which plugs straight onto the A500's male header. The board then
  sits above the motherboard.

Both mate correctly on the same holes because the footprint uses the pin-header pattern (pin 2 at +2.54 mm);
KiCad's socket footprint is mirrored and must not be used. This was worked out and checked on the Nano-Tek CN3.
JLC fits neither connector. They are hand-soldered, so the buyer picks.

## 5. Power

- **Input:** 4-pin floppy power header (171826-4 type, as on the Gotek and the Nano-Tek), fed from CN12. Only
  +5 V is used; +12 V is not connected.
- **Reverse polarity:** P-FET in the +5 V path (the mini-Berg can be forced on the wrong way round).
- **Bulk:** 100 µF + 10 µF at the input.
- **3.3 V:** a synchronous buck converter, not an LDO. The ESP32-S3 peaks at 350–500 mA while transmitting;
  an LDO would burn up to 0.8 W inside the closed case. MES's choice is the TPS562201; the plan picks a part from
  JLC's basic/preferred list if an equivalent exists there (open item O4).
- **USB-C for the bench:** VBUS joins +5 V through a Schottky diode, so the board runs from USB without an Amiga.
  With both connected, the higher rail wins; the Schottky stops USB from back-feeding the Amiga.
- **Decoupling:** 22 µF + 100 nF at the module's 3V3 pin (the RF bursts are the largest transient), 100 nF per
  logic IC, and the buck's own input and output capacitors per its datasheet.

## 6. ESP32-S3 module

- **ESP32-S3-WROOM-1-N16R8:** 16 MB flash, 8 MB octal PSRAM. The whole disk pre-encoded (1.9 MB) plus the ADF
  (880 KB) fits with room to spare, so a head step becomes a pointer change and no encoding happens under the
  host's deadline.
- **WROOM-1U-N16R8** (U.FL connector, external antenna) fits the same footprint. It is the fallback if the PCB
  antenna does not reach the GTi from inside the A500's shielded case (open item O5; range test in §11).
- **Reserved pins:** GPIO 26–32 (flash) and 33–37 (octal PSRAM) are taken inside the module. Strapping pins 0, 3,
  45, 46 are not used for bus signals. GPIO 45 must stay low or floating (it selects the flash voltage). GPIO 19/20
  are USB.
- **Boot and reset:** EN with 10 kΩ pull-up and 1 µF to ground; a RESET button on EN; a BOOT button on GPIO 0.
- **Antenna:** the module sits on a board edge with its antenna past the edge or over the keep-out from the
  Espressif datasheet: no copper on any layer, no components, no ground pour under it.

## 7. Other parts on the board

- **USB-C** (USB 2.0 only) on GPIO 19/20 for flashing and the serial console, with 5.1 kΩ on CC1 and CC2
  (sink), ESD protection on D+/D−.
- **Activity LED** on a free GPIO.
- **UART header** (TX, RX, GND, 2.54 mm) for a wired link to the GTi or a display, so the board can run with the
  radio off entirely.
- **Spare header** with 4 free GPIO + 3.3 V + GND. It replaces MES's unpopulated RP2350 footprint: that fallback
  needs a crystal, flash and a second power domain, and is better as a separate board if the bench gate ever
  fails.
- **Test pads** for the scope: `/DKRD`, `/INDEX`, `/SEL0`, `/STEP`, `/MTR0` (both sides of the buffers), 3.3 V,
  5 V, GND.

## 8. PCB

- 2 layers, 1.6 mm, JLC standard process. All SMD on the top side, assembled by JLC. Hand-soldered: the 34-pin
  connector (top or bottom, §4.4) and the power header.
- About 50 × 45 mm; the final size follows the layout and the fit test in the A500 (open item O7).
- Ground pour on both layers, stitched. `/DKRD` short and away from the buck's switch node, with a continuous
  ground return underneath.
- Tracks 0.2 mm / 0.15 mm, power 0.4 mm. Silkscreen: pin 1, the connector option, the signal names on the
  headers.

## 9. What the firmware must do because of this hardware

Firmware is a separate design; these points follow from the board and are fixed here.

- Pure ESP-IDF. Flux output through RMT with a ≥ 1024-symbol refill in an `IRAM_ATTR` interrupt, DMA buffers in
  internal SRAM, flux task pinned to core 1, radio on core 0. (I2S/LCD_CAM with circular DMA is an equal
  alternative; the bench gate picks one.)
- **Motor:** sample `/MTR0` on the falling edge of `/SEL0` and hold it. This is correct if the line is raw (a real
  drive latches it the same way) and gives the same result if Gary has already latched it.
- **`/CHNG`:** assert on eject; clear only on the next `/STEP` pulse.
- **`/RDY`:** asserted after a realistic spin-up delay once the motor is on. When the board is configured as
  DF1–DF3, shift out the drive ID on `/RDY` while the motor is off.
- **All six outputs released** until an image is mounted and the drive is selected; released within
  microseconds of deselect.
- **No flash writes while a disk is mounted** (cache suspend stalls the flux stream).
- **GTi compatibility:** from the GTi's side FluxDrive is a dongle-class device, with the same ESP-NOW protocol and
  the same pairing gesture as the GTi SuperMini dongle (hold BOOT 5 s to pair, 15 s to wipe).

## 10. Cost

Indicative, at 50 pieces. LCSC part numbers and prices are fixed in the plan.

| Part | ~€ |
|---|---|
| ESP32-S3-WROOM-1-N16R8 | 4.50 |
| 2× 74LVC14A, 1× 74LVC07A | 0.60 |
| Buck converter + inductor + capacitors | 1.00 |
| P-FET, Schottky, USB-C, ESD | 0.60 |
| Resistors, capacitors, LED, 2 buttons | 0.60 |
| PCB, 2 layers | 1.00 |
| 34-pin header or socket, power header (hand-fitted) | 0.80 |
| JLC assembly share (setup and extended-part fees spread over 50) | 1.00 |
| **Total** | **≈ 10** |

At 5 pieces the per-board price is dominated by JLC's fixed fees: expect €20–25.

## 11. How the design is proven

1. **Netlist tests** on the schematic export, as on the Nano-Tek: every bus pin on the right buffer and direction,
   pull-ups present, no 5 V on a 3.3 V pin, strapping pins free, and the power-on state of every output.
2. **ERC and DRC clean**, with JLC's 2-layer rules.
3. **Bench gate** (MES §8), before the Amiga is involved: flux on a bare dev board for 30 minutes, with ESP-NOW
   flooding. Tight 4/6/8 µs clusters, nothing at buffer boundaries or the wrap point.
4. **Fit test:** a 1:1 paper template and a printed dummy in the A500, in both connector variants.
5. **Range test:** a SuperMini inside the closed A500 must reach the GTi. If not, the board is ordered with the
   WROOM-1U.
6. **Bring-up** in MES's order (§7 of the input document): power, bus with firmware halted (the Amiga boots and
   sees no drive), inputs logged, static outputs, synthetic track, one real track, Workbench boot, GTi insert,
   eject.

**v1 is done when:** Workbench 1.3 boots from an ADF sent by the GTi. Ten trackloader games load, among them one
that needs `/RDY` (X-Copy Pro). A disk swap is seen by AmigaDOS. The Amiga boots normally with FluxDrive fitted
but unpowered or unflashed.

## 12. Review

Four specialist agents review this spec before it is final, and later the schematic and the layout:

1. **Amiga floppy bus:** pinout, direction, termination and loading, motor latch, `/RDY` and drive ID, `/CHNG`
   handshake, behaviour with an external DF1.
2. **Power and EMC:** input protection, buck choice and layout rules, USB power path, decoupling, noise near
   `/DKRD`.
3. **ESP32-S3 hardware:** module choice, strapping and boot state of every used GPIO, USB, antenna and keep-out,
   flashing path.
4. **PCB and manufacturing at JLC:** 2-layer rules, part availability (basic vs extended), assembly side,
   hand-fitted parts, cost.

Every finding needs a source (a datasheet, the A500 schematic, the HRM, JLC's capabilities page). Findings and
what was done with them go into `docs/reviews/`.

## 13. Open items

| # | Item | Decides |
|---|---|---|
| O1 | Is `/MTR0` on A500 pins 4/16 already latched by Gary? | firmware detail only (§9 covers both) |
| O2 | Pull-up value: 1 kΩ like a drive, or higher to leave room for an external DF1 on an A500+ (74LS05) | resistor values |
| O3 | Boot/flash glitches on the six output GPIOs | GPIO choice |
| O4 | Buck converter part from JLC's basic list | BOM, layout |
| O5 | PCB antenna or U.FL (range test) | module variant |
| O6 | Final GPIO allocation after review | schematic |
| O7 | Board outline and mounting in the A500 (fit test) | layout |
| O8 | Write-back policy for v2 (RAM disk, push to GTi, microSD) | nothing in v1 |
| O9 | Licence and where the repo is published (OMEGAWARE / GTi) | publication |
