# FluxDrive v1 rev B — pass-through to the original drive, DF0/DF1 swap

**Status:** v0.1, 2026-09-30, draft for Dimitri's review. Nothing is built from it yet.
**Based on:** the v1 hardware spec `docs/superpowers/specs/2026-09-28-fluxdrive-v1-hardware-design.md` v0.4 ("the v1
spec", which keeps describing rev A), its reviews in `docs/reviews/`, and the research of 2026-09-30 into the Nano-Tek
Rev 2.0 pass-through, the A500's floppy wiring and rev A's board (scratch reports in `build/revb-research/`, not
committed; every fact below that came from them carries its source).
**Branch:** `feature/rev-b`.

Rev B is rev A plus one new function: the A500's original internal drive stays usable next to FluxDrive, and either
of the two can be DF0. Everything the v1 spec says still holds unless this document changes it; §13 lists every change
to the v1 spec. Rev A is not ordered: rev B is the first FluxDrive board to be built.

## 1. Goal and decisions

Dimitri's decisions (2026-09-30, in the design conversation):

1. **Both drives work at the same time, and he picks which one is DF0** (and so which one boots).
2. **Approach A**: the swap happens on the FluxDrive board, in the manner of his Nano-Tek Rev 2.0, with FluxDrive's
   outputs gated by its select in logic. (Rejected: fixed roles with the real drive as DF0 and FluxDrive as DF1 —
   Kickstart 1.3 then cannot boot an ADF; and a swapper in the CIA-B socket — it collides with the board, which lies
   over the 8520 and Gary, and loses the GTi control.)
3. **"FluxDrive DF0 + real drive DF1" is prepared but not fitted** (mode 4, §3): its parts are laid out as unfitted
   pads plus a pad for one wire to the motherboard's raw motor line.
4. **Control:** from the GTi (and the web page), plus an optional 3-position switch in the case that always wins.
5. **Default without firmware:** the real drive is DF0 and DF1 is off, so the A500 behaves as stock. A latch keeps the
   chosen mode while the ESP32 restarts.
6. **External drives:** the Amiga has DF0–DF3. When the internal DF1 is in use, an external drive on the DB23 must be
   set to DF2 or DF3.
7. **Room:** at least 20 mm towards the A500's front, measured from the rev A template's north edge; the drive's ribbon
   reaches; J6 with its plug fits, if need be without the shield or with a cut-out in it. The fitted drive uses +12 V.
8. **Order:** rev A is skipped; rev B gets spec, schematic and layout now and is the board that is ordered.

## 2. Facts this design leans on

Sources: [SCH] A500 Rev 6a/7 schematic, https://amigawiki.org/dnl/schematics/A500_R6.pdf ("p8" = PDF page 8);
[A2K] A2000CR Rev 6 schematic, https://amigawiki.org/dnl/schematics/A2000_R6.pdf, sheet 10; [HRM] Hardware Reference
Manual appendix E, https://www.theflatnet.de/pub/cbm/amiga/AmigaDevDocs/hard_e.html; [GARY] Gary specification,
https://www.devili.iki.fi/mirrors/haynie/systems/amiga2k/docs/gary.txt; [CHI] Chinon F-354C specification,
http://www.bitsavers.org/pdf/chinon/Chinon_F-354C_135TPI_Double-Sided_3.5_In_Specifications.pdf; [TEAC] TEAC
FD-235HF specification, https://hxc2001.com/download/datasheet/floppy/thirdparty/Teac/FD-235HF-C9xx.pdf; [UAE] WinUAE
`disk.cpp`, https://github.com/tonioni/WinUAE; [AROS] https://github.com/aros-development-team/AROS; [NT] the Nano-Tek
Rev 2.0 spec, `C:\Claude projecten\Nano-Tek\docs\superpowers\specs\2026-09-27-nano-tek-gti-design.md`.

- **CN11 carries** /SEL0 (pin 10), /SEL1 (pin 12, live on the A500) and /MTR0 on pins 4 and 16 (the same net, Gary's
  latched "DF0 motor on"). Pins 6 and 14 are not connected. There is **no motor line for DF1**: the raw motor line
  (CIA-B PB7, pin 17 → Gary pin 7 → U36 → `_MTRX`) reaches only DB23 pin 8 ([SCH] p5, p7, p8; [GARY] §2.1, §3.4.17).
- **Shared with the DB23:** every CN11 signal except /SEL0 and /MTR0 — the six Amiga-driven lines and also the six
  drive outputs (/RDY, /CHNG, /TRK0, /WPROT, /DKRD, /INDEX), each with a 100 pF EMI filter ([SCH] p8). The v1 spec
  §2.1 lists only the Amiga-driven ones; §13 corrects it. So an internal DF1 on CN11 pin 12 and an external DF1 on DB23
  pin 21 are the same select: the internal DF1 and an external drive set to DF1 clash ([NT]:304).
- **A real internal drive** answers its DS0 input (pin 10), does not latch the motor (pin 16 runs the spindle directly,
  "independently of the DRIVE SELECT signals", [CHI] §5-2(2)), has open-collector outputs that are active only while
  it is selected ([CHI] §5-2(1)), and terminates its inputs with about 1 kΩ ([CHI] §5-4, §5-5; the TEAC: "1k ±5 %,
  unremovable"). It gives no drive ID; Kickstart-compatible code treats an empty ID on DF0 as a legacy drive ([UAE]
  disk.cpp:161-162; [AROS] `disk_intern_init.c`:49-55).
- **A drive as DF1** needs the raw /MTR latched on the falling edge of /SEL1 and a DD ID on /RDY. Without them it
  "will spin continuously … and DF1 won't show up" (https://www.pureamiga.co.uk/2022/01/02/dual-a500-600-1200-internal-drives/).
  Commodore did both on the A2000 with a 74LS74 and a 74LS38 ([A2K] sheet 10). FluxDrive as DF1 needs neither: it
  treats "selected" as "running" and holds /RDY low while selected, which is the DD ID (FlashFloppy `src/floppy.c`:163-170).
- **Booting:** Kickstart 1.x boots only from DF0; 2.x and later boot DF1–DF3 at lower priorities, and much software
  expects hardware DF0 (RKM Libraries "Events At BOOT Time",
  https://discmaster.textfiles.com/file/18/Amiga%20Developer%20CD%20v2.1.iso/Reference/HTML/Libraries_Manual_guide/node041E.html?html=true;
  RKM Devices "Amiga BootStrap",
  https://discmaster.textfiles.com/file/18/Amiga%20Developer%20CD%20v2.1.iso/Reference/HTML/Devices_Manual_guide/node007C.html?html=true;
  OpenSwitcher README, https://github.com/Ilkeston-Electronics/OpenSwitcher). The drive that boots games must be
  hardware DF0.
- **DF1 is probed only at start-up** ([AROS] `trackdisk_device.c`:582-608), so turning it on or off takes a reset.
- **ID polling selects a drive for a single CIA write** ([AROS] `disk_intern_init.c`:36-48): with two drives on one
  bus, releasing FluxDrive's outputs in firmware is too slow. This is v1's open item O14 (spec review BUS-9); rev B
  closes it with gating in logic.
- **Currents:** a drive peaks at about 1.0 A on +5 V while seeking or spinning up ([TEAC] Table 7.1-1); the Chinon
  family also takes 100–340 mA from +12 V ([CHI] §3-2). FluxDrive's eFuse limits at about 0.95 A (v1 spec §5).

## 3. Modes and control

| Mode | DF0 | DF1 | Real drive's pin 10 / pins 4+16 | Fitted |
|---|---|---|---|---|
| 1 | FluxDrive | — (an external drive may be DF1) | inactive / motor off | yes |
| 2 | real drive | — (an external drive may be DF1) | /SEL0 / /MTR0 | yes |
| 3 | real drive | FluxDrive | /SEL0 / /MTR0 | yes |
| 4 | FluxDrive | real drive | /SEL1 / DF1 motor latch | prepared, not fitted |

Two control bits select the mode: **DF0_FD** (1 = FluxDrive is DF0) and **DF1_EN** (1 = the internal DF1 exists: in
mode 3 that is FluxDrive, in mode 4 the real drive). Mode 1 is DF0_FD = 1, DF1_EN = 0; mode 2 is 0/0; mode 3 is 0/1;
mode 4 is 1/1 with the mode-4 parts fitted. Without them, DF0_FD = 1 with DF1_EN = 1 behaves as mode 1.

- **Mode latch.** Both bits live in a dual D flip-flop with preset and clear (74LVC74A), powered from +3V3, so they
  survive an ESP32 restart (RESET button, crash, OTA). The firmware sets them by putting the wanted values on the two D
  inputs and pulsing one clock. The clock only reaches the flip-flops while /SEL0 is inactive (§4.6), so DF0 never
  changes in the middle of an access; a clock during an access takes effect when /SEL0 goes inactive.
- **Power-on default:** an RC on the DF0_FD flip-flop's clear gives "real drive is DF0"; a solder jumper moves the RC
  to its preset for "FluxDrive is DF0". DF1_EN clears to 0 at power-on; a solder jumper on its preset gives "DF1
  always". An unflashed or halted FluxDrive therefore leaves a stock A500 (or, with the jumper, the v1 behaviour).
- **Switch.** An optional ON-OFF-ON toggle on a 3-pin header (J7): one side pulls the DF0_FD preset low (FluxDrive is
  DF0), the other its clear (real drive is DF0), the middle leaves the choice to the firmware. It always wins; the
  firmware reads the result back (DF0_STATE) and follows with a disk change (§4.5).
- **Swapping DF0** is "direct" by default: the firmware changes DF0_FD only after /SEL0 has been quiet for at least
  500 ms with /MTR0 off, holds the virtual disk change for 2.5 s, and reports "busy" after 10 s without a quiet moment
  ([NT]:212-215). With the optional reset wire (§4.8) it can instead swap at a reset of the Amiga, or ask the GTi user
  to allow a reset and pull it itself.
- **DF1 on/off** takes effect at the next reset. It defaults to off; the GTi shows which drive is DF1 and warns that an
  external drive must then be DF2 or DF3.
- **Real drive absent:** choosing "real drive is DF0" with no drive on J6 leaves the Amiga without DF0, exactly as an
  A500 with its drive unplugged. The firmware warns when it sees no /INDEX from DF0 while the motor runs.

## 4. Logic

All new logic is 74LVC (3.3 V supply, 5 V-tolerant inputs, Ioff), like U2–U4. It works on the **buffered, active-high**
signals behind the existing 100 Ω + 74LVC14A inputs, never on the raw bus nets. Names: SEL0, SEL1, MTR0 are the U3
outputs (1 = active); a trailing `_N` marks an active-low net.

### 4.1 Isolation from the ESP32's reset glitch

GPIO1–17 are driven low for about 60 µs at power-up and at every ESP32 reset (v1 spec §6). In v1 the U3 outputs go to
GPIO17 (SEL0), GPIO9 (SEL1) and GPIO11 (MTR0) directly; in rev B the same nets also drive the steering logic, and a
reset glitch would briefly deselect the real drive. So **every GPIO in the glitch group that touches a logic net does
so through a 1 kΩ series resistor**; the logic side stays at the 74LVC output's level. Control outputs from the
ESP32 are active-high with a pull-down, so a glitch low is their idle state.

### 4.2 FluxDrive's select

- `SEL1_EN = SEL1 AND DF1_EN` — a 74LVC1G157 wired as an AND (S = DF1_EN, I1 = SEL1, I0 = GND).
- `SEL_FD = DF0_FD ? SEL0 : SEL1_EN` — a 74LVC1G157 (S = DF0_FD, I1 = SEL0, I0 = SEL1_EN).
- `SEL_FD_N = NOT SEL_FD` — U2's spare Schmitt inverter (pins 9 → 8, tied off in rev A).

The firmware keeps reading SEL0 (GPIO17) and SEL1 (GPIO9) and, knowing the mode from DF0_STATE and its own DF1
setting, watches the right one; SEL_FD itself is for the gating.

### 4.3 Output gating

Each of U4's six inputs becomes `X_N OR SEL_FD_N` (two 74LVC32A, 2 gates spare): a FluxDrive that is not selected
always releases /CHNG, /INDEX, /TRK0, /WPROT, /DKRD and /RDY within a few ns of the select edge, whatever the firmware
does. v1's rule stays: GPIO low = assert, input with the 10 kΩ pull-up = release. SEL_FD_N drives the six OR inputs
from a push-pull output (the breadboard showed that a weak select net cannot drive several gate inputs,
`docs/input/FluxDrive_v0.1_review_notes.md`:83-85).

### 4.4 The real drive's connector J6

J6 is a second 2×17 box header with CN11's pinout (odd pins GND, pin 3 NC):

| J6 pins | Connection |
|---|---|
| 2, 8, 18, 20, 22, 24, 26, 28, 30, 32, 34 | 1:1 to the same J1 pins (the drive's outputs sit in parallel with FluxDrive's; they are active only while the drive is selected) |
| 10 | `REAL_SEL`, open-drain, 4k7 to +5V_A |
| 4, 16 | `REAL_MTR`, open-drain, 4k7 to +5V_A |
| 6, 12, 14 | not connected: the drive's own termination holds them inactive, so a drive strapped DS1–DS3 never answers |

- `REAL_SEL = DF0_FD ? M4_SEL : SEL0` — a 74LVC1G157 (S = DF0_FD, I0 = SEL0, I1 = M4_SEL).
- `REAL_MTR = DF0_FD ? M4_MTR : MTR0` — a 74LVC1G157 (S = DF0_FD, I0 = MTR0, I1 = M4_MTR).
- M4_SEL and M4_MTR come from the mode-4 parts (§4.7); a solder jumper ties each to GND while those are not fitted, so
  in mode 1 the real drive sees "not selected, motor off".
- Both drive J6 through two channels of a SN74LVC3G06 (triple inverter, open-drain): input 1 pulls the pin low. The
  third channel drives the optional reset wire (§4.8).
- **Bypass:** two open solder jumpers, J6.10 ↔ J1.10 and J6.4/16 ↔ J1.16, make the real drive a fixed DF0 even with
  FluxDrive's logic unpowered. They may only be closed with the switch on "real drive" (mode 2 forced); in any other
  mode both drives would answer /SEL0. The README says so.

### 4.5 Virtual disk change

A SN74LVC1G38 (2-input NAND, open-drain) pulls J1.2 low while `CHNG_REQ AND SEL0`: bus DF0 selected, whichever drive
that is. The firmware holds CHNG_REQ for 2.5 s after every DF0 change, so AmigaDOS sees a new disk in DF0 even when
the real drive's own change flop is clear ([NT]:196).

### 4.6 Mode latch

- A 74LVC74A: flip-flop A holds DF0_FD, flip-flop B holds DF1_EN (the Q outputs drive §4.2 and §4.4).
- D inputs from the GPIOs DF0_REQ and DF1_REQ; one clock for both, `MODE_CLK = SEL0 ? 0 : MODE_CLK_REQ` (a
  74LVC1G157: S = SEL0, I0 = MODE_CLK_REQ, I1 = GND), MODE_CLK_REQ with a 100 kΩ pull-down.
- The firmware keeps both D inputs equal to the present state except while it requests a change, so a stray clock is
  harmless; with MODE_CLK_REQ low (idle, and during an ESP32 restart) no clock reaches the flip-flops at all.
- Presets and clears: the power-on RC and its jumpers (§3), the switch (J7), and 10 kΩ pull-ups to +3V3.
- DF0_STATE (flip-flop A's Q) goes back to a GPIO through 1 kΩ (§4.1).

### 4.7 Mode 4, prepared (unfitted pads)

Laid out and routed, but not assembled (DNP, no paste):
- a wire pad `MTRX` for the raw motor line (DB23 pin 8, which is U36's open-collector output and needs the pull-up
  below, or CIA-B U8 pin 17), 4k7 to +5V_A and 100 Ω into a Schmitt inverter: U3's gate that rev A used for J1 pin 14
  (§7), fitted anyway;
- a SN74LVC1G74 motor latch: D = motor on, clocked by SEL1's rising edge (the /SEL1 falling edge), cleared at power-on;
  its Q is M4_MTR;
- `M4_SEL = DF0_FD AND SEL1_EN` (a 74LVC1G157 wired as an AND);
- the DD ID for the real drive as DF1: /RDY (J1.34) pulled low while `M4_SEL AND NOT motor` (a SN74LVC1G38 fed by M4_SEL
  and the latch's /Q), as the A2000's U203 does ([A2K] sheet 10).

Fitting mode 4 means: these four parts and their resistors, the wire, and moving the two jumpers of §4.4 from GND to
M4_SEL and M4_MTR. The latch timing (MTR and SEL1 change in one CIA write, [UAE] disk.cpp:3637-3645; Ian Stedman's
adapter V2.1, https://www.ianstedman.co.uk/v2-x-floppy-adaptor/) is checked with a logic analyser before anyone relies
on it.

### 4.8 Reset wire (optional)

A pad `RST` for a wire to the Amiga's /RESET (for example the keyboard connector), with a pull-up to +5V_A:
- in: 100 Ω into U3's gate that rev A used for J1 pin 4 (§7), out to a GPIO (RST_ACT) through 1 kΩ;
- out: the third SN74LVC3G06 channel pulls /RESET low while RST_REQ is high (100 kΩ pull-down), so the GTi can reboot
  the Amiga after a swap.

Without the wire both stay idle and the firmware uses the "direct" swap.

### 4.9 Parts added

| Part | Package | LCSC | Qty | Use |
|---|---|---|---|---|
| 74LVC1G157GW | SOT-363 | C135822 | 5 | §4.2 (2), §4.4 (2), §4.6 (1) |
| 74LVC32APW | TSSOP-14 | C6087 | 2 | §4.3 |
| 74LVC74A | TSSOP-14 | chosen in the plan | 1 | §4.6 |
| SN74LVC3G06 | VSSOP-8 | chosen in the plan | 1 | §4.4, §4.8 |
| SN74LVC1G38DBVR | SOT-23-5 | C2867613 | 1 | §4.5 |
| 2×17 box header (as J1) | — | C601943 | 1 | J6 |
| TE 171825-4 | — | C210162 | 1 | J6pwr (§6) |
| 1×3 pin header | — | — | 1 | J7, the switch (hand-soldered, optional) |
| resistors, capacitors, solder jumpers | 0402/0603 | as rev A | ~20 | pull-ups, isolation, RC, bypass |
| DNP: 74LVC1G157GW, SN74LVC1G74DCUR (C70285), SN74LVC1G38DBVR | | | 1 each | §4.7 |

The plan checks each LCSC number and its stock; a part without a JLC-assemblable number is replaced by one with the
same function and pinout family.

## 5. Bus loading and pull-ups

With the real drive's 1 kΩ termination on the bus and an external drive possible, /STEP, /DIR and /SIDE would draw
5 + 5 + 5 + 1.6 = 16.6 mA from CIA-B with FluxDrive's 1 kΩ, over the 13 mA of the v1 spec §4.2. Rev B:

| Line | Rev A | Rev B | Why |
|---|---|---|---|
| /STEP, /DIR, /SIDE | 1 kΩ | 4k7 | 12.7 mA with the real drive and an external drive (the Nano-Tek's choice, [NT]:169) |
| /SEL0 | 1 kΩ | 1 kΩ | the real drive is no longer on /SEL0 (it gets REAL_SEL) |
| /SEL1 | 10 kΩ | 10 kΩ | unchanged |
| /DKWD, /DKWE | 4k7 | 4k7 | unchanged; on an A500+ (74LS05, 8 mA) a real drive plus an external drive exceed the rating whatever FluxDrive does (v1 spec §4.2, BUS-10) |
| J6.10, J6.4/16 | — | 4k7 to +5V_A | the drive's 1 kΩ plus 4k7: 6.1 mA into the open-drain output |

The HRM's "1000-ohm pull-up on each device" is then met by the real drive on those lines; with no real drive on J6,
/STEP, /DIR and /SIDE see 4k7 plus the CIA's own pull-up, which is enough for their microsecond pulses.

## 6. Power

- **J6pwr**, a second TE 171825-4 (vertical, polarised, pin 1 = +5 V), sits in parallel with J2 **before** the eFuse:
  +5V_IN, GND, GND and **+12 V**. J2 pin 4 (not connected in rev A) now carries +12 V to J6pwr pin 4 and nowhere else.
- The drive's current (about 1 A peak on +5 V, up to about 0.35 A on +12 V) never passes the eFuse, which stays at about
  0.95 A for FluxDrive's own ≈ 0.4 A. If the drive ran behind it, spin-up and seeks would trip it.
- The J2 → J6pwr paths are a pour or at least 0.8 mm wide, with at least two vias per layer change; both GND pins of
  each header get their own vias to In1. The motor's return current stays in the power strip, away from U2–U4.
- The unfitted SMAJ13A pad on +5V_IN now protects both. A reversed plug on J6pwr reaches the drive unprotected,
  exactly as in a stock A500.

## 7. ESP32 GPIOs

Rev B needs six control signals. They come from the spare header J5 (GPIO13, 14, 47, 48), the unused GPIO12, and two
inputs rev A reads but the A500 does not need:
- J1 **pin 4** is the same net as pin 16 (/MTR0). Its input chain (R25 DNP, R26, R27, U3 gate 1→2, GPIO4) goes; U3's
  gate is reused for the reset wire (§4.8).
- J1 **pin 14** is not connected on the A500. Its input chain (R31, R32, R33, U3 gate 5→6, GPIO10) goes; U3's gate is
  reused for mode 4's MTRX (§4.7). Pin 6 keeps its input for later hosts.

| GPIO | Rev A | Rev B | Direction, idle |
|---|---|---|---|
| 47 | J5 | MODE_CLK_REQ | out, 100 kΩ pull-down |
| 48 | J5 | DF0_REQ | out |
| 13 | J5 | DF1_REQ | out |
| 14 | J5 | CHNG_REQ | out, 100 kΩ pull-down |
| 12 | NC | DF0_STATE | in, through 1 kΩ |
| 4 | J1 pin 4 input | RST_ACT | in, through 1 kΩ |
| 10 | J1 pin 14 input | RST_REQ | out, 100 kΩ pull-down |
| 9, 11, 17 | SEL1, MTR0, SEL0 | unchanged, now through 1 kΩ (§4.1) | in |

J5 goes; the UART1 "wired GTi" option of the v1 spec §6 moves to the UART0 header J4 or is dropped (plan decides with
the firmware plan). GPIO47/48 are glitch-free; GPIO4, 10, 12, 13 and 14 are in the glitch group, which the idle-low
convention of §4.1 makes harmless.

## 8. Firmware requirements (changes to the v1 spec §9)

The firmware is a separate project; these are the requirements rev B puts on it.
- **Role:** read DF0_STATE and the stored DF1 setting; as DF0 watch SEL0, as DF1 watch SEL1. The hardware gating makes
  the v1 rule "outputs gated by /SEL0 only" a firmware courtesy, no longer the only guard.
- **As DF1** (mode 3): there is no motor line, so "selected" means "running"; hold /RDY asserted (the DD ID); keep the
  virtual rotation running so /INDEX and /DKRD are right whenever DF1 is selected.
- **Setting the mode:** put the wanted DF0_FD and DF1_EN on DF0_REQ/DF1_REQ, pulse MODE_CLK_REQ, verify DF0_STATE, and
  return MODE_CLK_REQ low; keep DF0_REQ/DF1_REQ at the present state otherwise. Restore the stored mode within about
  0.3 s after start-up if the latch is at its power-on default and the switch is in the middle.
- **Swap policy:** direct (§3) or, with the reset wire, at reset; DF1 changes need a reset (RST_REQ if wired, otherwise
  ask the user). CHNG_REQ for 2.5 s after every DF0 change.
- **GTi:** DRIVE_GET, DRIVE_SET (DF0 = FluxDrive, DF1 on, reboot) and DRIVE_CFG (swap policy), as proposed for the
  Nano-Tek ([NT]:258-260), over the FluxDrive's ESP-NOW link; a drive page on the web interface.
- **Storage:** the chosen mode is written to flash only while no disk is mounted (v1 spec §9, flash-write rule).

## 9. Board and layout

- **Outline:** 60 mm wide (unchanged, the room between CN12 and the electrolytic) and about 72.5 mm long. J6 sits 17.78
  mm north of J1, same orientation, pin 1 on the same side (no twisted ribbon); everything north of J1 moves north by
  that much, the module with its antenna 0.5 mm inside the north edge as in rev A (the module stays centred; the range
  test O5 decides about LESP-2). J1 stays a plug-on socket or a box header, as the builder chooses; J6 is always a box
  header on the top; J6pwr sits in the west power strip next to J2.
- **Re-placement cures rev A's layout weaknesses** (layout review "The rebuilt board" and "Final review"):
  - /INDEX and /CHNG come from buffer gates at the west end, near J1 pins 2 and 8, so INDEX_D and CHNG_D no longer run
    along the whole board and the row A–B channel is free for the `_B` nets (rev A: SIDE_B 111 mm, PIN14_B 71 mm,
    DKWD_B 67 mm with 7 vias);
  - the unfitted 220 pF pads sit next to their own pull-ups;
  - every +3V3 pad gets its own via, checked by a test that follows the track path;
  - no track closer than 0.8 mm to the GND pin rows of J1 and J6, and none between their rows (rule areas as rev A's
    "J1 rows"), checked by a test;
  - GND stitching along the whole antenna keep-out border (a rule in `tools/pcb_stitch.py`), checked by a test;
  - the deferred tool and test minors of `docs/reviews/2026-09-30-build-rulings.md`, in one batch at the start.
- **Hand routes** (`tools/pcb_prefan.py`) are redone for the new placement; `/DKRD_D` stays short and on one layer.
- **Test pads:** SEL_FD, REAL_SEL, REAL_MTR, DF0_STATE and MODE_CLK in addition to rev A's sixteen.
- **Silkscreen:** J6 "TO DRIVE", J1 "TO CN11", J6pwr "DRIVE POWER", J7 "DF0: FD / GTi / REAL", the bypass jumpers
  with the warning of §4.4, and the mode-4 pads marked "mode 4, see README".
- The ESP32 module stays a hand-placed part (`tools/assembly.py`).

## 10. Verification

1. **Logic, exhaustively, on the exported netlist:** a test evaluates the steering circuit (§4.2–§4.8) as gates for
   every combination of mode bits, switch position, jumper settings, mode-4 fitted or not, SEL0, SEL1, MTR0, the six
   X_N lines and CHNG_REQ, and checks SEL_FD, the six U4 inputs, REAL_SEL, REAL_MTR and J1.2 against §3's table (the
   Nano-Tek's `tests/logic_cases.py` checks 288 cases the same way).
2. The rev A tests, updated (gate pairs, pull-up values, the GPIO table, the removed inputs); ERC and DRC clean with
   zone refill and schematic parity; `tools/pcb_place.py --check`.
3. The four specialist reviews (bus, power, ESP32, PCB and code) on the schematic and again on the layout, then a
   final whole-branch review.
4. A new fit template and a printed dummy with an IDC plug on J6, tried in Dimitri's A500 with the real drive's ribbon.
5. **Rev B is done when** everything in the v1 spec's done criteria holds, plus: with no firmware the A500 boots from
   the real drive as if FluxDrive were not there; mode 1 boots Workbench 1.3 from an ADF; mode 2 boots an original disk
   from the real drive; mode 3 copies a disk from FluxDrive (DF1) to the real drive (DF0) with X-Copy; an external
   drive set to DF2 works next to mode 3; a swap from the GTi and one with the switch are both seen by AmigaDOS.

## 11. Open items

| # | Item | Decides |
|---|---|---|
| O5 | Range test with a WROOM-1 board inside the closed A500, now with the antenna about 18 mm further forward | module variant, LESP-2 |
| O15 | TE 171825-4 outline, now for J2 and J6pwr | footprint |
| R1 | The real drive's input termination (1 kΩ from pins 4, 10, 16 and 20 to its +5 V, drive unplugged) | pull-up values |
| R2 | The real drive is strapped DS0 (pin 10), /CHNG on 2, /RDY on 34 | J6 pin table |
| R3 | Does a reset clear Gary's MTR0 latch (v1 O13) | swap at reset |
| R4 | Kickstart's DF0/DF1 probing and its timing, on a logic analyser (only AROS and WinUAE were read) | ID and gating timing |
| R5 | Mode 4's motor latch timing (MTR and SEL1 in one CIA write) | mode 4 |
| R6 | Is a "direct" DF0 swap safe with trackdisk's per-drive head position ([NT]:345) | default swap policy |
| R7 | Dimitri's motherboard revision (A500 Rev 5/6/8A) and its CN11 and /MTR0 wiring | scope |

Closed by rev B: v1's O14 (outputs gated by select in logic).

## 12. Before ordering (Dimitri)

The README's "Before ordering" for rev A, plus: the range test O5 with the antenna in its rev B position; R1 and R2 on
the real drive; the fit dummy with J6 and its plug (the shield may need a cut-out).

## 13. Changes to the v1 spec

When rev B is accepted, the v1 spec gets a v0.5 that points here for rev B and takes in:
- §1: "Not in v1: pass-through to a real drive" becomes "rev B: pass-through and DF0/DF1 swap (rev B spec)".
- §2.1: the six drive outputs are shared with the DB23 too, with 100 pF filters ([SCH] p8).
- §4.2: /STEP, /DIR, /SIDE pull-ups 4k7 in rev B; the J1 pin 4 and pin 14 inputs go.
- §4.3: outputs gated by select in logic (rev B §4.3); O14 closed.
- §5: J2 pin 4 carries +12 V to J6pwr; drive power before the eFuse.
- §6: the GPIO table of rev B §7; J5 goes.
- §8: the rev B outline and placement (rev B §9).
- §9: the firmware requirements of rev B §8.
- §11: rev B's done criteria (rev B §10).
