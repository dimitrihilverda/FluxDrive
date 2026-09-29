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
    for name in ("TPS259531", "TYPE-C16PIN", "171826-4"):
        sym = sch_gen.lib_symbol(f"FluxDrive:{name}")
        pins = [p for u in sch_gen.pins_of(sym).values() for p in u]
        assert pins, name
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
