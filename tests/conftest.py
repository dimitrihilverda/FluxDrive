import pathlib
import subprocess

import pytest

from tools import netlist

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLI = r"C:/Program Files/KiCad/10.0/bin/kicad-cli.exe"


@pytest.fixture(scope="session")
def nl(tmp_path_factory):
    """Netlist of FluxDrive.kicad_sch, exported fresh. Fails if that file is not what hardware/design.py gives."""
    import hardware.design as d
    from tools import sch_gen
    fresh = sch_gen.generate(d.TITLE, d.BLOCKS, d.PARTS, d.PWR_FLAGS)
    if fresh != (ROOT / "FluxDrive.kicad_sch").read_text(encoding="utf-8"):
        pytest.fail("FluxDrive.kicad_sch is out of date with hardware/design.py: run  bash tools/export_netlist.sh")
    out = tmp_path_factory.mktemp("net") / "FluxDrive.net"
    subprocess.run([CLI, "sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(out),
                    str(ROOT / "FluxDrive.kicad_sch")], check=True, capture_output=True)
    return netlist.load(out)
