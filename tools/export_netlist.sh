#!/usr/bin/env bash
# Generate the schematic from hardware/design.py and export its netlist. Needs KiCad 10.
set -euo pipefail
cd "$(dirname "$0")/.."
KICAD_CLI="${KICAD_CLI:-/c/Program Files/KiCad/10.0/bin/kicad-cli.exe}"
mkdir -p build
python tools/sch_gen.py FluxDrive.kicad_sch
"$KICAD_CLI" sch export netlist --format kicadsexpr -o build/FluxDrive.net FluxDrive.kicad_sch
echo "build/FluxDrive.net written"
