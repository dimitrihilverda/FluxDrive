#!/usr/bin/env bash
# 1:1 paper template of the board for the fit test in the A500 (plan task 10, spec 11.4): outline, courtyards,
# silkscreen, fab drawing and two scale bars (50 mm across, 40 mm down, Dwgs.User) to check the print scale;
# and a STEP model of the fitted board for a printed dummy.
#
#   bash tools/fit_template.sh [board]      -> mech/fit_template.pdf (print at 100 %, no "fit to page")
#                                              mech/FluxDrive.step
set -euo pipefail
cd "$(dirname "$0")/.."
CLI="${KICAD_CLI:-/c/Program Files/KiCad/10.0/bin/kicad-cli.exe}"
PCB="${1:-FluxDrive.kicad_pcb}"
LAYERS=Edge.Cuts,F.Courtyard,F.Silkscreen,F.Fab,Dwgs.User
mkdir -p mech
"$CLI" pcb export pdf --mode-single --scale 1 --black-and-white -l "$LAYERS" -o mech/fit_template.pdf "$PCB" > /dev/null
# the USB-C has a VRML model only (3dmodels/): kicad-cli leaves it out of the STEP and exits 2; any other error fails.
# KiCad 10 has no model for the buttons and the eFuse either (a warning only). None of them is taller than 3.3 mm.
if ! out=$("$CLI" pcb export step --subst-models --force -o mech/FluxDrive.step "$PCB" 2>&1); then
    if grep -v "Cannot use VRML models" <<< "$out" | grep -qi "error\|cannot\|failed" || [ ! -s mech/FluxDrive.step ]; then
        echo "$out"
        exit 1
    fi
    echo "note: no STEP model for the USB-C (3.3 mm high), the two buttons and the eFuse; the STEP leaves them out"
fi
echo "mech/fit_template.pdf and mech/FluxDrive.step written"
