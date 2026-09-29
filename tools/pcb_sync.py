"""Build or update the board from the schematic netlist, like KiCad's "Update PCB from Schematic" (F8).

Run with KiCad 10's own Python (it has the pcbnew module):
    "/c/Program Files/KiCad/10.0/bin/python.exe" tools/pcb_sync.py build/FluxDrive.net FluxDrive.kicad_pcb

- starts a new 2-layer board if the file does not exist yet (it takes the rules and netclasses of the
  .kicad_pro with the same name);
- adds footprints that are in the netlist but not on the board (parked below the board), with the
  schematic path and library name, so KiCad's own F8 later recognises them;
- updates value and fields (LCSC, Datasheet, Description), DNP and BOM flags of existing ones;
- sets every pad's net from the netlist, creates new nets.
Adapted from the Nano-Tek tool (2623d2f), without its Rev 1.2 migration.
"""
import pathlib
import sys

import pcbnew

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.netlist import _child, _children, _parse_sexpr, _value  # noqa: E402

KICAD_FP = pathlib.Path(r"C:/Program Files/KiCad/10.0/share/kicad/footprints")
FIELDS = ("LCSC", "Datasheet", "Description")
PARK_Y = 160.0                  # mm, below the board (the outline is y 100..145)


def read_netlist(path):
    root = _parse_sexpr(pathlib.Path(path).read_text(encoding="utf-8"))
    comps = {}
    for c in _children(_child(root, "components"), "comp"):
        ref = _value(c, "ref")
        fp = _value(c, "footprint", "")
        if not fp or ref.startswith("#"):
            continue
        sp = _child(c, "sheetpath")
        ts = _child(c, "tstamps")[1]
        props = {_value(p, "name"): _value(p, "value", "") for p in _children(c, "property")}
        fields = {}
        fl = _child(c, "fields")
        if fl is not None:
            for f in _children(fl, "field"):
                fields[_value(f, "name")] = f[-1] if isinstance(f[-1], str) else ""
        comps[ref] = {
            "fp": fp, "value": _value(c, "value", ""), "path": _value(sp, "tstamps") + ts,
            "sheetname": _value(sp, "names"), "sheetfile": props.get("Sheetfile", ""),
            "fields": {k: fields[k] for k in FIELDS if fields.get(k)},
            "dnp": "dnp" in props,
            "no_bom": "exclude_from_bom" in props,
        }
    pads = {}
    for n in _children(_child(root, "nets"), "net"):
        name = _value(n, "name")
        for node in _children(n, "node"):
            pads[(_value(node, "ref"), _value(node, "pin"))] = name
    return comps, pads


def load_fp(libname, fpname):
    lib = ROOT / "FluxDrive.pretty" if libname == "FluxDrive" else KICAD_FP / f"{libname}.pretty"
    fp = pcbnew.FootprintLoad(str(lib), fpname)
    assert fp is not None, f"footprint {libname}:{fpname} not found in {lib}"
    return fp


def set_field(fp, name, value):
    if fp.HasField(name):
        fp.GetField(name).SetText(value)
        return
    f = pcbnew.PCB_FIELD(fp, pcbnew.FIELD_T_USER, name)
    f.SetText(value)
    f.SetVisible(False)
    f.SetLayer(pcbnew.F_Fab)
    f.SetPosition(fp.GetPosition())
    fp.Add(f)


def open_board(pcb_path):
    if pathlib.Path(pcb_path).exists():
        return pcbnew.LoadBoard(pcb_path)
    board = pcbnew.NewBoard(pcb_path)
    board.SetCopperLayerCount(2)
    return board


def main(net_path, pcb_path):
    comps, pads = read_netlist(net_path)
    board = open_board(pcb_path)
    on_board = {fp.GetReference(): fp for fp in board.GetFootprints()}
    nets = {}
    for name in sorted(set(pads.values())):
        ni = board.FindNet(name)
        if ni is None:
            ni = pcbnew.NETINFO_ITEM(board, name)
            board.Add(ni)
        nets[name] = ni

    added, park_x = [], 100.0
    for ref, c in sorted(comps.items()):
        fp = on_board.get(ref)
        lib, name = c["fp"].split(":", 1)
        if fp is None:
            fp = load_fp(lib, name)
            fp.SetReference(ref)
            fp.SetPosition(pcbnew.VECTOR2I_MM(park_x, PARK_Y))
            park_x += 4
            board.Add(fp)
            added.append(ref)
        if not str(fp.GetFPID().GetLibNickname()):                # pcbnew's UTF8 object is never "falsy"
            fp.SetFPID(pcbnew.LIB_ID(lib, name))
        elif str(fp.GetFPID().GetLibItemName()) != name:
            print(f"warning: {ref} has footprint {fp.GetFPID().GetLibItemName()}, the schematic says {name}: "
                  f"delete it from the board and run this again")
        fp.SetValue(c["value"])
        fp.SetPath(pcbnew.KIID_PATH(c["path"]))
        fp.SetSheetname(c["sheetname"])
        fp.SetSheetfile(c["sheetfile"])
        for k in FIELDS:                       # the schematic's value, also when it is empty (parity check)
            if c["fields"].get(k) or fp.HasField(k):
                set_field(fp, k, c["fields"].get(k, ""))
        fp.SetDNP(c["dnp"])
        fp.SetExcludedFromBOM(c["no_bom"])
        fp.SetExcludedFromPosFiles(c["no_bom"] or c["dnp"])
        for pad in fp.Pads():
            num = pad.GetNumber()
            if not num:
                continue
            net = pads.get((ref, num))
            pad.SetNet(nets[net] if net else board.FindNet(0))

    stale = [r for r in on_board if r not in comps]
    board.BuildConnectivity()
    pcbnew.SaveBoard(pcb_path, board)
    print(f"added {len(added)} footprints; not in the schematic: {stale or 'none'}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
