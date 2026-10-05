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
