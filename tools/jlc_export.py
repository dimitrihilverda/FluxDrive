"""BOM and CPL for JLCPCB assembly, in the format of the JLCPCB Tools plugin (copied from the Nano-Tek, 2623d2f).

    python.exe tools/jlc_export.py FluxDrive.kicad_pcb jlcpcb/production_files [--check-against old_CPL.csv]

Which parts go in: every footprint with an LCSC field that is not excluded from the BOM or the position file,
is not DNP and has at least one SMD pad. Through-hole parts (every pad plated through: the floppy, power and
pin headers) are soldered by hand; the USB-C socket has SMD signal pins, so JLC places it. Everything
left out is listed.

Position is the centre of the footprint's pads (as the plugin does), rotation is KiCad's plus a
correction per footprint for JLC's package orientation. The ESP32 module is the exception: its antenna end
has no pads, so it takes the centre of its F.Fab outline (the body). The corrections are the ones the Nano-Tek Rev 1.2
CPL (made by the plugin, assembled by JLC) used; SOIC follows TSSOP, the same KiCad pin-1 orientation. Check the
ICs, the module, the diodes, the LED and the USB-C socket in JLC's placement preview anyway.
"""
import csv
import pathlib
import re
import sys

import pcbnew

# footprint name regex -> degrees added to KiCad's rotation, first match wins
ROTATION = [
    (r"^LQFP-", 270),                 # U1 in Rev 1.2
    (r"^SOT-23", 180),                # U3 (SOT-23-5) and Q1 (SOT-23) in Rev 1.2; also SOT-23-6
    (r"^SOT-363", 180),               # SC-70-6: the same orientation as the SOT-23 family
    (r"^TSSOP-", 0),                  # U2 in Rev 1.2
    (r"^SOIC-", 0),                   # same pin-1 orientation as TSSOP in KiCad (check in JLC's preview)
    (r"^(MSOP|VSSOP)-", 0),           # the same pin-1 orientation as TSSOP in KiCad
    (r"^IDC-Header_2x", 270),         # CN3 in Rev 1.2
    (r"^Pin(Header|Socket)_", 270),   # J1-J4 in Rev 1.2
]


# footprints whose pads do not surround the body centre: use the F.Fab outline instead
BODY_CENTRE = r"^ESP32-"


def correction(fp_name):
    for pattern, deg in ROTATION:
        if re.search(pattern, fp_name):
            return deg
    return 0


def natural(ref):
    m = re.match(r"([A-Za-z]+)(\d+)", ref)
    return (m.group(1), int(m.group(2))) if m else (ref, 0)


def main(pcb_path, out_dir, check=None):
    board = pcbnew.LoadBoard(pcb_path)
    name = pathlib.Path(pcb_path).stem
    parts, skipped = [], []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        lcsc = next((f.GetText() for f in fp.GetFields() if f.GetName() == "LCSC"), "")
        through_hole = all(pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH for pad in fp.Pads())
        if fp.IsExcludedFromBOM() or fp.IsExcludedFromPosFiles() or fp.IsDNP() or not lcsc.strip() or through_hole:
            skipped.append(ref)
            continue
        fp_name = str(fp.GetFPID().GetLibItemName())
        boxes = [pad.GetBoundingBox() for pad in fp.Pads()]
        if re.search(BODY_CENTRE, fp_name):
            boxes = [g.GetBoundingBox() for g in fp.GraphicalItems() if g.GetLayer() == pcbnew.F_Fab] or boxes
        centre = pcbnew.VECTOR2I((min(b.GetX() for b in boxes) + max(b.GetRight() for b in boxes)) // 2,
                                 (min(b.GetY() for b in boxes) + max(b.GetBottom() for b in boxes)) // 2)
        rot = fp.GetOrientationDegrees() + correction(fp_name)
        while rot >= 360:
            rot -= 360
        while rot <= -180:
            rot += 360
        layer = "top" if fp.GetLayer() == pcbnew.F_Cu else "bottom"
        parts.append(dict(ref=ref, value=fp.GetValue(), fp=fp_name, lcsc=lcsc.strip(),
                          x=centre.x / 1e6, y=-centre.y / 1e6, rot=float(rot), layer=layer))

    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    groups = {}
    for p in parts:
        groups.setdefault((p["lcsc"], p["fp"]), []).append(p)
    rows = []
    for (lcsc, fp_name), ps in groups.items():
        refs = sorted((p["ref"] for p in ps), key=natural)
        rows.append([ps[0]["value"] if len({p["value"] for p in ps}) == 1 else sorted(ps, key=lambda p: natural(p["ref"]))[0]["value"],
                     ",".join(refs), fp_name, lcsc, len(refs)])
    rows.sort(key=lambda r: (r[0], r[1]))
    with open(out / f"BOM-{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC", "Quantity"])
        w.writerows(rows)
    with open(out / f"CPL-{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Val", "Package", "Mid X", "Mid Y", "Rotation", "Layer"])
        for p in sorted(parts, key=lambda p: p["ref"]):
            w.writerow([p["ref"], p["value"], p["fp"], round(p["x"], 4), round(p["y"], 4), p["rot"], p["layer"]])
    print(f"BOM: {len(rows)} lines, {len(parts)} parts; CPL: {len(parts)} placements")
    print("not assembled by JLC:", ", ".join(sorted(skipped, key=natural)))

    if check:
        old = {r["Designator"]: r for r in csv.DictReader(open(check, encoding="utf-8"))}
        bad = 0
        for p in parts:
            o = old.get(p["ref"])
            if not o:
                continue
            dx, dy = abs(float(o["Mid X"]) - p["x"]), abs(float(o["Mid Y"]) - p["y"])
            drot = (float(o["Rotation"]) - p["rot"]) % 360
            if dx > 0.01 or dy > 0.01 or drot > 0.01:
                bad += 1
                print(f"  differs from the old CPL: {p['ref']} old ({o['Mid X']}, {o['Mid Y']}, {o['Rotation']}) "
                      f"new ({p['x']:.4f}, {p['y']:.4f}, {p['rot']})")
        print(f"CPL check: {len([p for p in parts if p['ref'] in old])} parts compared, {bad} differ")


if __name__ == "__main__":
    args = sys.argv[1:]
    chk = None
    if "--check-against" in args:
        i = args.index("--check-against")
        chk = args[i + 1]
        del args[i:i + 2]
    main(args[0], args[1], chk)
