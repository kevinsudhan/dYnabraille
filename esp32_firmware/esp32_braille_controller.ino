#include <Arduino.h>
#include <ArduinoJson.h>

#define NUM_SOLENOIDS 6

const int solenoidPins[NUM_SOLENOIDS] = {12, 14, 27, 26, 25, 33};

bool solenoidStates[NUM_SOLENOIDS] = {false, false, false, false, false, false};

const int ACTUATION_DURATION = 100;
const int BUFFER_SIZE = 512;

void setup() {
  Serial.begin(115200);
  
  for (int i = 0; i < NUM_SOLENOIDS; i++) {
    pinMode(solenoidPins[i], OUTPUT);
    digitalWrite(solenoidPins[i], LOW);
  }
  
  Serial.println("{\"status\":\"ready\",\"device\":\"ESP32_Braille_Controller\"}");
}

void actuateSolenoid(int dotNumber, bool raise) {
  if (dotNumber < 1 || dotNumber > NUM_SOLENOIDS) {
    return;
  }
  
  int index = dotNumber - 1;
  
  digitalWrite(solenoidPins[index], raise ? HIGH : LOW);
  solenoidStates[index] = raise;
}

void setBraillePattern(int dots[], int numDots) {
  for (int i = 0; i < NUM_SOLENOIDS; i++) {
    digitalWrite(solenoidPins[i], LOW);
    solenoidStates[i] = false;
  }
  
  for (int i = 0; i < numDots; i++) {
    actuateSolenoid(dots[i], true);
  }
}

void resetAllSolenoids() {
  for (int i = 0; i < NUM_SOLENOIDS; i++) {
    digitalWrite(solenoidPins[i], LOW);
    solenoidStates[i] = false;
  }
}

void sendStatus() {
  StaticJsonDocument<256> doc;
  doc["type"] = "status";
  doc["connected"] = true;
  doc["timestamp"] = millis();
  
  JsonArray states = doc.createNestedArray("solenoids");
  for (int i = 0; i < NUM_SOLENOIDS; i++) {
    states.add(solenoidStates[i]);
  }
  
  serializeJson(doc, Serial);
  Serial.println();
}

void processCommand(String command) {
  StaticJsonDocument<512> doc;
  DeserializationError error = deserializeJson(doc, command);
  
  if (error) {
    Serial.print("{\"error\":\"JSON parse failed: ");
    Serial.print(error.c_str());
    Serial.println("\"}");
    return;
  }
  
  const char* type = doc["type"];
  
  if (strcmp(type, "braille") == 0) {
    JsonArray dotsArray = doc["dots"];
    int numDots = dotsArray.size();
    int dots[NUM_SOLENOIDS];
    
    for (int i = 0; i < numDots && i < NUM_SOLENOIDS; i++) {
      dots[i] = dotsArray[i];
    }
    
    setBraillePattern(dots, numDots);
    
    Serial.print("{\"status\":\"pattern_set\",\"dots\":");
    Serial.print(numDots);
    Serial.println("}");
  }
  else if (strcmp(type, "character") == 0) {
    const char* character = doc["char"];
    JsonArray dotsArray = doc["dots"];
    int numDots = dotsArray.size();
    int dots[NUM_SOLENOIDS];
    
    for (int i = 0; i < numDots && i < NUM_SOLENOIDS; i++) {
      dots[i] = dotsArray[i];
    }
    
    setBraillePattern(dots, numDots);
    
    Serial.print("{\"status\":\"character_displayed\",\"char\":\"");
    Serial.print(character);
    Serial.println("\"}");
  }
  else if (strcmp(type, "reset") == 0) {
    resetAllSolenoids();
    Serial.println("{\"status\":\"reset_complete\"}");
  }
  else if (strcmp(type, "status") == 0) {
    sendStatus();
  }
  else {
    Serial.println("{\"error\":\"unknown_command\"}");
  }
}

void loop() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    
    if (command.length() > 0) {
      processCommand(command);
    }
  }
  
  delay(10);
}
