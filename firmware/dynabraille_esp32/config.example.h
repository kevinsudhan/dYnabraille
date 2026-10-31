// DynaBraille handheld firmware configuration.
//
// Copy this file to config.h (same folder) and edit it. config.h is git-ignored so
// your WiFi password never ends up in the repo. If config.h is missing, the firmware
// still compiles with these defaults (useful for CI), but it won't join your network.
#pragma once

// ---------------------------------------------------------------- WiFi
// Up to three networks; the strongest available one is used. Leave unused SSIDs "".
// The ESP32 only supports 2.4 GHz networks. An iPhone Personal Hotspot works
// (turn on "Maximise Compatibility").
#define WIFI_SSID_1 "your-wifi-name"
#define WIFI_PASS_1 "your-wifi-password"
#define WIFI_SSID_2 ""
#define WIFI_PASS_2 ""
#define WIFI_SSID_3 ""
#define WIFI_PASS_3 ""

// ---------------------------------------------------------------- Processing server
// Leave SERVER_HOST empty to find the server automatically over mDNS
// (it advertises itself as _dynabraille._tcp). Set an IP such as "192.168.1.20"
// if your network blocks multicast (common on guest/campus WiFi).
#define SERVER_HOST ""
#define SERVER_PORT 8000
// Must match DEVICE_TOKEN in server/.env. Letters, digits, '-' and '_' only.
#define DEVICE_TOKEN "change-me"
// Friendly name shown on the dashboard.
#define DEVICE_NAME "Handheld braille cell"

// ---------------------------------------------------------------- Solenoids
// GPIO for each solenoid, in YOUR solenoid numbering. On this build the
// solenoids are numbered row by row:
//
//        solenoids           braille dots
//         S1  S2               1   4
//         S3  S4               2   5
//         S5  S6               3   6
//
// These are the reference cell's pins, found with firmware/tools/pin_finder. A cell wired
// differently needs its own (the pin finder prints this line for you). Avoid GPIO12 if
// you can: it's a boot strapping pin and the ESP32 won't boot if it's pulled HIGH.
#define SOLENOID_PINS {15, 21, 4, 5, 18, 19}  // S1, S2, S3, S4, S5, S6

// Which solenoid sits under each braille dot (dot 1..6), from the diagram above.
// The server always speaks standard braille dot numbers; this maps them onto the
// hardware so the cell shows exactly what the dashboard shows.
#define DOT_TO_SOLENOID {1, 3, 5, 2, 4, 6}

// 0 = energising a solenoid pulls its pin DOWN (unpowered pins stay UP and show a dot).
//     This is the current build: to show a letter, the firmware powers the solenoids
//     for the dots that must NOT be felt. At rest (everything off) all six pins are up.
// 1 = energising a solenoid pushes its pin UP.
#define SOLENOID_ON_RAISES_DOT 0

// 0 = MOSFET gate driver (GPIO HIGH = solenoid powered).
// 1 = relay boards that switch on a LOW input.
#define SOLENOID_ACTIVE_LOW 0

// Playback defaults (the server normally sends its own timing with each word).
#define DEFAULT_CHAR_MS 900  // how long each letter is held
#define DEFAULT_GAP_MS 250   // pause between letters, so "ll" reads as two letters
#define MAX_CHAR_MS 4000     // upper limit for either of the above
// A single character or test sent on its own is held this long, then the cell rests.
#define STATIC_HOLD_MS 8000
// Safety: if any solenoid has been powered continuously for this long, everything
// is switched off. Solenoids held on get hot and drain the battery.
#define MAX_ON_MS 20000

// Power budget. A solenoid needs full current to pull its plunger in, but far less to
// keep it there. Each one pulls in at full power for PULL_IN_MS (PULL_IN_AT_ONCE at a
// time), then holds at HOLD_DUTY_PERCENT using PWM. Lower hold power = more solenoids
// can stay down together on a small supply. Tune it live from the dashboard
// (Hardware > Actuate solenoids); the server remembers it and sends it on connect.
// The reference cell's supply only pulls in about 3 solenoids at full power, so it holds at 50%.
#define HOLD_DUTY_PERCENT 50
#define PULL_IN_MS 60
#define PULL_IN_AT_ONCE 1
#define PWM_FREQ_HZ 20000  // above hearing, so the coils don't whine
// 0 = between letters switch everything off (no current needed);
// 1 = show a blank cell between letters (powers every solenoid on this build).
#define GAP_IS_BLANK 0

// Power-on self test: each solenoid S1..S6 is switched on, then off, one at a time.
#define BOOT_SELF_TEST 1
#define BOOT_TEST_ON_MS 400
#define BOOT_TEST_OFF_MS 250

// ---------------------------------------------------------------- Tactile button
// Wire the button between this pin and GND (internal pull-up is used). -1 disables.
//   short press  -> capture what the camera sees now and spell the objects in braille
//   double press -> repeat the last word
//   long press   -> turn continuous camera braille on / off
#define BUTTON_PIN 32
#define BUTTON_ACTIVE_HIGH 0  // 1 if the button connects the pin to 3V3 instead of GND

// ---------------------------------------------------------------- Status LED
// Fast blink = joining WiFi, slow blink = looking for server, solid = connected,
// short blip every 2 s = WiFi not configured (USB serial only).
#define STATUS_LED_PIN 2
#define STATUS_LED_ACTIVE_LOW 0

// ---------------------------------------------------------------- Optional: BH1750 + light aid
#define LUX_SENSOR_ENABLED 0
#define I2C_SDA_PIN 22  // not 21: that drives S2 on the reference cell
#define I2C_SCL_PIN 23
#define BH1750_ADDRESS 0x23
// LED/lamp driver pin switched on in the dark. -1 disables.
#define LIGHT_AID_PIN -1
#define LIGHT_AID_ON_LUX 15
#define LIGHT_AID_OFF_LUX 30

// ---------------------------------------------------------------- Optional: battery monitor
// ADC1 pin (32-39) behind a voltage divider. ADC2 pins don't work while WiFi is on.
#define BATTERY_ADC_PIN -1
#define BATTERY_DIVIDER 2.0f
#define BATTERY_EMPTY_V 3.30f
#define BATTERY_FULL_V 4.20f
