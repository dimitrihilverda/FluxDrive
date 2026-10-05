import pathlib
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


ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_bom_comment_lists_every_value():
    """Build-rulings minor: parts grouped in one BOM line with different values show all of them (SW1 BOOT and SW2
    RESET gave the comment "BOOT")."""
    from tools.jlc_rules import comment
    assert comment(["BOOT", "RESET"]) == "BOOT/RESET"
    assert comment(["100K", "100K"]) == "100K"


def test_gerber_zip_holds_files_only():
    """Build-rulings minor: kicad-cli leaves an org.kicad.kicad/ directory; the zip must not carry it."""
    import zipfile
    zp = ROOT / "jlcpcb" / "production_files" / "GERBER-FluxDrive.zip"
    assert all(not n.endswith("/") for n in zipfile.ZipFile(zp).namelist())


def test_maze_router_takes_its_widths_from_the_netclasses():
    """LCODE-8: tools/pcb_maze.py reads the track widths of FluxDrive.kicad_pro's netclasses, not constants."""
    from tools.netclass import netclass_widths, width_of
    w = netclass_widths(ROOT / "FluxDrive.kicad_pro")
    assert width_of("/+5V_A", *w) == 0.3 and width_of("/STEP_B", *w) == 0.2       # Power and Default
    src = (ROOT / "tools" / "pcb_maze.py").read_text(encoding="utf-8")
    assert "width_of(" in src and "POWER = {" not in src


def test_netlist_strings_unescaped():
    """SCODE-7: KiCad escapes a backslash and a quote in netlist strings; both must come back as themselves."""
    from tools.netlist import _parse_sexpr
    assert _parse_sexpr(r'(net (name "A\\B\"C"))') == ["net", ["name", 'A\\B"C']]
