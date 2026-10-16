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
    a((C("+5V_IN", "GND", after="U5"), 110.8, n(133.95), 0))     # U5's input capacitor at IN and the EP
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
    a((C("+5V_IN", "GND", after="U9"), 106.0, 132.5, 90))        # U9's input capacitor at IN (pins 3/4), in the strip
                                                                  # x 105.2-106.8, y 131-134 east of J2 pin 1
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
    a((R("M4_SEL_Q", "GND"), 154.2, 114.25, 180))                 # the 100 kOhm west of U23's input pin 1 (pad 1 east),
                                                                  # as R33 on U3's
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
    a((TP("DF0_FD"), 152.1, 114.45, 0))                           # no room near U8 or row M; west of R85 (was 153.2)
    a((TP("DF1_EN"), 111.3, 83.8, 0))
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
