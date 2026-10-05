TITLE = "tiny"
BLOCKS = ["A. test"]
PARTS = [
    dict(ref="R1", lib="Device:R", value="10K", footprint="Resistor_SMD:R_0402_1005Metric", lcsc="C25744",
         pins={"1": "+3V3", "2": "SIG"}, block="A. test", dnp=False, rot=90, in_bom=True),
    dict(ref="U1", lib="74xx:74HC14", value="74LVC14A", footprint="Package_SO:SOIC-14_3.9x8.7mm_P1.27mm",
         lcsc="C133541", block="A. test", dnp=False, rot=0, in_bom=True,
         pins={"1": "SIG", "2": "OUT", "3": "GND", "4": None, "5": "GND", "6": None, "9": "GND", "8": None,
               "11": "GND", "10": None, "13": "GND", "12": None, "14": "+3V3", "7": "GND"}),
    dict(ref="R2", lib="Device:R", value="1K", footprint="Resistor_SMD:R_0402_1005Metric", lcsc="C11702",
         pins={"1": "OUT", "2": "GND"}, block="A. test", dnp=False, rot=90, in_bom=True),
    dict(ref="R3", lib="Device:R", value="1K", footprint="Resistor_SMD:R_0603_1608Metric", lcsc="",
         pins={"1": "OUT", "2": "GND"}, block="A. test", dnp=True, rot=180, in_bom=False),
    dict(ref="D1", lib="Device:D", value="1N4148W", footprint="Diode_SMD:D_SOD-123", lcsc="C81598",
         pins={"K": "+3V3", "A": "SIG"}, block="A. test", dnp=False, rot=270, in_bom=True),
]
PWR_FLAGS = ["+3V3", "GND"]
