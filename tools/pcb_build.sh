#!/usr/bin/env bash
# Build the 4-layer board from the schematic in build/pcb/ (OUT= to choose), then install it in the repo.
# Needs KiCad 10, Java 17 and Freerouting 1.9 at ~/.kicad-mcp/freerouting.jar. About 15 minutes.
#
#   bash tools/pcb_build.sh          # when the DRC at the end is clean, the board goes to FluxDrive.kicad_pcb
#                                    # and the fit template is made again (INSTALL=0: leave the repo board)
#
# Steps: netlist -> new board from the netlist -> outline, planes, rule areas and placement -> hand-made routes
# -> fan-out of the GND and +3V3 pads to their planes -> Freerouting six times with different settings, the
# best kept and finished (tools/pcb_autoroute.py) -> loose track ends -> ground stitching -> silkscreen -> DRC
# with zone refill and schematic parity -> the board against the placement table.
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
"$PY" tools/pcb_place.py --check "$PCB"             # the board is what this placement table says
echo "$PCB: DRC clean"
if [ "${INSTALL:-1}" = 1 ]; then                     # INSTALL=0 keeps the repo's board as it is
    cp "$PCB" FluxDrive.kicad_pcb
    bash tools/fit_template.sh
    echo "FluxDrive.kicad_pcb updated; run python -m pytest -q"
fi
