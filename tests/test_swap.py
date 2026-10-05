"""Rev B steering logic (spec §3, §4): structure here, behaviour in Task 8's tests below."""
from tests.fd import between, esp_net, parts_between, pulls


def value(nl, ref):
    return nl.components[ref]["value"]


def test_mode_latch(nl):
    assert value(nl, "U8") == "74LVC74A"
    a = {p: nl.net_of("U8", p) for p in (1, 2, 3, 4, 5)}
    b = {p: nl.net_of("U8", p) for p in (13, 12, 11, 10, 9)}
    assert a == {1: "CLR_A", 2: "DF0_REQ", 3: "MODE_CLK", 4: "PRE_A", 5: "DF0_FD"}
    assert b == {13: "CLR_B", 12: "DF1_REQ", 11: "MODE_CLK", 10: "PRE_B", 9: "DF1_EN"}
    for net in ("CLR_A", "PRE_A", "CLR_B", "PRE_B"):
        assert ("10K", "+3V3") in pulls(nl, net), net
    assert [value(nl, r) for r in parts_between(nl, "DF0_FD", "DF0_REQ")] == ["100K"]      # D holds Q (§4.1)
    assert [value(nl, r) for r in parts_between(nl, "DF1_EN", "DF1_REQ")] == ["100K"]
    assert [value(nl, r) for r in parts_between(nl, "DF0_FD", "DF0_STATE")] == ["1K"]
    assert [value(nl, r) for r in parts_between(nl, "DF1_EN", "DF1_STATE")] == ["1K"]


def test_power_on_rcs(nl):
    assert parts_between(nl, "CLR_B", "GND", "C") and parts_between(nl, "POR_A", "GND", "C")
    assert {nl.net_of("D5", 2), nl.net_of("D5", 1)} == {"CLR_B", "+3V3"} and nl.net_of("D5", 1) == "+3V3"
    assert {nl.net_of("D6", 2), nl.net_of("D6", 1)} == {"POR_A", "+3V3"} and nl.net_of("D6", 1) == "+3V3"
    assert [nl.net_of("JP5", p) for p in (1, 2, 3)] == ["CLR_A", "POR_A", "PRE_A"]
    assert "Bridged12" in nl.components["JP5"]["footprint"]
    assert between(nl, "JP6") == {"CLR_A", "GND"} and between(nl, "JP7") == {"PRE_A", "+3V3"}
    assert "Open" in nl.components["JP6"]["footprint"] and "Open" in nl.components["JP7"]["footprint"]


def test_switch_pads(nl):
    assert [nl.net_of("J7", p) for p in (1, 2, 3)] == ["J7_FD", "GND", "J7_REAL"]
    assert [value(nl, r) for r in parts_between(nl, "J7_FD", "PRE_A")] == ["1K"]
    assert [value(nl, r) for r in parts_between(nl, "J7_REAL", "CLR_A")] == ["1K"]
    for net in ("J7_FD", "J7_REAL"):
        assert [value(nl, c) for c in parts_between(nl, net, "GND", "C")] == ["100nF"], net


def test_select_and_clock_gates(nl):
    mux = {"U12": ("DF1_EN", "GND", "SEL1", "SEL1_EN"), "U13": ("DF0_FD", "SEL1_EN", "SEL0", "SEL_FD"),
           "U16": ("BUSY", "MODE_CLK_REQ", "GND", "MODE_CLK")}                # S, I0, I1, Y
    for u, (s, i0, i1, y) in mux.items():
        assert value(nl, u) == "74LVC1G157"
        assert (nl.net_of(u, 6), nl.net_of(u, 3), nl.net_of(u, 1), nl.net_of(u, 4)) == (s, i0, i1, y), u


def test_control_gpios(nl):
    """Rev B spec §7: the GPIO map; outputs active-high with 10k pull-downs, read-backs through 1k."""
    want = {47: "MODE_CLK_REQ", 48: "DF0_REQ", 13: "DF1_REQ", 14: "CHNG_REQ", 12: "DF0_STATE", 8: "DF1_STATE",
            18: "GPIO18", 3: "GPIO3"}
    for gpio, net in want.items():
        assert esp_net(nl, gpio) == net, gpio
    for net in ("MODE_CLK_REQ", "CHNG_REQ"):
        assert pulls(nl, net) == [("10K", "GND")], net


J6_1TO1 = (2, 8, 18, 20, 22, 24, 26, 28, 30, 32, 34)


def test_j6_pinout(nl):
    for p in J6_1TO1:
        assert nl.net_of("J6", p) == nl.net_of("J1", p), p
    assert nl.net_of("J6", 10) == "J6_SEL" and nl.net_of("J6", 4) == nl.net_of("J6", 16) == "J6_MTR"
    for p, net in ((6, "J6_PIN6"), (12, "J6_PIN12"), (14, "J6_PIN14")):
        assert nl.net_of("J6", p) == net and pulls(nl, net) == [("10K", "+5V_A")], p
    for p in range(1, 35, 2):
        assert (nl.net_of("J6", p) or "").startswith("unconnected-") if p == 3 else nl.net_of("J6", p) == "GND"


def test_real_drive_drivers(nl):
    for u, (s, i0, i1, y) in {"U14": ("DF0_FD", "SEL0", "M4_SEL", "REAL_SEL"),
                              "U15": ("DF0_FD", "MTR0", "M4_MTR", "REAL_MTR")}.items():
        assert (nl.net_of(u, 6), nl.net_of(u, 3), nl.net_of(u, 1), nl.net_of(u, 4)) == (s, i0, i1, y), u
    assert value(nl, "U18") == "SN74LVC2G06"
    assert (nl.net_of("U18", 1), nl.net_of("U18", 6)) == ("REAL_SEL", "J6_SEL_D")
    assert (nl.net_of("U18", 3), nl.net_of("U18", 4)) == ("REAL_MTR", "J6_MTR_D")
    for net in ("J6_SEL_D", "J6_MTR_D"):
        assert pulls(nl, net) == [("4K7", "+5V_A")], net


def test_bypass_and_mode4_jumpers(nl):
    want = {"JP1": ("J6_SEL_D", "J6_SEL", "_SEL0"), "JP2": ("J6_MTR_D", "J6_MTR", "_MTR0"),
            "JP3": ("GND", "M4_SEL", "M4_SEL_Q"), "JP4": ("GND", "M4_MTR", "M4_MTR_Q")}
    for jp, nets in want.items():
        assert tuple(nl.net_of(jp, p) for p in (1, 2, 3)) == nets, jp
        assert "Bridged12" in nl.components[jp]["footprint"], jp


def test_virtual_disk_change(nl):
    assert value(nl, "U20") == "SN74LVC1G38"
    assert {nl.net_of("U20", 1), nl.net_of("U20", 2)} == {"CHNG_REQ", "SEL0"} and nl.net_of("U20", 4) == "VCHNG_D"
    r33 = parts_between(nl, "VCHNG_D", "_CHNG")
    assert len(r33) == 1 and value(nl, r33[0]) == "33"


def test_nothing_on_j6_leaves_its_lines_inactive(nl):
    """Review focus 3: with nothing plugged into J6, every J6-only line is pulled to its inactive high level."""
    from tests.logic import evaluate
    v = evaluate(nl, {"_CHNG": (1, 1), "_INDEX": (1, 1), "_TRK0": (1, 1), "_WPROT": (1, 1), "_DKRD": (1, 1),
                      "_RDY": (1, 1), "KBRESET": (1, 1)})
    for net in ("J6_SEL", "J6_MTR", "J6_PIN6", "J6_PIN12", "J6_PIN14"):
        assert v[net] == 1, net


def test_mode4_parts_prepared_not_fitted(nl):
    assert not nl.fitted("U21") and not nl.fitted("U22") and not nl.fitted("U23")
    assert (nl.net_of("U21", 6), nl.net_of("U21", 3), nl.net_of("U21", 1), nl.net_of("U21", 4)) == \
        ("DF0_FD", "GND", "SEL1_EN", "M4_SEL_Q")
    assert value(nl, "U22") == "SN74LVC1G175"
    assert nl.components["U22"]["fields"].get("LCSC") == "C128412"          # spec §4.9: the kit's number
    assert [nl.net_of("U22", p) for p in (1, 3, 6, 4)] == ["SEL1", "M4_MOTOR", "DF1_EN", "M4_MTR_Q"]
    assert {nl.net_of("U23", 1), nl.net_of("U23", 2)} == {"M4_SEL_Q", "M4_MTR_N"} and nl.net_of("U23", 4) == "ID_D"
    from tests.fd import dnp_between
    assert len(dnp_between(nl, "ID_D", "_RDY", "R")) == 1
    assert nl.net_of("J10", 1) == "MTRX"


def test_reset_wire(nl):
    assert nl.net_of("J9", 1) == "KBRESET"
    assert not pulls(nl, "KBRESET")                              # no pull-up on the pad: RP501 on the motherboard
    assert value(nl, "U19") == "SN74LVC1G06"
    assert (nl.net_of("U19", 2), nl.net_of("U19", 4)) == ("RST_REQ", "KBRESET")
    assert pulls(nl, "RST_REQ") == [("10K", "GND")]
    assert [value(nl, r) for r in parts_between(nl, "RST_ACT", "RST_ACT_IO")] == ["1K"]
    assert esp_net(nl, 4) == "RST_ACT_IO" and esp_net(nl, 10) == "RST_REQ"


# --- behaviour on the netlist (rev B spec §10.1) -----------------------------------------------------------------
import copy
import itertools

import pytest

from tests.logic import FLIPFLOPS, OD, PULL, STRONG, WEAK, evaluate, pin_map

BUS_OUT = ("_CHNG", "_INDEX", "_TRK0", "_WPROT", "_DKRD", "_RDY")
OUTS = {"CHNG": "_CHNG", "INDEX": "_INDEX", "TRK0": "_TRK0", "WPROT": "_WPROT", "DKRD": "_DKRD", "RDY": "_RDY"}
SWITCH = {"GTi": None, "FD": [("1", "2")], "REAL": [("3", "2")]}          # J7: centre, FD throw, REAL throw
REAL_PAIRS = ("none", "clear", "preset", "both")                          # JP6 (clear to GND), JP7 (preset to +3V3)
# (the six X_N asserted, CHNG_REQ, RST_REQ, MODE_CLK_REQ): a pairwise covering array. Every pair of these four takes
# all four pairs of values, so a request wired to another request's gate, or /CHNG's two drivers mixed up, shows.
CONTROLS = ((0, 0, 0, 0), (0, 1, 1, 1), (1, 0, 1, 1), (1, 1, 0, 1), (1, 1, 1, 0))


def fit_mode4(nl):
    """The unfitted parts a builder fits for mode 4: U21-U23 and the MTRX and ID resistors (found by net)."""
    from tests.fd import dnp_between
    refs = {"U21", "U22", "U23"}
    refs |= set(dnp_between(nl, "MTRX", "+5V_A", "R")) | set(dnp_between(nl, "MTRX", "MTRX_B", "R"))
    refs |= set(dnp_between(nl, "ID_D", "_RDY", "R"))
    return refs


def amiga(sel0, sel1, mtr0, motor_raw=0):
    """The Amiga side: CIA-B and Gary pull the active-low selects and /MTR0 low; the motherboard pulls the drive
    outputs and _KBRESET up; the raw motor line (mode 4) is low when a DF1-3 motor is on."""
    src = {n: (1, PULL) for n in BUS_OUT + ("KBRESET",)}
    for net, on in (("_SEL0", sel0), ("_SEL1", sel1), ("_MTR0", mtr0), ("MTRX", motor_raw)):
        if on:
            src[net] = (0, OD)
    src.setdefault("MTRX", (1, PULL))
    return src


def expected(df0_fd, df1_en, sel0, sel1, mtr0, m4, m4_q):
    """Rev B spec §3 table and §4 equations, written independently of the netlist."""
    sel1_en = sel1 & df1_en
    sel_fd = sel0 if df0_fd else sel1_en
    m4_sel = (df0_fd & sel1_en) if m4 else 0
    m4_mtr = (m4_q & df1_en) if m4 else 0
    return {"SEL_FD": sel_fd, "REAL_SEL": m4_sel if df0_fd else sel0, "REAL_MTR": m4_mtr if df0_fd else mtr0,
            "ID": m4_sel & (1 - m4_mtr)}


def legal(bypass, real_pair, switch):
    """Rev B §4.4, §10.1: the bypass needs DF0_FD held at 0, by the REAL pair (both jumpers) or by J7 on REAL."""
    return not bypass or real_pair == "both" or switch == "REAL"


def df0_of(stored, real_pair, switch):
    """Rev B §3, §4.4: J7's FD throw pulls the preset low unless JP7 holds it high; its REAL throw and JP6 pull the
    clear low; with both low the 74LVC74A gives Q = 1; with neither, the latch keeps what it stored."""
    pre_low = switch == "FD" and real_pair not in ("preset", "both")
    clr_low = switch == "REAL" or real_pair in ("clear", "both")
    return 1 if pre_low else 0 if clr_low else stored


def jumpers(switch, real_pair, bypass, m4):
    """The `bridged` argument of evaluate() for one state of J7 and the jumpers."""
    bridged = {}
    if bypass:
        bridged.update({"JP1": [("2", "3")], "JP2": [("2", "3")]})
    if m4:
        bridged.update({"JP3": [("2", "3")], "JP4": [("2", "3")]})
    if real_pair in ("clear", "both"):
        bridged["JP6"] = [("1", "2")]
    if real_pair in ("preset", "both"):
        bridged["JP7"] = [("1", "2")]
    if SWITCH[switch]:
        bridged["J7"] = SWITCH[switch]
    return bridged


@pytest.mark.parametrize("m4", (0, 1))
@pytest.mark.parametrize("bypass", (0, 1))
@pytest.mark.parametrize("real_pair", REAL_PAIRS)
@pytest.mark.parametrize("switch", tuple(SWITCH))
@pytest.mark.parametrize("stored0,stored1", ((0, 0), (0, 1), (1, 0), (1, 1)))
def test_steering_logic(nl, stored0, stored1, switch, real_pair, bypass, m4):
    """Rev B spec §10.1: every legal state of the stored mode bits, J7, the REAL pair, the bypass and mode 4, with
    every SEL0, SEL1, MTR0 and mode-4 latch output under the five CONTROLS patterns; every output §10.1 lists."""
    if not legal(bypass, real_pair, switch):
        pytest.skip("illegal: see test_illegal_bypass_states_put_two_drives_on_sel0")
    bridged = jumpers(switch, real_pair, bypass, m4)
    fit = fit_mode4(nl) if m4 else ()
    df0 = df0_of(stored0, real_pair, switch)
    for m4_q, sel0, sel1, mtr0, (asserted, chng_req, rst_req, clk_req) in itertools.product(
            (0, 1) if m4 else (0,), (0, 1), (0, 1), (0, 1), CONTROLS):
        case = dict(m4_q=m4_q, sel0=sel0, sel1=sel1, mtr0=mtr0, asserted=asserted, chng_req=chng_req,
                    rst_req=rst_req, clk_req=clk_req)
        src = amiga(sel0, sel1, mtr0)
        if asserted:                                             # released: the GPIO is an input, the 10k pulls up
            src.update({f"{s}_N": (0, STRONG) for s in OUTS})
        src.update({"CHNG_REQ": (chng_req, STRONG), "RST_REQ": (rst_req, STRONG), "MODE_CLK_REQ": (clk_req, STRONG)})
        state = {("U8", "A"): stored0, ("U8", "B"): stored1, ("U22", "A"): m4_q}
        v = evaluate(nl, src, state=state, bridged=bridged, fit=fit)
        e = expected(df0, stored1, sel0, sel1, mtr0, m4, m4_q)
        assert (v["DF0_FD"], v["DF1_EN"]) == (df0, stored1), case
        assert (v["SEL_FD"], v["REAL_SEL"], v["REAL_MTR"]) == (e["SEL_FD"], e["REAL_SEL"], e["REAL_MTR"]), case
        if bypass:
            assert (v["J6_SEL"], v["J6_MTR"]) == (1 - sel0, 1 - mtr0), case
        else:
            assert (v["J6_SEL"], v["J6_MTR"]) == (1 - e["REAL_SEL"], 1 - e["REAL_MTR"]), case
        for sig, conn in OUTS.items():
            mine = asserted and e["SEL_FD"]
            assert v[f"{sig}_G"] == (0 if mine else 1), (sig, case)                    # the buffer inputs
            low = mine or (sig == "CHNG" and chng_req and sel0) or (sig == "RDY" and e["ID"])
            assert v[conn] == (0 if low else 1), (sig, case)
        assert v["MODE_CLK"] == (1 if clk_req and not (sel0 or sel1) else 0), case
        assert v["KBRESET"] == 1 - rst_req, case
        if sel0 != sel1:                                         # one select active: one drive answers it at most
            assert not (v["SEL_FD"] and v["J6_SEL"] == 0), ("two drives selected", case)


def test_illegal_bypass_states_put_two_drives_on_sel0(nl):
    """Review focus 2: the bypass states test_steering_logic skips are illegal for a reason: with DF0_FD not held at
    0, FluxDrive and the real drive both answer /SEL0."""
    for bridged, stored in (({"J7": [("1", "2")]}, 0), ({}, 1)):          # J7 on FD; or the GTi chose FD
        bridged = {**bridged, "JP1": [("2", "3")], "JP2": [("2", "3")]}
        v = evaluate(nl, amiga(1, 0, 0), state={("U8", "A"): stored, ("U8", "B"): 0}, bridged=bridged)
        assert v["SEL_FD"] == 1 and v["J6_SEL"] == 0


@pytest.mark.parametrize("pattern", range(64))
def test_outputs_follow_the_firmware_only_when_selected(nl, pattern):
    """Rev B §4.3: each of the six X_N lines reaches the bus only while FluxDrive is selected, for all 64 patterns
    and every mode and select state (test_steering_logic takes all six asserted or all six released)."""
    for df0, df1, sel0, sel1 in itertools.product((0, 1), repeat=4):
        src = amiga(sel0, sel1, 0)
        src.update({f"{s}_N": (0, STRONG) for i, s in enumerate(OUTS) if pattern >> i & 1})
        v = evaluate(nl, src, state={("U8", "A"): df0, ("U8", "B"): df1})
        sel_fd = sel0 if df0 else sel1 & df1
        for i, (sig, conn) in enumerate(OUTS.items()):
            assert v[conn] == (0 if pattern >> i & 1 and sel_fd else 1), (sig, df0, df1, sel0, sel1)


class Board:
    """Steps the flip-flops through events (rev B spec §10.1, second test). Their pins are read from the netlist:
    after each event a low preset sets Q, a low clear clears it, and otherwise a rising clock takes D as it was just
    before the event, so a wrong clock, clear or preset wire on U8 or U22 shows."""

    def __init__(self, nl, m4=False, stored=(0, 0), m4_q=0, bridged=None):
        self.nl, self.fit = nl, fit_mode4(nl) if m4 else ()
        self.state = {("U8", "A"): stored[0], ("U8", "B"): stored[1], ("U22", "A"): m4_q}
        self.bridged = dict(bridged or {})
        if m4:
            self.bridged.update({"JP3": [("2", "3")], "JP4": [("2", "3")]})
        pins = pin_map(nl)
        self.ffs = [(ref, name, pins[ref].get(clr), pins[ref].get(pre) if pre else None, pins[ref].get(d),
                     pins[ref].get(clk))
                    for ref, comp in nl.components.items() if nl.fitted(ref) or ref in self.fit
                    for name, clr, pre, d, clk, _ in FLIPFLOPS.get(comp["value"], [])]
        self.src = amiga(0, 0, 0)
        self.v = self.eval()

    def eval(self):
        return evaluate(self.nl, self.src, state=self.state, bridged=self.bridged, fit=self.fit)

    def set(self, **nets):
        """Change the sources (None removes one), settle, then update the flip-flops."""
        for net, val in nets.items():
            if val is None:
                self.src.pop(net, None)
            else:
                self.src[net] = val
        before, after = self.v, self.eval()
        old = dict(self.state)
        for ref, name, clr, pre, d, clk in self.ffs:
            if pre and after[pre] == 0:
                self.state[(ref, name)] = 1
            elif clr and after[clr] == 0:
                self.state[(ref, name)] = 0
            elif clk and before[clk] == 0 and after[clk] == 1:
                self.state[(ref, name)] = before[d]
        self.v = self.eval() if self.state != old else after
        return self.v

    def copy(self):
        """An independent Board in the same state (the search of test_every_order_of_events branches from it)."""
        b = copy.copy(self)
        b.state, b.src, b.bridged = dict(self.state), dict(self.src), dict(self.bridged)
        return b

    def throw(self, position):
        """Move J7 to "GTi" (centre), "FD" or "REAL"."""
        self.bridged.pop("J7", None)
        if SWITCH[position]:
            self.bridged["J7"] = SWITCH[position]
        return self.set()


def test_clock_request_waits_for_the_access_to_end(nl):
    """Review focus 1: a DF0 request during a /SEL0 access takes effect when the access ends, not before."""
    b = Board(nl, stored=(0, 0))
    b.set(_SEL0=(0, OD))                                   # real drive DF0, being read
    b.set(DF0_REQ=(1, STRONG))                             # D first, then the clock request (spec §8)
    b.set(MODE_CLK_REQ=(1, STRONG))
    assert b.v["DF0_FD"] == 0 and b.v["REAL_SEL"] == 1 and b.v["MODE_CLK"] == 0
    b.set(_SEL0=None)                                      # access over: the clock arrives
    assert b.v["DF0_FD"] == 1 and b.v["REAL_SEL"] == 0
    b.set(MODE_CLK_REQ=(0, STRONG))
    assert b.v["DF0_FD"] == 1


def test_request_dropped_inside_an_access_is_lost(nl):
    b = Board(nl, stored=(0, 1))
    b.set(_SEL1=(0, OD))                                   # FluxDrive DF1 in use (mode 3)
    b.set(DF0_REQ=(1, STRONG))                             # D first, then the clock request (spec §8)
    b.set(MODE_CLK_REQ=(1, STRONG))
    b.set(MODE_CLK_REQ=(0, STRONG))
    b.set(_SEL1=None)
    assert b.v["DF0_FD"] == 0 and b.v["DF1_EN"] == 1


def test_switch_moved_during_an_access(nl):
    """Spec §3, §10.1: J7 acts at once, also during an access; the latch keeps a throw after the switch returns to
    the centre; it never touches DF1_EN."""
    b = Board(nl, stored=(0, 1))                           # mode 3
    b.set(_SEL0=(0, OD))                                   # the real drive, DF0, is being read
    assert b.v["REAL_SEL"] == 1 and b.v["SEL_FD"] == 0
    b.throw("FD")
    assert (b.v["DF0_FD"], b.v["DF1_EN"], b.v["REAL_SEL"], b.v["SEL_FD"]) == (1, 1, 0, 1)
    b.throw("GTi")
    b.set(_SEL0=None)
    assert (b.v["DF0_FD"], b.v["DF1_EN"]) == (1, 1)
    b.throw("REAL")
    assert (b.v["DF0_FD"], b.v["DF1_EN"]) == (0, 1)


def test_esp32_reset_changes_nothing(nl):
    """Review focus 4: control GPIOs undriven, with their internal pull-ups on: no clock, no /CHNG, no reset, and
    /RDY and the J6 lines idle."""
    for stored in ((0, 0), (1, 0), (0, 1)):
        b = Board(nl, stored=stored)
        b.set(_SEL0=(0, OD))
        b.set(**{n: (1, WEAK) for n in ("MODE_CLK_REQ", "DF0_REQ", "DF1_REQ", "CHNG_REQ", "RST_REQ")})
        b.set(_SEL0=None)
        assert (b.v["DF0_FD"], b.v["DF1_EN"]) == stored
        assert b.v["_CHNG"] == 1 and b.v["KBRESET"] == 1 and b.v["MODE_CLK"] == 0
        assert b.v["_RDY"] == 1 and b.v["J6_SEL"] == 1 and b.v["J6_MTR"] == 1


def test_esp32_glitch_changes_nothing(nl):
    """Rev B §4.1, §10.1: GPIO1-17 driven low for 60 us at an ESP32 reset, in every mode, with and without an
    access: no clock, no /CHNG, no reset pulse, the mode kept, the real drive's select follows the bus."""
    glitch = ("RST_ACT_IO", "DF1_STATE", "SEL1_IO", "RST_REQ", "MTR0_IO", "DF0_STATE", "DF1_REQ", "CHNG_REQ",
              "SEL0_IO")                                  # GPIO 4, 8, 9, 10, 11, 12, 13, 14, 17
    for stored in ((0, 0), (1, 0), (0, 1)):
        for sel0 in (0, 1):
            b = Board(nl, stored=stored)
            b.set(_SEL0=(0, OD) if sel0 else None)
            b.set(**{n: (0, STRONG) for n in glitch})
            b.set(**{n: None for n in glitch})
            assert (b.v["DF0_FD"], b.v["DF1_EN"]) == stored
            assert b.v["_CHNG"] == 1 and b.v["KBRESET"] == 1 and b.v["MODE_CLK"] == 0 and b.v["_RDY"] == 1
            assert b.v["J6_SEL"] == (0 if sel0 and not stored[0] else 1) and b.v["J6_MTR"] == 1


def test_mode1_with_mode4_fitted_keeps_the_real_drive_still(nl):
    """v0.1's finding I3: an external DF1's motor must not spin the real drive in mode 1."""
    b = Board(nl, m4=True, stored=(1, 0))
    for _ in range(3):
        b.set(MTRX=(0, OD))
        b.set(_SEL1=(0, OD))
        assert b.v["J6_MTR"] == 1 and b.v["J6_SEL"] == 1 and b.v["_RDY"] == 1
        b.set(_SEL1=None)
        b.set(MTRX=None)


def test_power_on_defaults(nl):
    """Rev B §3, §4.6: the power-on RCs give DF1 off and the real drive as DF0, or FluxDrive with JP5 on 2-3."""
    for jp5, want in ((None, 0), ([("2", "3")], 1)):
        bridged = {"JP5": jp5} if jp5 else {}
        b = Board(nl, stored=(1, 1), bridged=bridged)
        b.set(POR_A=(0, OD), CLR_B=(0, OD))                # capacitors still discharged
        b.set(POR_A=None, CLR_B=None)
        assert b.v["DF1_EN"] == 0 and b.v["DF0_FD"] == want


def test_every_order_of_events(nl):
    """Rev B spec §10.1 (second test), review focus 1: every state reachable by the Amiga's selects, the firmware's
    D inputs and clock request, and J7, entered by every single event from every state. After each event: FluxDrive
    answers only the unit it owns and the real drive only its own select; the mode bits change only on a clock edge
    or by the switch; MODE_CLK is never high during an access."""
    from collections import deque
    order = tuple(SWITCH)                                  # GTi -> FD -> REAL -> GTi

    def board(node):
        s0, s1, sel0, sel1, req0, req1, clk, sw = node
        b = Board(nl, stored=(s0, s1), bridged={"J7": SWITCH[sw]} if SWITCH[sw] else {})
        b.set(_SEL0=(0, OD) if sel0 else None, _SEL1=(0, OD) if sel1 else None,
              DF0_REQ=(req0, STRONG), DF1_REQ=(req1, STRONG), MODE_CLK_REQ=(clk, STRONG))
        return b

    starts = [(s0, s1, 0, 0, s0, s1, 0, "GTi") for s0, s1 in ((0, 0), (1, 0), (0, 1))]
    seen, todo = set(starts), deque(starts)
    while todo:
        node = todo.popleft()
        s0, s1, sel0, sel1, req0, req1, clk, sw = node
        start = board(node)
        for ev in ("sel0", "sel1", "req0", "req1", "clk", "sw"):
            b = start.copy()
            before = dict(b.v)
            n = dict(sel0=sel0, sel1=sel1, req0=req0, req1=req1, clk=clk)
            nsw = sw
            if ev == "sw":
                nsw = order[(order.index(sw) + 1) % 3]
                b.throw(nsw)
            else:
                n[ev] ^= 1
                net = {"sel0": "_SEL0", "sel1": "_SEL1", "req0": "DF0_REQ", "req1": "DF1_REQ",
                       "clk": "MODE_CLK_REQ"}[ev]
                b.set(**{net: ((0, OD) if n[ev] else None) if ev.startswith("sel") else (n[ev], STRONG)})
            v = b.v
            e = expected(v["DF0_FD"], v["DF1_EN"], n["sel0"], n["sel1"], 0, False, 0)
            assert v["SEL_FD"] == e["SEL_FD"] and v["J6_SEL"] == 1 - e["REAL_SEL"], (node, ev)
            assert not (v["MODE_CLK"] and (n["sel0"] or n["sel1"])), (node, ev)
            moved = (v["DF0_FD"], v["DF1_EN"]) != (before["DF0_FD"], before["DF1_EN"])
            clocked = before["MODE_CLK"] == 0 and v["MODE_CLK"] == 1
            assert not moved or ev == "sw" or clocked, (node, ev)
            nxt = (b.state[("U8", "A")], b.state[("U8", "B")], n["sel0"], n["sel1"], n["req0"], n["req1"],
                   n["clk"], nsw)
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    assert len(seen) > 100, len(seen)
