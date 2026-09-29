#!/usr/bin/env bash
# 1:1 paper template of the board for the fit test in the A500 (plan task 10, spec 11.4): outline, courtyards,
# silkscreen, fab drawing and a 50 mm scale bar (Dwgs.User) to check the print scale.
#
#   bash tools/fit_template.sh          -> mech/fit_template.pdf; print at 100 %, no "fit to page"
set -euo pipefail
cd "$(dirname "$0")/.."
CLI="${KICAD_CLI:-/c/Program Files/KiCad/10.0/bin/kicad-cli.exe}"
mkdir -p mech
"$CLI" pcb export pdf --mode-single --scale 1 --black-and-white \
    -l Edge.Cuts,F.Courtyard,F.Silkscreen,F.Fab,Dwgs.User -o mech/fit_template.pdf FluxDrive.kicad_pcb
echo "mech/fit_template.pdf written"
