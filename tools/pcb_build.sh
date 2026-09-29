#!/usr/bin/env bash
# Build the board from the schematic in build/pcb/ (the repo's board is not touched).
# Needs KiCad 10, Java 17 and Freerouting 1.9 at ~/.kicad-mcp/freerouting.jar.
#
#   bash tools/pcb_build.sh
#   cp build/pcb/FluxDrive.kicad_pcb FluxDrive.kicad_pcb        # when the DRC at the end is clean
#
# Steps: netlist -> new board from the netlist -> outline, pours and placement -> hand-made routes -> fan-out of the GND pads
# to the B.Cu plane -> Freerouting, with the maze router pinning what it leaves open (tools/pcb_autoroute.py)
# -> loose track ends -> ground stitching -> silkscreen -> DRC with zone refill and schematic parity.
set -euo pipefail
cd "$(dirname "$0")/.."
KICAD_BIN="${KICAD_BIN:-/c/Program Files/KiCad/10.0/bin}"
PY="$KICAD_BIN/python.exe"
CLI="$KICAD_BIN/kicad-cli.exe"
OUT="${OUT:-build/pcb}"
PCB="$OUT/FluxDrive.kicad_pcb"

rm -rf "$OUT"
mkdir -p "$OUT"
bash tools/export_netlist.sh
# project files next to the board: netclasses and rules, schematic (parity check) and libraries
cp FluxDrive.kicad_pro FluxDrive.kicad_sch FluxDrive.kicad_sym fp-lib-table sym-lib-table "$OUT/"
cp -r FluxDrive.pretty 3dmodels "$OUT/"

"$PY" tools/pcb_sync.py build/FluxDrive.net "$PCB"
"$PY" tools/pcb_place.py "$PCB"
"$PY" tools/pcb_prefan.py "$PCB"                 # hand-made routes (USB-C VBUS bridge)
"$PY" tools/pcb_fanout.py "$PCB"
"$PY" tools/pcb_autoroute.py "$PCB"                 # Freerouting, pinning what it leaves open
"$PY" tools/pcb_ripup.py "$PCB" --dangling          # loose track ends
[ -f tools/pcb_stitch.py ] && "$PY" tools/pcb_stitch.py "$PCB"
[ -f tools/pcb_silk.py ] && "$PY" tools/pcb_silk.py "$PCB"
"$CLI" pcb drc --schematic-parity --severity-error --refill-zones --save-board --exit-code-violations \
    -o "$OUT/drc.txt" "$PCB"
echo "$PCB: DRC clean"
