// DynaBraille pin finder — which GPIO drives which solenoid, and which one is the button?
//
// For the ESP32 DevKit V1 (30-pin) when the wiring is hidden under the board.
// Upload it, open the Serial Monitor at 115200 baud with line ending "Newline",
// and follow the prompts. Full steps: firmware/tools/pin_finder/README.md
//
// Before you start: connect the solenoid power supply and make sure its GND is
// joined to the ESP32's GND, otherwise nothing will move.
// On this build an unpowered solenoid sits UP, so the one being tested drops DOWN.

#include <Arduino.h>

// Every GPIO on the 30-pin DevKit V1 that can drive an output.
// Not tested: 1 and 3 (USB serial), 6-11 (flash chip), 34/35/36/39 (input only).
static const int kCandidates[] = {2, 4, 5, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 23, 25, 26, 27, 32, 33};
static const int kNumCandidates = sizeof(kCandidates) / sizeof(kCandidates[0]);
static const int kInputOnly[] = {34, 35, 36, 39};
static const int kNumInputOnly = sizeof(kInputOnly) / sizeof(kInputOnly[0]);

static const uint32_t PULSE_ON_MS = 500;   // never longer than this: solenoids heat up
static const uint32_t PULSE_OFF_MS = 700;

// The two header rows of the 30-pin DevKit V1, counted from the antenna end.
// Only pins that can drive an output are listed (EN, VP, VN, D34, D35 can't).
static const int kRowA[] = {32, 33, 25, 26, 27, 14, 12, 13};  // EN VP VN D34 D35 [D32 ... D13] GND VIN
static const int kRowAPos[] = {6, 7, 8, 9, 10, 11, 12, 13};
static const int kRowB[] = {23, 22, 1, 3, 21, 19, 18, 5, 17, 16, 4, 2, 15};  // [D23 ... D15] GND 3V3
static const int kRowBPos[] = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13};

int solenoidGpio[7] = {-1, -1, -1, -1, -1, -1, -1};  // [1..6] = GPIO for S1..S6
int buttonGpio = -1;

// Direct control ("p 21", "on 21", "off 21") used by the pin tester page.
static const uint32_t HOLD_LIMIT_MS = 3000;  // "on" switches itself off after this
uint32_t offAt[40];                          // per GPIO: when to switch off, 0 = not held

// ------------------------------------------------------------------ helpers

void allOff() {
  for (int i = 0; i < kNumCandidates; i++) {
    if (kCandidates[i] == buttonGpio) {
      pinMode(buttonGpio, INPUT);  // an output here could be shorted by pressing the button
      continue;
    }
    offAt[kCandidates[i]] = 0;
    digitalWrite(kCandidates[i], LOW);
    pinMode(kCandidates[i], OUTPUT);
    digitalWrite(kCandidates[i], LOW);
  }
}

bool isCandidate(int gpio) {
  for (int i = 0; i < kNumCandidates; i++)
    if (kCandidates[i] == gpio) return true;
  return false;
}

int solenoidOf(int gpio) {
  for (int s = 1; s <= 6; s++)
    if (solenoidGpio[s] == gpio) return s;
  return 0;
}

// Collects one line from the Serial Monitor without blocking. Returns true when complete.
bool readLine(String& out) {
  static String buffer;
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (buffer.length() == 0) continue;
      out = buffer;
      out.trim();
      out.toLowerCase();
      buffer = "";
      return true;
    }
    buffer += c;
  }
  return false;
}

void pulse(int gpio, int times) {
  for (int i = 0; i < times; i++) {
    digitalWrite(gpio, HIGH);
    delay(PULSE_ON_MS);
    digitalWrite(gpio, LOW);
    delay(PULSE_OFF_MS);
  }
}

// The name printed next to the pin on the board.
String boardLabel(int gpio) {
  switch (gpio) {
    case 1: return "TX0";
    case 3: return "RX0";
    case 16: return "RX2";
    case 17: return "TX2";
    default: return "D" + String(gpio);
  }
}

void printHelp() {
  Serial.println();
  Serial.println("=== DynaBraille pin finder ===");
  Serial.println("  s        guided scan: find the GPIO for each solenoid S1..S6");
  Serial.println("  b        find the tactile button's GPIO");
  Serial.println("  t        test the result: S1, S2 ... S6 one at a time");
  Serial.println("  m        show what has been found so far");
  Serial.println("  w        slow walk: every GPIO one by one, in header order, with its board label");
  Serial.println("  a        quick walk through every GPIO once");
  Serial.println("  <number> pulse one GPIO three times, e.g. 27");
  Serial.println("  x        switch everything off");
  Serial.println("  h        this help");
  Serial.println("Solenoid numbering (top view):  S1 S2 / S3 S4 / S5 S6");
}

void printMapping() {
  Serial.println();
  Serial.println("Solenoid -> GPIO");
  bool complete = true;
  for (int s = 1; s <= 6; s++) {
    if (solenoidGpio[s] >= 0) Serial.printf("  S%d -> GPIO %d\n", s, solenoidGpio[s]);
    else {
      Serial.printf("  S%d -> not found yet\n", s);
      complete = false;
    }
  }
  Serial.printf("Button -> %s\n", buttonGpio >= 0 ? String("GPIO " + String(buttonGpio)).c_str() : "not found yet (press b)");
  if (complete) {
    Serial.println();
    Serial.println("Paste into firmware/dynabraille_esp32/config.h:");
    Serial.printf("  #define SOLENOID_PINS {%d, %d, %d, %d, %d, %d}  // S1, S2, S3, S4, S5, S6\n",
                  solenoidGpio[1], solenoidGpio[2], solenoidGpio[3], solenoidGpio[4], solenoidGpio[5],
                  solenoidGpio[6]);
    if (buttonGpio >= 0) Serial.printf("  #define BUTTON_PIN %d\n", buttonGpio);
    for (int s = 1; s <= 6; s++) {
      if (solenoidGpio[s] == 12) {
        Serial.println("  Note: GPIO 12 is a boot-strapping pin. It's fine as long as its MOSFET gate");
        Serial.println("  has a pull-down; if the board ever fails to boot, move that wire to GPIO 13.");
      }
    }
  }
}

// ------------------------------------------------------------------ guided scan

void guidedScan() {
  allOff();
  for (int s = 1; s <= 6; s++) solenoidGpio[s] = -1;
  Serial.println();
  Serial.println("Guided scan. Each GPIO is switched on and off repeatedly.");
  Serial.println("Watch / feel the cell, then type which solenoid moves (1-6) and press Enter.");
  Serial.println("Type 0 if nothing moves, r to go back one pin, q to stop.");

  int i = 0;
  while (i < kNumCandidates) {
    int gpio = kCandidates[i];
    Serial.printf("\n[%d/%d] GPIO %d is pulsing", i + 1, kNumCandidates, gpio);
    if (gpio == 2) Serial.print("  (GPIO 2 is also the blue on-board LED)");
    Serial.print("  -> solenoid 1-6, or 0: ");

    bool on = false;
    uint32_t phaseAt = 0;
    String answer;
    while (true) {
      uint32_t now = millis();
      if (now - phaseAt >= (on ? PULSE_ON_MS : PULSE_OFF_MS)) {
        on = !on;
        digitalWrite(gpio, on ? HIGH : LOW);
        phaseAt = now;
      }
      if (readLine(answer)) break;
      delay(2);
    }
    digitalWrite(gpio, LOW);
    Serial.println(answer);

    if (answer == "q") break;
    if (answer == "r") {
      if (i > 0) {
        i--;
        int previous = solenoidOf(kCandidates[i]);
        if (previous) solenoidGpio[previous] = -1;
      }
      continue;
    }
    int s = answer.toInt();
    if (answer == "0") {
      i++;
      continue;
    }
    if (s < 1 || s > 6) {
      Serial.println("  Please type 1-6, 0, r or q.");
      continue;
    }
    if (solenoidGpio[s] >= 0 && solenoidGpio[s] != gpio)
      Serial.printf("  (S%d was GPIO %d before; now GPIO %d)\n", s, solenoidGpio[s], gpio);
    solenoidGpio[s] = gpio;
    Serial.printf("  S%d = GPIO %d\n", s, gpio);
    i++;

    bool done = true;
    for (int k = 1; k <= 6; k++) done = done && solenoidGpio[k] >= 0;
    if (done) {
      Serial.println("\nAll six solenoids found. Skipping the remaining pins.");
      break;
    }
  }
  allOff();
  printMapping();
  Serial.println("\nNext: press t to check the order, or b to find the button.");
}

// ------------------------------------------------------------------ order test

void testOrder() {
  allOff();
  Serial.println("\nSwitching S1..S6 on and off in order. They should go across, then down:");
  Serial.println("  S1 S2 / S3 S4 / S5 S6");
  bool any = false;
  for (int s = 1; s <= 6; s++) any = any || solenoidGpio[s] >= 0;
  if (!any) {
    Serial.println("  Nothing found yet: run s (guided scan) or w (slow walk) first.");
    return;
  }
  for (int s = 1; s <= 6; s++) {
    if (solenoidGpio[s] < 0) {
      Serial.printf("  S%d: not found yet, skipped\n", s);
      continue;
    }
    Serial.printf("  S%d (GPIO %d)\n", s, solenoidGpio[s]);
    pulse(solenoidGpio[s], 1);
  }
}

// ------------------------------------------------------------------ walk

void walkAll() {
  allOff();
  Serial.println("\nWalking every GPIO once (press Enter to stop).");
  for (int i = 0; i < kNumCandidates; i++) {
    Serial.printf("  GPIO %d\n", kCandidates[i]);
    pulse(kCandidates[i], 1);
    String ignored;
    if (readLine(ignored)) break;
  }
  allOff();
}

// ------------------------------------------------------------------ slow walk

// Pulses one pin three times. Returns false if the user pressed Enter to stop.
bool walkPin(int gpio, const char* row, int position) {
  int s = solenoidOf(gpio);
  Serial.printf("  GPIO %-2d  %-4s  %s row, pin %2d from the antenna end", gpio, boardLabel(gpio).c_str(), row,
                position);
  if (s) Serial.printf("   (found earlier: S%d)", s);
  Serial.println();
  if (gpio == 1) {
    // TX0 is the USB serial output: switch the UART off while this pin is driven.
    Serial.println("           serial pauses for ~4 s while TX0 is tested...");
    Serial.flush();
    Serial.end();
    pinMode(1, OUTPUT);
    pulse(1, 3);
    Serial.begin(115200);
    delay(100);
  } else {
    pulse(gpio, 3);
  }
  for (uint32_t start = millis(); millis() - start < 1500;) {
    String ignored;
    if (readLine(ignored)) return false;
    delay(5);
  }
  return true;
}

void slowWalk() {
  allOff();
  Serial.println("\nSlow walk. Each pin switches on and off 3 times, then pauses 1.5 s.");
  Serial.println("Note the GPIO whenever a solenoid moves. Press Enter to stop.");
  Serial.println("RX0 (GPIO 3) is skipped: the USB chip drives it, so it can't be tested safely.");
  bool completed = true;
  Serial.println("\nRow that starts D23 (antenna end) and ends 3V3:");
  for (int i = 0; completed && i < (int)(sizeof(kRowB) / sizeof(kRowB[0])); i++) {
    if (kRowB[i] != 3) completed = walkPin(kRowB[i], "D23..3V3", kRowBPos[i]);
  }
  if (completed) Serial.println("\nRow that starts EN (antenna end) and ends VIN:");
  for (int i = 0; completed && i < (int)(sizeof(kRowA) / sizeof(kRowA[0])); i++) {
    completed = walkPin(kRowA[i], "EN..VIN", kRowAPos[i]);
  }
  allOff();
  Serial.println(completed ? "\nWalk finished. Type a GPIO number to pulse just that one again." : "\nStopped.");
}

// ------------------------------------------------------------------ button finder

// A pin's state for button hunting. Pins with internal pulls are read twice: with a
// pull-up (a button to GND pulls it LOW) and with a pull-down (a button to 3V3 pulls
// it HIGH), so either wiring shows up. Bit 1 = low under pull-up, bit 0 = high under
// pull-down. GPIO 34-39 have no internal pulls and are read as they are.
uint8_t buttonState(int gpio, bool pulls) {
  if (!pulls) return digitalRead(gpio);
  pinMode(gpio, INPUT_PULLUP);
  delayMicroseconds(40);
  bool lowWithPullUp = digitalRead(gpio) == LOW;
  pinMode(gpio, INPUT_PULLDOWN);
  delayMicroseconds(40);
  bool highWithPullDown = digitalRead(gpio) == HIGH;
  return (lowWithPullUp << 1) | highWithPullDown;
}

// "b" or "b 15,21,4,5,18,19": the listed GPIOs (the solenoids) are left alone,
// because pulling a MOSFET gate up could switch its solenoid on.
void findButton(const String& skipList) {
  bool skip[40] = {false};
  for (int s = 1; s <= 6; s++)
    if (solenoidGpio[s] >= 0) skip[solenoidGpio[s]] = true;
  for (int from = 0; from < (int)skipList.length();) {
    int comma = skipList.indexOf(',', from);
    if (comma < 0) comma = skipList.length();
    int gpio = skipList.substring(from, comma).toInt();
    if (gpio > 0 && gpio < 40) skip[gpio] = true;
    from = comma + 1;
  }

  int pins[32];
  bool pulls[32];
  int n = 0;
  for (int i = 0; i < kNumCandidates; i++) {
    if (skip[kCandidates[i]]) continue;
    pins[n] = kCandidates[i];
    pulls[n++] = true;
  }
  for (int i = 0; i < kNumInputOnly; i++) {
    pinMode(kInputOnly[i], INPUT);
    pins[n] = kInputOnly[i];
    pulls[n++] = false;
  }
  Serial.print("\nWatching:");
  for (int i = 0; i < n; i++) Serial.printf(" %s", boardLabel(pins[i]).c_str());
  Serial.println();

  uint8_t last[32], stable[32], idle[32], pressed[32];
  uint32_t changedAt[32];
  int changes[32];
  for (int i = 0; i < n; i++) {
    last[i] = stable[i] = idle[i] = buttonState(pins[i], pulls[i]);
    pressed[i] = 0xFF;
    changedAt[i] = millis();
    changes[i] = 0;
  }

  Serial.println("Press and release the tactile button 3 times in the next 8 seconds...");
  uint32_t start = millis();
  int lastSecond = -1;
  while (millis() - start < 8000) {
    uint32_t now = millis();
    for (int i = 0; i < n; i++) {
      uint8_t state = buttonState(pins[i], pulls[i]);
      if (state != last[i]) {
        last[i] = state;
        changedAt[i] = now;
      }
      if (now - changedAt[i] > 30 && state != stable[i]) {
        stable[i] = state;
        changes[i]++;  // counts both press and release
        if (state != idle[i] && pressed[i] == 0xFF) pressed[i] = state;
      }
    }
    int second = (now - start) / 1000;
    if (second != lastSecond) {
      lastSecond = second;
      Serial.printf("  %d...\n", 8 - second);
    }
  }

  int best = -1;
  Serial.println("Pins that changed:");
  for (int i = 0; i < n; i++) {
    if (changes[i] == 0) continue;
    Serial.printf("  %s (GPIO %d) changed %d times\n", boardLabel(pins[i]).c_str(), pins[i], changes[i]);
    if (changes[i] >= 4 && changes[i] <= 8 && (best < 0 || abs(changes[i] - 6) < abs(changes[best] - 6))) best = i;
  }
  allOff();
  if (best < 0) {
    Serial.println("No clear match (3 presses = about 6 changes). Check the button wiring and try b again.");
    return;
  }
  buttonGpio = pins[best];
  bool toGnd = pulls[best] ? (pressed[best] & 0b10) : (pressed[best] == LOW);
  pinMode(buttonGpio, INPUT);  // never leave it as an output: pressing could short it
  Serial.printf("Button is on %s (GPIO %d), wired to %s.\n", boardLabel(buttonGpio).c_str(), buttonGpio,
                toGnd ? "GND" : "3V3");
  Serial.printf("@button %d %s\n", buttonGpio, toGnd ? "gnd" : "3v3");
  if (buttonGpio >= 34)
    Serial.println("  GPIO 34-39 have no internal pull resistors: keep the external one in your circuit.");
}

// ------------------------------------------------------------------ direct control
// Quiet, machine-friendly commands for the pin tester page. Replies start with '@'.
//   p 21    pulse once (PULSE_ON_MS)       -> @on 21 ... @off 21
//   on 21   switch on, off after 3 s max   -> @on 21
//   off 21  switch off                     -> @off 21

void switchOff(int gpio) {
  if (gpio != 1) digitalWrite(gpio, LOW);  // TX0 is already back to being the serial line
  offAt[gpio] = 0;
  Serial.printf("@off %d\n", gpio);
}

void switchOn(int gpio, uint32_t ms) {
  if (gpio == 1) {
    // TX0 carries the serial output, so it can only be pulsed blind.
    Serial.println("@on 1");
    Serial.flush();
    Serial.end();
    pinMode(1, OUTPUT);
    digitalWrite(1, HIGH);
    delay(PULSE_ON_MS);
    digitalWrite(1, LOW);
    Serial.begin(115200);
    delay(50);
    Serial.println("@off 1");
    return;
  }
  digitalWrite(gpio, HIGH);
  offAt[gpio] = millis() + ms;
  if (!offAt[gpio]) offAt[gpio] = 1;
  Serial.printf("@on %d\n", gpio);
}

void tickHolds() {
  uint32_t now = millis();
  for (int i = 0; i < kNumCandidates; i++) {
    int gpio = kCandidates[i];
    if (offAt[gpio] && (int32_t)(now - offAt[gpio]) >= 0) switchOff(gpio);
  }
}

bool directCommand(const String& line) {
  int space = line.indexOf(' ');
  if (space < 0) return false;
  String verb = line.substring(0, space);
  if (verb != "p" && verb != "on" && verb != "off") return false;
  int gpio = line.substring(space + 1).toInt();
  if (!isCandidate(gpio) && gpio != 1) {
    Serial.printf("@err GPIO %d can't drive a solenoid\n", gpio);
  } else if (verb == "off") {
    switchOff(gpio);
  } else {
    switchOn(gpio, verb == "p" ? PULSE_ON_MS : HOLD_LIMIT_MS);
  }
  return true;
}

// ------------------------------------------------------------------ arduino

void setup() {
  allOff();  // everything off first, so no solenoid stays powered
  Serial.begin(115200);
  delay(500);
  printHelp();
  Serial.print("\n> ");
}

void loop() {
  tickHolds();
  String line;
  if (!readLine(line)) {
    delay(2);
    return;
  }
  if (directCommand(line)) return;
  Serial.println(line);
  if (line == "s") guidedScan();
  else if (line == "b") findButton("");
  else if (line.startsWith("b ")) findButton(line.substring(2));
  else if (line == "t") testOrder();
  else if (line == "m") printMapping();
  else if (line == "a") walkAll();
  else if (line == "w") slowWalk();
  else if (line == "x") {
    allOff();
    Serial.println("All off.");
  } else if (line == "h" || line == "?") printHelp();
  else if (line.length() && isDigit(line[0])) {
    int gpio = line.toInt();
    if (isCandidate(gpio)) {
      Serial.printf("Pulsing GPIO %d three times\n", gpio);
      pulse(gpio, 3);
    } else {
      Serial.printf("GPIO %d can't be tested (input-only, flash or USB pin)\n", gpio);
    }
  } else {
    Serial.println("Unknown command, type h for help.");
  }
  Serial.print("\n> ");
}
