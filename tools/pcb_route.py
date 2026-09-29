"""Autoroute the board with Freerouting, keeping what is already on it (fan-out, pinned routes).

    "/c/Program Files/KiCad/10.0/bin/python.exe" tools/pcb_route.py FluxDrive.kicad_pcb [passes] [--continue]

--continue: a second round on a routed board. The tracks of the earlier round stay unlocked, so
Freerouting may rip them up to finish the last connections; the fan-out stays locked.

Adapted from the Nano-Tek tool (2623d2f) for 2 layers:
- GND is not routed as tracks: the export copy has no zones and the GND net has no pins in the DSN, so
  Freerouting treats GND pads as obstacles. GND is the B.Cu plane and the F.Cu fill, reached through the
  fan-out vias (tools/pcb_fanout.py) and the through-hole pins;
- every track and via that is already on the board is locked (exported as "protect");
- the DSN gets a keep-out strip along the outline, for the 0.3 mm copper-to-edge rule, which Freerouting
  does not take from KiCad's board setup;
- export DSN -> java -jar freerouting.jar -> import SES -> save. Refill zones afterwards with
  kicad-cli pcb drc --refill-zones --save-board.
"""
import pathlib
import subprocess
import sys

import pcbnew

JAR = pathlib.Path.home() / ".kicad-mcp" / "freerouting.jar"
EDGE_STRIP = 150                    # um; + 0.2 clearance keeps copper 0.35 mm from the edge (rule 0.3)
UNROUTED = ("/GND",)                # plane nets
# Freerouting's own settings: B.Cu costs four times F.Cu and vias are dear, so the bottom stays mostly plane
RULES = pathlib.Path(__file__).with_name("freerouting.rules")


def sexpr_end(text, i):
    """Index just past the s-expression that starts at text[i] == '('."""
    depth = 0
    for j in range(i, len(text)):
        depth += {"(": 1, ")": -1}.get(text[j], 0)
        if depth == 0:
            return j + 1
    raise ValueError("unbalanced DSN")


def patch_dsn(text, box):
    for net in UNROUTED:                               # keep the net (the fan-out vias refer to it), drop its pins
        i = text.index(f"(net {net}\n")
        text = text[:i] + f"(net {net})" + text[sexpr_end(text, i):]
    x0, y0, x1, y1 = box                               # um, DSN has y up
    e = EDGE_STRIP
    strips = [(x0, y0, x1, y0 + e), (x0, y1 - e, x1, y1), (x0, y0, x0 + e, y1), (x1 - e, y0, x1, y1)]
    keep = "".join(f'\n    (keepout "edge" (polygon {layer} 0  {a} {b}  {c} {b}  {c} {d}  {a} {d}  {a} {b}))'
                   for layer in ("F.Cu", "B.Cu") for a, b, c, d in strips)
    k = sexpr_end(text, text.index("(boundary"))
    return text[:k] + keep + text[k:]


def lock_all(b):
    locked = 0
    for t in b.GetTracks():
        if not t.IsLocked():
            t.SetLocked(True)
            locked += 1
    return locked


def main(pcb, passes="100", *flags):
    lock = "--continue" not in flags
    pcb = pathlib.Path(pcb).resolve()
    dsn, ses = pcb.with_suffix(".dsn"), pcb.with_suffix(".ses")
    b = pcbnew.LoadBoard(str(pcb))
    locked = lock_all(b) if lock else 0
    bb = b.GetBoardEdgesBoundingBox()                  # before Remove(): after it the bindings are unreliable
    um = lambda v: round(pcbnew.ToMM(v) * 1000)
    box = (um(bb.GetLeft()), -um(bb.GetBottom()), um(bb.GetRight()), -um(bb.GetTop()))
    for z in list(b.Zones()):                          # export copy only: it is never saved
        if not z.GetIsRuleArea():
            b.Remove(z)
    assert pcbnew.ExportSpecctraDSN(b, str(dsn)), "DSN export failed"
    dsn.write_text(patch_dsn(dsn.read_text(encoding="utf-8"), box), encoding="utf-8")
    print(f"locked {locked} existing tracks/vias, exported {dsn.name}", flush=True)
    ses.unlink(missing_ok=True)                        # never import the session of an earlier run
    rules = ["-dr", str(RULES)] if RULES.exists() else []
    r = subprocess.run(["java", "-jar", str(JAR), "-de", str(dsn), *rules, "-do", str(ses), "-mp", str(passes),
                        "-mt", "1"], capture_output=True, text=True)
    tail = "\n".join((r.stdout + r.stderr).strip().splitlines()[-6:])
    print(tail, flush=True)
    assert ses.exists(), "Freerouting wrote no .ses"
    # the import runs in a fresh process: after Remove() above, this one's pcbnew bindings are unreliable
    subprocess.run([sys.executable, "-u", __file__, "--import", str(pcb), "lock" if lock else "keep"], check=True)


def import_ses(pcb, lock):
    pcb = pathlib.Path(pcb)
    b = pcbnew.LoadBoard(str(pcb))                     # a fresh copy that still has all its zones
    if lock:
        lock_all(b)
    assert pcbnew.ImportSpecctraSES(b, str(pcb.with_suffix(".ses"))), "SES import failed"
    pcbnew.SaveBoard(str(pcb), b)
    print(f"routed and saved {pcb.name}")


if __name__ == "__main__":
    if sys.argv[1] == "--import":
        import_ses(sys.argv[2], sys.argv[3] == "lock")
    else:
        main(*sys.argv[1:])
