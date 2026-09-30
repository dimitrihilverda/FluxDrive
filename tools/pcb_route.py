"""Autoroute the board with Freerouting, keeping what is already on it (fan-out, hand-made and pinned routes).

    "/c/Program Files/KiCad/10.0/bin/python.exe" tools/pcb_route.py FluxDrive.kicad_pcb [passes] [--continue]
                                                                    [--rules FILE]

--continue: a second round on a routed board. The tracks of the earlier round stay unlocked, so
Freerouting may rip them up to finish the last connections; the fan-out and hand-made routes stay locked.
--rules: Freerouting's own settings file (via cost, rip-up cost, preferred directions); pcb_autoroute.py
gives each of its parallel runs a different one, because Freerouting is deterministic on identical input.

As the Nano-Tek tool (2623d2f), for the 4-layer board:
- In1.Cu (GND) and In2.Cu (+3V3) are power layers: their zones go into the DSN as planes, so Freerouting
  treats a pad with a via to its plane as connected (tools/pcb_fanout.py makes those vias first);
- the GND pours on F.Cu and B.Cu stay out of the export: as planes they would make Freerouting take every
  top/bottom GND pad as connected and block the outer layers;
- every track and via already on the board is locked (exported as "protect");
- the DSN gets a keep-out strip along the outline (the copper-to-edge rule) and fatter routing vias (hole to
  hole 0.5 mm: 0.68 mm vias + 0.2 mm clearance leave 0.58 mm between holes); the vias go back to 0.6 mm after
  the import. The import runs in a fresh process (after Remove() pcbnew's bindings here are unreliable).
"""
import pathlib
import re
import subprocess
import sys

import pcbnew

JAR = pathlib.Path.home() / ".kicad-mcp" / "freerouting.jar"
VIA_D, VIA_ROUTE_D = 600, 680       # um
EDGE_STRIP = 150                    # um; + 0.2 clearance keeps copper 0.35 mm from the edge (rule 0.3)
TIMEOUT = 3600                      # s, one Freerouting run (6-10 min on this board)


def sexpr_end(text, i):
    """Index just past the s-expression that starts at text[i] == '('."""
    depth = 0
    for j in range(i, len(text)):
        depth += {"(": 1, ")": -1}.get(text[j], 0)
        if depth == 0:
            return j + 1
    raise ValueError("unbalanced DSN")


def patch_dsn(text, box):
    for m in list(re.finditer(r'\(padstack "Via\[[^"]*\]_600:300_um"', text)):
        i = m.start()
        j = sexpr_end(text, i)
        text = text[:i] + text[i:j].replace(f" {VIA_D})", f" {VIA_ROUTE_D})") + text[j:]
    x0, y0, x1, y1 = box                               # um, DSN has y up
    e = EDGE_STRIP
    strips = [(x0, y0, x1, y0 + e), (x0, y1 - e, x1, y1), (x0, y0, x0 + e, y1), (x1 - e, y0, x1, y1)]
    keep = "".join(f'\n    (keepout "edge" (polygon {layer} 0  {a} {b}  {c} {b}  {c} {d}  {a} {d}  {a} {b}))'
                   for layer in ("F.Cu", "B.Cu") for a, b, c, d in strips)
    k = sexpr_end(text, text.index("(boundary"))
    return text[:k] + keep + text[k:]


def prepare(b, lock=True):
    for layer in (pcbnew.In1_Cu, pcbnew.In2_Cu):
        b.SetLayerType(layer, pcbnew.LT_POWER)
    locked = 0
    for t in b.GetTracks():
        if lock and not t.IsLocked():
            t.SetLocked(True)
            locked += 1
    return locked


def main(pcb, passes="100", *flags):
    flags = list(flags)
    lock = "--continue" not in flags
    rules = pathlib.Path(flags[flags.index("--rules") + 1]) if "--rules" in flags else None
    pcb = pathlib.Path(pcb).resolve()
    dsn, ses = pcb.with_suffix(".dsn"), pcb.with_suffix(".ses")
    b = pcbnew.LoadBoard(str(pcb))
    locked = prepare(b, lock)
    bb = b.GetBoardEdgesBoundingBox()                  # before Remove(): after it the bindings are unreliable
    um = lambda v: round(pcbnew.ToMM(v) * 1000)
    box = (um(bb.GetLeft()), -um(bb.GetBottom()), um(bb.GetRight()), -um(bb.GetTop()))
    for z in list(b.Zones()):                          # export copy only: it is never saved
        if not z.GetIsRuleArea() and (z.IsOnLayer(pcbnew.F_Cu) or z.IsOnLayer(pcbnew.B_Cu)):
            b.Remove(z)
    assert pcbnew.ExportSpecctraDSN(b, str(dsn)), "DSN export failed"
    dsn.write_text(patch_dsn(dsn.read_text(encoding="utf-8"), box), encoding="utf-8")
    print(f"locked {locked} existing tracks/vias, exported {dsn.name}", flush=True)
    ses.unlink(missing_ok=True)                        # never import the session of an earlier run
    cmd = ["java", "-jar", str(JAR), "-de", str(dsn), "-do", str(ses), "-mp", str(passes), "-mt", "1"]
    if rules:
        cmd[5:5] = ["-dr", str(rules)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    tail = "\n".join(line for line in (r.stdout + r.stderr).strip().splitlines()[-8:] if "image handler" not in line)
    print(tail, flush=True)
    assert ses.exists(), "Freerouting wrote no .ses"
    subprocess.run([sys.executable, "-u", __file__, "--import", str(pcb), "lock" if lock else "keep"], check=True)


def import_ses(pcb, lock):
    pcb = pathlib.Path(pcb)
    b = pcbnew.LoadBoard(str(pcb))                     # a fresh copy that still has all its zones
    prepare(b, lock)
    assert pcbnew.ImportSpecctraSES(b, str(pcb.with_suffix(".ses"))), "SES import failed"
    shrunk = 0
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA" and round(pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)) * 1000) == VIA_ROUTE_D:
            t.SetWidth(pcbnew.F_Cu, pcbnew.FromMM(VIA_D / 1000))
            shrunk += 1
    pcbnew.SaveBoard(str(pcb), b)
    print(f"routed and saved {pcb.name}; {shrunk} routing vias back to {VIA_D / 1000} mm")


if __name__ == "__main__":
    if sys.argv[1] == "--import":
        import_ses(sys.argv[2], sys.argv[3] == "lock")
    else:
        main(*sys.argv[1:])
