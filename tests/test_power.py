from tools.netlist import parse_ohms
from tests.fd import between, parts_between

BUS_NETS = {"_STEP", "_DIR", "_SIDE", "_SEL0", "_SEL1", "_MTR0", "_MTR0_P4", "_DKWD", "_DKWE", "_CHNG",
            "_INDEX", "_TRK0", "_WPROT", "_DKRD", "_RDY", "FD_PIN6", "FD_PIN14"}


def r(nl, a, b):
    refs = parts_between(nl, a, b)
    assert len(refs) == 1, (a, b, refs)
    return parse_ohms(nl.components[refs[0]]["value"])


def test_power_header_to_efuse(nl):
    assert nl.components["J2"]["footprint"].endswith(":171826-4")
    assert nl.net_of("J2", 1) == "+5V_IN" and nl.net_of("J2", 2) == nl.net_of("J2", 3) == "GND"
    assert (nl.net_of("J2", 4) or "").startswith("unconnected-")          # +12 V not used
    assert nl.net_of("U5", 3) == nl.net_of("U5", 4) == "+5V_IN"
    assert nl.net_of("U5", 5) == "+5V_A"
    assert nl.components["U5"]["value"] == "TPS259531"
    assert {r_ for r_, _, _ in nl.nets["+5V_IN"]} <= {"J2", "U5", *parts_between(nl, "+5V_IN", "GND", "C"),
                                                      *parts_between(nl, "+5V_IN", "EFUSE_EN")}


def test_efuse_survives_12v(nl):
    """Review focus 1: a reversed plug puts 12 V on IN; EN/UVLO must stay below its 7 V maximum."""
    top, bottom = r(nl, "+5V_IN", "EFUSE_EN"), r(nl, "EFUSE_EN", "GND")
    assert 12 * bottom / (top + bottom) < 6.5
    uvlo = 1.2 * (top + bottom) / bottom                                   # V_UVLO(R) = 1.2 V
    assert 3.5 <= uvlo <= 4.4, uvlo
    ilim = 2100 / r(nl, "EFUSE_ILM", "GND")                                 # table: 487R 4.17 A, 1780R 1.17 A, 4420R 0.49 A
    assert 0.8 <= ilim <= 1.3, ilim


def test_power_or(nl):
    d = {x: (nl.net_of(x, 2), nl.net_of(x, 1)) for x in ("D1", "D2")}    # SS34: pin 2 = A, pin 1 = K
    assert sorted(d.values()) == [("+5V_A", "V5SYS"), ("VBUS", "V5SYS")]
    for x in ("D1", "D2"):
        assert nl.components[x]["value"] == "SS34"
    assert not any(c.get("value", "").upper().startswith(("AO34", "SI23")) for c in nl.components.values())


def test_v5sys_capacitance_within_usb_limit(nl):
    total = 0.0
    for ref in parts_between(nl, "V5SYS", "GND", "C"):
        v = nl.components[ref]["value"].replace("uF", "e-6").replace("nF", "e-9").replace("pF", "e-12")
        total += float(v)
    assert total <= 10.2e-6, total


def test_buck(nl):
    assert nl.components["U6"]["value"].startswith("TLV62569")
    assert nl.net_of_function("U6", "VIN") == "V5SYS" and nl.net_of_function("U6", "EN") == "V5SYS"
    sw = nl.net_of_function("U6", "SW")
    assert between(nl, "L1") == {sw, "+3V3"} and nl.components["L1"]["value"] == "2.2uH"
    fb = nl.net_of_function("U6", "FB")
    vout = 0.6 * (1 + r(nl, "+3V3", fb) / r(nl, fb, "GND"))
    assert abs(vout - 3.3) < 0.05, vout


def test_amiga_pwr_sense(nl):
    top, bottom = r(nl, "+5V_A", "AMIGA_PWR"), r(nl, "AMIGA_PWR", "GND")
    assert 2.8 <= 5.0 * bottom / (top + bottom) <= 3.2
    assert 5.9 * bottom / (top + bottom) <= 3.6                            # at the eFuse clamp
    assert nl.net_of_function("U1", "IO1") == "AMIGA_PWR"


def test_pullups_on_amiga_side_only(nl):
    for ref, a, b, _ in nl.resistors():
        if {a, b} & BUS_NETS:
            assert not {a, b} & {"V5SYS", "VBUS", "+5V_IN"}, ref


def test_no_backfeed_paths(nl):
    """Review focus 2: on USB alone nothing reaches +5V_A or the bus except a reverse-biased diode or >= 100k."""
    amiga_nets = BUS_NETS - {"FD_PIN6", "FD_PIN14"}      # pins 6 and 14 are NC on the A500 (spec 2.1, 4.2)
    for ref, a, b, ohms in nl.resistors():
        pair = {a, b}
        if pair & {"VBUS", "V5SYS", "+3V3"} and pair & (amiga_nets | {"+5V_A"}):
            assert ohms is not None and ohms >= 100e3, (ref, a, b)
    feeders = {r_ for r_, _, _ in nl.nets["+5V_A"]} - {"U5", "D1"}
    for ref in feeders:
        assert ref.startswith(("R", "C", "TP", "#")), ref
