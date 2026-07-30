/*
 * Mark2 Uno firmware — Sensor Shield V5
 * Protocolo: MOVE,base,ombro,cotovelo,garra,velocidade | HOME | STOP
 * Respostas: READY | OK | STOPPED | ERROR,...
 * Baud: 115200
 * Pinos: Base=11, Ombro=10, Cotovelo=9, Garra=8
 * (Garra no pino 8 para teste com um único servo)
 */

#include <Servo.h>

const int PIN_BASE = 11;
const int PIN_SHOULDER = 10;
const int PIN_ELBOW = 9;
const int PIN_GRIPPER = 8;

const int MIN_BASE = 15;
const int MAX_BASE = 165;
const int MIN_SHOULDER = 30;
const int MAX_SHOULDER = 150;
const int MIN_ELBOW = 20;
const int MAX_ELBOW = 160;
const int MIN_GRIPPER = 50;
const int MAX_GRIPPER = 120;

const int HOME_BASE = 90;
const int HOME_SHOULDER = 90;
const int HOME_ELBOW = 90;
const int HOME_GRIPPER = 110;

Servo servoBase;
Servo servoShoulder;
Servo servoElbow;
Servo servoGripper;

int curBase = HOME_BASE;
int curShoulder = HOME_SHOULDER;
int curElbow = HOME_ELBOW;
int curGripper = HOME_GRIPPER;

bool busy = false;
volatile bool stopRequested = false;

String inputBuffer;

int clampAngle(int value, int minV, int maxV) {
  if (value < minV) return minV;
  if (value > maxV) return maxV;
  return value;
}

void attachServos() {
  servoBase.attach(PIN_BASE);
  servoShoulder.attach(PIN_SHOULDER);
  servoElbow.attach(PIN_ELBOW);
  servoGripper.attach(PIN_GRIPPER);
}

void writeAll(int b, int s, int e, int g) {
  servoBase.write(b);
  servoShoulder.write(s);
  servoElbow.write(e);
  servoGripper.write(g);
  curBase = b;
  curShoulder = s;
  curElbow = e;
  curGripper = g;
}

void moveSync(int tBase, int tShoulder, int tElbow, int tGripper, int speed) {
  busy = true;
  stopRequested = false;

  tBase = clampAngle(tBase, MIN_BASE, MAX_BASE);
  tShoulder = clampAngle(tShoulder, MIN_SHOULDER, MAX_SHOULDER);
  tElbow = clampAngle(tElbow, MIN_ELBOW, MAX_ELBOW);
  tGripper = clampAngle(tGripper, MIN_GRIPPER, MAX_GRIPPER);

  int stepDelay = constrain(100 - speed, 2, 40);

  int dB = tBase - curBase;
  int dS = tShoulder - curShoulder;
  int dE = tElbow - curElbow;
  int dG = tGripper - curGripper;

  int steps = abs(dB);
  if (abs(dS) > steps) steps = abs(dS);
  if (abs(dE) > steps) steps = abs(dE);
  if (abs(dG) > steps) steps = abs(dG);
  if (steps < 1) steps = 1;

  for (int i = 1; i <= steps; i++) {
    if (stopRequested) {
      Serial.println("STOPPED");
      busy = false;
      return;
    }
    int nb = curBase + (dB * i) / steps;
    int ns = curShoulder + (dS * i) / steps;
    int ne = curElbow + (dE * i) / steps;
    int ng = curGripper + (dG * i) / steps;
    writeAll(nb, ns, ne, ng);
    delay(stepDelay);
  }

  writeAll(tBase, tShoulder, tElbow, tGripper);
  Serial.println("OK");
  busy = false;
}

bool parseIntField(const String& s, int& out) {
  out = s.toInt();
  return true;
}

void handleCommand(String line) {
  line.trim();
  if (line.length() == 0) return;

  if (line.equalsIgnoreCase("STOP")) {
    stopRequested = true;
    if (!busy) {
      Serial.println("STOPPED");
    }
    return;
  }

  if (busy) {
    Serial.println("ERROR,BUSY");
    return;
  }

  if (line.equalsIgnoreCase("HOME")) {
    moveSync(HOME_BASE, HOME_SHOULDER, HOME_ELBOW, HOME_GRIPPER, 15);
    return;
  }

  if (line.startsWith("MOVE,")) {
    // MOVE,base,ombro,cotovelo,garra,velocidade
    int vals[5];
    int start = 5;
    for (int i = 0; i < 5; i++) {
      int comma = line.indexOf(',', start);
      String part;
      if (comma < 0) {
        if (i < 4) {
          Serial.println("ERROR,INVALID_COMMAND");
          return;
        }
        part = line.substring(start);
      } else {
        part = line.substring(start, comma);
        start = comma + 1;
      }
      part.trim();
      if (part.length() == 0) {
        Serial.println("ERROR,INVALID_COMMAND");
        return;
      }
      vals[i] = part.toInt();
    }

    if (vals[0] < MIN_BASE || vals[0] > MAX_BASE ||
        vals[1] < MIN_SHOULDER || vals[1] > MAX_SHOULDER ||
        vals[2] < MIN_ELBOW || vals[2] > MAX_ELBOW ||
        vals[3] < MIN_GRIPPER || vals[3] > MAX_GRIPPER) {
      Serial.println("ERROR,OUT_OF_RANGE");
      return;
    }

    moveSync(vals[0], vals[1], vals[2], vals[3], vals[4]);
    return;
  }

  Serial.println("ERROR,INVALID_COMMAND");
}

void setup() {
  Serial.begin(115200);
  while (!Serial) { ; }
  attachServos();
  writeAll(HOME_BASE, HOME_SHOULDER, HOME_ELBOW, HOME_GRIPPER);
  delay(300);
  Serial.println("READY");
}

void loop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (inputBuffer.length() > 0) {
        handleCommand(inputBuffer);
        inputBuffer = "";
      }
    } else {
      inputBuffer += c;
      if (inputBuffer.length() > 80) {
        inputBuffer = "";
        Serial.println("ERROR,INVALID_COMMAND");
      }
    }
  }
}
