// DynaBraille handheld braille cell — ESP32 firmware.
//
// Talks to the processing server over WiFi (WebSocket) and, as a fallback,
// over USB serial. Both channels carry the same JSON messages; see
// docs/PROTOCOL.md for the full list.
//
// The protocol always uses standard braille dot numbers (1-2-3 down the left
// column, 4-5-6 down the right). This file maps them onto the physical solenoids
// (DOT_TO_SOLENOID) and their polarity (SOLENOID_ON_RAISES_DOT), so what the
// server shows is exactly what the fingers feel.

#include <Arduino.h>
#include <ArduinoJson.h>
#include <ESPmDNS.h>
#include <WebSocketsClient.h>
#include <WiFi.h>
#include <Wire.h>

#if __has_include("config.h")
#include "config.h"
#else
#warning "config.h not found: building with config.example.h. Copy it to config.h and set your WiFi."
#include "config.example.h"
#define USING_EXAMPLE_CONFIG 1
#endif

// Defaults for settings that older config.h files don't have.
#ifndef BUTTON_ACTIVE_HIGH
#define BUTTON_ACTIVE_HIGH 0
#endif
#ifndef HOLD_DUTY_PERCENT
#define HOLD_DUTY_PERCENT 100
#endif
#ifndef PULL_IN_MS
#define PULL_IN_MS 60
#endif
#ifndef PULL_IN_AT_ONCE
#define PULL_IN_AT_ONCE 1
#endif
#ifndef PWM_FREQ_HZ
#define PWM_FREQ_HZ 20000
#endif
#ifndef GAP_IS_BLANK
#define GAP_IS_BLANK 0
#endif

#define FW_VERSION "2.3.0"
#define PROTOCOL_VERSION 2
#define NUM_DOTS 6
#define MAX_CELLS 256
#define MIN_GAP_MS 60
#define STATUS_INTERVAL_MS 5000
#define SERIAL_BUFFER 4096

static const int kSolenoidPins[NUM_DOTS] = SOLENOID_PINS;
static const uint8_t kDotToSolenoid[NUM_DOTS] = DOT_TO_SOLENOID;

// ------------------------------------------------------------------ state

struct WifiAp {
  const char* ssid;
  const char* pass;
};
static const WifiAp kAps[] = {{WIFI_SSID_1, WIFI_PASS_1}, {WIFI_SSID_2, WIFI_PASS_2}, {WIFI_SSID_3, WIFI_PASS_3}};
uint8_t apIndex[3];  // indexes into kAps of the networks actually configured
uint8_t numAps = 0;
uint32_t lastSerialCommandAt = 0;

WebSocketsClient ws;

char deviceId[24];
bool wifiUp = false;
bool wsStarted = false;
bool wsConnected = false;
bool hostFromMdns = false;
uint8_t wsFailures = 0;
uint32_t nextDiscoveryAt = 0;
String serverHost;
uint16_t serverPort = SERVER_PORT;

// Peak-and-hold drive: a solenoid needs full current to pull its plunger in, but much
// less to keep it there. Each one waits its turn, pulls in at full power for
// pullInMs, then holds at holdDuty percent (PWM). Relay boards can't be PWM'd.
#define PWM_BITS 8
#define PWM_MAX 255
enum : uint8_t { SOL_OFF, SOL_WAITING, SOL_PULLING, SOL_HOLDING };
uint8_t solState[NUM_DOTS];
uint32_t pullEndsAt[NUM_DOTS];
uint8_t holdDuty = HOLD_DUTY_PERCENT;
uint16_t pullInMs = PULL_IN_MS;
const bool usePwm = !SOLENOID_ACTIVE_LOW;

uint8_t energized = 0;       // bit s set = solenoid S(s+1) powered
uint32_t onSince[NUM_DOTS];  // when each powered solenoid was switched on
uint8_t raisedMask = 0;      // braille dots currently felt (bit d = dot d+1)
bool resting = true;         // all solenoids off
uint32_t releaseAt = 0;      // 0 = nothing scheduled

struct Job {
  uint32_t id;
  uint8_t cells[MAX_CELLS];
  uint16_t count;
  uint16_t index;
  uint16_t charMs;
  uint16_t gapMs;
  bool active;
  bool inGap;
  uint32_t phaseEndsAt;
};
Job job = {};
uint16_t defaultCharMs = DEFAULT_CHAR_MS;
uint16_t defaultGapMs = DEFAULT_GAP_MS;

float luxValue = -1;
bool lightAidOn = false;
uint8_t lightMode = 0;  // 0 auto, 1 forced on, 2 forced off
float batteryVolts = -1;

// ------------------------------------------------------------------ output

void emit(JsonDocument& doc) {
  String out;
  serializeJson(doc, out);
  if (wsConnected) ws.sendTXT(out);
  Serial.println(out);
}

void emitError(const char* message) {
  JsonDocument doc;
  doc["type"] = "error";
  doc["message"] = message;
  emit(doc);
}

// ------------------------------------------------------------------ solenoids

// duty: 0 = off ... PWM_MAX = fully on.
void outputSolenoid(int s, uint32_t duty) {
  if (!usePwm) {
    bool level = SOLENOID_ACTIVE_LOW ? !(duty > 0) : (duty > 0);
    digitalWrite(kSolenoidPins[s], level ? HIGH : LOW);
    return;
  }
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(kSolenoidPins[s], duty);  // PWM_MAX is treated as 100% on
#else
  ledcWrite(s, duty);
#endif
}

void setupSolenoidOutputs() {
  for (int s = 0; s < NUM_DOTS; s++) {
    // Drive "off" before the pin becomes an output, so nothing twitches at boot.
    digitalWrite(kSolenoidPins[s], SOLENOID_ACTIVE_LOW ? HIGH : LOW);
    pinMode(kSolenoidPins[s], OUTPUT);
    if (usePwm) {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
      ledcAttach(kSolenoidPins[s], PWM_FREQ_HZ, PWM_BITS);
#else
      ledcSetup(s, PWM_FREQ_HZ, PWM_BITS);
      ledcAttachPin(kSolenoidPins[s], s);
#endif
    }
    solState[s] = SOL_OFF;
    outputSolenoid(s, 0);
  }
}

uint32_t holdLevel() { return (uint32_t)holdDuty * PWM_MAX / 100; }

// Starts waiting solenoids (PULL_IN_AT_ONCE at a time) and moves pulled-in ones to hold.
void tickSolenoids(uint32_t now) {
  int pulling = 0;
  for (int s = 0; s < NUM_DOTS; s++) {
    if (solState[s] != SOL_PULLING) continue;
    if ((int32_t)(now - pullEndsAt[s]) >= 0) {
      solState[s] = SOL_HOLDING;
      outputSolenoid(s, holdLevel());
    } else {
      pulling++;
    }
  }
  for (int s = 0; s < NUM_DOTS && pulling < PULL_IN_AT_ONCE; s++) {
    if (solState[s] != SOL_WAITING) continue;
    solState[s] = SOL_PULLING;
    pullEndsAt[s] = now + pullInMs;
    outputSolenoid(s, PWM_MAX);
    pulling++;
  }
}

int solenoidForDot(int dotIndex) {  // 0-based dot -> 0-based solenoid
  return kDotToSolenoid[dotIndex] - 1;
}

// Which braille dots a given set of powered solenoids produces.
uint8_t raisedFromEnergized(uint8_t on) {
  uint8_t mask = 0;
  for (int d = 0; d < NUM_DOTS; d++) {
    bool powered = on & (1 << solenoidForDot(d));
    if (SOLENOID_ON_RAISES_DOT ? powered : !powered) mask |= 1 << d;
  }
  return mask;
}

// Which solenoids to power so exactly the dots in `mask` are felt.
uint8_t energizedForBraille(uint8_t mask) {
  uint8_t on = 0;
  for (int d = 0; d < NUM_DOTS; d++) {
    bool raised = mask & (1 << d);
    if (SOLENOID_ON_RAISES_DOT ? raised : !raised) on |= 1 << solenoidForDot(d);
  }
  return on;
}

void setSolenoids(uint8_t next, bool rest) {
  next &= 0x3F;
  uint32_t now = millis();
  for (int s = 0; s < NUM_DOTS; s++) {
    bool on = next & (1 << s);
    bool was = energized & (1 << s);
    if (on && !was) {
      onSince[s] = now;
      solState[s] = SOL_WAITING;  // pulls in when its turn comes (tickSolenoids)
    } else if (!on && was) {
      solState[s] = SOL_OFF;
      outputSolenoid(s, 0);
    }
  }
  energized = next;
  tickSolenoids(now);
  uint8_t raised = raisedFromEnergized(energized);
  if (raised != raisedMask || rest != resting) {
    raisedMask = raised;
    resting = rest;
    JsonDocument doc;
    doc["type"] = "dots";
    doc["mask"] = raised;
    doc["rest"] = rest;
    emit(doc);
  }
}

void showBraille(uint8_t mask) { setSolenoids(energizedForBraille(mask & 0x3F), false); }
void showBlank() { showBraille(0); }
void restCell() { setSolenoids(0, true); }  // everything off: no current, no heat

uint16_t clampMs(uint32_t ms, uint32_t lo, uint32_t hi) {
  return (uint16_t)constrain(ms, lo, hi);
}

uint8_t maskFromDots(JsonArrayConst dots) {
  uint8_t mask = 0;
  for (JsonVariantConst d : dots) {
    int n = d.as<int>();
    if (n >= 1 && n <= NUM_DOTS) mask |= 1 << (n - 1);
  }
  return mask;
}

// ------------------------------------------------------------------ playback

void emitProgress() {
  JsonDocument doc;
  doc["type"] = "progress";
  doc["id"] = job.id;
  doc["index"] = job.index;
  doc["count"] = job.count;
  emit(doc);
}

void emitDone(bool cancelled) {
  JsonDocument doc;
  doc["type"] = "done";
  doc["id"] = job.id;
  doc["cancelled"] = cancelled;
  emit(doc);
}

void showJobCell() {
  releaseAt = 0;
  showBraille(job.cells[job.index]);
  job.inGap = false;
  job.phaseEndsAt = millis() + job.charMs;
  emitProgress();
}

void startJob() {
  if (job.count == 0) {
    restCell();
    emitDone(false);
    return;
  }
  job.index = 0;
  job.active = true;
  showJobCell();
}

void stopJob() {
  if (job.active) {
    job.active = false;
    emitDone(true);
  }
}

// letter (charMs) -> blank (gapMs) -> next letter ... -> rest
void tickJob(uint32_t now) {
  if (!job.active || (int32_t)(now - job.phaseEndsAt) < 0) return;
  if (!job.inGap) {
    // Between letters. A blank cell powers every solenoid on a build where unpowered
    // pins stay up, which a small supply can't hold, so by default switch everything
    // off instead: the pins still move, so "ll" reads as two letters.
    if (GAP_IS_BLANK) showBlank();
    else setSolenoids(0, false);
    job.inGap = true;
    job.phaseEndsAt = now + job.gapMs;
    return;
  }
  job.index++;
  if (job.index >= job.count) {
    job.active = false;
    restCell();
    emitDone(false);
    return;
  }
  showJobCell();
}

void tickSafety(uint32_t now) {
  if (releaseAt && (int32_t)(now - releaseAt) >= 0) {
    releaseAt = 0;
    restCell();
  }
  for (int s = 0; s < NUM_DOTS; s++) {
    // Signed: onSince can be a few ms newer than `now` (taken at the top of loop()).
    if ((energized & (1 << s)) && (int32_t)(now - onSince[s]) > (int32_t)MAX_ON_MS) {
      stopJob();
      releaseAt = 0;
      restCell();
      char message[64];
      snprintf(message, sizeof(message), "solenoid S%d was on too long; all switched off", s + 1);
      emitError(message);
      return;
    }
  }
}

void selfTest() {
  // S1..S6 in your numbering, one at a time: on, then off.
  for (int s = 0; s < NUM_DOTS; s++) {
    Serial.printf("# self test: solenoid S%d (GPIO %d)\n", s + 1, kSolenoidPins[s]);
    setSolenoids(1 << s, false);
    delay(BOOT_TEST_ON_MS);
    restCell();
    delay(BOOT_TEST_OFF_MS);
  }
}

// ------------------------------------------------------------------ sensors

#if LUX_SENSOR_ENABLED
bool bh1750Begin() {
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  Wire.beginTransmission(BH1750_ADDRESS);
  Wire.write(0x01);  // power on
  if (Wire.endTransmission() != 0) return false;
  Wire.beginTransmission(BH1750_ADDRESS);
  Wire.write(0x10);  // continuous high-resolution mode, 1 lx
  return Wire.endTransmission() == 0;
}

float bh1750Read() {
  if (Wire.requestFrom((int)BH1750_ADDRESS, 2) != 2) return -1;
  uint16_t raw = (Wire.read() << 8) | Wire.read();
  return raw / 1.2f;
}
#endif

void setLightAid(bool on) {
#if LIGHT_AID_PIN >= 0
  digitalWrite(LIGHT_AID_PIN, on ? HIGH : LOW);
#endif
  lightAidOn = on;
}

void updateLightAid() {
  if (lightMode == 1) setLightAid(true);
  else if (lightMode == 2) setLightAid(false);
  else if (luxValue >= 0) {
    if (!lightAidOn && luxValue < LIGHT_AID_ON_LUX) setLightAid(true);
    else if (lightAidOn && luxValue > LIGHT_AID_OFF_LUX) setLightAid(false);
  } else setLightAid(false);
}

void tickSensors(uint32_t now) {
  static uint32_t lastRead = 0;
  if (lastRead && now - lastRead < 1000) return;
  lastRead = now;

#if LUX_SENSOR_ENABLED
  luxValue = bh1750Read();
#endif
  updateLightAid();

#if BATTERY_ADC_PIN >= 0
  uint32_t mv = 0;
  for (int i = 0; i < 8; i++) mv += analogReadMilliVolts(BATTERY_ADC_PIN);
  batteryVolts = (mv / 8.0f / 1000.0f) * BATTERY_DIVIDER;
#endif
}

// ------------------------------------------------------------------ status

void sendHello() {
  JsonDocument doc;
  doc["type"] = "hello";
  doc["proto"] = PROTOCOL_VERSION;
  doc["device_id"] = deviceId;
  doc["name"] = DEVICE_NAME;
  doc["fw"] = FW_VERSION;
  doc["dots"] = NUM_DOTS;
  doc["max_on_ms"] = MAX_ON_MS;
  doc["hold_duty"] = holdDuty;
  doc["pull_in_ms"] = pullInMs;
  doc["pwm"] = usePwm;
  doc["rest_mask"] = raisedFromEnergized(0);
  doc["solenoid_on_raises"] = (bool)SOLENOID_ON_RAISES_DOT;
  JsonArray map = doc["dot_to_solenoid"].to<JsonArray>();
  for (int d = 0; d < NUM_DOTS; d++) map.add(kDotToSolenoid[d]);
  doc["ip"] = WiFi.localIP().toString();
  JsonObject features = doc["features"].to<JsonObject>();
  features["button"] = BUTTON_PIN >= 0;
  features["lux"] = (bool)LUX_SENSOR_ENABLED;
  features["light_aid"] = LIGHT_AID_PIN >= 0;
  features["battery"] = BATTERY_ADC_PIN >= 0;
  emit(doc);
}

void sendStatus() {
  JsonDocument doc;
  doc["type"] = "status";
  doc["device_id"] = deviceId;
  doc["uptime_ms"] = millis();
  doc["heap"] = ESP.getFreeHeap();
  doc["mask"] = raisedMask;
  doc["rest"] = resting;
  doc["energized"] = energized;
  doc["hold_duty"] = holdDuty;
  doc["pull_in_ms"] = pullInMs;
  doc["job"] = job.active ? job.id : 0;
  if (wifiUp) {
    doc["rssi"] = WiFi.RSSI();
    doc["ip"] = WiFi.localIP().toString();
  }
  if (luxValue >= 0) doc["lux"] = luxValue;
  doc["light_aid"] = lightAidOn;
  if (batteryVolts >= 0) {
    float pct = (batteryVolts - BATTERY_EMPTY_V) / (BATTERY_FULL_V - BATTERY_EMPTY_V) * 100.0f;
    doc["battery_v"] = batteryVolts;
    doc["battery_pct"] = (int)constrain(pct, 0.0f, 100.0f);
  }
  emit(doc);
}

// ------------------------------------------------------------------ commands

void handleCommand(const char* data, size_t len) {
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, data, len);
  if (err) {
    emitError("invalid json");
    return;
  }
  const char* type = doc["type"] | "";
  uint32_t now = millis();

  if (!strcmp(type, "show")) {
    // {"type":"show","id":7,"cells":[32,9,37,15],"char_ms":900,"gap_ms":250}
    stopJob();
    job.id = doc["id"] | 0;
    job.count = 0;
    for (JsonVariantConst c : doc["cells"].as<JsonArrayConst>()) {
      if (job.count >= MAX_CELLS) break;
      job.cells[job.count++] = c.as<uint8_t>() & 0x3F;
    }
    job.charMs = clampMs(doc["char_ms"] | defaultCharMs, 50, MAX_CHAR_MS);
    job.gapMs = clampMs(doc["gap_ms"] | defaultGapMs, MIN_GAP_MS, MAX_CHAR_MS);
    startJob();
  } else if (!strcmp(type, "cell") || !strcmp(type, "braille") || !strcmp(type, "character")) {
    // {"type":"cell","mask":5} or {"type":"cell","dots":[1,3]}.
    // "braille" / "character" are the v1 serial commands; still accepted.
    stopJob();
    uint8_t mask = doc["mask"].is<int>() ? (doc["mask"].as<uint8_t>() & 0x3F)
                                         : maskFromDots(doc["dots"].as<JsonArrayConst>());
    showBraille(mask);
    releaseAt = now + clampMs(doc["hold_ms"] | (uint32_t)STATIC_HOLD_MS, 50, STATIC_HOLD_MS);
  } else if (!strcmp(type, "test")) {
    // Powers a single solenoid: {"type":"test","solenoid":2} (your numbering)
    // or {"type":"test","dot":4} (braille numbering; same solenoid here).
    int s = doc["solenoid"] | 0;
    int dot = doc["dot"] | 0;
    if (s < 1 && dot >= 1 && dot <= NUM_DOTS) s = kDotToSolenoid[dot - 1];
    if (s < 1 || s > NUM_DOTS) {
      emitError("test: give solenoid or dot 1-6");
      return;
    }
    stopJob();
    setSolenoids(1 << (s - 1), false);
    releaseAt = now + clampMs(doc["ms"] | 600, 50, STATIC_HOLD_MS);
  } else if (!strcmp(type, "selftest")) {
    stopJob();
    releaseAt = 0;
    selfTest();
  } else if (!strcmp(type, "replay")) {
    stopJob();
    startJob();
  } else if (!strcmp(type, "stop") || !strcmp(type, "reset")) {
    stopJob();
    releaseAt = 0;
    restCell();
  } else if (!strcmp(type, "config")) {
    if (doc["char_ms"].is<int>()) defaultCharMs = clampMs(doc["char_ms"].as<int>(), 50, MAX_CHAR_MS);
    if (doc["gap_ms"].is<int>()) defaultGapMs = clampMs(doc["gap_ms"].as<int>(), MIN_GAP_MS, MAX_CHAR_MS);
    if (doc["pull_in_ms"].is<int>()) pullInMs = clampMs(doc["pull_in_ms"].as<int>(), 10, 500);
    if (doc["hold_duty"].is<int>()) {
      holdDuty = constrain(doc["hold_duty"].as<int>(), 10, 100);
      for (int s = 0; s < NUM_DOTS; s++)  // apply to anything already holding
        if (solState[s] == SOL_HOLDING) outputSolenoid(s, holdLevel());
    }
    sendStatus();
  } else if (!strcmp(type, "light")) {
    const char* mode = doc["mode"] | "auto";
    lightMode = !strcmp(mode, "on") ? 1 : !strcmp(mode, "off") ? 2 : 0;
    updateLightAid();
    sendStatus();
  } else if (!strcmp(type, "status")) {
    sendStatus();
  } else if (!strcmp(type, "hello")) {
    sendHello();  // a USB host asking who we are (over WiFi it's sent on connect)
  } else if (!strcmp(type, "ping")) {
    JsonDocument pong;
    pong["type"] = "pong";
    pong["t"] = doc["t"];
    emit(pong);
  } else if (!strcmp(type, "welcome")) {
    // Server greeting; nothing to do.
  } else {
    emitError("unknown command");
  }
}

// ------------------------------------------------------------------ button

void sendButton(const char* event) {
  Serial.printf("# button: %s\n", event);
  if (!wsConnected) {
    // Capturing needs the server; offline, any press repeats the last word instead.
    stopJob();
    startJob();
    return;
  }
  JsonDocument doc;
  doc["type"] = "button";
  doc["event"] = event;
  emit(doc);
}

void tickButton(uint32_t now) {
#if BUTTON_PIN >= 0
  static bool stable = false, lastRaw = false, longFired = false;
  static uint32_t changedAt = 0, pressedAt = 0, releasedAt = 0;
  static uint8_t clicks = 0;
  const uint32_t debounceMs = 25, longMs = 900, doubleGapMs = 350;

  bool raw = digitalRead(BUTTON_PIN) == (BUTTON_ACTIVE_HIGH ? HIGH : LOW);
  if (raw != lastRaw) {
    lastRaw = raw;
    changedAt = now;
  }
  if (now - changedAt > debounceMs && raw != stable) {
    stable = raw;
    if (stable) {
      pressedAt = now;
      longFired = false;
    } else if (!longFired) {
      clicks++;
      releasedAt = now;
    }
  }
  if (stable && !longFired && now - pressedAt >= longMs) {
    longFired = true;
    clicks = 0;
    sendButton("long");
  }
  if (!stable && clicks && now - releasedAt > doubleGapMs) {
    sendButton(clicks >= 2 ? "double" : "short");
    clicks = 0;
  }
#endif
}

// ------------------------------------------------------------------ networking

void onWsEvent(WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED:
      wsConnected = true;
      wsFailures = 0;
      Serial.printf("# server connected: %s:%u\n", serverHost.c_str(), serverPort);
      sendHello();
      sendStatus();
      break;
    case WStype_DISCONNECTED:
      if (wsConnected) Serial.println("# server disconnected");
      wsConnected = false;
      if (wsFailures < 255) wsFailures++;
      break;
    case WStype_TEXT:
      handleCommand((const char*)payload, length);
      break;
    default:
      break;
  }
}

void startWebSocket() {
  String path = String("/ws/device?token=") + DEVICE_TOKEN + "&id=" + deviceId;
  Serial.printf("# connecting to ws://%s:%u/ws/device\n", serverHost.c_str(), serverPort);
  ws.begin(serverHost.c_str(), serverPort, path.c_str());
  ws.onEvent(onWsEvent);
  ws.setReconnectInterval(2000);
  ws.enableHeartbeat(15000, 3000, 2);
  wsStarted = true;
  wsFailures = 0;
}

bool discoverServer() {
  int found = MDNS.queryService("dynabraille", "tcp");
  if (found <= 0) return false;
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  serverHost = MDNS.address(0).toString();
#else
  serverHost = MDNS.IP(0).toString();
#endif
  serverPort = MDNS.port(0);
  hostFromMdns = true;
  Serial.printf("# found server via mDNS: %s:%u\n", serverHost.c_str(), serverPort);
  return true;
}

// Joins the configured networks one after another without ever blocking the loop:
// WiFi.begin() returns at once and the radio connects in the background.
void tickWifiJoin(uint32_t now) {
  static uint8_t next = 0;
  static uint32_t startedAt = 0;
  if (numAps == 0 || WiFi.status() == WL_CONNECTED) return;
  if (startedAt && now - startedAt < 12000) return;  // give each network 12 s
  const WifiAp& ap = kAps[apIndex[next]];
  next = (next + 1) % numAps;
  startedAt = now ? now : 1;
  Serial.printf("# joining WiFi \"%s\"\n", ap.ssid);
  WiFi.disconnect();
  WiFi.begin(ap.ssid, ap.pass);
}

void tickNetwork(uint32_t now) {
  bool connected = WiFi.status() == WL_CONNECTED;

  if (connected && !wifiUp) {
    wifiUp = true;
    Serial.printf("# wifi up: %s  ip=%s  rssi=%d\n", WiFi.SSID().c_str(),
                  WiFi.localIP().toString().c_str(), WiFi.RSSI());
    MDNS.begin(deviceId);
    nextDiscoveryAt = now;
  } else if (!connected && wifiUp) {
    wifiUp = false;
    Serial.println("# wifi lost");
  }

  if (!connected) {
    tickWifiJoin(now);
    return;
  }

  // An mDNS lookup blocks for up to 3 s, so never run one mid-word or while a
  // program is driving the cell over USB, and back off while nothing answers.
  // A fixed SERVER_HOST needs no lookup, so it connects straight away.
  static uint32_t discoveryBackoff = 5000;
  bool busy = job.active || (lastSerialCommandAt && (int32_t)(now - lastSerialCommandAt) < 15000);
  if (!wsStarted && strlen(SERVER_HOST) > 0) {
    serverHost = SERVER_HOST;
    serverPort = SERVER_PORT;
    hostFromMdns = false;
    startWebSocket();
  } else if (!wsStarted && !busy && (int32_t)(now - nextDiscoveryAt) >= 0) {
    if (discoverServer()) {
      discoveryBackoff = 5000;
      startWebSocket();
    } else {
      Serial.printf("# server not found via mDNS, retrying in %us (set SERVER_HOST to skip discovery)\n",
                    (unsigned)(discoveryBackoff / 1000));
      nextDiscoveryAt = now + discoveryBackoff;
      discoveryBackoff = min<uint32_t>(discoveryBackoff * 2, 30000);
    }
  }

  // The server's address may have changed (laptop moved networks): look it up again.
  if (wsStarted && hostFromMdns && !wsConnected && wsFailures >= 5) {
    ws.disconnect();
    wsStarted = false;
    nextDiscoveryAt = now;
  }

  if (wsStarted) ws.loop();
}

void tickSerial() {
  static char buffer[SERIAL_BUFFER];
  static size_t used = 0;
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (used > 0) {
        // Routine polls from a USB host ("status", "hello", "ping") don't count as
        // driving the cell; anything else pauses the WiFi server search for a while.
        buffer[used] = '\0';
        if (!strstr(buffer, "\"status\"") && !strstr(buffer, "\"hello\"") && !strstr(buffer, "\"ping\""))
          lastSerialCommandAt = millis();
        handleCommand(buffer, used);
      }
      used = 0;
    } else if (used < SERIAL_BUFFER - 1) {
      buffer[used++] = c;
    }
  }
}

void tickStatus(uint32_t now) {
  static uint32_t last = 0;
  if (now - last < STATUS_INTERVAL_MS) return;
  last = now;
  if (wsConnected) sendStatus();
}

void tickLed(uint32_t now) {
#if STATUS_LED_PIN >= 0
  bool on;
  if (numAps == 0) on = (now % 2000) < 80;  // USB-only: short blip every 2 s
  else if (!wifiUp) on = (now / 120) % 2;
  else if (!wsConnected) on = (now / 600) % 2;
  else on = true;
  digitalWrite(STATUS_LED_PIN, (on != (bool)STATUS_LED_ACTIVE_LOW) ? HIGH : LOW);
#endif
}

// ------------------------------------------------------------------ arduino

void setup() {
  // Switch every solenoid off before anything else so nothing twitches at boot.
  setupSolenoidOutputs();
  raisedMask = raisedFromEnergized(0);
#if BUTTON_PIN >= 0
  pinMode(BUTTON_PIN, BUTTON_ACTIVE_HIGH ? INPUT_PULLDOWN : INPUT_PULLUP);
#endif
#if STATUS_LED_PIN >= 0
  pinMode(STATUS_LED_PIN, OUTPUT);
#endif
#if LIGHT_AID_PIN >= 0
  pinMode(LIGHT_AID_PIN, OUTPUT);
  digitalWrite(LIGHT_AID_PIN, LOW);
#endif

  Serial.begin(115200);
  delay(200);

  uint64_t mac = ESP.getEfuseMac();
  snprintf(deviceId, sizeof(deviceId), "dynabraille-%02x%02x%02x", (uint8_t)(mac >> 24),
           (uint8_t)(mac >> 32), (uint8_t)(mac >> 40));
  Serial.printf("# DynaBraille firmware %s  id=%s\n", FW_VERSION, deviceId);
#ifdef USING_EXAMPLE_CONFIG
  Serial.println("# WARNING: no config.h - using example WiFi settings");
#endif

#if LUX_SENSOR_ENABLED
  if (!bh1750Begin()) Serial.println("# BH1750 not found on I2C");
#endif

#if BOOT_SELF_TEST
  selfTest();
#endif

  WiFi.setHostname(deviceId);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);  // modem sleep adds 100+ ms of latency to every message
  WiFi.setAutoReconnect(true);
  for (uint8_t i = 0; i < sizeof(kAps) / sizeof(kAps[0]); i++) {
    // Empty or still the example placeholder = not configured.
    if (strlen(kAps[i].ssid) && strcmp(kAps[i].ssid, "your-wifi-name") != 0) apIndex[numAps++] = i;
  }
  if (numAps == 0) Serial.println("# WiFi not configured: USB serial only (set WIFI_SSID_1 in config.h)");

  // Serial is always live, so the cell is usable over USB before WiFi is set up.
  Serial.println("{\"type\":\"ready\",\"device\":\"ESP32_Braille_Controller\",\"fw\":\"" FW_VERSION "\"}");
}

void loop() {
  uint32_t now = millis();
  tickSerial();
  tickNetwork(now);
  tickJob(now);
  tickSolenoids(now);
  tickSafety(now);
  tickButton(now);
  tickSensors(now);
  tickStatus(now);
  tickLed(now);
  delay(2);
}
