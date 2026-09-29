from tools.netlist import parse_ohms


def test_every_fitted_part_has_lcsc(nl):
    for ref, c in nl.components.items():
        if ref.startswith("#") or not nl.fitted(ref) or ref.startswith(("TP", "H", "FID", "J4", "J5")):
            continue
        assert c["fields"].get("LCSC", "").startswith("C"), ref


def test_resistor_values_parse(nl):
    for ref, c in nl.components.items():
        if ref.startswith("R"):
            parse_ohms(c["value"])


def test_test_pads(nl):
    nets = {nl.net_of(r, 1) for r in nl.components if r.startswith("TP")}
    need = {"_DKRD", "DKRD_N", "_INDEX", "INDEX_N", "_SEL0", "SEL0", "_STEP", "STEP", "_MTR0", "MTR0",
            "+5V_A", "V5SYS", "VBUS", "+3V3", "GND"}
    en = nl.net_of_function("U1", "EN")
    assert need | {en} <= nets
