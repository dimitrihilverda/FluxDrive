from tools import sexpr
from tools.netlist import parse_ohms


def test_sexpr_round_trip_keeps_quotes():
    text = '(kicad_sch (version 20260101) (symbol (lib_id "Device:R") (at 1.27 2.54 90)))'
    node = sexpr.parse(text)
    again = sexpr.parse(sexpr.dump(node))
    assert again == node
    assert isinstance(sexpr.child(again, "symbol")[1][1], sexpr.Q)


def test_parse_ohms():
    assert parse_ohms("4K7") == 4700 and parse_ohms("100") == 100 and parse_ohms("2K2") == 2200
