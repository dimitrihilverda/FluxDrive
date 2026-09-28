# OMEGAWARE FluxDrive — Hardware Design Document

**Rev 0.1 — working draft**
ESP32-S3 direct Shugart floppy emulator, Amiga DD target

---

## 1. Scope

A single PCB that presents itself to an Amiga as an internal DD floppy drive (DF0)
over the 34-pin Shugart bus. It receives ADF images wirelessly from the GTi over
ESP-NOW, holds them in PSRAM, and generates MFM flux directly. The Gotek is
eliminated from the system entirely.

### v1 definition (deliberately minimal)

| Item | v1 | Deferred |
|---|---|---|
| Density | DD only (250 kbit/s) | HD (500 kbit/s) |
| Format | Amiga trackdisk (11 sec/track) | IBM 720K/1.44M |
| Writes | `/WPRO` asserted always | Write capture + write-back |
| Images resident | 1 | Multi-disk set |
| Host | Amiga 500 internal DF0 | A1200, A2000, external DF1, PC |
| Radio during motor-on | deaf | — |

### Non-negotiables (established during design review)

1. **ESP32-S3-WROOM-1-N16R8.** 8 MB octal PSRAM. Not N8R2.
2. **No flash writes while a disk is mounted.** No NVS, no LittleFS, no OTA.
   A cache suspend of 20–40 ms is unsurvivable at any buffer depth. Buffer
   config changes in RAM, commit on eject.
3. **Refill ISR is `IRAM_ATTR`**, all DMA buffers in internal SRAM, flux task
   pinned to core 1, WiFi initialised from core 0.
4. **Output buffer released at power-on by hardware**, not firmware. The Amiga
   boots faster than the ESP32.
5. **RMT TX buffer ≥ 1024 symbols** (4 KB internal SRAM → ~3 ms slack at DD).

---

## 2. The 34-pin interface

### 2.1 Amiga internal pinout

All odd pins are GND. The Amiga uses a *modified* Shugart pinout — it is **not**
the PC pinout. Three differences will destroy a board if got wrong:

- Amiga selects on **DS0 (pin 10)**; PC drives use DS1
- **`/CHNG` is on pin 2** on Amiga; on PC it is pin 34
- **`/RDY` is on pin 34** on Amiga; PCs have no such signal

| Pin | Signal | Dir (from board) | Notes |
|---|---|---|---|
| 2 | `/CHNG` | **OUT** | Disk change. PC puts density select here. |
| 4 | `/MTR0` | IN | Amiga alternate motor line (drives LED) |
| 6 | n/c | — | |
| 8 | `/INDEX` | **OUT** | Optional for ADF — see §6.3 |
| 10 | `/SEL0` | IN | Drive select 0 — this is DF0 |
| 12 | n/c | — | (`/SEL1` on some machines) |
| 14 | n/c | — | |
| 16 | `/MTR` | IN | Motor on — **latched on `/SEL` falling edge** |
| 18 | `/DIR` | IN | Step direction |
| 20 | `/STEP` | IN | Step pulse |
| 22 | `/WDATA` | IN | Write data (flux from host) |
| 24 | `/WGATE` | IN | Write enable |
| 26 | `/TK0` | **OUT** | Track 0 |
| 28 | `/WPRO` | **OUT** | Write protect |
| 30 | `/RDATA` | **OUT** | **Read data — the flux stream** |
| 32 | `/SIDE` | IN | Head select |
| 34 | `/RDY` | **OUT** | Ready. Required by trackloaders (X-Copy etc.) |

**Count:** 8 inputs, 6 outputs. All active low. All open-collector on the bus.

> **VERIFY BEFORE ROUTING.** Pins 4 and 16 both carry motor-related signals in
> different Amiga models, and pin 12/14 select-line usage varies between A500,
> A1200 and A2000. Buzz out the actual target machine's connector with a meter
> before committing copper. Route pins 4, 12 and 14 to spare GPIO through the
> input buffer so they can be reassigned in firmware.

### 2.2 Electrical character of the bus

- 5 V TTL, **open collector / open drain**, active low
- Host provides pull-ups (typically 1 kΩ to +5 V on 3.5" machines)
- Sink current at 1 kΩ: **~5 mA per line**
- 5.25" systems with 150 Ω termination would need ~33 mA — out of scope for v1
  but affects driver choice if ever targeted

---

## 3. Level translation

The ESP32-S3 is 3.3 V and **not 5 V tolerant**. Every line needs conditioning.

### 3.1 Inputs (host → board)

**2 × 74LVC14A** hex Schmitt-trigger inverter, VCC = 3.3 V.

- LVC family inputs are 5 V tolerant when the part is powered at 3.3 V
- Schmitt hysteresis matters — ribbon cable in a metal case next to a switching
  PSU is a genuinely noisy environment, and `/STEP` glitches cause phantom seeks
- It inverts. Bus signals are already active-low, so a single inversion presents
  active-high logic to the S3 — handle in firmware, don't add a second stage
- Series 100 Ω on each line at the connector for ESD and ringing

Capacity: 12 inverters across two packages, 8 inputs used, 4 spare for the
verify-before-routing signals above.

### 3.2 Outputs (board → host)

**1 × 74LVC07A** hex open-drain buffer, VCC = 3.3 V.

- Open drain is mandatory — a push-pull output fighting the host's pull-up on a
  shared bus will damage something
- Sinks 24 mA min, comfortably above the ~5 mA required
- Output pins tolerate being pulled to 5 V by the host

**The safe-state trick:** fit **10 kΩ pull-ups to 3.3 V on every LVC07A input.**
At power-on the S3's GPIOs are high-impedance; the pull-ups hold the buffer
inputs high, the open drains release, and the bus floats to the host's idle
state. No `/OE` logic, no enable pin, no firmware involvement. The Amiga sees an
absent drive until firmware asserts otherwise.

This is worth being deliberate about — `ESP32FloppyTester` documents exactly the
inverse failure: on that board, flashing the ESP32 puts pins high-Z with pull-ups
and drives SELECT, MOTOR, SIDE and WRITE GATE all active, erasing whatever track
is under the head. The pull-up polarity is the whole difference.

### 3.3 Bus release on deselect

A real drive stops driving the bus when `/SEL` is deasserted. Firmware handles
this: on `/SEL` rising edge, drive all six output GPIOs high (releasing the open
drains) and stop the RMT channel. Microsecond-scale, no hardware gating needed.

Only relevant in a two-drive setup, but implement it from the start — it's three
lines of code and impossible to retrofit into a habit.

### 3.4 Pin remapping — what is and isn't possible

**The one hard rule: direction is baked into copper.** An input-buffer pin can
never become an output, and vice versa. Everything else is firmware.

FlashFloppy establishes the precedent and the scope. Its `interface=` modes remap
**only pins 2 and 34**:

| Mode | Pin 2 | Pin 34 |
|---|---|---|
| `shugart` (Amiga, Atari ST, CPC) | `DSKCHG` | `RDY` |
| `ibmpc` | unused | `DSKCHG` |
| `ibmpc-hdout` | `HD_OUT` | `DSKCHG` |
| `jppc` (Japanese PC) | unused | `RDY` |
| `jppc-hdout` | `HD_OUT` | `RDY` |

Plus `pin02 = auto` / `pin34 = auto` overrides for finer control.

**Critically: every variant of both pins is an output.** `DSKCHG`, `RDY`, `HD_OUT`,
unused — never an input. So both sit on the `74LVC07A` and mode switching costs
nothing in hardware. No dual-path, no bidirectional shifter.

Note that FlashFloppy does *not* remap drive select in firmware — that's a
physical jumper (S0 / S1 / JC on the Gotek's rear).

**Where FluxDrive can do better:** pins 10, 12 and 14 (`/SEL0`, `/SEL1`, `/SEL2`)
are all inputs, as are pins 4 and 6. Route all of them through the input buffer
and drive selection becomes a config value — **no jumper required**. Costs 3 spare
GPIO and 5 inverters, both of which the budget already has.

**Design rule for this board:**

| Pin | Direction | Fixed forever? |
|---|---|---|
| 2 | OUT | `/CHNG` ↔ `HD_OUT` — firmware |
| 34 | OUT | `/RDY` ↔ `/DSKCHG` — firmware |
| 4, 6, 10, 12, 14, 16 | IN | select/motor assignment — firmware |
| 18, 20, 22, 24, 32 | IN | fixed by function |
| 8, 26, 28, 30 | OUT | fixed by function |

That covers every documented interface variant with no hardware change. Only a
host that needs pin 2 or 34 as an *input* would break it, and no known machine
does.

---

## 4. Power tree

### 4.1 Input

The Amiga internal 34-pin connector carries **no power** — all odd pins are GND.
Power must come from the drive power connector (4-pin Berg on the A500 harness:
+5 V, GND, GND, +12 V). Only +5 V is needed; leave +12 V unconnected.

- Reverse polarity protection: series Schottky or P-FET (a reversed Berg is a
  classic way to destroy a board)
- 470 µF electrolytic + 10 µF ceramic bulk on the 5 V rail at entry

### 4.2 3.3 V generation

**Use a buck converter, not an LDO.**

ESP32-S3 with WiFi transmitting peaks around 350–500 mA. From 5 V:

| Regulator | Drop | Dissipation @ 450 mA | Verdict |
|---|---|---|---|
| AMS1117-3.3 (LDO) | 1.7 V | **0.77 W** | runs hot, marginal in SOT-223 |
| AP2112K-3.3 (LDO) | 1.7 V | 0.77 W | 600 mA rated, thermally tight |
| TPS562201 (buck) | — | ~0.15 W | **recommended** |
| MP2359 (buck) | — | ~0.15 W | acceptable alternative |

A hot LDO inside a sealed A500 next to the PSU is asking for thermal drift on a
board whose entire value proposition is timing accuracy. Spend the extra 40p.

### 4.3 Decoupling

- 100 µF + 10 µF + 100 nF at the WROOM-1 3V3 pin — the module's RF bursts are
  the largest transient on the board
- 100 nF per logic IC
- Steady state with radio off is ~50–70 mA, so most of the budget exists purely
  for the ADF transfer window

---

## 5. GPIO allocation

N16R8 consumes GPIO **26–32** (flash) and **33–37** (octal PSRAM). Avoid
strapping pins 0, 3, 45, 46. GPIO 19/20 are USB D-/D+.

Usable on WROOM-1: 1, 2, 4–18, 21, 38–42, 47, 48 (+43/44 if UART0 is sacrificed).
That is ~25 pins against 14 required — comfortable.

| Signal | GPIO | Notes |
|---|---|---|
| `/RDATA` (RMT TX) | 4 | Flux out. Keep trace short, away from switcher. |
| `/WDATA` (RMT RX) | 5 | Deferred to v2, route anyway |
| `/STEP` | 6 | Interrupt |
| `/DIR` | 7 | Sampled at STEP edge |
| `/SIDE` | 15 | |
| `/WGATE` | 16 | Interrupt |
| `/SEL0` | 17 | Interrupt (both edges — motor latch + bus release) |
| `/MTR` | 18 | Sampled at SEL falling edge |
| `/INDEX` | 8 | Optional, see §6.3 |
| `/TK0` | 9 | |
| `/WPRO` | 10 | Tied asserted in v1 |
| `/CHNG` | 11 | |
| `/RDY` | 12 | |
| Status LED | 14 | Mimic drive activity LED |
| Bus pin 4 (`/MTR0`) | 21 | IN — firmware-assignable |
| Bus pin 6 | 38 | IN — firmware-assignable |
| Bus pin 12 (`/SEL1`) | 39 | IN — firmware-assignable |
| Bus pin 14 (`/SEL2`) | 40 | IN — firmware-assignable |
| Spare | 41, 42, 47, 48 | Future: OLED I²C, SD |

Routing pins 4, 6, 12 and 14 to the input buffer is what makes drive-select and
motor-line assignment a firmware config rather than a jumper (§3.4). Four GPIO and
four inverters, both already in budget.

RMT reaches any GPIO through the peripheral matrix, so `/RDATA` placement is a
layout decision, not a constraint. Put it far from the buck converter's switch
node and give it a clean ground return.

---

## 6. Firmware architecture (summary — full detail separate document)

### 6.1 Three states

| State | Radio | Flux engine | Bus |
|---|---|---|---|
| `EMPTY` | listening | idle | `/RDY` deasserted |
| `MOUNTED_BUSY` | deaf | RMT streaming | driven when selected |
| `MOUNTED_IDLE` | listening | idle (motor off) | driven when selected |

The flux engine being idle in `MOUNTED_IDLE` is not a compromise — a real drive
isn't spinning when the motor is off, so silence on `/RDATA` is *correct
emulation*. The radio window falls out of accuracy rather than fighting it.

### 6.2 Memory plan (of 8 MB PSRAM)

| Region | Size |
|---|---|
| ADF, raw sectors | 880 KB |
| Whole disk pre-encoded as MFM bitcells | 1.91 MB |
| **Used** | **~2.8 MB** |
| Free | ~5.2 MB (HD headroom, future multi-disk) |

**Pre-encode all 160 tracks at insert time** (~50 ms, once). `/STEP` then becomes
a pointer change and the encoder leaves the host-deadline path entirely.

### 6.3 Amiga protocol specifics

- **Motor is latched, not level-read.** The drive latches `/MTR` on the falling
  edge of `/SEL`. A naïve `digitalRead(MTR)` reports "off" every time the machine
  deselects, including mid-load. Latch it in the `/SEL` ISR.
- **`/RDY` is required, and pin 34 is dual-purpose.** Amiga hosts expect a drive
  ID sequence on pin 34 when the motor is *disabled*, and `RDY` when the motor is
  *enabled*. FlashFloppy's default `shugart` mode ignores this and attaches `RDY`
  permanently — which works because a mounted image asserting `RDY` happens to
  match the DD drive ID anyway. The accurate approach multiplexes ID and `RDY`
  based on motor state with a realistic ~500 ms motor-on-to-`RDY` delay, and
  FlashFloppy can only do this on AT32F435-based Goteks because slower ones can't
  emulate the signals fast enough.

  **The S3 is comfortably faster than an AT32F435, and the `/SEL`-`/MTR` latch
  state machine this needs is already required for the motor-idle window.** So
  implement the accurate behaviour as the default, not as a premium option. It is
  a genuine fidelity edge over most Goteks in the field, and it's the difference
  between working and not working for HD images and external-drive use.

  AmigaOS tolerates a missing `/RDY`; trackloaders such as X-Copy Pro do not.
- **`/CHNG` handshake.** Assert on eject; clear **only** on a subsequent `/STEP`
  pulse. Otherwise AmigaDOS never notices the new disk.
- **`/INDEX` is optional for ADF.** Paula DMAs raw MFM and hunts `0x4489` sync
  words; it has no rotational-position requirement. Route it, populate it, leave
  it unasserted in v1.
- **Track wrap lands in the gap.** A real Amiga track has padding after sector 11
  before the first sync word. Point the RMT wrap at the middle of that gap — any
  minor discontinuity is invisible because nothing is being decoded there. No
  sub-tick seamlessness required.

### 6.4 Eject transaction

GTi retries `EJECT(txn_id)` at ~200 ms until the S3's motor-off window opens.
Must be **idempotent** (eject on an already-ejected slot returns `DONE`, not an
error — a lost ACK otherwise wedges the GTi) and **atomic** (if motor re-latches
mid-transaction, abort and report `BUSY`; never leave `/CHNG` asserted with the
image still mounted).

Failure case to handle in UI: trackloaders that leave the motor spinning during
gameplay never open a window. Show "waiting for drive idle" rather than a spinner,
and offer force-eject after ~10 s that fires on the next `/SEL` deassert.

---

## 7. Bring-up order

Staged so each step is independently verifiable and nothing depends on the Amiga
until it must.

| # | Step | Pass criterion |
|---|---|---|
| 0 | **Bench gate** (§8) | No gap or jitter at buffer boundary |
| 1 | Board powered, no bus connection | 3.3 V clean, module boots, LVC07A outputs float high |
| 2 | Bus connected, firmware halted | Amiga boots normally, sees no drive |
| 3 | Input capture only | Serial log shows `/SEL`, `/MTR`, `/STEP`, `/SIDE` from real Amiga |
| 4 | Static outputs | `/TK0`, `/WPRO`, `/RDY` assert; Amiga reports a drive present |
| 5 | Hardcoded synthetic track | Amiga reads *something* (garbage acceptable) |
| 6 | Real ADF, one track | Correct sector data on that track |
| 7 | Full disk | Workbench disk boots |
| 8 | ESP-NOW insert from GTi | Wireless load, then boot |
| 9 | Eject transaction | Disk swap recognised by AmigaDOS |

Steps 3 and 4 need no flux engine at all and will shake out most wiring errors.

---

## 8. The bench gate (do this first)

Everything above is contingent on one unvalidated property: **RMT ping-pong
buffer continuity under sustained load.** No Amiga, no level shifters, no ADF
parsing required.

### Setup
- Bare ESP32-S3 dev board, scope on the RMT TX pin
- Synthetic 11-sector Amiga MFM track in PSRAM, 1024-symbol ping-pong
- Loop indefinitely with the wrap point in the track gap
- ESP-NOW flooding the device from a second ESP32 throughout

### Measure
1. Interval histogram — expect tight clusters at 4/6/8 µs, spread < 0.2 µs
2. **Every buffer boundary** — no gap, no doubled interval, no accumulating drift
3. **The wrap point** — same
4. Run for 30+ minutes, not 30 seconds
5. Repeat with radio idle vs flooding — quantify the delta

### Interpreting it

The prior is better than "unknown". `ESP32FloppyTester` writes full MFM tracks to
real disks at 4/6/8 µs intervals and reads them back with passing CRCs — that is
200 ms of gapless flux across roughly 34 consecutive buffer boundaries, on older
silicon, verified magnetically. This test extrapolates 34 proven boundaries to
thousands; it does not ask whether ESP32 flux generation works at all.

**If it fails** and IRAM placement plus core pinning doesn't fix it: the fallback
is an RP2350 as a dumb flux coprocessor over SPI, with the S3 retaining radio and
storage. Leave 4 spare GPIO and an unpopulated footprint against that possibility
— it costs nothing now and saves a respin.

---

## 9. BOM (indicative)

| Qty | Part | Purpose | ~£ |
|---|---|---|---|
| 1 | ESP32-S3-WROOM-1-N16R8 | MCU, 8 MB PSRAM | 4.50 |
| 2 | 74LVC14A (SO-14) | Input Schmitt, 5 V tolerant | 0.60 |
| 1 | 74LVC07A (SO-14) | Output open drain | 0.35 |
| 1 | TPS562201 + L/C | 3.3 V buck | 0.90 |
| 1 | 34-pin IDC male header, 2.54 mm | Bus | 0.40 |
| 1 | 4-pin Berg male | Power | 0.20 |
| — | Passives, 100 Ω series ×14, 10 k ×6 | | 0.80 |
| 1 | microSD socket (**unpopulated**) | Future persistence | 0.30 |
| 1 | PCB, 2-layer, ~50 × 40 mm | | 1.50 |
| | | **Total** | **~£9.55** |

Against a Gotek at ~£15 plus a SuperMini plus a USB socket, and with one fewer
board in the machine.

---

## 10. Open items

| # | Item | Blocks |
|---|---|---|
| 1 | **Bench gate (§8)** | Everything |
| 2 | Buzz out target A500 connector — pins 4, 12, 14 | ~~Routing~~ firmware config only (§3.4) |
| 3 | Confirm A500 drive power connector type and pinout | Power section |
| 4 | Verify `/RDY` timing expectation of X-Copy specifically | v1 acceptance |
| 5 | Decide write policy for v2 (volatile RAM-disk vs SD vs push-to-GTi) | SD footprint |
| 6 | ESP-NOW protocol spec — separate document | Step 8 |
| 7 | Mechanical: does the board need to fit the DF0 bay, or sit loose? | Outline |
| 8 | Measure actual S3 WiFi ISR stall tail — validates policy-deaf assumption | Buffer sizing |

Item 8 is the one that could still change a design decision: if the WiFi ISR tail
is materially worse than the ~250 µs assumed, the 1024-symbol buffer stops being
comfortable and the deaf-while-spinning policy needs to become hardware-deaf.

---

*OMEGAWARE — draft, not yet reviewed against a physical machine.*
