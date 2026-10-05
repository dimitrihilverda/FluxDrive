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
# kicad-cli exits 2 when a model is missing. Known gaps: the USB-C has a VRML model only (3dmodels/), and KiCad 10
# has no STEP model for the buttons (SW1, SW2) or the eFuses (U5, U9). None of them is taller than 3.3 mm.
# Any other error fails, and so does an empty STEP; the old STEP goes first, so a failed export cannot leave it.
rm -f mech/FluxDrive.step
if ! out=$("$CLI" pcb export step --subst-models --force -o mech/FluxDrive.step "$PCB" 2>&1); then
    unknown=$(grep -i "error\|cannot\|could not\|not found" <<< "$out" \
        | grep -v -e "Cannot use VRML models" -e "for SW1" -e "for SW2" -e "for U5" -e "for U9" \
                  -e "SW_Push_1P1T_XKB_TS-1187A" -e "Texas_DSG0008A_WSON-8" || true)
    if [ -n "$unknown" ] || [ ! -s mech/FluxDrive.step ]; then
        echo "$out"
        exit 1
    fi
    echo "note: no STEP model for the USB-C (3.3 mm), the buttons and the eFuses; the STEP leaves them out"
fi
echo "mech/fit_template.pdf and mech/FluxDrive.step written"
