import pytest

from tests.fd import between, esp_net, parts_between, pulls

EVEN = {2: "_CHNG", 4: "_MTR0_P4", 6: "FD_PIN6", 8: "_INDEX", 10: "_SEL0", 12: "_SEL1", 14: "FD_PIN14",
        16: "_MTR0", 18: "_DIR", 20: "_STEP", 22: "_DKWD", 24: "_DKWE", 26: "_TRK0", 28: "_WPROT",
        30: "_DKRD", 32: "_SIDE", 34: "_RDY"}
# signal, connector net, fitted pull-up, GPIO (spec 4.1 / 4.2)
INPUTS = [("STEP", "_STEP", [("1K", "+5V_A")], 6), ("DIR", "_DIR", [("1K", "+5V_A")], 7),
          ("SIDE", "_SIDE", [("1K", "+5V_A")], 15), ("SEL0", "_SEL0", [("1K", "+5V_A")], 17),
          ("SEL1", "_SEL1", [("10K", "+5V_A")], 9), ("MTR0", "_MTR0", [], 11),
          ("DKWD", "_DKWD", [("4K7", "+5V_A")], 5), ("DKWE", "_DKWE", [("4K7", "+5V_A")], 16),
          ("MTR0_P4", "_MTR0_P4", [], 4), ("PIN6", "FD_PIN6", [("10K", "+3V3")], 8),
          ("PIN14", "FD_PIN14", [("10K", "+3V3")], 10)]
OUTPUTS = [("DKRD", "_DKRD", 38), ("INDEX", "_INDEX", 39), ("TRK0", "_TRK0", 40), ("WPROT", "_WPROT", 41),
           ("CHNG", "_CHNG", 42), ("RDY", "_RDY", 21)]
GLITCH_FREE = {21, 38, 39, 40, 41, 42, 47, 48}      # ESP32-S3 datasheet v2.2, table 2-2


def test_connector_pinout(nl):
    for pin, net in EVEN.items():
        assert nl.net_of("J1", pin) == net, pin
    for pin in range(1, 34, 2):
        assert (nl.net_of("J1", pin) or "").startswith("unconnected-") if pin == 3 else nl.net_of("J1", pin) == "GND"


@pytest.mark.parametrize("sig,conn,pull,gpio", INPUTS)
def test_input_chain(nl, sig, conn, pull, gpio):
    assert pulls(nl, conn) == pull                                 # pull-up on the connector side, fitted only
    assert len(parts_between(nl, conn, f"{sig}_B")) == 1           # the 100 ohm
    r100 = parts_between(nl, conn, f"{sig}_B")[0]
    assert nl.components[r100]["value"] == "100"
    assert pulls(nl, f"{sig}_B") == [("100K", "+3V3")]
    ins = {(r, p) for r, p, _ in nl.nets[f"{sig}_B"] if r in ("U2", "U3")}
    assert len(ins) == 1, ins
    assert esp_net(nl, gpio) == sig
    assert any(r in ("U2", "U3") for r, _, _ in nl.nets[sig])      # the inverter output drives the GPIO


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
    assert nl.net_of("U3", 13) == "GND"                     # the spare inverter's input


def test_unfitted_pads_exist(nl):
    """SCODE-5, spec 4.2: the optional parts exist, between the right nets, unfitted."""
    from tests.fd import dnp_between
    for conn in ("_MTR0", "_MTR0_P4"):
        assert len(dnp_between(nl, conn, "+5V_A", "R")) == 1, conn
    for sig in ("STEP", "SEL0", "SEL1", "MTR0"):
        assert len(dnp_between(nl, f"{sig}_B", "GND", "C")) == 1, sig
