"""Route the board: Freerouting several times side by side, keep the best, then finish what it left open.

    "/c/Program Files/KiCad/10.0/bin/python.exe" tools/pcb_autoroute.py FluxDrive.kicad_pcb [--finish]

Freerouting gives the same result on the same input, but a different one for other settings, and one run
may leave two connections open where another leaves eight. So PARALLEL copies of the board are routed at the
same time, each with its own Freerouting settings (via cost, rip-up cost, preferred directions: VARIANTS),
and the copy with the fewest open signal connections becomes the board.
Then finishing rounds: the maze router tries each open net without rip-up; if nets still have no path,
Freerouting runs again on the routed board (--continue). A round that leaves no fewer open than the best
state so far is undone, and finishing stops. --finish runs only the finishing rounds.
Open connections on the plane nets are islands, not tracks to route: ground stitching joins those later.
Adapted from the Nano-Tek tool (2623d2f). Each step runs in its own process: removing tracks leaves pcbnew's
Python bindings unusable.
"""
import json
import pathlib
import re
import shutil
import subprocess
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
KICAD_CLI = r"C:/Program Files/KiCad/10.0/bin/kicad-cli.exe"
PLANES = {"/GND", "/+3V3"}
FINISH_ROUNDS = 3
# (via cost, start rip-up cost, F.Cu direction, B.Cu direction, cost against the preferred direction)
VARIANTS = [(50, 100, "horizontal", "vertical", 2.0), (30, 100, "horizontal", "vertical", 2.5),
            (80, 100, "horizontal", "vertical", 1.8), (50, 50, "vertical", "horizontal", 2.0),
            (120, 150, "horizontal", "vertical", 1.5), (50, 200, "vertical", "horizontal", 2.5)]
PARALLEL = len(VARIANTS)


def step(script, *args):
    subprocess.run([sys.executable, "-u", str(TOOLS / script), *args], check=True)


def open_items(pcb):
    """[(net, description)] of every unconnected item pair DRC reports."""
    report = pathlib.Path(pcb).with_suffix(".drc.json")
    subprocess.run([KICAD_CLI, "pcb", "drc", "--format", "json", "--severity-error", "--refill-zones",
                    "-o", str(report), str(pcb)], capture_output=True, check=True)
    out = []
    for u in json.loads(report.read_text(encoding="utf-8"))["unconnected_items"]:
        m = re.search(r"\[(.+?)\]", u["items"][0]["description"])
        out.append(m.group(1) if m else "")
    return out


def signal_open(pcb):
    """(number of open signal connections, their nets in order)."""
    nets = [n for n in open_items(pcb) if n not in PLANES]
    return len(nets), list(dict.fromkeys(nets))


def rules_file(path, variant):
    via, ripup, f_dir, b_dir, against = variant
    layer = lambda name, d: (f"    (layer_rule {name}\n      (active on)\n      (preferred_direction {d})\n"
                             f"      (preferred_direction_trace_costs 1.0)\n"
                             f"      (against_preferred_direction_trace_costs {against})\n    )\n")
    path.write_text("(rules PCB FluxDrive\n  (snap_angle\n    fortyfive_degree\n  )\n  (autoroute_settings\n"
                    "    (fanout off)\n    (autoroute on)\n    (postroute on)\n    (vias on)\n"
                    f"    (via_costs {via})\n    (plane_via_costs 5)\n    (start_ripup_costs {ripup})\n"
                    "    (start_pass_no 1)\n" + layer("F.Cu", f_dir) + layer("B.Cu", b_dir) + "  )\n)\n",
                    encoding="utf-8")


def route_parallel(pcb):
    """Freerouting on PARALLEL copies at once, one settings variant each; the best copy becomes the board."""
    pcb = pathlib.Path(pcb)
    tries = [pcb.with_name(f"{pcb.stem}.try{i}.kicad_pcb") for i in range(PARALLEL)]
    procs = []
    for t, variant in zip(tries, VARIANTS):
        shutil.copyfile(pcb, t)
        shutil.copyfile(pcb.with_suffix(".kicad_pro"), t.with_suffix(".kicad_pro"))   # netclasses and rules
        rules_file(t.with_suffix(".rules"), variant)
        procs.append(subprocess.Popen([sys.executable, "-u", str(TOOLS / "pcb_route.py"), str(t), "100",
                                       "--rules", str(t.with_suffix(".rules"))],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    results = []
    for t, proc, variant in zip(tries, procs, VARIANTS):
        if proc.wait() != 0:
            print(f"  {t.name} {variant}: Freerouting failed", flush=True)
            continue
        step("pcb_ripup.py", str(t))
        n, nets = signal_open(t)
        print(f"  {t.name} {variant}: {n} open {nets or ''}", flush=True)
        results.append((n, str(t)))
    assert results, "every Freerouting run failed"
    n_open, best = min(results)
    shutil.copyfile(best, pcb)
    for t in tries:
        for suffix in (".kicad_pcb", ".dsn", ".ses", ".drc.json", ".kicad_pro", ".kicad_prl", ".rules"):
            t.with_suffix(suffix).unlink(missing_ok=True)
    return n_open


def main(pcb, finish_only=False):
    if not finish_only:
        n_open = route_parallel(pcb)
        print(f"best Freerouting run: {n_open} open signal connections", flush=True)
    keep = pathlib.Path(pcb).with_suffix(".keep.kicad_pcb")
    best_open, nets = signal_open(pcb)
    shutil.copyfile(pcb, keep)
    for rnd in range(1, FINISH_ROUNDS + 1):
        if not nets:
            break
        for net in nets:
            step("pcb_maze.py", "--lock", "--no-ripup", pcb, net)
        n_open, nets = signal_open(pcb)
        if nets:
            # Freerouting again on the routed board: its own rip-up and re-route, everything negotiable but
            # the locked items. (Pinning the stuck nets first with the maze router's rip-up made things worse:
            # its paths are long and wall off their neighbours.)
            step("pcb_route.py", pcb, "100", "--continue")
            step("pcb_ripup.py", pcb)
            n_open, nets = signal_open(pcb)
        print(f"finishing round {rnd}: {n_open} open signal connections {nets or ''}", flush=True)
        if n_open < best_open:
            best_open = n_open
            shutil.copyfile(pcb, keep)
        else:
            shutil.copyfile(keep, pcb)
            best_open, nets = signal_open(pcb)
            print(f"finishing round {rnd} made it no better: undone, {best_open} open", flush=True)
            break
    keep.unlink(missing_ok=True)
    return 0 if best_open == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], "--finish" in sys.argv[2:]))
