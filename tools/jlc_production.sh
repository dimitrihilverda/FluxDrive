#!/usr/bin/env bash
# JLCPCB production files for the board, in jlcpcb/production_files/: the gerber + drill zip, BOM and CPL.
# tools/jlc_export.py explains the BOM/CPL rules (copied from the Nano-Tek, 2623d2f; 4 layers).
#
#   bash tools/jlc_production.sh
set -euo pipefail
cd "$(dirname "$0")/.."
KICAD_BIN="${KICAD_BIN:-/c/Program Files/KiCad/10.0/bin}"
PY="$KICAD_BIN/python.exe"
CLI="$KICAD_BIN/kicad-cli.exe"
PCB=FluxDrive.kicad_pcb
OUT=jlcpcb/production_files
TMP=build/gerber
rm -rf "$TMP"
mkdir -p "$TMP" "$OUT"
"$CLI" pcb export gerbers --no-x2 --check-zones -o "$TMP/" "$PCB" -l F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts
"$CLI" pcb export drill --excellon-separate-th --generate-map --map-format pdf -o "$TMP/" "$PCB"
"$PY" -c "import pathlib, sys, zipfile; src = pathlib.Path(sys.argv[1]); z = zipfile.ZipFile(sys.argv[2], 'w', zipfile.ZIP_DEFLATED); [z.write(f, f.name) for f in sorted(src.iterdir())]; z.close()" "$TMP" "$OUT/GERBER-FluxDrive.zip"
"$PY" tools/jlc_export.py "$PCB" "$OUT"
