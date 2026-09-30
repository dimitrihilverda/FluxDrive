"""Delete the autorouted tracks and vias that DRC flags, so a --continue round of pcb_route.py redoes them.

    "/c/Program Files/KiCad/10.0/bin/python.exe" tools/pcb_ripup.py FluxDrive.kicad_pcb [--all]

Runs kicad-cli DRC (JSON), takes every copper violation (clearance, hole-to-hole, edge) and removes
the unlocked tracks/vias in it. Locked items (the fan-out, pinned routes) are never touched.
--all removes every unlocked track and via, before a fresh Freerouting run.
--dangling removes tracks with a loose end (locked or not: stubs the router did not use), one piece at a time, each in a fresh process. Freerouting sometimes joins such a stub halfway
(a T), and then the whole segment is still needed: a removal that leaves anything open is undone.
"""
import json
import pathlib
import shutil
import subprocess
import sys

import pcbnew

KICAD_CLI = r"C:/Program Files/KiCad/10.0/bin/kicad-cli.exe"
COPPER = {"clearance", "hole_to_hole", "copper_edge_clearance", "hole_clearance", "tracks_crossing", "shorting_items"}


def flagged(pcb, types=COPPER):
    report = pathlib.Path(pcb).with_suffix(".drc.json")
    # --refill-zones: with stale zone fills every new track "violates" the old pour
    severity = ["--severity-error"] if types is COPPER else ["--severity-all"]
    subprocess.run([KICAD_CLI, "pcb", "drc", "--format", "json", *severity, "--refill-zones",
                    "-o", str(report), str(pcb)], capture_output=True, check=True)
    data = json.loads(report.read_text(encoding="utf-8"))
    return {item["uuid"] for v in data.get("violations", []) if v["type"] in types for item in v["items"]}


def open_count(pcb):
    report = pathlib.Path(pcb).with_suffix(".drc.json")
    subprocess.run([KICAD_CLI, "pcb", "drc", "--format", "json", "--severity-error", "--refill-zones",
                    "-o", str(report), str(pcb)], capture_output=True, check=True)
    return len(json.loads(report.read_text(encoding="utf-8"))["unconnected_items"])


def remove_uuid(pcb, uuid):
    b = pcbnew.LoadBoard(pcb)
    doomed = [t for t in b.GetTracks() if t.m_Uuid.AsString() == uuid]
    for t in doomed:
        b.Remove(t)
    pcbnew.SaveBoard(pcb, b)


def main(pcb, everything=False):
    uuids = set() if everything else flagged(pcb)
    b = pcbnew.LoadBoard(pcb)
    doomed = [t for t in b.GetTracks() if not t.IsLocked() and (everything or t.m_Uuid.AsString() in uuids)]
    gone = [t.GetNetname() for t in doomed]
    for t in doomed:                    # one pass: removing while iterating the board's list crashes pcbnew
        b.Remove(t)
    pcbnew.SaveBoard(pcb, b)
    print(f"ripped up {len(gone)} items" + ("" if everything else f" on {sorted(set(gone)) or 'no nets'}"))


if __name__ == "__main__":
    if "--remove" in sys.argv:
        remove_uuid(sys.argv[1], sys.argv[sys.argv.index("--remove") + 1])
    elif "--dangling" in sys.argv:
        pcb, removed, kept = sys.argv[1], 0, set()
        before = open_count(pcb)
        backup = pathlib.Path(pcb).with_suffix(".undo.kicad_pcb")
        while True:
            todo = sorted(flagged(pcb, {"track_dangling"}) - kept)
            if not todo:
                break
            for uuid in todo:
                shutil.copyfile(pcb, backup)
                subprocess.run([sys.executable, __file__, pcb, "--remove", uuid], check=True)
                if open_count(pcb) > before:
                    shutil.copyfile(backup, pcb)            # it carried a T: keep it
                    kept.add(uuid)
                else:
                    removed += 1
        backup.unlink(missing_ok=True)
        print(f"removed {removed} dangling track pieces, kept {len(kept)} that carry a junction")
    else:
        main(sys.argv[1], "--all" in sys.argv[2:])
