"""FluxDrive v1: every part and every pin (spec v0.2). tools/sch_gen.py draws FluxDrive.kicad_sch from this.
The tests read the exported netlist, not this file. Refs are numbered in the order parts are added."""
import itertools

TITLE = "FluxDrive v1 rev A"
BLOCKS = ["A. Floppy connector and bus inputs", "B. Bus outputs", "C. Power", "D. ESP32-S3 module",
          "E. USB-C", "F. Headers, buttons, LED, test pads, mechanics"]
R0402 = "Resistor_SMD:R_0402_1005Metric"
R0603, C0603 = "Resistor_SMD:R_0603_1608Metric", "Capacitor_SMD:C_0603_1608Metric"   # unfitted: hand-solderable
RES_LCSC = {"22": "C25092", "33": "C25105", "100": "C25076", "470": "C25117", "1K": "C11702", "1K5": "C25867",
            "2K2": "C25879",
            "4K7": "C25900", "5K1": "C25905", "10K": "C25744", "15K": "C25756", "22K": "C25768", "100K": "C25741"}
CAPS = {"100nF": ("Capacitor_SMD:C_0402_1005Metric", "C1525"), "1uF": ("Capacitor_SMD:C_0402_1005Metric", "C52923"),
        "22nF": ("Capacitor_SMD:C_0402_1005Metric", "C1532"), "10uF": ("Capacitor_SMD:C_0603_1608Metric", "C19702"),
        "22uF": ("Capacitor_SMD:C_0805_2012Metric", "C45783"), "47uF": ("Capacitor_SMD:C_1206_3216Metric", "C96123")}
PARTS = []
_n = {k: itertools.count(1) for k in ("R", "C", "D", "TP")}
SOIC14 = "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm"


def part(ref, lib, value, footprint, pins, block, lcsc="", dnp=False, rot=0, in_bom=True):
    PARTS.append(dict(ref=ref, lib=lib, value=value, footprint=footprint, pins=pins, block=block,
                      lcsc=lcsc, dnp=dnp, rot=rot, in_bom=in_bom))


def R(value, a, b, block, dnp=False):
    part(f"R{next(_n['R'])}", "Device:R", value, R0603 if dnp else R0402, {"1": a, "2": b}, block,
         "" if dnp else RES_LCSC[value], dnp, rot=90, in_bom=not dnp)


def C(value, a, b, block, dnp=False):
    fp, lcsc = (C0603, "") if dnp else CAPS[value]
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

# signal, connector net, pull-up (value, rail) or None, GPIO, buffer, input pin, output pin, optional C pad.
# U3 (west) takes the lines on J1 pins 4-16, U2 (east) the ones on pins 18-32, each in the connector's
# west-to-east order over the gates (input pins 1, 13, 3, 11, 5, 9 with the SOIC turned 90 degrees on the
# board), so the lines from the connector to the buffers do not cross (layout review LBUS-3).
INPUTS = [
    ("STEP", "_STEP", ("1K", "+5V_A"), 6, "U2", 13, 12, True),        # J1 pin 20
    ("DIR", "_DIR", ("1K", "+5V_A"), 7, "U2", 1, 2, False),           # 18
    ("SIDE", "_SIDE", ("1K", "+5V_A"), 15, "U2", 5, 6, False),        # 32
    ("SEL0", "_SEL0", ("1K", "+5V_A"), 17, "U3", 3, 4, True),         # 10
    ("SEL1", "_SEL1", ("10K", "+5V_A"), 9, "U3", 11, 10, True),       # 12
    ("MTR0", "_MTR0", None, 11, "U3", 9, 8, True),                    # 16
    ("DKWD", "_DKWD", ("4K7", "+5V_A"), 5, "U2", 3, 4, False),        # 22
    ("DKWE", "_DKWE", ("4K7", "+5V_A"), 16, "U2", 11, 10, False),     # 24
    ("MTR0_P4", "_MTR0_P4", None, 4, "U3", 1, 2, False),              # 4
    ("PIN6", "FD_PIN6", ("10K", "+3V3"), 8, "U3", 13, 12, False),     # 6
    ("PIN14", "FD_PIN14", ("10K", "+3V3"), 10, "U3", 5, 6, False),    # 14
]
buf = {"U2": {"14": "+3V3", "7": "GND", "9": "GND", "8": None}, "U3": {"14": "+3V3", "7": "GND"}}
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
# signal, connector net, GPIO, U4 input pin, output pin. The gates whose output faces the connector (the
# bottom row with the SOIC turned 90 degrees: 2, 4, 6) take /WPROT, /DKRD and /RDY in the connector's order,
# so /DKRD runs straight down to its 33 ohm; /TRK0, /CHNG and /INDEX go the long way anyway (layout review LBUS-4).
OUTPUTS = [("DKRD", "_DKRD", 38, 3, 4), ("INDEX", "_INDEX", 39, 9, 8), ("TRK0", "_TRK0", 40, 13, 12),
           ("WPROT", "_WPROT", 41, 1, 2), ("CHNG", "_CHNG", 42, 11, 10), ("RDY", "_RDY", 21, 5, 6)]
u4 = {"14": "+3V3", "7": "GND"}
for sig, conn, gpio, pin_in, pin_out in OUTPUTS:
    R("10K", f"{sig}_N", "+3V3", B)
    R("33", f"{sig}_D", conn, B)
    u4.update({str(pin_in): f"{sig}_N", str(pin_out): f"{sig}_D"})
part("U4", "74xx:74LCX07", "74LVC07A", SOIC14, u4, B, lcsc="C6049")     # same pinout and open-drain outputs
C("100nF", "+3V3", "GND", B)

# --- C: power ------------------------------------------------------------------------------------------------
part("J2", "FluxDrive:171825-4", "Floppy power", "FluxDrive:171825-4",          # vertical (spec 8)
     {"1": "+5V_IN", "2": "GND", "3": "GND", "4": None}, P, lcsc="C210162")
part("D4", "Diode:SMAJ13A", "SMAJ13A", "Diode_SMD:D_SMA", {"1": "+5V_IN", "2": "GND"}, P, dnp=True,
     in_bom=False)                          # unfitted: 13 V standoff, for hot-plug ringing (review SPWR-3)
part("U5", "FluxDrive:TPS259531", "TPS259531", "Package_SON:Texas_DSG0008A_WSON-8-1EP_2x2mm_P0.5mm_EP0.9x1.6mm",
     {"1": "EFUSE_DVDT", "2": "EFUSE_EN", "3": "+5V_IN", "4": "+5V_IN", "5": "+5V_A", "6": None,
      "7": "EFUSE_ILM", "8": "GND", "9": "GND"}, P, lcsc="C2155674")
C("1uF", "+5V_IN", "GND", P)
C("22nF", "EFUSE_DVDT", "GND", P)
R("10K", "+5V_IN", "EFUSE_EN", P)           # UVLO 1.2 V x 14.7/4.7 = 3.75 V; EN 3.8 V with 12 V on IN
R("4K7", "EFUSE_EN", "GND", P)
R("2K2", "EFUSE_ILM", "GND", P)             # current limit about 0.95 A
C("47uF", "+5V_A", "GND", P)               # 10 V parts: the clamp is 5.7 V (review SPCB-2)
C("47uF", "+5V_A", "GND", P)
C("100nF", "+5V_A", "GND", P)
part("D1", "Diode:SS34", "SS34", "Diode_SMD:D_SMA", {"1": "V5SYS", "2": "+5V_A"}, P, lcsc="C8678")
part("D2", "Diode:SS34", "SS34", "Diode_SMD:D_SMA", {"1": "V5SYS", "2": "VBUS"}, P, lcsc="C8678")
C("10uF", "V5SYS", "GND", P)               # 4.7 uF if the damper below is fitted (USB limit 10 uF)
C("100nF", "V5SYS", "GND", P)
R("1R", "V5SYS", "V5SYS_DAMP", P, dnp=True)  # unfitted hot-plug damper (review SPWR-2)
C("4.7uF", "V5SYS_DAMP", "GND", P, dnp=True)
part("U6", "Regulator_Switching:TLV62569DBV", "TLV62569DBVR", "Package_TO_SOT_SMD:SOT-23-5",
     {"EN": "V5SYS", "GND": "GND", "SW": "BUCK_SW", "VIN": "V5SYS", "FB": "BUCK_FB"}, P, lcsc="C141836")
part("L1", "Device:L", "2.2uH", "Inductor_SMD:L_Sunlord_SWPA4020S", {"1": "BUCK_SW", "2": "+3V3"}, P, lcsc="C83423")
R("100K", "+3V3", "BUCK_FB", P)             # 0.6 V x (1 + 100/22) = 3.33 V
R("22K", "BUCK_FB", "GND", P)
C("15pF", "+3V3", "BUCK_FB", P, dnp=True)    # feed-forward, optional; 15 pF suits the 100k top (review SPWR-5)
C("22uF", "+3V3", "GND", P)
R("1K", "+5V_A", "AMIGA_PWR", P)            # 3.0 V at 5 V, 3.5 V at the clamp; stiff enough that the bus
R("1K5", "AMIGA_PWR", "GND", P)             # pull-ups cannot lift it on USB alone (review SESP-1)
PWR_FLAGS = ["GND", "+3V3", "+5V_IN", "V5SYS", "VBUS"]          # +5V_A is driven by the eFuse OUT pin

# --- D: ESP32-S3 module --------------------------------------------------------------------------------------
esp = {"1": "GND", "40": "GND", "41": "GND", "3V3": "+3V3", "EN": "ESP_EN", "IO0": "BOOT", "IO1": "AMIGA_PWR",
       "IO2": "LED", "USB_D-": "USB_DN", "USB_D+": "USB_DP", "TXD0": "ESP_TXD0", "RXD0": "ESP_RXD0",
       "IO13": "GPIO13", "IO14": "GPIO14", "IO47": "GPIO47", "IO48": "GPIO48"}
for g in (3, 12, 18, 35, 36, 37, 45, 46):
    esp[f"IO{g}"] = None
for sig, _, _, gpio, *_ in INPUTS:
    esp[f"IO{gpio}"] = sig
for sig, _, gpio, *_ in OUTPUTS:
    esp[f"IO{gpio}"] = f"{sig}_N"
part("U1", "RF_Module:ESP32-S3-WROOM-1", "ESP32-S3-WROOM-1-N16R8", "FluxDrive:ESP32-S3-WROOM-1", esp, E,
     lcsc="C2913202")
C("22uF", "+3V3", "GND", E)
C("100nF", "+3V3", "GND", E)
R("10K", "+3V3", "ESP_EN", E)
C("1uF", "ESP_EN", "GND", E)
R("10K", "+3V3", "BOOT", E)
BTN = "Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A"
part("SW1", "Switch:SW_Push", "BOOT", BTN, {"1": "BOOT", "2": "GND"}, E, lcsc="C318884")
part("SW2", "Switch:SW_Push", "RESET", BTN, {"1": "ESP_EN", "2": "GND"}, E, lcsc="C318884")

# --- E: USB-C ------------------------------------------------------------------------------------------------
part("J3", "FluxDrive:TYPE-C16PIN", "USB-C", "FluxDrive:USB-C-SMD_TYPE-C16PIN",
     {"A1B12": "GND", "B1A12": "GND", "A4B9": "VBUS", "B4A9": "VBUS", "A5": "USB_CC1", "B5": "USB_CC2",
      "A6": "USB_DP_C", "B6": "USB_DP_C", "A7": "USB_DN_C", "B7": "USB_DN_C", "A8": None, "B8": None,
      "1": "GND", "2": "GND", "3": "GND", "4": "GND"}, U, lcsc="C393939")
R("5K1", "USB_CC1", "GND", U)
R("5K1", "USB_CC2", "GND", U)
part("U7", "Power_Protection:USBLC6-2SC6", "USBLC6-2SC6", "Package_TO_SOT_SMD:SOT-23-6",
     {"1": "USB_DN_C", "6": "USB_DN_C", "3": "USB_DP_C", "4": "USB_DP_C", "5": "+3V3", "2": "GND"}, U,
     lcsc="C2687116")                       # pin 5 on 3V3: on VBUS, D+ would lift VBUS (review SPWR-1)
R("10K", "VBUS", "GND", U)                  # bleeds D2's leakage, so VBUS reads 0 V without a cable
R("22", "USB_DP_C", "USB_DP", U)
R("22", "USB_DN_C", "USB_DN", U)
C("10pF", "USB_DP", "GND", U, dnp=True)
C("10pF", "USB_DN", "GND", U, dnp=True)

# --- F: headers, LED, test pads, mechanics -------------------------------------------------------------------
HDR6 = "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical"
R("470", "ESP_TXD0", "UART_TX", F)
part("J4", "Connector_Generic:Conn_01x06", "UART / recovery", HDR6,
     {"1": "UART_TX", "2": "ESP_RXD0", "3": "ESP_EN", "4": "BOOT", "5": "+3V3", "6": "GND"}, F, in_bom=False)
part("J5", "Connector_Generic:Conn_01x06", "Spare GPIO", HDR6,
     {"1": "GPIO13", "2": "GPIO14", "3": "GPIO47", "4": "GPIO48", "5": "+3V3", "6": "GND"}, F, in_bom=False)
R("1K", "LED", "LED_A", F)
part("D3", "Device:LED", "LED red", "LED_SMD:LED_0603_1608Metric", {"1": "GND", "2": "LED_A"}, F, lcsc="C2286")
for net in ("_DKRD", "DKRD_N", "_INDEX", "INDEX_N", "_SEL0", "SEL0", "_STEP", "STEP", "_MTR0", "MTR0",
            "+5V_A", "V5SYS", "VBUS", "+3V3", "ESP_EN", "GND"):
    part(f"TP{next(_n['TP'])}", "Connector:TestPoint", net, "TestPoint:TestPoint_Pad_D1.0mm", {"1": net}, F,
         in_bom=False)
for i in (1, 2):
    part(f"H{i}", "Mechanical:MountingHole", "3.2mm", "MountingHole:MountingHole_3.2mm_M3", {}, F, in_bom=False)
for i in (1, 2, 3):
    part(f"FID{i}", "Mechanical:Fiducial", "Fiducial", "Fiducial:Fiducial_1mm_Mask2mm", {}, F, in_bom=False)
