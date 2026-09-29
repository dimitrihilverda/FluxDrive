"""Route the board: Freerouting, then pin what it leaves open and let Freerouting route the rest again.

    "/c/Program Files/KiCad/10.0/bin/python.exe" tools/pcb_autoroute.py FluxDrive.kicad_pcb [--finish]

Copied from the Nano-Tek tool (2623d2f); 2 layers, so there is no last resort on an inner layer.
Freerouting may leave a few connections open. Every attempt is:
  Freerouting -> rip up what DRC flags -> if connections are still open and attempts remain: route those
  nets with the maze router *through* Freerouting's result (ripping up what is in the way), lock them,
  remove every other autorouted track, and start again.
Pinning a net inside a full routing keeps it in the room Freerouting left for it; pinning it on an empty
board takes the middle of the board and leaves more open, not less. The best attempt is kept; what is
still open after that is finished in rounds: the maze router pins each open net (ripping up what is in
its way), then Freerouting --continue routes what that left open; a last maze pass without rip-up.
On this board one attempt leaves two or three connections: ATTEMPTS = 1. (A maze pass with rip-up over
all nets at once cascades: every rip-up opens another net.)
Each step runs in its own process: removing tracks leaves pcbnew's Python bindings unusable.
"""
import json
import pathlib
import re
import shutil
import subprocess
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
KICAD_CLI = r"C:/Program Files/KiCad/10.0/bin/kicad-cli.exe"
ATTEMPTS = 1              # sequential attempts (each re-pins and re-routes); the parallel ones below do better
PARALLEL = 6              # Freerouting runs side by side on copies of the board; its result varies a lot per run
                          # (2 to 10 open on the same input), so the best of six is kept
FINISH_ROUNDS = 3         # pin the open nets with the maze router, then Freerouting --continue
PLANES = {"/GND"}                        # open "connections" on it are plane islands, not tracks to route


def step(script, *args):
    subprocess.run([sys.executable, "-u", str(TOOLS / script), *args], check=True)


def open_nets(pcb):
    report = pathlib.Path(pcb).with_suffix(".drc.json")
    subprocess.run([KICAD_CLI, "pcb", "drc", "--format", "json", "--severity-error", "--refill-zones",
                    "-o", str(report), str(pcb)], capture_output=True, check=True)
    data = json.loads(report.read_text(encoding="utf-8"))
    nets = []
    for u in data["unconnected_items"]:
        m = re.search(r"\[(.+?)\]", u["items"][0]["description"])
        if m and m.group(1) not in nets:
            nets.append(m.group(1))
    return nets, len(data["unconnected_items"])


def route_parallel(pcb, n=PARALLEL):
    """Freerouting on n copies at once; the copy with the fewest open connections becomes the board."""
    pcb = pathlib.Path(pcb)
    tries = [pcb.with_name(f"{pcb.stem}.try{i}.kicad_pcb") for i in range(n)]
    for t in tries:
        shutil.copyfile(pcb, t)
        shutil.copyfile(pcb.with_suffix(".kicad_pro"), t.with_suffix(".kicad_pro"))   # netclasses and rules
    procs = [subprocess.Popen([sys.executable, "-u", str(TOOLS / "pcb_route.py"), str(t), "100"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for t in tries]
    results = []
    for t, proc in zip(tries, procs):
        if proc.wait() != 0:
            print(f"  {t.name}: Freerouting failed", flush=True)
            continue
        step("pcb_ripup.py", str(t))
        nets, n_open = open_nets(t)
        print(f"  {t.name}: {n_open} open {nets or ''}", flush=True)
        results.append((n_open, t))
    assert results, "every Freerouting run failed"
    n_open, best = min(results)
    shutil.copyfile(best, pcb)
    for t in tries:
        for f in (t, t.with_suffix(".dsn"), t.with_suffix(".ses"), t.with_suffix(".drc.json"),
                  t.with_suffix(".kicad_pro"), t.with_suffix(".kicad_prl")):
            f.unlink(missing_ok=True)


def main(pcb, finish_only=False):
    best = pathlib.Path(pcb).with_suffix(".best.kicad_pcb")
    best_open = None
    for attempt in range(1, 0 if finish_only else ATTEMPTS + 1):
        route_parallel(pcb)
        step("pcb_ripup.py", pcb)
        nets, n_open = open_nets(pcb)
        print(f"attempt {attempt}: {n_open} open connections {nets or ''}", flush=True)
        if best_open is None or n_open < best_open:
            best_open = n_open
            shutil.copyfile(pcb, best)
        if not n_open:
            break
        signal_nets = [n for n in nets if n not in PLANES]
        if attempt == ATTEMPTS or not signal_nets:
            break
        for net in signal_nets:
            step("pcb_maze.py", "--lock", pcb, net)
        step("pcb_ripup.py", pcb, "--all")
    if best.exists():
        shutil.copyfile(best, pcb)             # the .best file stays: the Freerouting result, to finish again
        print(f"kept the best attempt: {best_open} open connections", flush=True)
    # Finishing: a round first tries the maze router without rip-up; if nets still have no path, Freerouting
    # runs again on the routed board (--continue, full passes). A round that leaves no fewer open than the
    # best state so far is undone, and finishing stops.
    keep = pathlib.Path(pcb).with_suffix(".keep.kicad_pcb")
    nets, best_open = open_nets(pcb)
    shutil.copyfile(pcb, keep)
    for rnd in range(1, FINISH_ROUNDS + 1):
        signal_nets = [n for n in nets if n not in PLANES]
        if not signal_nets:
            break
        for net in signal_nets:
            step("pcb_maze.py", "--lock", "--no-ripup", pcb, net)
        nets, n_open = open_nets(pcb)
        stuck = [n for n in nets if n not in PLANES]
        if stuck:
            # Freerouting again on the routed board: its own rip-up and re-route, all tracks negotiable except
            # the locked ones (fan-out, hand-made routes, the maze's pins). Pinning the stuck nets first with
            # the maze router's rip-up made things worse: its paths are long and wall off their neighbours.
            step("pcb_route.py", pcb, "100", "--continue")
            step("pcb_ripup.py", pcb)
            nets, n_open = open_nets(pcb)
        print(f"finishing round {rnd}: {n_open} open connections {nets or ''}", flush=True)
        if n_open < best_open:
            best_open = n_open
            shutil.copyfile(pcb, keep)
        else:
            shutil.copyfile(keep, pcb)
            nets, best_open = open_nets(pcb)
            print(f"finishing round {rnd} made it no better: undone, {best_open} open", flush=True)
            break
    keep.unlink(missing_ok=True)
    # open plane connections are islands: ground stitching (tools/pcb_stitch.py) comes next and joins them
    return 0 if not [n for n in open_nets(pcb)[0] if n not in PLANES] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], "--finish" in sys.argv[2:]))       # --finish: only the finishing rounds
