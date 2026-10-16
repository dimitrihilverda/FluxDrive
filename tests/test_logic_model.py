"""The evaluator of tests/logic.py on tiny hand-made netlists."""
import pytest

from tests.logic import OD, PULL, STRONG, WEAK, Conflict, evaluate
from tools.netlist import Netlist


def nl_of(parts):
    """parts: [(ref, value, {pin: net}, fitted)] -> Netlist."""
    nl = Netlist()
    for ref, value, pins, fitted in parts:
        nl.components[ref] = {"value": value, "footprint": "", "fields": {} if fitted else {"dnp": ""}}
        for pin, net in pins.items():
            nl.nets.setdefault(net, []).append((ref, pin, ""))
    return nl


def test_inverter_and_pull_up():
    nl = nl_of([("U1", "74LVC14A", {"1": "A", "2": "Y", "7": "GND", "14": "+3V3"}, True),
                ("R1", "10K", {"1": "A", "2": "+3V3"}, True)])
    assert evaluate(nl, {})["Y"] == 0                       # pulled-up input, inverted
    assert evaluate(nl, {"A": (0, STRONG)})["Y"] == 1


def test_open_drain_wired_and_through_series_resistor():
    nl = nl_of([("U1", "SN74LVC2G06", {"1": "IN", "6": "OUT", "3": "GND", "4": "X", "2": "GND", "5": "+3V3"}, True),
                ("R1", "4K7", {"1": "OUT", "2": "+5V_A"}, True),
                ("R2", "100", {"1": "OUT", "2": "FAR"}, True),
                ("R3", "100K", {"1": "FAR", "2": "+3V3"}, True)])
    assert evaluate(nl, {"IN": (0, STRONG)})["FAR"] == 1
    v = evaluate(nl, {"IN": (1, STRONG)})
    assert v["OUT"] == 0 and v["FAR"] == 0                  # the 100 ohm carries the low past the 100k


def test_mux_and_or():
    nl = nl_of([("U1", "74LVC1G157", {"6": "S", "3": "I0", "1": "I1", "4": "Y", "2": "GND", "5": "+3V3"}, True),
                ("U2", "74LVC32A", {"1": "Y", "2": "B", "3": "Z", "7": "GND", "14": "+3V3"}, True)])
    v = evaluate(nl, {"S": (1, STRONG), "I0": (0, STRONG), "I1": (1, STRONG), "B": (0, STRONG)})
    assert v["Y"] == 1 and v["Z"] == 1


def test_flip_flop_preset_clear_and_state():
    ff = {"1": "CLR", "2": "D", "3": "CLK", "4": "PRE", "5": "Q", "7": "GND", "14": "+3V3",
          "13": "+3V3", "12": "GND", "11": "GND", "10": "+3V3", "9": "Q2"}
    nl = nl_of([("U1", "74LVC74A", ff, True), ("R1", "10K", {"1": "CLR", "2": "+3V3"}, True),
                ("R2", "10K", {"1": "PRE", "2": "+3V3"}, True)])
    assert evaluate(nl, {}, state={("U1", "A"): 1})["Q"] == 1
    assert evaluate(nl, {"CLR": (0, OD)}, state={("U1", "A"): 1})["Q"] == 0
    assert evaluate(nl, {"PRE": (0, OD), "CLR": (0, OD)}, state={("U1", "A"): 0})["Q"] == 1   # both low: Q high


def test_bridged_jumper_joins_nets_and_rail_wins():
    nl = nl_of([("JP1", "SolderJumper_2_Open", {"1": "PRE", "2": "+3V3"}, True),
                ("R1", "1K", {"1": "SW", "2": "PRE"}, True)])
    assert evaluate(nl, {"SW": (0, STRONG)})["PRE"] == 0
    assert evaluate(nl, {"SW": (0, STRONG)}, bridged={"JP1": [("1", "2")]})["PRE"] == 1


def test_weak_pull_up_loses_to_10k_pull_down():
    nl = nl_of([("R1", "10K", {"1": "REQ", "2": "GND"}, True)])
    assert evaluate(nl, {"REQ": (1, WEAK)})["REQ"] == 0


def test_conflict_is_reported():
    nl = nl_of([("U1", "74LVC14A", {"1": "A", "2": "Y", "7": "GND", "14": "+3V3"}, True)])
    with pytest.raises(Conflict):
        evaluate(nl, {"A": (0, STRONG), "Y": (0, STRONG)})


def test_dnp_parts_are_open_unless_fitted():
    nl = nl_of([("U1", "74LVC14A", {"1": "A", "2": "Y", "7": "GND", "14": "+3V3"}, False),
                ("R1", "10K", {"1": "Y", "2": "GND"}, True)])
    assert evaluate(nl, {"A": (0, STRONG)})["Y"] == 0                     # DNP inverter: only the pull-down
    assert evaluate(nl, {"A": (0, STRONG)}, fit={"U1"})["Y"] == 1         # a live one would give 1
    nl = nl_of([("R1", "10K", {"1": "Y", "2": "+3V3"}, False)])
    assert evaluate(nl, {})["Y"] is None                                  # DNP pull-up: Y floats
    assert evaluate(nl, {}, fit={"R1"})["Y"] == 1


def test_floating_gate_input_gives_no_level():
    """RBUS-8: a gate whose input floats may drive its output either way, so the output has no level, and a check
    downstream fails instead of reading an open-drain output as released (or a pull as the gate's answer)."""
    nl = nl_of([("U1", "SN74LVC1G06", {"2": "IN", "4": "OUT", "3": "GND", "5": "+3V3"}, True),
                ("R1", "4K7", {"1": "OUT", "2": "+5V_A"}, True)])
    assert evaluate(nl, {})["OUT"] is None                                # input floats: not "released"
    assert evaluate(nl, {"IN": (0, STRONG)})["OUT"] == 1
    assert evaluate(nl, {"IN": (1, STRONG)})["OUT"] == 0
    nl = nl_of([("U1", "74LVC14A", {"1": "A", "2": "Y", "7": "GND", "14": "+3V3"}, True),
                ("R1", "10K", {"1": "Y", "2": "GND"}, True)])
    assert evaluate(nl, {})["Y"] is None                                  # push-pull: the pull-down is not its answer


def test_no_level_passes_across_a_series_resistor():
    """RBUS-8: U20 and U23 reach their bus through 33 ohm. A gate with a floating input gives its far side no level
    either, so the bus does not read as released (its pull-up's value) while the gate may be pulling it low."""
    nl = nl_of([("U1", "SN74LVC1G06", {"2": "IN", "4": "OUT", "3": "GND", "5": "+3V3"}, True),
                ("R1", "33", {"1": "OUT", "2": "BUS"}, True),
                ("R2", "4K7", {"1": "BUS", "2": "+5V_A"}, True)])
    v = evaluate(nl, {})
    assert v["OUT"] is None and v["BUS"] is None                          # input floats: the bus has no level
    assert evaluate(nl, {"IN": (0, STRONG)})["BUS"] == 1                  # input low: released, the pull-up
    assert evaluate(nl, {"IN": (1, STRONG)})["BUS"] == 0                  # input high: pulled low through the 33 ohm


def test_divider_between_rails_is_no_logic_level():
    """AMIGA_PWR, EFUSE_EN and BUCK_FB are dividers between two rails: an analog level (None), not a Conflict."""
    nl = nl_of([("R1", "1K", {"1": "+5V_A", "2": "MID"}, True), ("R2", "1K5", {"1": "MID", "2": "GND"}, True)])
    assert evaluate(nl, {})["MID"] is None


def test_released_open_drain_does_not_hold_its_bus_low():
    """A 33 ohm series resistor must not hand a net's own low back to it once its driver has released."""
    nl = nl_of([("U1", "74LVC14A", {"1": "A", "2": "B", "7": "GND", "14": "+3V3"}, True),
                ("R1", "10K", {"1": "B", "2": "GND"}, True),
                ("U2", "SN74LVC2G07", {"1": "B", "6": "OUT", "3": "GND", "4": "X", "2": "GND", "5": "+3V3"}, True),
                ("R2", "33", {"1": "OUT", "2": "BUS"}, True)])
    v = evaluate(nl, {"A": (0, STRONG), "BUS": (1, PULL)})
    assert v["OUT"] == v["BUS"] == 1


def test_interim_disagreement_is_not_a_conflict():
    """Round 2 still sees A at its pull-up's 1 while U1 already pulls it to 0, so Y is driven 0 and 1 for one round;
    at the fixed point A=0 and both inverters drive Y to 1. Only a disagreement that survives is a Conflict."""
    nl = nl_of([("U1", "74LVC14A", {"1": "N0", "2": "A", "3": "A", "4": "Y", "5": "M0", "6": "Y",
                                    "7": "GND", "14": "+3V3"}, True),
                ("R1", "10K", {"1": "A", "2": "+3V3"}, True)])
    v = evaluate(nl, {"N0": (1, STRONG), "M0": (0, STRONG)})
    assert v["A"] == 0 and v["Y"] == 1


def _small():
    return nl_of([("U1", "74LVC14A", {"1": "A", "2": "Y", "7": "GND", "14": "+3V3"}, True),
                  ("JP1", "SolderJumper_2_Open", {"1": "A", "2": "Y"}, True)])


def test_unknown_source_net_raises():
    with pytest.raises(KeyError, match="/A"):
        evaluate(_small(), {"/A": (0, STRONG)})                           # the board's "/A", not the netlist's "A"


def test_unknown_bridged_ref_raises():
    with pytest.raises(KeyError, match="JP9"):
        evaluate(_small(), {}, bridged={"JP9": [("1", "2")]})


def test_unknown_fit_ref_raises():
    with pytest.raises(KeyError, match="U99"):
        evaluate(_small(), {}, fit={"U99"})


def test_unknown_state_ref_raises():
    with pytest.raises(KeyError, match="U99"):
        evaluate(_small(), {}, state={("U99", "A"): 1})


def test_bridged_pin_not_on_the_part_raises():
    """A mistyped pad number must not turn a bridge into a no-op: a "never both drives" check would hold for nothing."""
    nl = nl_of([("U1", "74LVC14A", {"1": "X1", "2": "P", "3": "X2", "4": "Q", "7": "GND", "14": "+3V3"}, True),
                ("JP1", "SolderJumper_3_Open", {"1": "P", "2": "Q", "3": "Z"}, True)])
    sources = {"X1": (0, STRONG), "X2": (1, STRONG)}                      # P driven to 1, Q driven to 0
    v = evaluate(nl, sources)
    assert v["P"] == 1 and v["Q"] == 0
    with pytest.raises(Conflict):                                         # the real pair joins them
        evaluate(nl, sources, bridged={"JP1": [("1", "2")]})
    with pytest.raises(KeyError, match=r"pin '4'.*JP1"):                  # there is no pad 4
        evaluate(nl, sources, bridged={"JP1": [("2", "4")]})
    with pytest.raises(KeyError, match=r"pin '4'.*JP1"):                  # either side of the pair
        evaluate(nl, sources, bridged={"JP1": [("4", "2")]})
