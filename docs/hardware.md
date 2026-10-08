# Ulanzi D100H on Linux

Observed on Ubuntu 26.04, BlueZ, input-remapper 2.2.0, 2026-10-08.

- Bluetooth LE HID only; USB-C is charge-only. Modalias `usb:vFFF1p0082`.
- Kernel exposes four evdev nodes via uhid:
  - `Ulanzi Dial Keyboard` — EV_KEY/REL/ABS/MSC/LED/REP. **All defaults arrive here**, including
    the consumer keys (dial = KEY_VOLUMEDOWN 114 / KEY_VOLUMEUP 115, press = KEY_MUTE 113;
    top keys = KEY_PREVIOUSSONG 165 / KEY_PLAYPAUSE 164 / KEY_NEXTSONG 163).
  - `Ulanzi Dial Mouse` — relative axes + mouse buttons (unused by defaults).
  - two `Ulanzi Dial` nodes — single ABS axis each (unused by defaults).
- Side keys send chords: left upper Ctrl+V, left lower Ctrl+C, right upper Ctrl+Y,
  right lower Ctrl+Z (LEFTCTRL assumed — confirm with input-remapper's recorder if a side key misfires).
- Dial press reportedly only fires while USB-powered (homebrew notes); don't make it critical.

## Upstream developer resources
- Reverse-engineering notes: https://github.com/brendanwelsh/ulanzi-d100h-homebrew
- UlanziDeck plugin SDK (Ulanzi Studio, Windows/macOS): https://github.com/UlanziTechnology/UlanziDeckPlugin-SDK
  — not usable on Linux directly since Ulanzi Studio has no Linux build; Dialtone works one layer
  lower, on the device's offline HID output.
