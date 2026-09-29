# Review of the v1 hardware spec (draft of 2026-09-28)

Four specialist reviews of `docs/superpowers/specs/2026-09-28-fluxdrive-v1-hardware-design.md`, done by separate
agents on 2026-09-28/29. None of them changed a file. This document lists every finding, what was decided and where
it went in the spec (v0.2).

| Review | Findings | Blockers |
|---|---|---|
| Amiga floppy bus (BUS) | 12: 7 major, 3 minor, 2 nits | — |
| Power and EMC (PWR, SI) | 12: 1 blocker, 5 major, 5 minor, 1 nit | PWR-1 |
| ESP32-S3 hardware (ESP) | 11: 1 blocker, 3 major, 6 minor, 1 nit | ESP-1 |
| PCB and manufacturing at JLC (PCB) | 14: 4 major, 8 minor, 2 nits | — |

## Sources the reviews used

- **[SCH]** A500 schematic Rev 6a/7, https://amigawiki.org/dnl/schematics/A500_R6.pdf (sheet numbers from the title blocks)
- **[HRM]** Amiga Hardware Reference Manual, appendix E, https://www.theflatnet.de/pub/cbm/amiga/AmigaDevDocs/hard_e.html
- **[GARY]** Gary chip specification, https://www.devili.iki.fi/mirrors/haynie/systems/amiga2k/docs/gary.txt
- **[8520]** CIA 8520 specification, https://rastport.com/techblog/8520-complex-interface-adapter-specification/
- **[FF]** FlashFloppy source (`src/floppy.c`, `src/gotek/floppy.c`) and wiki page Host-Platforms, https://github.com/keirf/flashfloppy
- **[D]** ESP32-S3 datasheet v2.2, https://documentation.espressif.com/esp32-s3_datasheet_en.pdf
- **[W]** ESP32-S3-WROOM-1/1U datasheet v1.8, https://documentation.espressif.com/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf
- **[HDG]** ESP32-S3 hardware design guidelines, https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/
- **[RMT]** ESP-IDF RMT documentation and `esp_driver_rmt` source; ESP-IDF pages on USB-Serial/JTAG, SPI flash concurrency, I2S, `esp_wifi.h`
- **[TI]** SN74LS38 (SDLS105), SN74LS05, TPS562201, TLV62569, LM66100 datasheets, https://www.ti.com
- **[NXP]** Nexperia 74LVC14A (Rev 11) and 74LVC07A (Rev 10) datasheets
- **[AN88]** Linear Technology AN88, ceramic input capacitors and hot-plugging
- **[JLC]** JLCPCB assembly price, assembly capabilities, assembly FAQ and PCB capabilities pages; part data from the
  jlcsearch mirror of JLC's database (https://jlcsearch.tscircuit.com). Stock and prices from the mirror are to be
  re-checked in JLC's BOM tool at order time.

The ESP-1 claim was re-checked against [D] directly: table 2-2 lists GPIO1–14, XTAL_32K_P/N (GPIO15/16) and GPIO17
with a 60 µs low-level glitch at power-up, GPIO18 low and high, GPIO19/20 high. Footnote 1 defines a low-level glitch
as "the pin is at a low level output status".

## Where the reviews disagreed

| Topic | Positions | Decision |
|---|---|---|
| Bulk capacitor | PWR-4: aluminium electrolytic, a ceramic overshoots on hot-plug. PCB-14: 100 µF 1206 MLCC (basic part). | Ceramic, but only on `+5V_A` behind the eFuse. Its soft-start separates the capacitor from the cable, which is what AN88 is about. The `V5SYS` node stays at 10 µF (USB limit). |
| Power header | PCB-4: a generic 1×4 header (the 171826-4 has 16 in stock at JLC). PWR-3: the polarised 171826-4 is mandatory. | Polarised 171826-4. Dimitri solders all through-hole parts himself, so JLC stock does not matter. |
| Test pads | PCB-12: 1.5 mm pads on the bottom for a pogo jig. PCB-3: no exposed copper on the bottom, the plug-on board may rest on motherboard parts. | Test pads on the top side. |
| Buck converter | PCB-6: keep the TPS562201. PWR-5: its 4.5 V minimum input does not fit a diode-fed rail. | TLV62569 (PWR-5). |
| Output buffer | PCB-7: six 2N7002 would save one extended-part fee. | Keep the 74LVC07A: no inversion, fewer parts, the saving only counts at 5–10 boards. |

## Findings and decisions

"Accepted" means the spec now does what the finding asks; the column "Spec" gives the section of v0.2.

### Amiga floppy bus

| ID | Sev. | Finding | Decision | Spec |
|---|---|---|---|---|
| BUS-1 | major | `/MTR0` on pins 4/16 is latched by Gary (MTRON, U5 pin 46, via U36 74LS38 [SCH] sheet 4; [GARY] §2.1, §3.4.17). The breadboard symptom came from the HCT125 at 3.3 V. Sampling on the `/SEL0` edge would need ≥ 100 ns delay. | Accepted. O1 closed: firmware reads `/MTR0` as a level with a short glitch filter. A hardware latch is noted for a later external DF1. | 2.1, 9, 13 |
| BUS-2 | major | `/MTR0` already has R506 10 kΩ and the drive-LED transistor Q503 on the motherboard ([SCH] sheet 6). 2 × 1 kΩ on pins 4 and 16 (one net) is about 10.5 mA, over the A500+'s 74LS05 rating of 8 mA. | Accepted: no pull-up on pins 4 and 16, footprint left unfitted. | 4.1, 4.2 |
| BUS-3 | major | With the pull-up on the buffer side of the 100 Ω, the LVC14A sees up to 0.92 V for a low; its VT− can be 0.8 V ([NXP] 74LVC14A p.8). | Accepted: pull-up on the connector side, 100 Ω between that node and the buffer. A netlist test checks it. | 4.2, 11 |
| BUS-4 | major | Power domains: with FluxDrive unpowered the 1 kΩ pull-ups load the bus from a dead rail; on USB alone they feed about 1 mA per line into a dead Amiga; the P-FET conducts backwards. | Accepted: pull-ups on `+5V_A` (Amiga side of the power OR), 100 kΩ to 3.3 V on the buffer side, an `AMIGA_PWR` sense input, P-FET replaced (PWR-1). A ribbon without the power cable is declared unsupported. | 4.2, 5, 11 |
| BUS-5 | major | A mini-Berg forced on the wrong way round puts +12 V on pin 1 (CN12: 1 = +5 V, 4 = +12 V, [SCH] sheet 8), not a negative voltage. | Accepted, handled by the eFuse (PWR-3). | 5 |
| BUS-6 | major | An empty drive is not an absent drive: `/CHNG` stays set while no disk is in, `/TRK0` works without a disk ([HRM] appendix E, [FF]). "All outputs released until mounted" looks like "disk present, unchanged". | Accepted: outputs are gated by `/SEL0` only; empty state defined. | 9 |
| BUS-7 | major (DF1–3), minor (DF0) | `/RDY` with the motor off is the drive ID; a DD drive holds it low while selected ([HRM]). FlashFloppy does `pin 34 = !motor` in Amiga mode. | Accepted: the rule is used on DF0 as well; spin-up 500 ms. "Kickstart never probes DF0" softened. | 2.1, 9 |
| BUS-8 | minor | `/INDEX` goes to CIA-B /FLAG ([SCH] sheet 6); a real drive pulses once per revolution. | Accepted: 200 ms period, 2 ms low, only with motor on, disk mounted and selected. | 9 |
| BUS-9 | minor | Firmware release on deselect is too slow for two drives on one bus; real drives gate outputs in logic. | Deferred: fine for v1 (DF0 only). Hardware gating is an item for external-DF1 support. | 13 |
| BUS-10 | minor | `/DKWD` and `/DKWE` have no host pull-up and are shared with the external port; 1 kΩ + a DF1's 1 kΩ is 10 mA, over the 74LS05's 8 mA. | Accepted: 4.7 kΩ on `/DKWD` and `/DKWE`, 1 kΩ on `/STEP`, `/DIR`, `/SIDE`, `/SEL0`, 10 kΩ on `/SEL1`. The 0.7 µs rise on `/DKWD` is checked against Paula's write pulse before v2. | 4.2, 13 |
| BUS-11 | nit | Rise times are fine; the DB23 port adds 100 pF filters to the shared nets ([SCH] sheet 7). | No parts added. The `/DKRD` pulse width is fixed in the firmware spec after measuring a real drive. | 9, 13 |
| BUS-12 | nit | Cite [HRM] appendix E for the 1 kΩ termination, not the TEAC drive. | Accepted. | 2.1 |

### Power and EMC

| ID | Sev. | Finding | Decision | Spec |
|---|---|---|---|---|
| PWR-1 | blocker | A P-FET wired for reverse polarity conducts both ways once on: on USB alone it back-feeds the A500's whole 5 V rail. The spec's claim that the Schottky prevents back-feeding is wrong. | Accepted: CN12 → eFuse → `+5V_A` → Schottky → `V5SYS`; VBUS → USBLC6-2SC6 → Schottky → `V5SYS`. No P-FET. | 3, 5 |
| PWR-2 | major | Same as BUS-4 from the power side. | Accepted, see BUS-4. | 4.2, 5 |
| PWR-3 | major | Reversed plug = +12 V on the 5 V pin; it reaches the LVC14A inputs (abs. max 6.5 V) and the Amiga's pins through the pull-ups. A plug shifted by one pin shorts the PSU. | Accepted: eFuse with over-voltage clamp at 5.7 V (TPS259531, to be verified in the plan against its datasheet), and the polarised 171826-4 header is mandatory. | 5, 7 |
| PWR-4 | major | Ceramic bulk + hot-plug overshoot ([AN88]); inrush on the running A500; USB allows 10 µF on VBUS. | Accepted with a change: see "Where the reviews disagreed". | 5 |
| PWR-5 | major | TPS562201 needs 4.5 V in and ~4.4 V for 3.3 V out; USB minus a Schottky is ~4.35 V. | Accepted: TLV62569 (2.5–5.5 V, 100 % duty). Its 6 V abs. max is covered by the eFuse clamp. | 5 |
| PWR-6 | minor | No usable buck on JLC's basic list. | Accepted: one extended part. | 5, 10 |
| PWR-7 | major | The WROOM-1-N16R8 is rated −40…65 °C; with PSRAM ECC 85 °C ([W] §1). | Accepted: PSRAM ECC on (7.5 MB left, 2.8 MB used), one-hour lid-closed temperature test. | 6, 9, 11 |
| SI-1 | minor | Released `/DKRD` is a high-impedance node that picks up switch-node edges. | Accepted: connector at one end, buck at the other (≥ 15 mm), unbroken ground under the signals, stitching. | 8 |
| SI-2 | minor | LVC07A edges into an unterminated ribbon ring. | Accepted: 33 Ω in series on every output. | 4.3 |
| SI-3 | minor | The 100 Ω does not damp ringing; the hysteresis does. | Accepted: wording fixed; optional (unfitted) 100–220 pF pads after the 100 Ω on `/STEP`, `/SEL0`, `/SEL1`, `/MTR0`. | 4.2 |
| PWR-8 | minor | USB protection. | Accepted: USBLC6-2SC6 at the connector, before the VBUS diode. | 7 |
| PWR-9 | nit | Test points for the rails. | Accepted: `+5V_A`, `V5SYS`, VBUS, 3V3, EN. | 7 |

### ESP32-S3 hardware

| ID | Sev. | Finding | Decision | Spec |
|---|---|---|---|---|
| ESP-1 | blocker | All six output GPIOs (4, 8–12) are driven low for ~60 µs at power-up ([D] table 2-2), which overrides the 10 kΩ pull-ups and asserts every bus output, also on a RESET press while the Amiga runs. | Accepted: outputs moved to GPIO21 and 38–42, which have no glitch and are not strapping pins. O3 closed. | 4.1, 6 |
| ESP-2 | minor | GPIO18 also has a high-level glitch: output contention with the LVC14A. | Accepted: GPIO18 unused. | 4.1 |
| ESP-3 | major | RMT and GPIO drivers start pins low by default (`init_level`, `eot_level` = 0); I2S `auto_clear` sends zeros. | Accepted: release = pin to input, never a peripheral idle level; idle and end levels 1; release first in `app_main` and in a panic hook. | 9 |
| ESP-4 | minor | GPIO0 needs an external pull-up and no capacitor ([HDG]). | Accepted: 10 kΩ, no debounce capacitor; the 15 s wipe only with no disk mounted. | 6, 9 |
| ESP-5 | minor | No series parts on D+/D−; CC and pair wiring. | Accepted: 22 Ω series pads (0 Ω allowed), unfitted capacitor pads, separate 5.1 kΩ on CC1/CC2, A6–B6 and A7–B7 tied, 90 Ω pair. | 7, 8 |
| ESP-6 | minor | UART header pins not defined; a closed A500 hides USB and buttons. | Accepted: 6-pin header with UART0 (GPIO43/44, 499 Ω on TX), EN, IO0, 3.3 V, GND. A wired GTi link uses UART1 on spare pins. Wi-Fi OTA with rollback is the normal update path, only with no disk mounted. | 7, 9 |
| ESP-7 | minor | Temperature rating of the R8 modules. | Accepted with PWR-7; thermal pad to ground with vias. | 6, 8 |
| ESP-8 | major | Antenna: Espressif prefers the antenna outside the board, 15 mm clearance from metal ([HDG]); the SuperMini range test does not transfer. | Accepted: antenna past the board edge, 15 mm rule, range test with a real WROOM-1 board in both connector variants. | 6, 11 |
| ESP-9 | major | Flux ISR vs flash writes: an ISR that is safe with the cache off must still not touch PSRAM during a flash write; Wi-Fi stores its config in flash by default. | Accepted: Wi-Fi storage in RAM, the current track copied to internal RAM on each step, endless RMT transmission, channel created on core 1. | 9 |
| ESP-10 | minor | GPIO39–42 are JTAG pins; they stay GPIO with default eFuses. | Accepted: eFuse rules for v1. | 9 |
| ESP-11 | nit | GPIO47/48 run from VDD_SPI: 3.3 V on N16R8, 1.8 V on R16V. | Accepted: the module variant is fixed exactly in the BOM. | 6 |

### PCB and manufacturing at JLC

| ID | Sev. | Finding | Decision | Spec |
|---|---|---|---|---|
| PCB-1 | major | A 34-way boxed header body is about 51–54 mm long; 50 mm is too short. | Accepted: at least 56 mm along the connector; 54 × 10 mm on top kept free of SMD parts. | 8 |
| PCB-2 | minor | The pin-header hole pattern is right; the overhang direction and a mechanical key are missing. | Accepted: pin-1 triangle and edge marks on both sides, even row towards the board, key or foot; direction from the fit test. | 4.4, 8, 13 |
| PCB-3 | major | The plug-on board hangs on 34 contacts; cables lever it. | Accepted: power header next to the 34-way connector, vertical; two 3.2 mm non-plated holes at the far end for a foot; bottom vias tented, no exposed copper on the bottom. | 8 |
| PCB-4 | minor | Who solders the through-hole parts; stock of the 171826-4. | Accepted: Dimitri solders all through-hole parts; the header stays the polarised 171826-4 (PWR-3). | 7, 8 |
| PCB-5 | major | Economic assembly: 30 or 50 pieces (JLC's pages disagree); standard assembly needs 70 × 70 mm with rails. | Accepted: the board is laid out so a 2-up JLC panel is possible; decided at order time. | 8 |
| PCB-6 | minor | No basic buck; TPS562201 values. | Superseded by PWR-5. | 5 |
| PCB-7 | minor | Seven extended parts, about $21.5 per order. | Accepted as a cost; the 2N7002 option rejected. | 10 |
| PCB-8 | minor | Use SOIC-14 for the logic, reserve LVC07 stock. | Accepted. | 4, 10 |
| PCB-9 | minor | Module stock and price; windowpane paste on the ground pad. | Accepted. | 6, 8, 10 |
| PCB-10 | major | Antenna placement on a 45 mm board. | Accepted with ESP-8; whether economic assembly takes an overhanging module is asked at JLC (O10). | 6, 13 |
| PCB-11 | minor | Design rules. | Accepted. | 8 |
| PCB-12 | minor | Fiducials, test pads, serial box, order-number position. | Accepted; test pads on top (PCB-3). | 7, 8 |
| PCB-13 | nit | UART and spare headers: unpopulated holes. | Accepted. | 7 |
| PCB-14 | nit | 100 µF as 1206 MLCC. | Accepted, see "Where the reviews disagreed". | 5 |

## What the reviews could not verify

Carried into the spec's open items (§13) where they affect the design:

- Termination on the original Chinon/Matsushita A500 drives; how Kickstart 1.3/2.x/3.x treats a DF0 ID; whether reset
  clears Gary's motor latch; real-drive `/DKRD` and `/INDEX` pulse widths; Paula's write pulse width; the A500+
  `/MTR0` network (BUS).
- Unpowered 8520 pin behaviour; temperature in a closed A500; the default ESP-NOW rate; whether the A500's own CN12 is
  polarised (PWR).
- What the ROM and bootloader do to GPIO21 and 38–42 during download mode; whether an endless RMT transmission has no
  gap; whether Paula accepts the chosen `/DKRD` pulse width (ESP).
- JLC's own part pages and PCB prices; boxed-header dimensions from a datasheet; whether economic assembly takes a
  bottom-side through-hole part or an overhanging module (PCB).
