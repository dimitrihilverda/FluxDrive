# FluxDrive

An Amiga floppy drive emulator built around one ESP32-S3: no Gotek, no second microcontroller. It plugs into the
A500's internal floppy connector, holds a disk image in PSRAM and generates the MFM flux stream itself. Disk
images come from the [GTi](https://github.com/mesarim/Gotek-Touchscreen-interface) touchscreen over ESP-NOW, or
from a phone over WiFi.

Status: hardware design under review. Nothing has been built yet.

| Where | What |
|---|---|
| `docs/superpowers/specs/` | design specs (start with the v1 hardware design) |
| `docs/input/` | the documents this design builds on: MES's FluxDrive HW design v0.1, breadboard measurements |
| `docs/reviews/` | specialist reviews of the spec, schematic and layout, with what was done about each finding |

Related: the breadboard prototype and its firmware live in
[dimitrihilverda/amiga-floppy-emulator](https://github.com/dimitrihilverda/amiga-floppy-emulator).
