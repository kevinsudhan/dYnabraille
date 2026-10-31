# Pin finder

Finds which ESP32 GPIO drives each solenoid (S1–S6) and which GPIO the tactile
button is on, when the wiring is hidden under the board. At the end it prints the
two lines to paste into `firmware/dynabraille_esp32/config.h`.

Solenoid numbering, looking down at the cell:

```
S1  S2
S3  S4
S5  S6
```

## Before you start

- Connect the **solenoid power supply** and make sure its **GND is joined to the
  ESP32 GND**. Without it the MOSFETs switch, but nothing moves.
- Plug the ESP32 into the PC with a USB-C **data** cable. Some cables only charge.
- On this build an unpowered solenoid sits **up**. The one being tested **drops down**
  each time it is switched on.
- Close anything else using the board's COM port: the Arduino Serial Monitor, or
  `python -m dynabraille` with `DEVICE_SERIAL_PORT` set.

On this PC the board shows up as **COM5** ("USB-Enhanced-SERIAL CH9102"). The
driver is already installed.

## Upload — option A: command line (already set up in this repo)

From the repo root in PowerShell:

```powershell
cd firmware\tools
..\.pio-venv\Scripts\pio run -t upload --upload-port COM5
..\.pio-venv\Scripts\pio device monitor --port COM5
```

`firmware\.pio-venv` is created by `scripts\flash-firmware.ps1`. It's already there
on this PC. Leave the monitor with `Ctrl+C`.

## Upload — option B: Arduino IDE 2

1. **File → Preferences → Additional boards manager URLs**:
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
2. **Tools → Board → Boards Manager**, search **esp32**, install
   **"esp32 by Espressif Systems"**.
3. **File → Open** `firmware/tools/pin_finder/pin_finder.ino`.
4. **Tools → Board → esp32 → ESP32 Dev Module**, **Tools → Port → COM5**.
5. Click **Upload** (→). If it stops at `Connecting....`, hold the **BOOT**
   button on the board until the upload percentage starts.
6. **Tools → Serial Monitor**: set **115200 baud** and **Newline**, then press
   the board's **EN/RST** button to see the menu.

No extra libraries are needed for this sketch.

## Easiest: the clickable pin tester

With the pin finder on the board, run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\pin-tester.ps1 -Port COM5
```

A page opens showing the board from the top, every header pin in its real position.
**Click** a pin to pulse it for 0.5 s, or **hold** it to keep it on (3 s maximum), then tap
the solenoid that dropped. **Walk all pins** steps through every pin for you. When all six
are tagged, **Save to config.h** writes `SOLENOID_PINS` into the firmware config. Close any
serial monitor first: only one program can use COM5 at a time.

## Using it

Type a command and press Enter:

| Command | What it does |
|---|---|
| `s` | **Guided scan.** Each GPIO switches on and off in turn. Type the solenoid that moves (1–6), or `0` if nothing moves. `r` goes back one pin, `q` stops. |
| `t` | Checks the result: S1 → S6 move one after another (across, then down). |
| `b` | Finds the button: press and release it 3 times within 8 seconds. |
| `m` | Shows what has been found so far, plus the lines to paste. |
| `27` | Pulses GPIO 27 three times (any number works). |
| `w` | **Slow walk:** every GPIO one by one in header order, named as printed on the board (D21, TX2…), 3 pulses each then a pause. Includes TX0. |
| `a` | Walks through every GPIO once, with no questions. |
| `x` | Switches everything off. |

Example result:

```
Paste into firmware/dynabraille_esp32/config.h:
  #define SOLENOID_PINS {12, 14, 27, 26, 25, 33}  // S1, S2, S3, S4, S5, S6
  #define BUTTON_PIN 32
```

Notes:

- GPIO 2 is also the blue on-board LED, so it blinks during the scan. That's normal.
- GPIOs 1, 3 (USB serial), 6–11 (flash) and 34–39 (input-only) can't drive a solenoid,
  so they're skipped. The button finder does watch 34–39.
- No pin is ever left on for more than half a second.

When you're done, flash the real firmware again (see `docs/HARDWARE.md`).
