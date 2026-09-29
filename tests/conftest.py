import os
import pathlib

import pytest

from tools import netlist

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def nl():
    path = pathlib.Path(os.environ.get("FD_NETLIST", ROOT / "build" / "FluxDrive.net"))
    if not path.exists():
        pytest.fail(f"{path} is missing: run  bash tools/export_netlist.sh  first")
    return netlist.load(path)
