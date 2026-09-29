import pathlib
import subprocess

import pytest

from tools import netlist, sch_gen

CLI = r"C:/Program Files/KiCad/10.0/bin/kicad-cli.exe"


def test_tiny_design_round_trips(tmp_path):
    sch = tmp_path / "tiny.kicad_sch"
    sch_gen.main(str(sch), "tests.fixtures.tiny_design")
    net = tmp_path / "tiny.net"
    subprocess.run([CLI, "sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(net), str(sch)], check=True)
    nl = netlist.load(net)
    assert nl.net_of("R1", 2) == "SIG" and nl.net_of("U1", 1) == "SIG"
    assert nl.net_of("U1", 2) == "OUT" and nl.net_of("R2", 1) == "OUT"
    assert nl.net_of("U1", 14) == "+3V3" and nl.net_of("U1", 7) == "GND"
    erc = tmp_path / "erc.txt"
    r = subprocess.run([CLI, "sch", "erc", "--severity-error", "--exit-code-violations", "-o", str(erc), str(sch)])
    assert r.returncode == 0, erc.read_text()


def test_missing_pin_is_an_error():
    import copy
    import tests.fixtures.tiny_design as d
    parts = copy.deepcopy(d.PARTS)
    del parts[1]["pins"]["12"]
    with pytest.raises(ValueError, match="U1.*12"):
        sch_gen.generate("t", ["A. test"], parts, [])


def test_project_symbols_load():
    for name in ("TPS259531", "TYPE-C16PIN", "171825-4"):
        sym = sch_gen.lib_symbol(f"FluxDrive:{name}")
        pins = [p for u in sch_gen.pins_of(sym).values() for p in u]
        assert pins, name
        fp = next(c[2] for c in sym if isinstance(c, list) and c[0] == "property" and c[1] == "Footprint")
        assert fp.startswith(("FluxDrive:", "Package_")), (name, fp)                # SPCB-5
    pins = {n: name for n, name, *_ in sch_gen.pins_of(sch_gen.lib_symbol("FluxDrive:TPS259531"))[1]}
    assert pins["3"] == pins["4"] == "IN" and pins["5"] == "OUT" and pins["7"] == "ILM"


def test_generation_is_deterministic():
    import tests.fixtures.tiny_design as d
    a = sch_gen.generate(d.TITLE, d.BLOCKS, d.PARTS, d.PWR_FLAGS)
    b = sch_gen.generate(d.TITLE, d.BLOCKS, d.PARTS, d.PWR_FLAGS)
    assert a == b


def test_everything_fits_on_the_sheet():
    import re
    import hardware.design as d
    text = sch_gen.generate(d.TITLE, d.BLOCKS, d.PARTS, d.PWR_FLAGS)
    paper = re.search(r'\(paper "(A\d)"\)', text).group(1)
    w, h = sch_gen.PAPERS[paper]
    ats = [(float(x), float(y)) for x, y in re.findall(r"\(at ([\d.\-]+) ([\d.\-]+)", text)]
    assert max(x for x, _ in ats) < w - 10 and max(y for _, y in ats) < h - 10, paper



def test_pin_assigned_twice_is_an_error():
    """SCODE-3: a pin named by number and by name must not silently take the last net."""
    import copy
    import tests.fixtures.tiny_design as d
    parts = copy.deepcopy(d.PARTS)
    parts[1]["pins"]["GND"] = "OTHER"                  # pin 7 is GND, and it is already in the design as "7"
    with pytest.raises(ValueError, match="U1.*7.*twice"):
        sch_gen.generate("t", ["A. test"], parts, [])


TEST_LIB = """(kicad_symbol_lib
  (symbol "Dual" (property "Reference" "U" (at 0 0 0)) (property "Value" "Dual" (at 0 0 0))
    (property "Footprint" "" (at 0 0 0))
    (symbol "Dual_0_1" (pin power_in line (at 0 7.62 270) (length 2.54) (name "V+") (number "8")))
    (symbol "Dual_1_1" (pin input line (at -7.62 0 0) (length 2.54) (name "A") (number "1")))
    (symbol "Dual_2_1" (pin input line (at -7.62 0 0) (length 2.54) (name "B") (number "2"))))
  (symbol "Stack" (property "Reference" "U" (at 0 0 0)) (property "Value" "Stack" (at 0 0 0))
    (property "Footprint" "" (at 0 0 0))
    (symbol "Stack_1_1" (pin passive line (at -7.62 0 0) (length 2.54) (name "G") (number "1"))
                        (pin passive line (at -7.62 0 0) (length 2.54) (name "G") (number "2")))))"""


def _test_part(lib, pins):
    return [dict(ref="U1", lib=f"Test:{lib}", value=lib, footprint="", pins=pins, block="A. test", rot=0)]


@pytest.fixture
def test_lib(monkeypatch):
    from tools.sexpr import children, parse
    monkeypatch.setitem(sch_gen._libs, "Test", {s[1]: s for s in children(parse(TEST_LIB), "symbol")})


def test_common_pins_of_multi_unit_symbols_get_unique_ids(test_lib):
    """SCODE-4: pin 8 is drawn on both units; every uuid in the file must still be unique."""
    import re
    text = sch_gen.generate("t", ["A. test"], _test_part("Dual", {"1": "A", "2": "B", "8": "+3V3"}), [])
    ids = re.findall(r'\(uuid "([0-9a-f-]+)"\)', text)
    assert ids and len(ids) == len(set(ids))


def test_stacked_pins_on_different_nets_are_an_error(test_lib):
    """SCODE-2: two labels on one point would merge two nets without a word from ERC."""
    sch_gen.generate("t", ["A. test"], _test_part("Stack", {"1": "GND", "2": "GND"}), [])
    with pytest.raises(ValueError, match="U1.*stacked"):
        sch_gen.generate("t", ["A. test"], _test_part("Stack", {"1": "GND", "2": "OTHER"}), [])
    with pytest.raises(ValueError, match="U1.*stacked"):
        sch_gen.generate("t", ["A. test"], _test_part("Stack", {"1": "GND", "2": None}), [])


def test_unplaced_parts_stay_out_of_the_position_file():
    """SPCB-7: in_pos_files = in_bom and not dnp."""
    import re
    import hardware.design as d
    text = sch_gen.generate(d.TITLE, d.BLOCKS, d.PARTS, d.PWR_FLAGS)
    flags = re.findall(r"\(in_bom (yes|no)\)\s*\(on_board \w+\)\s*\(in_pos_files (yes|no)\)\s*\(dnp (yes|no)\)", text)
    assert len(flags) == text.count("(lib_id ")
    for in_bom, pos, dnp in flags:
        assert pos == ("yes" if in_bom == "yes" and dnp == "no" else "no")


def test_real_schematic_erc(nl, tmp_path):
    """SCODE-2: the real schematic at every severity; only the 14 known footprint_filter warnings (the 74HC14
    symbol's filter lists DIP only) may remain. `nl` first proves the file is up to date."""
    import re
    root = pathlib.Path(__file__).resolve().parents[1]
    rep = tmp_path / "erc.txt"
    subprocess.run([CLI, "sch", "erc", "--severity-all", "-o", str(rep), str(root / "FluxDrive.kicad_sch")],
                   check=True, capture_output=True)
    kinds = re.findall(r"^\[(\w+)\]", rep.read_text(encoding="utf-8"), re.M)
    assert set(kinds) <= {"footprint_filter"}, sorted(set(kinds))
