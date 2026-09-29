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
