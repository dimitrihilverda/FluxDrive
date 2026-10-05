"""FluxDrive v1: every part and every pin (spec v0.2). tools/sch_gen.py draws FluxDrive.kicad_sch from this.
The tests read the exported netlist, not this file. Refs are numbered in the order parts are added."""
import itertools

TITLE = "FluxDrive v1 rev B"
BLOCKS = ["A. Floppy connector and bus inputs", "B. Bus outputs", "C. Power", "D. ESP32-S3 module",
          "E. USB-C", "F. Headers, buttons, LED, test pads, mechanics", "G. Drive pass-through and DF0/DF1 swap"]
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


A, B, P, E, U, F, G = BLOCKS

# --- A: connector and inputs -----------------------------------------------------------------------------
EVEN = {2: "_CHNG", 4: None, 6: None, 8: "_INDEX", 10: "_SEL0", 12: "_SEL1", 14: None,
        16: "_MTR0", 18: "_DIR", 20: "_STEP", 22: "_DKWD", 24: "_DKWE", 26: "_TRK0", 28: "_WPROT",
        30: "_DKRD", 32: "_SIDE", 34: "_RDY"}          # rev B spec §7: pins 4, 6, 14 are not used on the A500
j1 = {str(p): ("GND" if p != 3 else None) for p in range(1, 34, 2)}
j1.update({str(p): n for p, n in EVEN.items()})
part("J1", "Connector_Generic:Conn_02x17_Odd_Even", "Amiga floppy 34", "Connector_IDC:IDC-Header_2x17_P2.54mm_Vertical",
     j1, A, lcsc="C601943")

# signal, connector net, pull-up, GPIO, buffer, input pin, output pin, C pad, 1 kOhm to the GPIO (rev B §4.1).
# U3 (west) takes the lines on J1 pins 10-16, U2 (east) the ones on pins 18-32, each in the connector's west-to-east
# order over the gates (input pins 1, 13, 3, 11, 5, 9 with the SOIC turned 90 degrees; layout review LBUS-3).
INPUTS = [
    ("STEP", "_STEP", ("4K7", "+5V_A"), 6, "U2", 13, 12, True, False),      # J1 pin 20
    ("DIR", "_DIR", ("4K7", "+5V_A"), 7, "U2", 1, 2, False, False),         # 18
    ("SIDE", "_SIDE", ("4K7", "+5V_A"), 15, "U2", 5, 6, False, False),      # 32
    ("SEL0", "_SEL0", ("1K", "+5V_A"), 17, "U3", 3, 4, True, True),         # 10
    ("SEL1", "_SEL1", ("1K", "+5V_A"), 9, "U3", 11, 10, True, True),        # 12
    ("MTR0", "_MTR0", None, 11, "U3", 9, 8, True, True),                    # 16
    ("DKWD", "_DKWD", ("4K7", "+5V_A"), 5, "U2", 3, 4, False, False),       # 22
    ("DKWE", "_DKWE", ("4K7", "+5V_A"), 16, "U2", 11, 10, False, False),    # 24
]
GPIO_NET = {}
buf = {"U2": {"14": "+3V3", "7": "GND", "9": "SEL_FD", "8": "SEL_FD_N"},   # U2's spare makes SEL_FD_N (§4.2)
       "U3": {"14": "+3V3", "7": "GND",
              "1": "RST_B", "2": "RST_ACT",              # rev A's J1 pin 4 gate: the reset wire (§4.8)
              "5": "MTRX_B", "6": "M4_MOTOR",            # rev A's pin 14 gate: mode 4's motor line (§4.7)
              "13": "M4_MTR_Q", "12": "M4_MTR_N"}}       # rev A's pin 6 gate: NOT M4_MTR for the DF1 ID (§4.7)
for sig, conn, pull, gpio, u, pin_in, pin_out, cpad, iso in INPUTS:
    if pull:
        R(pull[0], conn, pull[1], A)
    else:
        R("1K", conn, "+5V_A", A, dnp=True)                  # /MTR0: the motherboard has R506 (spec 4.2)
    R("100", conn, f"{sig}_B", A)
    R("100K", f"{sig}_B", "+3V3", A)
    if cpad:
        C("220pF", f"{sig}_B", "GND", A, dnp=True)
    if iso:
        R("1K", sig, f"{sig}_IO", A)
    GPIO_NET[gpio] = f"{sig}_IO" if iso else sig
    buf[u].update({str(pin_in): f"{sig}_B", str(pin_out): sig})
R("100", "KBRESET", "RST_B", A)                               # the reset wire's input (§4.8)
R("100K", "RST_B", "+3V3", A)
R("4K7", "MTRX", "+5V_A", A, dnp=True)                        # mode 4's motor wire (§4.7)
R("100", "MTRX", "MTRX_B", A, dnp=True)
R("100K", "MTRX_B", "+3V3", A)
R("100K", "M4_MTR_Q", "GND", A)
for u in ("U2", "U3"):
    part(u, "74xx:74HC14", "74LVC14A", SOIC14, buf[u], A, lcsc="C133541")
    C("100nF", "+3V3", "GND", A)

# --- B: outputs --------------------------------------------------------------------------------------------
# signal, connector net, GPIO, buffer, buffer in/out pins, OR chip and its (a, b, y) pins (rev B spec §4.3):
# U4 keeps the east-end outputs, the SN74LVC2G07 U17 drives /CHNG and /INDEX at the west end
OUTPUTS = [("DKRD", "_DKRD", 38, "U4", 3, 4, "U10", (1, 2, 3)), ("TRK0", "_TRK0", 40, "U4", 13, 12, "U10", (4, 5, 6)),
           ("WPROT", "_WPROT", 41, "U4", 1, 2, "U10", (9, 10, 8)), ("RDY", "_RDY", 21, "U4", 5, 6, "U10", (12, 13, 11)),
           ("CHNG", "_CHNG", 42, "U17", 1, 6, "U11", (1, 2, 3)), ("INDEX", "_INDEX", 39, "U17", 3, 4, "U11", (4, 5, 6))]
pins_of = {"U4": {"14": "+3V3", "7": "GND", "9": "+3V3", "11": "+3V3", "8": None, "10": None},
           "U17": {"2": "GND", "5": "+3V3"},
           "U10": {"14": "+3V3", "7": "GND"},
           "U11": {"14": "+3V3", "7": "GND", "9": "SEL0", "10": "SEL1", "8": "BUSY", "12": "GND", "13": "GND",
                   "11": None}}
for sig, conn, gpio, bufr, pin_in, pin_out, orc, (a, b, y) in OUTPUTS:
    R("10K", f"{sig}_N", "+3V3", B)                 # release pull-up, on the OR input (rev B §4.3)
    R("33", f"{sig}_D", conn, B)
    pins_of[orc].update({str(a): f"{sig}_N", str(b): "SEL_FD_N", str(y): f"{sig}_G"})
    pins_of[bufr].update({str(pin_in): f"{sig}_G", str(pin_out): f"{sig}_D"})
    GPIO_NET[gpio] = f"{sig}_N"
part("U4", "74xx:74LCX07", "74LVC07A", SOIC14, pins_of["U4"], B, lcsc="C6049")
C("100nF", "+3V3", "GND", B)
part("U17", "74xGxx:74LVC2G07", "SN74LVC2G07", "Package_TO_SOT_SMD:SOT-23-6", pins_of["U17"], B, lcsc="C37708")
C("100nF", "+3V3", "GND", B)
TSSOP14 = "Package_SO:TSSOP-14_4.4x5mm_P0.65mm"
for u in ("U10", "U11"):
    part(u, "74xx:74LS32", "74LVC32A", TSSOP14, pins_of[u], B, lcsc="C6087")
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
       "IO2": "LED", "USB_D-": "USB_DN", "USB_D+": "USB_DP", "TXD0": "ESP_TXD0", "RXD0": "ESP_RXD0"}
for g in (3, 4, 8, 10, 12, 18, 35, 36, 37, 45, 46):
    esp[f"IO{g}"] = None
for gpio, net in GPIO_NET.items():
    esp[f"IO{gpio}"] = net
esp.update({"IO47": "MODE_CLK_REQ", "IO48": "DF0_REQ", "IO13": "DF1_REQ", "IO14": "CHNG_REQ",
            "IO10": "RST_REQ", "IO12": "DF0_STATE", "IO8": "DF1_STATE", "IO4": "RST_ACT_IO", "IO18": "GPIO18",
            "IO3": "GPIO3"})
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
HDR4 = "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical"
part("J5", "Connector_Generic:Conn_01x04", "Spare / OLED", HDR4,              # rev B §7: GND 3V3 SCL SDA order
     {"1": "GND", "2": "+3V3", "3": "GPIO18", "4": "GPIO3"}, F, in_bom=False)
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

# --- G: drive pass-through and DF0/DF1 swap (rev B spec §3, §4) ------------------------------------------------
G1157 = ("FluxDrive:74LVC1G157", "74LVC1G157", "Package_TO_SOT_SMD:SOT-363_SC-70-6")


def mux(ref, s, i0, i1, y, dnp=False):
    part(ref, G1157[0], G1157[1], G1157[2], {"6": s, "3": i0, "1": i1, "4": y, "2": "GND", "5": "+3V3"}, G,
         lcsc="" if dnp else "C135822", dnp=dnp, in_bom=not dnp)
    C("100nF", "+3V3", "GND", G, dnp=dnp)


mux("U12", "DF1_EN", "GND", "SEL1", "SEL1_EN")                 # SEL1_EN = SEL1 AND DF1_EN
mux("U13", "DF0_FD", "SEL1_EN", "SEL0", "SEL_FD")              # FluxDrive's own select
mux("U16", "BUSY", "MODE_CLK_REQ", "GND", "MODE_CLK")          # the clock only while both selects are idle
part("U8", "74xx:74LS74", "74LVC74A", TSSOP14,                 # the base symbol: 74HC74 only extends it
     {"1": "CLR_A", "2": "DF0_REQ", "3": "MODE_CLK", "4": "PRE_A", "5": "DF0_FD", "6": None,
      "13": "CLR_B", "12": "DF1_REQ", "11": "MODE_CLK", "10": "PRE_B", "9": "DF1_EN", "8": None,
      "7": "GND", "14": "+3V3"}, G, lcsc="C6100")
C("100nF", "+3V3", "GND", G)
for net in ("CLR_A", "PRE_A", "CLR_B", "PRE_B"):
    R("10K", net, "+3V3", G)
R("100K", "DF0_FD", "DF0_REQ", G)                              # an undriven D holds the present state (§4.1)
R("100K", "DF1_EN", "DF1_REQ", G)
R("1K", "DF0_FD", "DF0_STATE", G)
R("1K", "DF1_EN", "DF1_STATE", G)
R("10K", "MODE_CLK_REQ", "GND", G)
R("10K", "CHNG_REQ", "GND", G)
DIODE = ("Device:D", "1N4148W", "Diode_SMD:D_SOD-123", "C81598")
C("1uF", "CLR_B", "GND", G)                                   # power-on: DF1 off (§4.6)
part("D5", DIODE[0], DIODE[1], DIODE[2], {"1": "+3V3", "2": "CLR_B"}, G, lcsc=DIODE[3])
C("1uF", "POR_A", "GND", G)                                   # power-on: real drive DF0 via JP5 1-2
part("D6", DIODE[0], DIODE[1], DIODE[2], {"1": "+3V3", "2": "POR_A"}, G, lcsc=DIODE[3])
JP3B = ("Jumper:SolderJumper_3_Bridged12", "Bridged12", "Jumper:SolderJumper-3_P1.3mm_Bridged12_RoundedPad1.0x1.5mm")
JP2O = ("Jumper:SolderJumper_2_Open", "Open", "Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm")
part("JP5", JP3B[0], "DF0 at power-on", JP3B[2], {"1": "CLR_A", "2": "POR_A", "3": "PRE_A"}, G, in_bom=False)
part("JP6", JP2O[0], "REAL clear", JP2O[2], {"1": "CLR_A", "2": "GND"}, G, in_bom=False)
part("JP7", JP2O[0], "REAL preset", JP2O[2], {"1": "PRE_A", "2": "+3V3"}, G, in_bom=False)
part("J7", "Connector_Generic:Conn_01x03", "DF0 switch", "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
     {"1": "J7_FD", "2": "GND", "3": "J7_REAL"}, G, in_bom=False)
R("1K", "J7_FD", "PRE_A", G)
R("1K", "J7_REAL", "CLR_A", G)
C("100nF", "J7_FD", "GND", G)
C("100nF", "J7_REAL", "GND", G)
mux("U14", "DF0_FD", "SEL0", "M4_SEL", "REAL_SEL")             # the real drive's select (§4.4)
mux("U15", "DF0_FD", "MTR0", "M4_MTR", "REAL_MTR")             # and its motor
part("U18", "74xGxx:74LVC2G06", "SN74LVC2G06", "Package_TO_SOT_SMD:SOT-23-6",
     {"1": "REAL_SEL", "6": "J6_SEL_D", "3": "REAL_MTR", "4": "J6_MTR_D", "2": "GND", "5": "+3V3"}, G, lcsc="C402162")
C("100nF", "+3V3", "GND", G)
R("4K7", "J6_SEL_D", "+5V_A", G)
R("4K7", "J6_MTR_D", "+5V_A", G)
part("JP1", JP3B[0], "bypass SEL", JP3B[2], {"1": "J6_SEL_D", "2": "J6_SEL", "3": "_SEL0"}, G, in_bom=False)
part("JP2", JP3B[0], "bypass MTR", JP3B[2], {"1": "J6_MTR_D", "2": "J6_MTR", "3": "_MTR0"}, G, in_bom=False)
part("JP3", JP3B[0], "mode 4 SEL", JP3B[2], {"1": "GND", "2": "M4_SEL", "3": "M4_SEL_Q"}, G, in_bom=False)
part("JP4", JP3B[0], "mode 4 MTR", JP3B[2], {"1": "GND", "2": "M4_MTR", "3": "M4_MTR_Q"}, G, in_bom=False)
j6 = {str(p): ("GND" if p != 3 else None) for p in range(1, 34, 2)}
j6.update({str(p): EVEN[p] for p in (2, 8, 18, 20, 22, 24, 26, 28, 30, 32, 34)})
j6.update({"4": "J6_MTR", "16": "J6_MTR", "10": "J6_SEL", "6": "J6_PIN6", "12": "J6_PIN12", "14": "J6_PIN14"})
part("J6", "Connector_Generic:Conn_02x17_Odd_Even", "Original drive", "Connector_IDC:IDC-Header_2x17_P2.54mm_Vertical",
     j6, G, lcsc="C601943")
for net in ("J6_PIN6", "J6_PIN12", "J6_PIN14"):
    R("10K", net, "+5V_A", G)
part("U20", "74xGxx:74LVC1G38", "SN74LVC1G38", "Package_TO_SOT_SMD:SOT-23-5",
     {"1": "CHNG_REQ", "2": "SEL0", "4": "VCHNG_D", "3": "GND", "5": "+3V3"}, G, lcsc="C2867613")
C("100nF", "+3V3", "GND", G)
R("33", "VCHNG_D", "_CHNG", G)                                # virtual disk change on bus DF0 (§4.5)
