from tools.netlist import parse_ohms


# The fitted parts outside the BOM, by ref (README "Order", rev A's rule): headers and wire pads without an LCSC number
# (J4, J5, J7, J9, J10), the solder jumpers, the test pads, the holes and the fiducials. U1 and the through-hole parts
# with an LCSC number (J1, J2, J6, J8) stay in the BOM: tools/jlc_export.py leaves them out of JLC's files by
# tools/assembly.py's HAND_PLACED and by their pads.
NOT_IN_BOM = {"J4", "J5", "J7", "J9", "J10", *(f"JP{i}" for i in range(1, 8)), *(f"TP{i}" for i in range(1, 23)),
              "H1", "H2", "FID1", "FID2", "FID3"}


def test_parts_left_out_of_the_bom(nl):
    """Task 9 review RCODE-4: a fitted part marked in_bom=False drops out of JLC's BOM and CPL, and the board arrives
    without it. So the set is written out by ref, not by prefix."""
    out = {ref for ref, c in nl.components.items() if nl.fitted(ref) and "exclude_from_bom" in c["fields"]}
    assert out == NOT_IN_BOM


def test_every_fitted_part_has_lcsc(nl):
    for ref, c in nl.components.items():
        if nl.fitted(ref) and ref not in NOT_IN_BOM:
            assert c["fields"].get("LCSC", "").startswith("C"), ref


def test_resistor_values_parse(nl):
    for ref, c in nl.components.items():
        if ref.startswith("R"):
            parse_ohms(c["value"])


TEST_PADS = ["_DKRD", "DKRD_N", "_INDEX", "INDEX_N", "_SEL0", "SEL0", "_STEP", "STEP", "_MTR0", "MTR0",
             "+5V_A", "V5SYS", "VBUS", "+3V3", "ESP_EN", "GND",                       # rev A's sixteen
             "SEL_FD", "REAL_SEL", "REAL_MTR", "DF0_FD", "DF1_EN", "MODE_CLK"]        # rev B (spec §9)


def test_test_pads(nl):
    """Spec §9: exactly these 22 pads, each a 1.0 mm probe pad (ruling SPCB-8). The mode bits are probed on the
    latch side of their 1 kΩ, so the pads show the latch and not the ESP32's reset glitch (Task 9 review RESP-1)."""
    tps = [r for r in nl.components if r.startswith("TP")]
    assert sorted(nl.net_of(r, 1) for r in tps) == sorted(TEST_PADS)
    assert nl.net_of_function("U1", "EN") == "ESP_EN"
    for ref in tps:
        assert nl.components[ref]["footprint"] == "TestPoint:TestPoint_Pad_D1.0mm", ref


def test_unfitted_pads_are_hand_solderable(nl):
    """SPCB-3: the parts JLC does not fit are 0603, not 0402."""
    unfitted = [r for r in nl.components if r.startswith(("R", "C")) and not nl.fitted(r)]
    assert unfitted
    for ref in unfitted:
        assert "_0603_" in nl.components[ref]["footprint"], ref
