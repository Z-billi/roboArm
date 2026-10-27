// UNO + CNC Shield V3 + A4988 + two positional servos. Requires Arduino Servo library.
#include <Arduino.h>
#include <Servo.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

const uint8_t ENABLE_PIN = 8;  // Shared by all shield axes, active LOW.
const uint32_t MAX_STEPS = 1000000UL;
const uint16_t MAX_SPEED = 2000;
const uint32_t LINK_TIMEOUT_MS = 1500;
const bool INVERT_X_DIRECTION = false;
const bool INVERT_Y_DIRECTION = false;
const bool INVERT_Z_DIRECTION = false;

struct Axis {
  char name;
  uint8_t stepPin, dirPin;
  bool invert, running;
  int8_t direction;
  uint32_t total, completed, intervalUs, lastStepUs;
  uint16_t speed;
  const char *state;
};
Axis axes[] = {
  {'X', 2, 5, INVERT_X_DIRECTION, false, 0, 0, 0, 2000, 0, 500, "IDLE"},
  {'Y', 3, 6, INVERT_Y_DIRECTION, false, 0, 0, 0, 2000, 0, 500, "IDLE"},
  {'Z', 4, 7, INVERT_Z_DIRECTION, false, 0, 0, 0, 2000, 0, 500, "IDLE"}
};
const uint8_t AXIS_COUNT = sizeof(axes) / sizeof(axes[0]);
const uint8_t SERVO_COUNT = 2;
const uint8_t SERVO_PINS[SERVO_COUNT] = {12, 13};
const uint8_t INITIAL_SERVO_ANGLE = 90;
Servo servos[SERVO_COUNT];
uint8_t servoAngles[SERVO_COUNT] = {INITIAL_SERVO_ANGLE, INITIAL_SERVO_ANGLE};
char inputLine[80];
uint8_t inputLength = 0;
bool inputOverflow = false;
uint32_t lastContactMs = 0, lastReportMs = 0;
uint8_t reportAxis = 0;

// Buffered output: never let Serial.print() block the stepping/STOP loop.
char txLines[3][160];
uint8_t txHead = 0, txCount = 0, txOffset = 0;

Axis *findAxis(const char *name) {
  if (!name || name[0] == 0 || name[1] != 0) return NULL;
  for (uint8_t i = 0; i < AXIS_COUNT; i++)
    if (axes[i].name == name[0]) return &axes[i];
  return NULL;
}

int8_t findServo(const char *name) {
  if (strcmp(name, "D12") == 0) return 0;
  if (strcmp(name, "D13") == 0) return 1;
  return -1;
}

void enqueue(const char *line, bool periodic = false) {
  if (periodic && txCount) return;
  if (txCount == 3) return; // Flooded command replies may be dropped; STATUS recovers state.
  uint8_t slot = (txHead + txCount) % 3;
  strncpy(txLines[slot], line, sizeof(txLines[slot]) - 1);
  txLines[slot][sizeof(txLines[slot]) - 1] = 0;
  txCount++;
}

void pumpOutput() {
  if (!txCount) return;
  uint8_t sent = 0;
  while (Serial.availableForWrite() > 0 && sent < 16) {
    char c = txLines[txHead][txOffset];
    if (!c) {
      txHead = (txHead + 1) % 3;
      txCount--;
      txOffset = 0;
      break;
    }
    Serial.write((uint8_t)c);
    txOffset++;
    sent++;
  }
}

void report(const char *event, Axis &axis, const char *reason = "NONE", bool periodic = false) {
  char line[160];
  const char *direction = axis.direction > 0 ? "FORWARD" : axis.direction < 0 ? "REVERSE" : "NONE";
  snprintf(line, sizeof(line), "%s %c state=%s dir=%s total=%lu completed=%lu remaining=%lu speed=%u reason=%s\n",
    event, axis.name, axis.state, direction, (unsigned long)axis.total,
    (unsigned long)axis.completed, (unsigned long)(axis.total - axis.completed), axis.speed, reason);
  enqueue(line, periodic);
}

void error(const char *code, const char *axis = NULL) {
  char line[64];
  if (axis) snprintf(line, sizeof(line), "ERROR axis=%s code=%s\n", axis, code);
  else snprintf(line, sizeof(line), "ERROR code=%s\n", code);
  enqueue(line);
}

void reportServo(uint8_t index, bool acknowledged = false, bool periodic = false) {
  char line[48];
  snprintf(line, sizeof(line), "%sSERVO D%u angle=%u\n",
    acknowledged ? "OK " : "", SERVO_PINS[index], servoAngles[index]);
  enqueue(line, periodic);
}

void servoError(const char *code, const char *pin) {
  char line[64];
  snprintf(line, sizeof(line), "ERROR servo=%s code=%s\n", pin, code);
  enqueue(line);
}

bool number(const char *token, long &value) {
  if (!token || !*token) return false;
  const char *p = token;
  if (*p == '-' || *p == '+') p++;
  if (!*p) return false;
  // Bound length before strtol, avoiding overflow on AVR (32-bit long).
  uint8_t digits = 0;
  for (; *p; p++) {
    if (*p < '0' || *p > '9' || ++digits > 7) return false;
  }
  value = strtol(token, NULL, 10);
  return true;
}

void updateEnable() {
  bool anyRunning = false;
  for (uint8_t i = 0; i < AXIS_COUNT; i++) anyRunning |= axes[i].running;
  digitalWrite(ENABLE_PIN, anyRunning ? LOW : HIGH);
}

void stopAxis(Axis &axis, const char *reason, bool sendReport = true) {
  axis.running = false;
  axis.state = "STOPPED";
  digitalWrite(axis.stepPin, LOW);
  updateEnable();
  if (sendReport) report("STOPPED", axis, reason);
}

void command(char *line) {
  char *tokens[5];
  uint8_t count = 0;
  char *context;
  char *token = strtok_r(line, " \t", &context);
  while (token && count < 5) {
    tokens[count++] = token;
    token = strtok_r(NULL, " \t", &context);
  }
  if (!count) return;
  if (strcmp(tokens[0], "PING") == 0 && count == 1) {
    lastContactMs = millis();
    enqueue("OK PING\n");
    return;
  }
  if (strcmp(tokens[0], "SERVO_STATUS") == 0 && (count == 1 || count == 2)) {
    if (count == 1) {
      lastContactMs = millis();
      for (uint8_t i = 0; i < SERVO_COUNT; i++) reportServo(i);
      return;
    }
    int8_t index = findServo(tokens[1]);
    if (index < 0) { servoError("SERVO_UNSUPPORTED", tokens[1]); return; }
    lastContactMs = millis();
    reportServo(index);
    return;
  }
  if (strcmp(tokens[0], "SERVO") == 0 && count == 3) {
    int8_t index = findServo(tokens[1]);
    if (index < 0) { servoError("SERVO_UNSUPPORTED", tokens[1]); return; }
    long angle;
    if (!number(tokens[2], angle)) { servoError("BAD_NUMBER", tokens[1]); return; }
    if (angle < 0 || angle > 180) { servoError("ANGLE_RANGE", tokens[1]); return; }
    lastContactMs = millis();
    servoAngles[index] = (uint8_t)angle;
    servos[index].write(angle); // Interrupt-driven pulses; never sweep with delay().
    reportServo(index, true);
    return;
  }
  if (strcmp(tokens[0], "STATUS") == 0 && (count == 1 || count == 2)) {
    if (count == 1) {
      lastContactMs = millis();
      for (uint8_t i = 0; i < AXIS_COUNT; i++) report("STATUS", axes[i]);
      return;
    }
    Axis *axis = findAxis(tokens[1]);
    if (!axis) { error("AXIS_UNSUPPORTED", tokens[1]); return; }
    lastContactMs = millis();
    report("STATUS", *axis);
    return;
  }
  if (strcmp(tokens[0], "STOP") == 0 && count == 2) {
    if (strcmp(tokens[1], "ALL") == 0) {
      lastContactMs = millis();
      for (uint8_t i = 0; i < AXIS_COUNT; i++) stopAxis(axes[i], "USER", false);
      enqueue("OK STOP_ALL\n"); // Acknowledge only after every axis has stopped.
      return;
    }
    Axis *axis = findAxis(tokens[1]);
    if (!axis) { error("AXIS_UNSUPPORTED", tokens[1]); return; }
    lastContactMs = millis();
    stopAxis(*axis, "USER");
    return;
  }
  if (strcmp(tokens[0], "MOVE") == 0 && count == 4) {
    Axis *axis = findAxis(tokens[1]);
    if (!axis) { error("AXIS_UNSUPPORTED", tokens[1]); return; }
    long steps, speed;
    if (!number(tokens[2], steps) || !number(tokens[3], speed)) { error("BAD_NUMBER", tokens[1]); return; }
    if (steps == 0 || steps > (long)MAX_STEPS || steps < -(long)MAX_STEPS) { error("STEPS_RANGE", tokens[1]); return; }
    if (speed < 1 || speed > MAX_SPEED) { error("SPEED_RANGE", tokens[1]); return; }
    if (axis->running) { error("BUSY", tokens[1]); return; }
    lastContactMs = millis();
    axis->total = steps < 0 ? -steps : steps;
    axis->completed = 0;
    axis->direction = steps > 0 ? 1 : -1;
    axis->speed = speed;
    axis->intervalUs = 1000000UL / speed;
    digitalWrite(axis->dirPin, (axis->direction > 0) != axis->invert ? HIGH : LOW);
    digitalWrite(ENABLE_PIN, LOW);
    axis->lastStepUs = micros(); // First step after one interval; DIR has time to settle.
    axis->running = true;
    axis->state = "RUNNING";
    report("OK", *axis);
    report("RUNNING", *axis);
    return;
  }
  error("BAD_COMMAND");
}

void tickMotion() {
  for (uint8_t i = 0; i < AXIS_COUNT; i++) {
    Axis &axis = axes[i];
    if (!axis.running) continue;
    if ((uint32_t)(millis() - lastContactMs) >= LINK_TIMEOUT_MS) {
      stopAxis(axis, "LINK_TIMEOUT");
      continue;
    }
    uint32_t now = micros();
    if ((uint32_t)(now - axis.lastStepUs) < axis.intervalUs) continue;
    axis.lastStepUs = now; // No burst catch-up if the loop is late.
    digitalWrite(axis.stepPin, HIGH);
    delayMicroseconds(3); // A4988 minimum HIGH/LOW = 1 us; only this tiny pulse waits.
    digitalWrite(axis.stepPin, LOW);
    axis.completed++;
    if (axis.completed == axis.total) {
      axis.running = false;
      axis.state = "DONE";
      updateEnable();
      report("DONE", axis);
    }
  }
}

void setup() {
  digitalWrite(ENABLE_PIN, HIGH);
  pinMode(ENABLE_PIN, OUTPUT);
  for (uint8_t i = 0; i < AXIS_COUNT; i++) {
    digitalWrite(axes[i].stepPin, LOW);
    pinMode(axes[i].stepPin, OUTPUT);
    pinMode(axes[i].dirPin, OUTPUT);
    digitalWrite(axes[i].dirPin, LOW);
  }
  for (uint8_t i = 0; i < SERVO_COUNT; i++) {
    servos[i].attach(SERVO_PINS[i]);
    servos[i].write(INITIAL_SERVO_ANGLE);
  }
  Serial.begin(115200);
  lastContactMs = millis();
  enqueue("READY protocol=3 axes=X,Y,Z servos=D12,D13\n");
}

void loop() {
  // Bound receive work per loop so a serial flood cannot starve motion/watchdog.
  for (uint8_t n = 0; n < 32 && Serial.available(); n++) {
    char c = Serial.read();
    if (c == '\n') {
      if (inputOverflow) error("LINE_TOO_LONG");
      else { inputLine[inputLength] = 0; command(inputLine); }
      inputLength = 0;
      inputOverflow = false;
    } else if (c != '\r') {
      if (inputLength < sizeof(inputLine) - 1) inputLine[inputLength++] = c;
      else inputOverflow = true;
    }
    tickMotion();
  }
  tickMotion();
  if ((uint32_t)(millis() - lastReportMs) >= 80 && !txCount) {
    lastReportMs = millis();
    if (reportAxis < AXIS_COUNT) report("STATUS", axes[reportAxis], "NONE", true);
    else reportServo(reportAxis - AXIS_COUNT, false, true);
    reportAxis = (reportAxis + 1) % (AXIS_COUNT + SERVO_COUNT);
  }
  pumpOutput();
}
