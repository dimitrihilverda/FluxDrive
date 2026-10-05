import pytest

from tests.fd import between, esp_net, parts_between, pulls

EVEN = {2: "_CHNG", 8: "_INDEX", 10: "_SEL0", 12: "_SEL1", 16: "_MTR0", 18: "_DIR", 20: "_STEP", 22: "_DKWD",
        24: "_DKWE", 26: "_TRK0", 28: "_WPROT", 30: "_DKRD", 32: "_SIDE", 34: "_RDY"}
NC_PINS = (3, 4, 6, 14)                  # rev B spec §7: pins 4, 6 and 14 have no use on the A500
# signal, connector net, fitted pull-up, GPIO, GPIO net (rev B spec §5, §7)
INPUTS = [("STEP", "_STEP", [("4K7", "+5V_A")], 6, "STEP"), ("DIR", "_DIR", [("4K7", "+5V_A")], 7, "DIR"),
          ("SIDE", "_SIDE", [("4K7", "+5V_A")], 15, "SIDE"), ("SEL0", "_SEL0", [("1K", "+5V_A")], 17, "SEL0_IO"),
          ("SEL1", "_SEL1", [("1K", "+5V_A")], 9, "SEL1_IO"), ("MTR0", "_MTR0", [], 11, "MTR0_IO"),
          ("DKWD", "_DKWD", [("4K7", "+5V_A")], 5, "DKWD"), ("DKWE", "_DKWE", [("4K7", "+5V_A")], 16, "DKWE")]


def test_connector_pinout(nl):
    for pin, net in EVEN.items():
        assert nl.net_of("J1", pin) == net, pin
    for pin in range(1, 35):
        if pin in NC_PINS:
            assert (nl.net_of("J1", pin) or "").startswith("unconnected-"), pin
        elif pin % 2:
            assert nl.net_of("J1", pin) == "GND", pin


@pytest.mark.parametrize("sig,conn,pull,gpio,gnet", INPUTS)
def test_input_chain(nl, sig, conn, pull, gpio, gnet):
    assert pulls(nl, conn) == pull
    r100 = parts_between(nl, conn, f"{sig}_B")
    assert len(r100) == 1 and nl.components[r100[0]]["value"] == "100"
    assert pulls(nl, f"{sig}_B") == [("100K", "+3V3")]
    assert esp_net(nl, gpio) == gnet
    if gnet != sig:                                              # rev B spec §4.1: 1 kOhm to the GPIO
        iso = parts_between(nl, sig, gnet)
        assert len(iso) == 1 and nl.components[iso[0]]["value"] == "1K"


def test_buffers_follow_the_connector(nl):
    """LBUS-3 kept: U3 takes J1 pins 10-16, U2 pins 18-32, each buffer's gates in the connector's west-to-east order
    (input pins 1, 13, 3, 11, 5, 9 with the SOIC turned 90 degrees)."""
    pin_of = {net: pin for pin, net in EVEN.items()}
    order = [1, 13, 3, 11, 5, 9]
    used = {"U2": [], "U3": []}
    for sig, conn, *_ in INPUTS:
        (u, pin_in), = [(r, int(p)) for r, p, _ in nl.nets[f"{sig}_B"] if r in ("U2", "U3")]
        assert u == ("U3" if pin_of[conn] <= 16 else "U2"), sig
        used[u].append((pin_of[conn], order.index(pin_in)))
    for u, pairs in used.items():
        ranks = [r for _, r in sorted(pairs)]
        assert ranks == sorted(ranks), u


def test_freed_gates_reused(nl):
    """Rev B spec §7: U3's gates for rev A's J1 pins 4, 6, 14 serve the reset wire and mode 4; U2's spare makes
    SEL_FD_N; none of their inputs floats."""
    assert (nl.net_of("U3", 1), nl.net_of("U3", 2)) == ("RST_B", "RST_ACT")
    assert (nl.net_of("U3", 5), nl.net_of("U3", 6)) == ("MTRX_B", "M4_MOTOR")
    assert (nl.net_of("U3", 13), nl.net_of("U3", 12)) == ("M4_MTR_Q", "M4_MTR_N")
    assert (nl.net_of("U2", 9), nl.net_of("U2", 8)) == ("SEL_FD", "SEL_FD_N")
    assert pulls(nl, "RST_B") == [("100K", "+3V3")] and pulls(nl, "MTRX_B") == [("100K", "+3V3")]
    assert pulls(nl, "M4_MTR_Q") == [("100K", "GND")]


def test_unfitted_pads_exist(nl):
    """SCODE-5, spec 4.2: the optional parts exist, between the right nets, unfitted."""
    from tests.fd import dnp_between
    assert len(dnp_between(nl, "_MTR0", "+5V_A", "R")) == 1
    for sig in ("STEP", "SEL0", "SEL1", "MTR0"):
        assert len(dnp_between(nl, f"{sig}_B", "GND", "C")) == 1, sig


OUTPUTS = [("DKRD", "_DKRD", 38), ("INDEX", "_INDEX", 39), ("TRK0", "_TRK0", 40), ("WPROT", "_WPROT", 41),
           ("CHNG", "_CHNG", 42), ("RDY", "_RDY", 21)]
GLITCH_FREE = {21, 38, 39, 40, 41, 42, 47, 48}      # ESP32-S3 datasheet v2.2, table 2-2


@pytest.mark.parametrize("sig,conn,gpio", OUTPUTS)
def test_output_chain(nl, sig, conn, gpio):
    assert esp_net(nl, gpio) == f"{sig}_N"
    assert pulls(nl, f"{sig}_N") == [("10K", "+3V3")]
    assert any(r == "U4" for r, _, _ in nl.nets[f"{sig}_N"])
    r33 = parts_between(nl, f"{sig}_D", conn)
    assert len(r33) == 1 and nl.components[r33[0]]["value"] == "33"


def test_outputs_quiet_at_power_up(nl):
    """Review focus 3: no bus output moves when the ESP32 (re)starts."""
    for sig, _, gpio in OUTPUTS:
        assert gpio in GLITCH_FREE, sig
        assert pulls(nl, f"{sig}_N") == [("10K", "+3V3")], sig


def test_buffers_on_3v3(nl):
    for u in ("U2", "U3", "U4"):
        assert nl.net_of(u, 14) == "+3V3" and nl.net_of(u, 7) == "GND"
        assert nl.components[u]["footprint"].endswith("SOIC-14_3.9x8.7mm_P1.27mm")
    assert nl.components["U4"]["value"] == "74LVC07A"
    assert nl.components["U2"]["value"] == nl.components["U3"]["value"] == "74LVC14A"


def test_no_5v_on_the_esp(nl):
    for net, nodes in nl.nets.items():
        if any(r == "U1" for r, _, _ in nodes):
            assert net not in ("+5V_IN", "+5V_A", "V5SYS", "VBUS"), net


GATE = {1: 2, 3: 4, 5: 6, 9: 8, 11: 10, 13: 12}           # input pin -> output pin, 74LVC14A and 74LVC07A


def test_gate_pairs(nl):
    """SBUS-2: each signal goes in and out of the same gate, the right way round."""
    for sig, *_ in INPUTS:
        pins = [(r, int(p)) for r, p, _ in nl.nets[f"{sig}_B"] if r in ("U2", "U3")]
        assert len(pins) == 1, sig
        u, pin_in = pins[0]
        assert pin_in in GATE and nl.net_of(u, GATE[pin_in]) == sig, sig
    for sig, _, _ in OUTPUTS:
        pins = [int(p) for r, p, _ in nl.nets[f"{sig}_N"] if r == "U4"]
        assert len(pins) == 1 and pins[0] in GATE and nl.net_of("U4", GATE[pins[0]]) == f"{sig}_D", sig


