import pathlib

from tools.netlist import _child, _children, _parse_sexpr

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_module_ground_pad_solder_through_hole():
    """Rev B §9: a 1.0 mm plated hole at the ground pad's centre, mask open on both sides; the four inner thermal
    vias go, the other eight stay tented."""
    fp = _parse_sexpr((ROOT / "FluxDrive.pretty" / "ESP32-S3-WROOM-1.kicad_mod").read_text(encoding="utf-8"))
    pads41 = [p for p in _children(fp, "pad") if p[1] == "41"]
    ep = next(p for p in pads41 if p[2] == "smd" and float(_child(p, "size")[1]) > 3)
    cx, cy = float(_child(ep, "at")[1]), float(_child(ep, "at")[2])
    holes = [p for p in pads41 if p[2] == "thru_hole"]
    big = [p for p in holes if abs(float(_child(p, "drill")[1]) - 1.0) < 0.01]
    assert len(big) == 1
    bx, by = float(_child(big[0], "at")[1]), float(_child(big[0], "at")[2])
    assert abs(bx - cx) < 0.01 and abs(by - cy) < 0.01
    assert {"F.Mask", "B.Mask"} <= set(_child(big[0], "layers")[1:])
    small = [p for p in holes if p is not big[0]]
    assert len(small) == 8 and all("B.Mask" not in _child(p, "layers")[1:] for p in small)
