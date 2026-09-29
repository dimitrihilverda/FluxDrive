"""FluxDrive v1: every part and every pin (spec v0.2). tools/sch_gen.py draws FluxDrive.kicad_sch from this.
The tests read the exported netlist, not this file. Refs are numbered in the order parts are added."""
import itertools

TITLE = "FluxDrive v1 rev A"
BLOCKS = ["A. Floppy connector and bus inputs", "B. Bus outputs", "C. Power", "D. ESP32-S3 module",
          "E. USB-C", "F. Headers, buttons, LED, test pads, mechanics"]
R0402 = "Resistor_SMD:R_0402_1005Metric"
RES_LCSC = {"22": "C25092", "33": "C25105", "100": "C25076", "470": "C25117", "1K": "C11702", "2K2": "C25879",
            "4K7": "C25900", "5K1": "C25905", "10K": "C25744", "15K": "C25756", "22K": "C25768", "100K": "C25741"}
CAPS = {"100nF": ("Capacitor_SMD:C_0402_1005Metric", "C1525"), "1uF": ("Capacitor_SMD:C_0402_1005Metric", "C52923"),
        "22nF": ("Capacitor_SMD:C_0402_1005Metric", "C1532"), "10uF": ("Capacitor_SMD:C_0603_1608Metric", "C19702"),
        "22uF": ("Capacitor_SMD:C_0805_2012Metric", "C45783"), "100uF": ("Capacitor_SMD:C_1206_3216Metric", "C15008"),
        "220pF": ("Capacitor_SMD:C_0402_1005Metric", ""), "10pF": ("Capacitor_SMD:C_0402_1005Metric", "")}
PARTS = []
_n = {k: itertools.count(1) for k in ("R", "C", "D", "TP")}
SOIC14 = "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm"


def part(ref, lib, value, footprint, pins, block, lcsc="", dnp=False, rot=0, in_bom=True):
    PARTS.append(dict(ref=ref, lib=lib, value=value, footprint=footprint, pins=pins, block=block,
                      lcsc=lcsc, dnp=dnp, rot=rot, in_bom=in_bom))


def R(value, a, b, block, dnp=False):
    part(f"R{next(_n['R'])}", "Device:R", value, R0402, {"1": a, "2": b}, block,
         "" if dnp else RES_LCSC[value], dnp, rot=90, in_bom=not dnp)


def C(value, a, b, block, dnp=False):
    fp, lcsc = CAPS[value]
    part(f"C{next(_n['C'])}", "Device:C", value, fp, {"1": a, "2": b}, block, "" if dnp else lcsc, dnp,
         rot=90, in_bom=not dnp)


A, B, P, E, U, F = BLOCKS

# --- A: connector and inputs -----------------------------------------------------------------------------
EVEN = {2: "_CHNG", 4: "_MTR0_P4", 6: "FD_PIN6", 8: "_INDEX", 10: "_SEL0", 12: "_SEL1", 14: "FD_PIN14",
        16: "_MTR0", 18: "_DIR", 20: "_STEP", 22: "_DKWD", 24: "_DKWE", 26: "_TRK0", 28: "_WPROT",
        30: "_DKRD", 32: "_SIDE", 34: "_RDY"}
j1 = {str(p): ("GND" if p != 3 else None) for p in range(1, 34, 2)}
j1.update({str(p): n for p, n in EVEN.items()})
part("J1", "Connector_Generic:Conn_02x17_Odd_Even", "Amiga floppy 34", "Connector_IDC:IDC-Header_2x17_P2.54mm_Vertical",
     j1, A, lcsc="C601943")

# signal, connector net, pull-up (value, rail) or None, GPIO, buffer, input pin, output pin, optional C pad
INPUTS = [
    ("STEP", "_STEP", ("1K", "+5V_A"), 6, "U2", 1, 2, True),
    ("DIR", "_DIR", ("1K", "+5V_A"), 7, "U2", 3, 4, False),
    ("SIDE", "_SIDE", ("1K", "+5V_A"), 15, "U2", 5, 6, False),
    ("SEL0", "_SEL0", ("1K", "+5V_A"), 17, "U2", 9, 8, True),
    ("SEL1", "_SEL1", ("10K", "+5V_A"), 9, "U2", 11, 10, True),
    ("MTR0", "_MTR0", None, 11, "U2", 13, 12, True),
    ("DKWD", "_DKWD", ("4K7", "+5V_A"), 5, "U3", 1, 2, False),
    ("DKWE", "_DKWE", ("4K7", "+5V_A"), 16, "U3", 3, 4, False),
    ("MTR0_P4", "_MTR0_P4", None, 4, "U3", 5, 6, False),
    ("PIN6", "FD_PIN6", ("10K", "+3V3"), 8, "U3", 9, 8, False),
    ("PIN14", "FD_PIN14", ("10K", "+3V3"), 10, "U3", 11, 10, False),
]
buf = {"U2": {"14": "+3V3", "7": "GND"}, "U3": {"14": "+3V3", "7": "GND", "13": "GND", "12": None}}
for sig, conn, pull, gpio, u, pin_in, pin_out, cpad in INPUTS:
    if pull:
        R(pull[0], conn, pull[1], A)
    else:
        R("1K", conn, "+5V_A", A, dnp=True)                  # /MTR0: the motherboard has R506 (spec 4.2)
    R("100", conn, f"{sig}_B", A)
    R("100K", f"{sig}_B", "+3V3", A)
    if cpad:
        C("220pF", f"{sig}_B", "GND", A, dnp=True)
    buf[u].update({str(pin_in): f"{sig}_B", str(pin_out): sig})
for u in ("U2", "U3"):
    part(u, "74xx:74HC14", "74LVC14A", SOIC14, buf[u], A, lcsc="C133541")
    C("100nF", "+3V3", "GND", A)

# --- B: outputs --------------------------------------------------------------------------------------------
OUTPUTS = [("DKRD", "_DKRD", 38, 1, 2), ("INDEX", "_INDEX", 39, 3, 4), ("TRK0", "_TRK0", 40, 5, 6),
           ("WPROT", "_WPROT", 41, 9, 8), ("CHNG", "_CHNG", 42, 11, 10), ("RDY", "_RDY", 21, 13, 12)]
u4 = {"14": "+3V3", "7": "GND"}
for sig, conn, gpio, pin_in, pin_out in OUTPUTS:
    R("10K", f"{sig}_N", "+3V3", B)
    R("33", f"{sig}_D", conn, B)
    u4.update({str(pin_in): f"{sig}_N", str(pin_out): f"{sig}_D"})
part("U4", "74xx:74LS07", "74LVC07A", SOIC14, u4, B, lcsc="C6049")
C("100nF", "+3V3", "GND", B)

PWR_FLAGS = ["GND", "+3V3"]
