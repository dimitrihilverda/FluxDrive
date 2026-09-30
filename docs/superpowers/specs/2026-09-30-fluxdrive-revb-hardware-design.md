# FluxDrive v1 rev B — pass-through to the original drive, DF0/DF1 swap

**Status:** v0.2, 2026-09-30, for Dimitri's review. v0.1 was reviewed by four agents (logic with an exhaustive
simulation, Amiga facts, power/parts/board, completeness) before anyone read it; v0.2 takes in their findings and
Dimitri's answers of the same day. Nothing is built from it yet.
**Based on:** the v1 hardware spec `docs/superpowers/specs/2026-09-28-fluxdrive-v1-hardware-design.md` v0.4 ("the v1
spec", which keeps describing rev A), its reviews in `docs/reviews/`, the research of 2026-09-30 into the Nano-Tek
Rev 2.0 pass-through, the A500's floppy wiring and rev A's board, and Mez's audit of rev A (all scratch reports in
`build/revb-research/`, `build/revb-review/` and `build/mez-verify/`, not committed; every fact below that came
from them carries its source).
**Branch:** `feature/rev-b`.

Rev B is rev A plus one new function: the A500's original internal drive stays usable next to FluxDrive, and either
of the two can be DF0. Everything the v1 spec says still holds unless this document changes it; §13 lists every change
to the v1 spec.

## 1. Goal and decisions

Dimitri's decisions (2026-09-30):

1. **Both drives work at the same time, and he picks which one is DF0** (and so which one boots), and which one is
   DF1. The GTi shows which drive is DF0 and which is DF1.
2. **Approach A**: the swap happens on the FluxDrive board, in the manner of his Nano-Tek Rev 2.0, with FluxDrive's
   outputs gated by its select in logic. (Rejected: fixed roles with the real drive as DF0 and FluxDrive as DF1 —
   Kickstart 1.3 then cannot boot an ADF; and a swapper in the CIA-B socket — it collides with the board, which lies
   over the 8520 and Gary, and loses the GTi control.)
3. **"FluxDrive DF0 + real drive DF1" is prepared but not fitted** (mode 4, §3): its parts are laid out as unfitted
   pads plus a pad for one wire to the motherboard's raw motor line.
4. **Control:** from the GTi (and the web page), plus an optional 3-position switch in the case that always wins.
5. **Default without firmware:** the real drive is DF0 and DF1 is off, so the A500 behaves as stock. A latch keeps the
   chosen mode while the ESP32 restarts.
6. **External drives:** the Amiga has DF0–DF3. When the internal DF1 is in use, an external drive must not answer
   DF1 (§3, "External drives").
7. **Room:** at least 20 mm towards the A500's front, measured from the rev A template's north edge; the drive's ribbon
   reaches; J6 with its plug fits, if need be without the shield or with a cut-out in it. The fitted drive uses +12 V.
8. **Order:** rev A may be ordered for an early range test, bring-up and firmware work, but rev B does not wait for
   it; rev B is the version Dimitri continues with.
9. **Spare header J5 stays**, as a 4-pin header for an OLED, a piezo or a UART (§7), without giving up any of the
   swap functions.
10. **The ESP32 module stays hand-placed** (as rev A, `tools/assembly.py`), which keeps the choice between the
    WROOM-1 and the WROOM-1U open until the range test; its ground pad gets a solder-through hole (§9).

## 2. Facts this design leans on

Sources: [SCH] A500 Rev 6a/7 schematic, https://amigawiki.org/dnl/schematics/A500_R6.pdf ("p8" = PDF page 8);
[A2K] A2000CR Rev 6 schematic, https://amigawiki.org/dnl/schematics/A2000_R6.pdf, sheet 10; [HRM] Hardware Reference
Manual appendix E, https://www.theflatnet.de/pub/cbm/amiga/AmigaDevDocs/hard_e.html; [GARY] Gary specification,
https://www.devili.iki.fi/mirrors/haynie/systems/amiga2k/docs/gary.txt; [CHI] Chinon F-354C specification (a PC-type
relative of the A500's FB-354), http://www.bitsavers.org/pdf/chinon/Chinon_F-354C_135TPI_Double-Sided_3.5_In_Specifications.pdf;
[TEAC] TEAC FD-235HF specification, https://hxc2001.com/download/datasheet/floppy/thirdparty/Teac/FD-235HF-C9xx.pdf;
[UAE] WinUAE `disk.cpp`, https://github.com/tonioni/WinUAE; [AROS] https://github.com/aros-development-team/AROS
(`arch/m68k-amiga/devs/trackdisk/`, `arch/m68k-amiga/disk/`); [NT] the Nano-Tek Rev 2.0 spec,
`C:\Claude projecten\Nano-Tek\docs\superpowers\specs\2026-09-27-nano-tek-gti-design.md`.

- **CN11 carries** /SEL0 (pin 10), /SEL1 (pin 12, live on the A500) and /MTR0 on pins 4 and 16 (the same net, Gary's
  latched "DF0 motor on"). Pins 6 and 14 are not connected. There is **no motor line for DF1**: the raw motor line
  (CIA-B U8 PB7, pin 17 → Gary pin 7 → U36 → `_MTRX`) reaches only DB23 pin 8 ([SCH] p5, p7, p8; [GARY] §2.1, §3.4.17).
- **Shared with the DB23:** every CN11 signal except /SEL0 and /MTR0 — the six Amiga-driven lines and also the six
  drive outputs (/RDY, /CHNG, /TRK0, /WPROT, /DKRD, /INDEX), each with a 100 pF EMI filter ([SCH] p8). So an internal
  DF1 on CN11 pin 12 and an external DF1 on DB23 pin 21 are the same select net.
- **Select lines shift along the external chain:** "SEL1B* is not drive 1, but rather the first external drive", and
  the select lines "are shifted as they pass through a string of daisy chained devices" ([HRM]). A standard external
  drive (A1010/A1011) plugged straight into the DB23 answers pin 21 and is DF1.
- **A real internal drive** answers its DS0 input (pin 10), does not latch the motor (pin 16 runs the spindle directly,
  "independently of the DRIVE SELECT signals", [CHI] §5-2(2)), has open-collector outputs that are active only while
  it is selected ([CHI] §5-2(1)), and terminates its inputs, pins 4 (IN USE) and 16 among them, with about 1 kΩ
  ([CHI] §5-2(8), §5-4, §5-5; the TEAC: "1k ±5 %, unremovable"). It gives no drive ID; Kickstart-compatible code treats
  an empty ID on DF0 as a legacy drive ([UAE] disk.cpp:161-162; [AROS] `disk_intern_init.c`:49-55).
- **A drive as DF1** needs the raw /MTR latched on the falling edge of /SEL1 and a DD ID on /RDY. Without them it
  "will spin continuously … and DF1 won't show up" (https://www.pureamiga.co.uk/2022/01/02/dual-a500-600-1200-internal-drives/).
  Commodore did both on the A2000 with a 74LS74 and a 74LS38 ([A2K] sheet 10). The HRM guarantees MTRXD 1.4 µs of set-up
  and hold around the select edge ([HRM]). FluxDrive as DF1 needs neither: it treats "selected" as "running" and holds
  /RDY low while selected, which reads as the DD ID (FlashFloppy `src/floppy.c`:163-170; [AROS] disk.h:62-65).
- **Booting:** Kickstart 1.x boots only from DF0 (RKM Libraries "Events At BOOT Time",
  https://discmaster.textfiles.com/file/18/Amiga%20Developer%20CD%20v2.1.iso/Reference/HTML/Libraries_Manual_guide/node041E.html?html=true);
  2.x and later boot DF1–DF3 at lower priorities (RKM Devices "Amiga BootStrap",
  https://discmaster.textfiles.com/file/18/Amiga%20Developer%20CD%20v2.1.iso/Reference/HTML/Devices_Manual_guide/node007C.html?html=true),
  and much software expects hardware DF0 (OpenSwitcher README, https://github.com/Ilkeston-Electronics/OpenSwitcher).
- **Drive probing:** disk.resource reads all four IDs once at start-up; trackdisk then recalibrates each unit and
  mounts DF1–DF3 only if their ID is not empty ([AROS] `disk_intern_init.c`:166-171, `trackdisk_device.c`:582-608).
  Turning DF1 on or off therefore takes a reset, and whatever FluxDrive presents must be in place before that probe.
- **ID polling selects a drive for one CIA write** (about 2–3 µs with the following read, [AROS]
  `disk_intern_init.c`:36-48): with two drives on one bus, releasing FluxDrive's outputs in firmware is too slow. This
  is v1's open item O14 (spec review BUS-9); rev B closes it with gating in logic.
- **Disk-change polling:** trackdisk polls every 2 s plus 500 ms, restarting its timer after its per-unit loop, so the
  period is at least 2.5 s ([AROS] `trackdisk_device.c`:389-391, 453-458); it recalibrates a unit on removal and on
  insertion (`trackdisk_device.c`:87-90, 426-430), which is what makes a swap with its per-unit head position safe.
- **Resets:** the keyboard connector carries `_KBRESET` into Gary pin 5 (with RP501 10 kΩ); the 68000's RST and the
  general RESET are separate nets ([SCH] p2, p5, p7). A software reboot never shows on `_KBRESET`.
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
mode 4 is 1/1 with the mode-4 parts fitted. Without them, 1/1 behaves as mode 1 with no DF1, and the firmware never
sets it (a firmware setting says whether mode 4 is fitted, default no).

- **Mode latch.** Both bits live in a dual D flip-flop with preset and clear (74LVC74A), powered from +3V3, so they
  survive an ESP32 restart (RESET button, crash, OTA, USB flashing). The firmware sets them by putting the wanted
  values on the two D inputs and pulsing one clock. The clock only reaches the flip-flops while neither /SEL0 nor
  /SEL1 is active (§4.6); a request during an access takes effect when the bus goes idle. Both bits are read back
  (DF0_STATE, DF1_STATE, §7).
- **Power-on default:** power-on RCs give "real drive is DF0" and "DF1 off" (mode 2, a stock A500). A copper-bridged
  3-pad jumper moves flip-flop A's RC from its clear to its preset for "FluxDrive is DF0" (mode 1); fit it for the
  everyday mode if the builder normally uses mode 1 or has no real drive. There is no "DF1 always" jumper: without
  firmware FluxDrive is no drive.
- **Switch J7** (three wire pads: 1 = FluxDrive, 2 = GND, 3 = real drive) for an optional ON-OFF-ON toggle in the case.
  Its throws pull flip-flop A's preset or clear low, each through 1 kΩ with 100 nF to GND against bounce and pick-up
  on the wire. It always wins and acts **immediately**, also during an access, as on the Nano-Tek ([NT] §9): the README
  says to move it only with the drive LED off or while the Amiga is held in reset. Moving it out of mode 3 leaves the
  Amiga with a dead DF1 until the next reset. The firmware sees the result on DF0_STATE and follows with a disk change.
- **Changing DF0 directly** (mode 1 ↔ mode 2, DF1 off): the firmware changes DF0_FD only after /SEL0 and /SEL1 have
  both been quiet for at least 500 ms with /MTR0 off, then holds the virtual disk change (§4.5), and reports "busy"
  after 10 s without a quiet moment ([NT]:212-215).
- **Changing DF1:** turning DF1 on (0 → 1, entering mode 3) may be applied at once; the Amiga sees it after its next
  reset. Every change that removes or replaces a DF1 — DF1 off, leaving mode 3 by a DF0 change, entering or leaving
  mode 4 — is applied only while the Amiga is in reset (RST_ACT, §4.8) or at power-on. Without the reset wire the
  firmware stores it, the GTi asks the user for a keyboard reset or a power cycle, and it is applied then.
- **External drives:** with the internal DF1 on, the first external drive must not answer DB23 pin 21. Use a drive with
  a DF2/DF3 switch, or a DB23 select-shifting adapter (its pin 9 to the drive's pin 21, pin 20 to pin 9, pin 21 open).
  A standard A1010/A1011 plugged in directly is DF1 and clashes. With DF1 off (modes 1, 2) an external DF1 works as on a
  stock A500. The GTi shows the DF0 and DF1 roles and gives this warning when DF1 is turned on.
- **Real drive absent:** choosing "real drive is DF0" with no drive on J6 leaves the Amiga without DF0, exactly as an
  A500 with its drive unplugged. The GTi shows "real drive (not checked)".

## 4. Logic

All new logic is 74LVC on +3V3 with 5 V-tolerant inputs; the parts whose outputs meet a 5 V net (the open-drain
drivers) have Ioff. It works on the **buffered, active-high** signals behind the existing 100 Ω + 74LVC14A inputs, never
on the raw bus nets. Names: SEL0, SEL1, MTR0 are the U3 outputs (1 = active); a trailing `_N` marks an active-low net.
Unused gate inputs are tied to GND or +3V3; no input floats (v1 spec §4.2).

### 4.1 Isolation from the ESP32's reset glitch and pull-ups

- GPIO1–17 are driven low for about 60 µs at power-up and at every ESP32 reset, and GPIO18 low then high (v1 spec
  §2.3). **Every GPIO that reads a logic net does so through a 1 kΩ series resistor**, so the logic side stays at the
  74LVC output's level: GPIO9 (SEL1), GPIO11 (MTR0), GPIO17 (SEL0), and the read-backs of §7.
- **Control outputs are active-high with a 10 kΩ pull-down** (MODE_CLK_REQ, CHNG_REQ, RST_REQ): a glitch low is their
  idle state, and 10 kΩ holds them below the 74LVC's 0.8 V input-low level even if an internal pull-up (about 45 kΩ)
  is enabled by mistake. The firmware never enables the internal pull-ups on these pins (§8).
- **The two D inputs** (DF0_REQ, DF1_REQ) each have 100 kΩ from their own flip-flop's Q, so an undriven D (ESP32 in
  reset, download mode) holds the present state and a stray clock changes nothing.

### 4.2 FluxDrive's select

- `SEL1_EN = SEL1 AND DF1_EN` — a 74LVC1G157 wired as an AND (S = DF1_EN, I1 = SEL1, I0 = GND).
- `SEL_FD = DF0_FD ? SEL0 : SEL1_EN` — a 74LVC1G157 (S = DF0_FD, I1 = SEL0, I0 = SEL1_EN).
- `SEL_FD_N = NOT SEL_FD` — U2's spare Schmitt inverter (pins 9 → 8, tied off in rev A).

DF0_FD and DF1_EN here are the flip-flops' Q outputs.

### 4.3 Output gating and output buffers

- Each output GPIO X_N passes an OR with SEL_FD_N (two 74LVC32A, eight gates: six for the outputs, one for §4.6, one
  spare with its inputs tied). A FluxDrive that is not selected releases /CHNG, /INDEX, /TRK0, /WPROT, /DKRD and /RDY
  within a few ns of the select edge, whatever the firmware does. v1's rule stays: GPIO low = assert, input with the
  10 kΩ pull-up = release. SEL_FD_N drives the OR inputs from a push-pull output (a weak select net cannot drive
  several gate inputs, `docs/input/FluxDrive_v0.1_review_notes.md`:83-85).
- **Two output buffers:** U4 (74LVC07A) keeps /DKRD, /TRK0, /WPROT and /RDY, at the east end near J1 pins 26–34; its two
  spare inputs are tied to +3V3. A new SN74LVC2G07 (open-drain, Ioff) at the west end drives /CHNG (J1 pin 2) and
  /INDEX (J1 pin 8). Every output keeps its 33 Ω series resistor. This removes rev A's 81 mm /CHNG_D and 43 mm
  /INDEX_D, the cause of its long `_B` detours (layout review, "The rebuilt board").

### 4.4 The real drive's connector J6

J6 is a second 2×17 box header with CN11's pinout (odd pins GND, pin 3 NC):

| J6 pins | Connection |
|---|---|
| 2, 8, 18, 20, 22, 24, 26, 28, 30, 32, 34 | 1:1 to the same J1 pins (the drive's outputs sit in parallel with FluxDrive's; they are active only while the drive is selected) |
| 10 | `REAL_SEL`, open-drain, 4k7 to +5V_A |
| 4, 16 | `REAL_MTR`, open-drain, 4k7 to +5V_A |
| 6, 12, 14 | 10 kΩ to +5V_A each, nothing else: inactive, so a drive strapped DS1–DS3 never answers |

- `REAL_SEL = DF0_FD ? M4_SEL : SEL0` — a 74LVC1G157 (S = DF0_FD, I0 = SEL0, I1 = M4_SEL).
- `REAL_MTR = DF0_FD ? M4_MTR : MTR0` — a 74LVC1G157 (S = DF0_FD, I0 = MTR0, I1 = M4_MTR).
- M4_SEL and M4_MTR come from the mode-4 parts (§4.7). A copper-bridged 3-pad jumper each ties them to GND while those
  are not fitted, so in mode 1 the real drive sees "not selected, motor off".
- Both drive J6 through a SN74LVC2G06 (dual inverter, open-drain, Ioff): input 1 pulls the pin low.
- **Bypass:** two copper-bridged 3-pad jumpers whose centre pad is J6.10 (resp. J6.4/16). Delivered state: pads 1–2
  bridged, joining J6's pin to the 2G06 output and its 4k7. Bypass: cut 1–2 and bridge 2–3 on both, which joins J6.10 to
  J1.10 and J6.4/16 to J1.16 and disconnects the 2G06 from J6, so no loop can form in any mode or power state (v0.1's
  two-pad jumpers latched /SEL0 and /MTR0 low through the 2G06). The real drive is then a fixed DF0 even with
  FluxDrive's logic unpowered; FluxDrive must not also be DF0, so the bypass requires DF0_FD held at 0: a solder jumper
  "REAL" from flip-flop A's clear to GND, or J7 on the real-drive throw (modes 2 and 3 remain possible). Silkscreen and
  README say so.
- **Load:** J6.10 sinks the drive's 1 kΩ plus 4k7 (6.1 mA); J6.4/16 sinks two drive terminations plus 4k7 (11.1 mA),
  within the 2G06's rating.

### 4.5 Virtual disk change

A SN74LVC1G38 (2-input NAND, open-drain, 33 Ω to J1.2) pulls /CHNG low while `CHNG_REQ AND SEL0`: bus DF0 selected,
whichever drive that is. After every DF0 change the firmware holds CHNG_REQ until it has seen /SEL0 active at least once
during the hold and then either a /STEP with /SEL0 active or /SEL0 released, but at most 10 s. A fixed hold can end just
before trackdisk's next poll (§2); this rule makes sure AmigaDOS sees the change and recalibrates the unit.

### 4.6 Mode latch

- A 74LVC74A (Nexperia 74LVC74APW,118, Schmitt action on all inputs, so the RC edges are fine): flip-flop A holds
  DF0_FD, flip-flop B holds DF1_EN (their Q outputs drive §4.2 and §4.4).
- D inputs from the GPIOs DF0_REQ and DF1_REQ (§4.1: 100 kΩ from Q). One clock for both:
  `MODE_CLK = BUSY ? 0 : MODE_CLK_REQ` with `BUSY = SEL0 OR SEL1` (the spare 74LVC32A gate and a 74LVC1G157: S = BUSY,
  I0 = MODE_CLK_REQ, I1 = GND). A clock during an access of either internal drive reaches the flip-flops when the bus
  goes idle; with MODE_CLK_REQ low (idle, and during an ESP32 restart) no clock reaches them at all.
- Presets and clears have 10 kΩ pull-ups to +3V3. Power-on: one RC (10 kΩ to +3V3, 1 µF to GND, a Schottky across the
  resistor so a short +3V3 dip discharges it) on flip-flop B's clear, and one on flip-flop A's clear or, through the
  3-pad jumper of §3, its preset. J7 and the "REAL" bypass jumper act on flip-flop A only, so they never touch DF1_EN.
- DF0_STATE (Q_A) and DF1_STATE (Q_B) go back to GPIOs through 1 kΩ (§7).

### 4.7 Mode 4, prepared (unfitted pads)

Laid out and routed, but not assembled (DNP, no paste), in packages that can be fitted by hand (SOT-23, SC-70):
- a wire pad `MTRX` for the raw motor line: CIA-B U8 pin 17 is preferred (it is ahead of Gary and U36; DB23 pin 8, U36's
  open-collector output, also works); 4k7 to +5V_A and 100 Ω into U3's gate that rev A used for J1 pin 14 (§7). That
  gate's input keeps rev A's fitted 100 kΩ to +3V3, so it does not float without mode 4;
- a SN74LVC1G175 motor latch (D flip-flop with clear): D = motor on (the U3 gate's output), clocked by SEL1's rising
  edge (the /SEL1 falling edge), **clear = DF1_EN**, so it is cleared at power-on and held clear whenever DF1 is off
  (v0.1 let it run in mode 1, where an external DF1's motor would have spun the real drive). Its Q is M4_MTR;
- `M4_SEL = DF0_FD AND SEL1_EN` (a 74LVC1G157 wired as an AND);
- the DD ID for the real drive as DF1: /RDY (J1.34, through 33 Ω) pulled low while `M4_SEL AND NOT M4_MTR` by a
  SN74LVC1G38, its "NOT M4_MTR" from U3's gate that rev A used for J1 pin 6 (§7), as the A2000's U203 does
  ([A2K] sheet 10). That gate's input gets a fitted 100 kΩ to GND.

Fitting mode 4 means: these three ICs and their resistors, the wire, and moving the two jumpers of §4.4 from GND to
M4_SEL and M4_MTR, and setting "mode 4 fitted" in the firmware. The latch timing (R5) is checked with a logic analyser
before anyone relies on it.

### 4.8 Reset wire (optional)

A pad `RST` for a wire to `_KBRESET` (keyboard connector CN13 pin 3, or Gary U5 pin 5). No pull-up on the pad (RP501
on the motherboard); 100 kΩ to +3V3 on the buffer side, so RST_ACT idles without the wire.
- in: 100 Ω into U3's gate that rev A used for J1 pin 4 (§7), out to a GPIO (RST_ACT) through 1 kΩ. It sees keyboard
  resets (Ctrl-Amiga-Amiga) and power-up, not software reboots;
- out: a SN74LVC1G06 (inverter, open-drain, Ioff) pulls `_KBRESET` low while RST_REQ is high (10 kΩ pull-down); the
  firmware pulses it for 250 ms, so the GTi can reboot the Amiga to apply a DF1 change.

Without the wire both stay idle, DF0 changes use the direct rule and DF1 changes wait for a power cycle (§3).

### 4.9 Parts added

| Part | Package | LCSC | Qty | Use |
|---|---|---|---|---|
| 74LVC1G157GW,125 | SOT-363 | C135822 | 5 | §4.2 (2), §4.4 (2), §4.6 (1) |
| 74LVC32APW,118 | TSSOP-14 | C6087 | 2 | §4.3, §4.6 |
| 74LVC74APW,118 | TSSOP-14 | C6100 | 1 | §4.6 |
| SN74LVC2G06DBVR | SOT-23-6 | C402162 | 1 | §4.4 |
| SN74LVC1G06DBVR | SOT-23-5 | C840103 | 1 | §4.8 |
| SN74LVC2G07DBVR | SOT-23-6 | C37708 | 1 | §4.3 (/CHNG, /INDEX) |
| SN74LVC1G38DBVR | SOT-23-5 | C2867613 | 1 | §4.5 |
| TPS259531 (as U5) | WSON-8 | C2155674 | 1 | §6, the drive's eFuse |
| 2×17 box header (as J1) | — | C601943 | 1 | J6 |
| TE 171825-4 | — | C210162 | 1 | J6pwr (§6) |
| 1×4 pin header, 2.54 mm | — | — | 1 | J5 (§7, hand-soldered, optional) |
| resistors, capacitors, Schottkys, jumpers | 0402/0603, SOD-323 | as rev A | ~40 fitted | pull-ups, isolation, RCs, filters, 33 Ω, decoupling (one 100 nF per IC) |
| DNP: 74LVC1G157GW, SN74LVC1G175 (SOT-23-6), SN74LVC1G38DBVR, the MTRX resistors | | | | §4.7 |

The SN74LVC3G06 of v0.1 is out: JLC had 3 in stock. Stock figures (JLC, 2026-09-30): C135822 7,815; C6087 25,503;
C6100 5,454; C402162 10,258; C840103 5,490; C37708 152,596; C2867613 1,914; C601943 2,075; C210162 5,495. The plan
checks each again and adds the SN74LVC1G175's number. Removed from rev A: the J1 pin 4, 6 and 14 input resistors (§7).

## 5. Bus loading and pull-ups

With the real drive's 1 kΩ termination on the bus and an external drive possible, /STEP, /DIR and /SIDE would draw
5 + 5 + 5 + 1.6 = 16.6 mA from CIA-B with FluxDrive's 1 kΩ, over the 8520's 13 mA (v1 spec §4.2). Rev B:

| Line | Rev A | Rev B | Why |
|---|---|---|---|
| /STEP, /DIR, /SIDE | 1 kΩ | 4k7 | 12.7 mA with the real drive and one external drive (the Nano-Tek's choice, [NT]:169); with no real drive, 4k7 and the CIA's pull-up give τ ≈ 0.3 µs against pulses of at least 1.4 µs |
| /SEL0 | 1 kΩ | 1 kΩ | the real drive is no longer on /SEL0 (it gets REAL_SEL) |
| /SEL1 | 10 kΩ | 1 kΩ | now a real select (FluxDrive's in mode 3, and it gates the outputs): 10 kΩ with the 100 pF DB23 filter gave a 0.3–0.45 µs edge; 1 kΩ is 6.6 mA alone, 11.6 mA with an external DF1 (modes 1 and 2) |
| /DKWD, /DKWE | 4k7 | 4k7 | unchanged; on an A500+ (74LS05, 8 mA) a real drive plus an external drive exceed the rating whatever FluxDrive does (v1 spec §4.2, BUS-10) |
| J6.10, J6.4/16 | — | 4k7 to +5V_A | §4.4 |
| J6.6, 12, 14 | — | 10 kΩ to +5V_A | inactive for any strapping |

Two external drives (DF2 and DF3) next to the real drive reach 17.7 mA on /STEP, /DIR and /SIDE, outside the 8520's
guaranteed VOL — as a stock A500 with two external drives already does (16.6 mA). The README says so.

## 6. Power

- **J6pwr**, a second TE 171825-4 (vertical, polarised, pin 1 = +5 V), carries the drive's power: pin 1 = +5V_DRIVE,
  pins 2 and 3 = GND, pin 4 = **+12 V** (J2 pin 4, not connected in rev A, now carries +12 V to J6pwr pin 4 and nowhere
  else).
- **+5V_DRIVE comes from +5V_IN through a second TPS259531** (the same part as U5, so no new part type), with its
  current limit at about 1.5 A (R_ILM ≈ 1.37 kΩ, TI Eq. 4) and its own dV/dt capacitor; it shares U5's EN/UVLO divider.
  The drive's current (about 1 A peak) never passes U5, which stays at about 0.95 A for FluxDrive's own ≈ 0.4 A.
  Its 5.7 V clamp protects the drive against a reversed plug on **J2** (+12 V on +5V_IN), and with it the bus lines the
  drive's terminations would otherwise pull towards 12 V (above the 6.5 V maximum of U2, U3 and the open-drain drivers).
  A reversed plug on J6pwr itself (or a crossed drive cable) still reaches the drive unprotected, as in a stock A500.
- **J2's pin 1** now carries FluxDrive's and the drive's current: about 1.4 A at the drive's peak, against the
  171825-4's 2 A rating (R9 measures the drive's peak).
- The J2 → J6pwr paths are a pour or at least 0.8 mm wide, with at least two vias per layer change; both GND pins of
  each header get their own vias to In1. The motor's return current stays in the power strip, away from U2–U4.
- **Drive power cable** (hand-made, in the README's part list): 2 × TE 171822-4 housings with 170204-2 contacts, AWG
  20–22, pin 1 to pin 1, its length taken from the fit dummy. The README asks for a continuity check (+5 V on pin 1,
  +12 V on pin 4) before the drive is plugged in, and says never to plug J6 without J6pwr: an unpowered drive's
  terminations pull the shared lines to about 0.9 V, which reads as asserted.
- The unfitted SMAJ13A on +5V_IN stays; it protects the eFuses' 20 V input maximum, not a 5 V drive.
- The reversed-plug bench test of the v1 spec §11 runs with nothing on J6 or J6pwr.

## 7. ESP32 GPIOs

Rev B needs seven control signals and two read-backs. They come from the spare header J5 of rev A (GPIO13, 14, 47,
48), the unused GPIO12, and three inputs rev A reads but the A500 does not need:
- J1 **pin 4** is the same net as pin 16 (/MTR0). Its input chain (R25 DNP, R26, R27, U3 gate 1→2, GPIO4) goes; U3's
  gate is reused for the reset wire (§4.8).
- J1 **pin 6** and **pin 14** are not connected on the A500. Their input chains (R28–R33, U3 gates 13→12 and 5→6, GPIO8
  and GPIO10) go; U3's gates are reused for mode 4 (§4.7). Rev B is an A500 board; a later host that needs pins 6 or 14
  gets them in its own revision.

| GPIO | Rev A | Rev B | Direction, idle |
|---|---|---|---|
| 47 | J5 | MODE_CLK_REQ | out, 10 kΩ pull-down |
| 48 | J5 | DF0_REQ | out, 100 kΩ from Q_A |
| 13 | J5 | DF1_REQ | out, 100 kΩ from Q_B |
| 14 | J5 | CHNG_REQ | out, 10 kΩ pull-down |
| 10 | J1 pin 14 input | RST_REQ | out, 10 kΩ pull-down |
| 12 | NC | DF0_STATE | in, through 1 kΩ |
| 8 | J1 pin 6 input | DF1_STATE | in, through 1 kΩ |
| 4 | J1 pin 4 input | RST_ACT | in, through 1 kΩ |
| 9, 11, 17 | SEL1, MTR0, SEL0 | unchanged, now through 1 kΩ (§4.1) | in |
| 18, 3 | free | **J5**: 1×4 header GND / 3V3 / IO18 / IO3 | free for an I2C OLED (SCL 18, SDA 3, the usual 4-pin module order), a piezo or UART1 |

- GPIO47/48 are glitch-free; GPIO4, 8, 10, 12, 13 and 14 are in the glitch group, which §4.1 makes harmless. GPIO18
  glitches low then high, harmless for J5's uses. GPIO3 is free because the JTAG-select eFuse is never burned (v1
  spec §9); GPIO45 and GPIO46 stay unused (strapping).
- J5 sits next to module pins 11 (IO18) and 15 (IO3), on the west side, routed on B.Cu (F.Cu under the module is a
  no-track area). Its pins are labelled on the silkscreen.

## 8. Firmware requirements (changes to the v1 spec §9)

The firmware is a separate project; these are the requirements rev B puts on it.
- **First thing in `app_main` and in the panic handler:** drive CHNG_REQ, RST_REQ and MODE_CLK_REQ low. Never enable
  the internal pull-ups on GPIO4, 8, 10, 12, 13, 14, 47 or 48 (v1 §9's rule that gave J5 internal pull-ups is void).
- **Start-up:** read DF0_STATE and DF1_STATE and adopt them as the current mode. Only after a power-on reset
  (`esp_reset_reason() == ESP_RST_POWERON`) apply the stored mode, by the rules of §3 (at power-on every change is
  allowed); after any other reset keep the latch. The stored mode must be in the latch, and as DF1 the /RDY answer and
  /TRK0 tracking must be live, **before Kickstart's disk.resource probe** after a cold boot (R4 measures when that is);
  if the application starts too late, do it in a bootloader hook with the PSRAM memory test and boot-time image
  validation off.
- **Setting the mode:** before every clock, set DF0_REQ and DF1_REQ from DF0_STATE and DF1_STATE, change only the bit
  that is meant to change, pulse MODE_CLK_REQ, and verify the read-back once both selects have been idle. A DF0
  request that DF0_STATE does not follow means the switch forces DF0: report "DF0 set by the switch" to the GTi and
  stop writing DF0 until DF0_STATE changes. No mode writes while AMIGA_PWR reads low (on USB alone /SEL0 reads asserted
  and blocks the clock anyway).
- **Change rules:** as §3 (DF0 direct only with DF1 off and both selects quiet; DF1 removal or replacement only in reset
  or at power-on; RST_REQ pulse 250 ms if the reset wire is fitted).
- **Outputs:** set every X_N from the drive's own state (ready or ID, /TRK0, /WPROT, /CHNG, the /INDEX and /DKRD
  stream) continuously, whether or not the drive is selected, and never switch an output on a select edge; the gates of
  §4.3 do all the select timing (the firmware still reads the select for /STEP and disk-change handling). This replaces the v1 §9 rule "outputs are gated by /SEL0 only … while deselected all six are
  released".
- **As DF0:** /RDY follows a stock drive (motor on, disk in, up to speed, released a short time after motor-off); the DD
  ID on DF0 (v1 §9) becomes a setting, default off, because some software expects none (S.T.A.G, [UAE] disk.cpp:160-162).
- **As DF1** (mode 3): there is no motor line, so the drive is "running" from a /SEL1 assertion longer than trackdisk's
  poll and ID reads until 3 s after /SEL1 was last active; the v1 rule "radio off while the motor runs" follows that
  definition. /RDY is held asserted (the DD ID) and the virtual rotation keeps running, so /INDEX and /DKRD are right
  whenever DF1 is selected.
- **Virtual disk change:** the hold rule of §4.5.
- **GTi:** DRIVE_GET, DRIVE_SET (DF0 = FluxDrive or real drive, DF1 on/off, reboot) and DRIVE_CFG (swap policy,
  settings), as proposed for the Nano-Tek ([NT]:258-260), over the FluxDrive's ESP-NOW link; the opcodes are fixed in
  the shared contract with the GTi. A drive page on the web interface shows DF0 and DF1 and the switch state.
- **Settings:** "reset wire fitted", "mode 4 fitted" (both default no), "power-on default" (for the display), "DD ID on
  DF0" (default no). The chosen mode is written to flash only while no disk is mounted (v1 spec §9).

## 9. Board and layout

- **Outline:** 60 mm wide (unchanged, the room between CN12 and the electrolytic). J6 sits 17.78 mm north of J1, same
  orientation, pin 1 on the same side (no twisted ribbon). Rev A's 2.4 mm strip south of J1 goes (its test pads move
  into the band between J1 and J6), so the board is about 60 × 70 mm; the placement task fixes the length after
  placing and legalising every rev B part, at most 74.5 mm (rev A plus decision 7's 20 mm). The module with its
  antenna stays centred, 0.5 mm inside the north edge; if the range test O5 fails, the fallback is the WROOM-1U on the
  same footprint (§9, "Module"). J1 stays a plug-on socket or a box header, as the builder chooses; J6 is always a box
  header on the top; J6pwr sits in the west power strip next to J2, clear of J6's body.
- **Connector rules** (replacing v0.1's, which no route could meet: J6's GND row faces J1, so every 1:1 net must cross
  it):
  - J1 (hand-soldered, on either side): no track between its rows or within 0.8 mm of its GND row, on both layers; no
    test-pad stubs through it any more (rev A's notches go).
  - J6 (a top box header, soldered on B.Cu): on F.Cu one 0.2 mm track may pass centred through each gap between its
    pins and between its rows; on B.Cu, J1's rule applies.
  - J1 pin n runs straight to J6 pin n on F.Cu; J1.6/10/12/16 end at the logic.
  - J6's courtyard is SMD-free like J1's; the connector-zone test covers both (LCODE-9).
- **Rev A's layout weaknesses are cured** (layout review "The rebuilt board" and "Final review"):
  - /INDEX and /CHNG from the west-end buffer (§4.3), so the row A–B channel is free for the `_B` nets (rev A:
    SIDE_B 111 mm, PIN14_B 71 mm, DKWD_B 67 mm with 7 vias); a test caps each `_B` net at 1.5 × its pad-to-pad length;
  - the unfitted 220 pF pads sit on their net after the 100 Ω, next to their own pull-ups;
  - every IC supply pin and every decoupling capacitor's +3V3 pad has its own via to In2, and C17/L1 two; a test
    follows the track path (not the straight-line distance);
  - no track closer than 0.8 mm to J1's GND row (above);
  - GND stitching at most 3 mm apart along the whole antenna keep-out border (a rule in `tools/pcb_stitch.py`, checked
    by a test);
  - the deferred tool and test minors of `docs/reviews/2026-09-30-build-rulings.md` (with LCODE-8), in one batch at the
    start.
- **Module:** hand-placed (`tools/assembly.py`). Its ground pad (pin 41) gets a 1.0 mm plated solder-through hole at
  its centre with the mask open on both sides; the four inner thermal vias, which would overlap it, go, and the other
  eight stay tented (Mez's audit, `build/mez-verify/`). The footprint also takes the WROOM-1U-N16R8 (C3013946, the same
  pads; its U.FL sits at the pin-40 corner, and its cable must leave the shield).
- **Hand routes** (`tools/pcb_prefan.py`) are redone for the new placement; `/DKRD_D` stays short and on one layer.
- **Test pads:** rev A's sixteen, the connector-side ones moved into the J1–J6 band, plus SEL_FD, REAL_SEL, REAL_MTR,
  DF0_STATE, DF1_STATE and MODE_CLK.
- **Silkscreen:** J6 "TO DRIVE", J1 "TO CN11", J6pwr "DRIVE POWER – plug before J6", J7 "DF0: FD / GND / REAL", J5's pin
  names, the bypass jumpers with "cut 1-2, bridge 2-3, jumper REAL", the power-on jumper "DF0 at power-on", and the
  mode-4 pads marked "mode 4, see README".
- **Jumpers as delivered:** every jumper that starts closed is a copper-bridged 3-pad footprint (JLC does not close
  solder jumpers): the bypass pair (1–2), the M4_SEL/M4_MTR pair (to GND), the power-on jumper (to clear).

## 10. Verification

1. **Logic, exhaustively, on the exported netlist:** a combinational test evaluates the circuit of §4 as gates, with
   every bus net as a wired-AND of all its open-drain drivers (both bypass states included) iterated to a fixed point,
   for every combination of mode bits, switch position, jumper states, mode 4 fitted or not (its latch output a free
   input), SEL0, SEL1, MTR0, the six X_N lines and CHNG_REQ; expected values come from §3's table and the §4 equations,
   and the outputs checked include SEL_FD, the six buffer inputs, REAL_SEL, REAL_MTR, J1.2, J1.34, RST and MODE_CLK
   (v0.1's review found its bypass loop and mode-4 motor fault this way). A second, sequential test steps the latches
   through every order of SEL0/SEL1 edges, clock requests, switch moves and power-on, including mode 1 with mode 4
   fitted and the control GPIOs in their reset state and with their internal pull-ups enabled.
2. The rev A tests, updated (gate pairs, pull-up values, the GPIO table, the removed inputs, the two output buffers);
   ERC and DRC clean with zone refill and schematic parity; `tools/pcb_place.py --check`.
3. The four specialist reviews (bus, power, ESP32, PCB and code) on the schematic and again on the layout, then a
   final whole-branch review.
4. A new fit template and a printed dummy with an IDC plug on J6 and the drive power cable, tried in Dimitri's A500
   with the real drive's ribbon lying as in use.
5. **Rev B is done when** everything in the v1 spec's done criteria holds, plus:
   - with no firmware the A500 boots from the real drive as if FluxDrive were not there;
   - mode 1 boots Workbench 1.3 from an ADF; mode 2 boots an original from the real drive;
   - in mode 3, X-Copy booted from a real disk in the real drive (Kickstart 1.3), or on Kickstart 2.x+ from FluxDrive
     as DF1 with DF0 empty, copies a disk from FluxDrive (DF1) to the real drive (DF0);
   - an external drive on DF2 (named: a drive with a DF2 switch or a select-shifting adapter) works next to mode 3;
   - a DF0 swap from the GTi and one with the switch are both seen by AmigaDOS; with the reset wire, a DF1 change at a
     keyboard reset works;
   - a RESET press, an OTA update and a USB flash in mode 3 leave DF0 and DF1 unchanged, with no pulse on J6.10,
     J6.4/16 or `_KBRESET` (scoped);
   - the bypass (cut and bridged, jumper REAL) boots the real drive with FluxDrive unpowered.

## 11. Open items

| # | Item | Owner | How | When |
|---|---|---|---|---|
| O5 | Range test, antenna about 18 mm further forward, the drive's ribbon lying as in use | Dimitri | WROOM-1 dev board in the closed A500 | before ordering rev B |
| O7 | Mounting of the plug-on variant, now with J6 and J6pwr plugged | Dimitri | printed dummy | before ordering |
| O15 | TE 171825-4 outline, for J2 and J6pwr; the J6pwr plug clears J6's body | plan | TE drawing | before the layout freezes |
| — | C601943 body at most 52 mm, now for J1 and J6 | Dimitri | part drawing | before ordering |
| R1 | The drive's termination on pins 4, 6, 10, 12, 14, 16 and 20 | Dimitri | ohmmeter to its +5 V, drive unplugged | before the layout freezes |
| R3 | Does a reset clear Gary's MTR0 latch (v1 O13) | bring-up | scope /MTR0 across Ctrl-Amiga-Amiga | bring-up |
| R4 | When Kickstart's disk.resource probe runs after a cold boot and a reset (KS 1.3 and 3.x), against the ESP32's start-up time | Dimitri / firmware | logic analyser on CN11 | before the firmware's start-up code is fixed |
| R5 | Mode 4's latch timing: does Kickstart keep the HRM's 1.4 µs, or change MTR and SEL1 in one CIA write ([UAE] disk.cpp:3637-3645) | bring-up | logic analyser on CIA-B pins 14 and 17 | only for mode 4 |
| R6 | A direct DF0 swap with trackdisk's per-unit head position ([NT]:345) | bring-up | test | bring-up |
| R7 | Dimitri's motherboard revision (Rev 5/6/8A) and its CN11 and /MTR0 wiring | Dimitri | look at the board | before the layout freezes |
| R8 | trackdisk's disk-change poll period on KS 1.3 and 3.x | Dimitri / firmware | logic analyser, with R4 | before the firmware's swap code is fixed |
| R9 | The drive's peak current on +5 V (spin-up, seek) | Dimitri | shunt in the CN12 cable | before the layout freezes |
| R10 | Stock of the new parts at order time (§4.9) | order | JLC BOM tool | at ordering |

Closed by rev B: v1's O14 (outputs gated by select in logic). v0.1's R2 (drive strapping) is settled: the drive works on
CN11 today, so it answers DS0 on pin 10.

## 12. Before ordering (Dimitri)

The README's "Before ordering" for rev A, plus O5, O7, R1, R7 and R9 above, and the fit dummy with J6, its plug and
the drive power cable (the shield may need a cut-out).

## 13. Changes to the v1 spec

When rev B is accepted, the v1 spec gets a v0.5 that points here for rev B and takes in:
- §1: the scope table's "Host: A500 internal DF0" becomes "DF0, or DF1 next to the original drive"; "Not in v1:
  pass-through to a real drive" becomes "rev B: pass-through and DF0/DF1 swap (rev B spec)".
- §2.1: the six drive outputs are shared with the DB23 too, with 100 pF filters ([SCH] p8); "Kickstart does not probe
  DF0 at boot" is corrected (disk.resource reads all four units, [AROS]).
- §2.3: outputs that can disturb the bus are on GPIO21 or 38–42, or active-high with a 10 kΩ pull-down (rev B §4.1).
- §3: the block diagram gets J6, J6pwr, the steering logic and the second output buffer.
- §4.1: rows 4, 6 and 14 go; the input count changes; the glitch rule relies on the 1 kΩ isolation.
- §4.2: /STEP, /DIR, /SIDE 4k7 and /SEL1 1 kΩ in rev B.
- §4.3: outputs gated by select in logic, and split over U4 and the west-end buffer (rev B §4.3); O14 closed.
- §4.4: J6 and the connector count.
- §5: J2 pin 4 carries +12 V to J6pwr; the drive behind its own eFuse; the reversed-plug text of rev B §6.
- §6: the GPIO table of rev B §7; J5 becomes a 1×4 header (IO18, IO3); the UART1 wired-GTi option uses J5.
- §7: the spare header, the test-pad list, J7, the RST and MTRX pads.
- §8: the rev B outline, connector rules and placement (rev B §9); the "rev A" text in the serial box; the module's
  solder-through hole; "windowpane paste" is gone since U1 is hand-placed.
- §9: the firmware requirements of rev B §8 (outputs set from state, not from select edges; DD ID on DF0 a setting;
  "running" as DF1; the J5 pull-up rule void).
- §10: seven new extended part types (about $21 per order in JLC's extended-part fees) and about $2 more parts per
  board at 50 pieces; the under-€10 target is re-checked against the BOM.
- §11: rev B's verification and done criteria (rev B §10); item 6's "firmware halted: DF0 looks like a drive holding an
  unreadable disk" becomes "firmware halted: the A500 boots from the real drive".
- §13: the open items of rev B §11.
