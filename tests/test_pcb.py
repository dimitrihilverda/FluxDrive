import pathlib

import pytest

from tools import pcb

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def board():
    return pcb.load(ROOT / "FluxDrive.kicad_pcb")


def test_outline(board):
    x0, y0, x1, y1 = pcb.board_extents(board)
    assert x1 - x0 >= 56.0 and 40.0 <= y1 - y0 <= 48.0


def test_connector_along_south_edge(board):
    fps = pcb.footprints(board)
    x0, y0, x1, y1 = pcb.board_extents(board)
    jx, jy, rot, layer = fps["J1"]
    assert layer == "F.Cu" and rot in (90.0, 270.0) and jy > y1 - 8.0


def test_module_antenna_over_north_edge(board):
    fps = pcb.footprints(board)
    x0, y0, x1, y1 = pcb.board_extents(board)
    ux, uy, rot, layer = fps["U1"]
    assert layer == "F.Cu" and rot == 0.0 and uy - 12.75 < y0          # body top (antenna end) past the edge


def test_power_header_next_to_connector(board):
    fps = pcb.footprints(board)
    assert abs(fps["J2"][1] - fps["J1"][1]) < 12.0
