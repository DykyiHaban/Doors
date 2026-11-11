/*
  Проєкт «Двері» — STM32F411 BlackPill + датчики ривка (SW-420, ADXL345, датчик Холла)
  + радар LD2410C + HW-247A (DFPlayer Mini)

  Коли заклад зачинений і хтось смикає двері (або стоїть біля них), модуль програє /mp3/0001.mp3.

  Кожен датчик має свій пін, тож на одній платі можна поставити будь-який один, кілька
  або всі одразу. ADXL345 і радар визначаються автоматично; список знайдених датчиків
  виводиться в Serial Monitor після ввімкнення.

  Режим роботи — SENSOR_MODE нижче:
    MODE_JERK  — лише ривки (SW-420 / ADXL345 / датчик Холла). Радар не потрібен.
    MODE_RADAR — лише радар: людина стоїть ближче RADAR_MAX_CM довше RADAR_DWELL_MS.
    MODE_BOTH  — ривки зараховуються, тільки якщо радар бачить людину поруч (найменше хибних).
    MODE_ANY   — спрацьовує будь-що: ривки або людина, що стоїть біля дверей.

  Arduino IDE (ядро STM32duino, "STM32 MCU based boards"):
    Board:               Generic STM32F4 series
    Board part number:   BlackPill F411CE
    USB support:         CDC (generic 'Serial' supersede U(S)ART)   <-- обов'язково
    Upload method:       STM32CubeProgrammer (DFU) або ST-Link

  Підключення (збігається з платою STM32/schemes/gen_pcb.py). Кожен датчик має свій гвинтовий
  клемник на нижньому краю плати, зліва направо:
    ХОЛЛ:     GND, VCC 3.3 В, OUT -> PA1
    РАДАР:    RX радара <- PA2, TX радара -> PA3 (USART2), OUT -> PA4, 5V, GND
    SW-420:   GND, VCC 3.3 В, DO -> PB12
    ADXL345:  VCC 3.3 В, SCL -> PA8, SDA -> PB4 (I2C3), GND (на модулі з'єднати CS з VCC, SDO з GND)
    ЗАЧИНЕНО: SIG -> PB5, GND (замкнено = заклад зачинений)
    PB6  -> RX модуля MP3 (USART1; TX модуля не потрібен)
    PB10 <- BUSY модуля MP3 (LOW, поки грає)
    PC13 -- вбудований світлодіод (світиться, поки грає повідомлення)

  Картка microSD: FAT32, файл /mp3/0001.mp3
*/

#if !defined(USBCON) || !defined(USBD_USE_CDC)
#error "У меню Tools -> USB support оберіть: CDC (generic 'Serial' supersede U(S)ART)"
#endif

#include <Wire.h>

// ---------- Режим ----------
enum SensorMode { MODE_JERK, MODE_RADAR, MODE_BOTH, MODE_ANY };
const SensorMode SENSOR_MODE = MODE_JERK;   // див. опис угорі файлу

// ---------- Які датчики ривка опитувати ----------
const bool USE_SW420  = true;    // без модуля вхід підтягнутий до 3.3 В і мовчить — можна лишати true
const bool USE_ADXL   = true;    // визначається автоматично; якщо не знайдено — просто не використовується
const bool USE_ANALOG = false;   // клемник ХОЛЛ: вмикати ТІЛЬКИ якщо датчик підключено (інакше вхід «плаває»)
// Скільки РІЗНИХ датчиків мають помітити той самий удар, щоб він рахувався ривком.
// 1 — вистачить будь-якого; 2 — потрібна згода двох (менше хибних, якщо стоять кілька датчиків).
const uint8_t  JERK_SENSORS_AGREE = 1;
const uint32_t JERK_MERGE_MS      = 300;   // спрацювання різних датчиків у цьому вікні — один і той самий удар

// ---------- Піни ----------
#define PIN_ANALOG    PA1              // клемник ХОЛЛ, OUT
#define PIN_SW420     PB12
#define PIN_SDA       PB4              // I2C3
#define PIN_SCL       PA8
#define PIN_MP3_BUSY  PB10
#define PIN_ARMED     PB5
#define PIN_LED       PC13
#define PIN_RADAR_OUT PA4

HardwareSerial mp3Serial(PB7, PB6);    // RX, TX (USART1); RX (PB7) на платі не розведений — не потрібен
HardwareSerial radarSerial(PA3, PA2);  // RX, TX (USART2)

// ---------- Загальні налаштування (підбираються на реальних дверях) ----------
const uint8_t  JERKS_TO_TRIGGER = 2;       // скільки ривків потрібно
const uint32_t JERK_WINDOW_MS   = 2000;    // ...за цей час
const uint32_t COOLDOWN_MS      = 60000;   // пауза після повідомлення
const uint32_t SETTLE_MS        = 3000;    // заспокоєння після переходу в режим «зачинено»
const uint32_t STUCK_MS         = 5000;    // якщо сигнал «завис» над порогом — прийняти як нову базу
const uint32_t MAX_PLAY_MS      = 60000;   // захист, якщо BUSY не повернувся
const uint8_t  MP3_VOLUME       = 25;      // 0..30
const uint16_t MP3_TRACK        = 1;       // /mp3/0001.mp3

const uint32_t SAMPLE_MS        = 5;       // 200 вимірів на секунду
const float    BASE_ALPHA       = 0.001f;  // повільна базова лінія (~5 с)
const float    BASE_ALPHA_QUICK = 0.05f;   // швидке підлаштування бази (старт, пауза)

// ---------- Датчик Холла (аналоговий вхід) ----------
const float    ANALOG_THRESHOLD = 40.0f;   // відхилення від базової лінії, одиниці АЦП (0..4095)
const float    ANALOG_ALPHA     = 0.25f;   // згладжування шуму

// ---------- SW-420 ----------
// Модуль дає пачку коротких імпульсів на кожен удар. Пачка = одне спрацювання.
// Чутливість — підстроювальним резистором на модулі.
const uint32_t VIB_GAP_MS       = 150;     // тиша довша за це — пачка закінчилась
const uint8_t  VIB_MIN_EDGES    = 2;       // менше перемикань у пачці — випадкове клацання, не рахується

// ---------- ADXL345 ----------
const uint8_t  ADXL_ADDR        = 0x53;    // SDO на GND; якщо SDO на 3V3 — 0x1D
const float    ADXL_THRESHOLD   = 40.0f;   // поштовх понад стільки мг — спрацювання (див. Serial Plotter)
const float    ADXL_ALPHA       = 0.6f;    // згладжування: удари короткі, тому слабке
const float    ADXL_GRAV_ALPHA  = 0.02f;   // повільна складова (сила тяжіння, нахил), ~0.25 с

// ---------- Радар LD2410C ----------
const uint16_t RADAR_MAX_CM     = 100;     // людина ближче цієї відстані — «стоїть біля дверей»
const uint32_t RADAR_DWELL_MS   = 2000;    // MODE_RADAR / MODE_ANY: скільки має простояти
const uint32_t RADAR_CLEAR_MS   = 3000;    // після паузи спершу біля дверей має нікого не бути
const uint32_t RADAR_EXIT_MS    = 30000;   // після «зачинено» радар мовчить стільки часу — власник іде від дверей
const uint32_t RADAR_RECENT_MS  = 3000;    // MODE_BOTH: людина була поруч не раніше ніж за стільки до ривка
const uint32_t RADAR_GAP_MS     = 600;     // короткі пропадання цілі не переривають «стоїть»
const uint32_t RADAR_SILENT_MS  = 3000;    // немає кадрів довше — радар вважається відключеним, читаємо OUT
const bool     RADAR_CONFIGURE  = true;    // при старті записати в радар дальність і час утримання OUT

const bool     DEBUG_PLOT       = true;    // вивід у Serial Plotter
const uint32_t DEBUG_MS         = 50;

// ---------- Стан ----------
enum State { DISARMED, SETTLING, WATCHING, PLAY_START, PLAYING, COOLDOWN };
State    state = DISARMED;
uint32_t stateSince = 0;

uint8_t  jerkCount = 0;
uint32_t firstJerkAt = 0, lastJerkAt = 0;

bool     armedStable = false;
bool     armedLast = false;
uint32_t armedChangedAt = 0;

// Датчики ривка: кожен лише повідомляє «помітив удар», рішення — у jerkFrom()
enum SensorId { S_SW420, S_ADXL, S_ANALOG, S_COUNT };
uint32_t sensorFiredAt[S_COUNT] = { 0, 0, 0 };
bool     sensorActive[S_COUNT]  = { false, false, false };

// Детектор для аналогових сигналів (Холл і ADXL345): швидке значення, повільна база, поріг
struct Detector {
  float    alpha, thr;
  float    fast = 0, base = 0, dev = 0;
  bool     above = false;
  uint32_t aboveSince = 0;
  Detector(float a, float t) : alpha(a), thr(t) {}
  void reset(float v) { fast = base = v; dev = 0; above = false; }
  // true — у цей момент почався удар
  bool update(float raw, uint32_t now, bool watching) {
    fast += (raw - fast) * alpha;
    dev = fabsf(fast - base);
    if (!watching) {
      base += (fast - base) * BASE_ALPHA_QUICK;
      above = false;
      return false;
    }
    bool started = false;
    if (!above && dev > thr) {
      above = true;
      aboveSince = now;
      started = true;
    } else if (above && dev < thr * 0.5f) {
      above = false;
    } else if (above && now - aboveSince > STUCK_MS) {
      base = fast;                 // сигнал лишився в іншому положенні — це нова база, а не ривок
      above = false;
    }
    if (!above) base += (fast - base) * BASE_ALPHA;
    return started;
  }
};
Detector analogDet(ANALOG_ALPHA, ANALOG_THRESHOLD);
Detector adxlDet(ADXL_ALPHA, ADXL_THRESHOLD);

volatile uint32_t vibEdges = 0;        // перемикання виходу SW-420 (рахує переривання)
volatile uint32_t vibLastEdgeAt = 0;
uint32_t vibEdgesSeen = 0, vibBurstEdges = 0;
bool     vibBurst = false;

bool     adxlPrimed = false;
float    gX = 0, gY = 0, gZ = 0;      // повільна складова прискорення, мг

const bool RADAR_USED = SENSOR_MODE != MODE_JERK;
uint8_t  radarBuf[64];
uint8_t  radarLen = 0;          // скільки байтів поточного кадру прийнято (разом із заголовком)
uint32_t radarFrameAt = 0;      // коли прийшов останній кадр
uint16_t radarDistCm = 0;       // відстань до найближчої цілі, 0 — цілі немає
uint32_t radarSeenAt = 0;       // коли востаннє бачили людину в зоні
bool     present = false;       // людина біля дверей зараз
uint32_t presentSince = 0, absentSince = 0, lastPresentAt = 0;
bool     radarReady = false;    // біля дверей уже було порожньо після «зачинено» / паузи
uint32_t armedAt = 0;           // коли ввімкнули «зачинено»
bool     radarSilentReported = false;

// ---------- MP3 (протокол DFPlayer) ----------
void mp3Command(uint8_t cmd, uint16_t param) {
  uint8_t ph = param >> 8, pl = param & 0xFF;
  uint16_t sum = 0 - (0xFF + 0x06 + cmd + 0x00 + ph + pl);
  uint8_t frame[10] = { 0x7E, 0xFF, 0x06, cmd, 0x00, ph, pl,
                        (uint8_t)(sum >> 8), (uint8_t)(sum & 0xFF), 0xEF };
  mp3Serial.write(frame, sizeof(frame));
}
void mp3SetVolume(uint8_t v)      { mp3Command(0x06, v); }
void mp3PlayMp3Folder(uint16_t n) { mp3Command(0x12, n); }
void mp3Stop()                    { mp3Command(0x16, 0); }
bool mp3Busy()                    { return digitalRead(PIN_MP3_BUSY) == LOW; }

// ---------- Радар LD2410C (протокол HLK) ----------
// Кадр даних: F4 F3 F2 F1 | довжина (2 байти) | тип, AA, стан цілі, відстань руху (2),
// енергія руху, відстань нерухомої цілі (2), енергія, ... | F8 F7 F6 F5. Радар шле ~10 кадрів/с.
void radarParse(const uint8_t *d, uint16_t len, uint32_t now) {
  if (len < 11 || d[1] != 0xAA || (d[0] != 0x01 && d[0] != 0x02)) return;
  uint8_t  st = d[2];                        // 0 — нікого, 1 — рух, 2 — нерухома ціль, 3 — обидві
  uint16_t moving = d[3] | (d[4] << 8);
  uint16_t still  = d[6] | (d[7] << 8);
  uint16_t dist = 0xFFFF;
  if (st & 1) dist = moving;
  if ((st & 2) && still < dist) dist = still;
  radarFrameAt = now;
  radarDistCm = st ? dist : 0;
  if (st && dist <= RADAR_MAX_CM) radarSeenAt = now;
}

void radarPoll(uint32_t now) {
  static const uint8_t HDR[4] = { 0xF4, 0xF3, 0xF2, 0xF1 };
  static const uint8_t END[4] = { 0xF8, 0xF7, 0xF6, 0xF5 };
  while (radarSerial.available()) {
    uint8_t c = radarSerial.read();
    if (radarLen < 4) {                     // шукаємо заголовок
      if (c == HDR[radarLen]) radarLen++;
      else radarLen = (c == HDR[0]) ? 1 : 0;
      continue;
    }
    uint8_t i = radarLen - 4;               // позиція після заголовка
    radarBuf[i] = c;
    radarLen++;
    if (i < 1) continue;
    uint16_t len = radarBuf[0] | (radarBuf[1] << 8);
    if (len + 6 > sizeof(radarBuf)) { radarLen = 0; continue; }   // це не наш кадр
    if (i + 1 < len + 6) continue;
    if (memcmp(radarBuf + 2 + len, END, 4) == 0) radarParse(radarBuf + 2, len, now);
    radarLen = 0;
  }
}

void radarCommand(const uint8_t *data, uint8_t len) {
  static const uint8_t HDR[4] = { 0xFD, 0xFC, 0xFB, 0xFA };
  static const uint8_t END[4] = { 0x04, 0x03, 0x02, 0x01 };
  radarSerial.write(HDR, 4);
  radarSerial.write(len);
  radarSerial.write((uint8_t)0);
  radarSerial.write(data, len);
  radarSerial.write(END, 4);
  radarSerial.flush();
  delay(150);
}

// Записує в радар найбільшу зону (кожна ~0.75 м, допустимо 2..8) і утримання OUT 1 с,
// щоб запасний вихід OUT теж не бачив далеких перехожих. Точну межу RADAR_MAX_CM
// перевіряє сама прошивка за відстанню з кадрів.
void radarConfigure() {
  uint8_t gate = RADAR_MAX_CM / 75;
  if (gate < 2) gate = 2;
  if (gate > 8) gate = 8;
  const uint8_t enable[] = { 0xFF, 0x00, 0x01, 0x00 };
  const uint8_t setup[]  = { 0x60, 0x00,
                             0x00, 0x00, gate, 0, 0, 0,     // найбільша зона руху
                             0x01, 0x00, gate, 0, 0, 0,     // найбільша зона нерухомої цілі
                             0x02, 0x00, 1, 0, 0, 0 };      // утримання OUT, с
  const uint8_t finish[] = { 0xFE, 0x00 };
  radarCommand(enable, sizeof(enable));
  radarCommand(setup, sizeof(setup));
  radarCommand(finish, sizeof(finish));
  while (radarSerial.available()) radarSerial.read();      // відповіді радара не потрібні
  radarLen = 0;
}

void radarUpdate(uint32_t now) {
  radarPoll(now);
  bool uartOk = radarFrameAt && now - radarFrameAt < RADAR_SILENT_MS;
  if (!uartOk) {
    radarDistCm = 0;
    if (digitalRead(PIN_RADAR_OUT) == HIGH) radarSeenAt = now;
    if (!radarSilentReported && now > 10000) {
      radarSilentReported = true;
      Serial.println(F("# Радар не надсилає даних: перевірте клемник РАДАР (TX радара -> PA3) і живлення 5 В. Працюю за OUT."));
    }
  }
  bool p = radarSeenAt && now - radarSeenAt < RADAR_GAP_MS;
  if (p && !present) presentSince = now;
  if (!p && present) absentSince = now;
  if (p) lastPresentAt = now;
  present = p;
}

bool personNearRecently(uint32_t now) {
  return present || (lastPresentAt && now - lastPresentAt < RADAR_RECENT_MS);
}

// ---------- ADXL345 (I2C) ----------
bool adxlWrite(uint8_t reg, uint8_t v) {
  Wire.beginTransmission(ADXL_ADDR);
  Wire.write(reg);
  Wire.write(v);
  return Wire.endTransmission() == 0;
}

bool adxlBegin() {
  Wire.beginTransmission(ADXL_ADDR);
  Wire.write(0x00);                                   // DEVID
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom((int)ADXL_ADDR, 1) != 1 || Wire.read() != 0xE5) return false;
  return adxlWrite(0x2C, 0x0B)       // 200 вимірів/с
      && adxlWrite(0x31, 0x08)       // повна роздільність, ±2 g, 3.9 мг на одиницю
      && adxlWrite(0x2D, 0x08);      // режим вимірювання
}

// Поштовх у мг: наскільки поточне прискорення відхилилось від повільної складової.
float readAdxl() {
  Wire.beginTransmission(ADXL_ADDR);
  Wire.write(0x32);                                   // DATAX0..DATAZ1
  if (Wire.endTransmission(false) != 0 || Wire.requestFrom((int)ADXL_ADDR, 6) != 6) return 0;
  int16_t v[3];
  for (uint8_t i = 0; i < 3; i++) {
    uint8_t lo = Wire.read(), hi = Wire.read();
    v[i] = (int16_t)(lo | (hi << 8));
  }
  float x = v[0] * 3.9f, y = v[1] * 3.9f, z = v[2] * 3.9f;
  if (!adxlPrimed) { gX = x; gY = y; gZ = z; adxlPrimed = true; }
  gX += (x - gX) * ADXL_GRAV_ALPHA;
  gY += (y - gY) * ADXL_GRAV_ALPHA;
  gZ += (z - gZ) * ADXL_GRAV_ALPHA;
  float dx = x - gX, dy = y - gY, dz = z - gZ;
  return sqrtf(dx * dx + dy * dy + dz * dz);
}

// ---------- SW-420 ----------
void onVibration() {
  vibEdges++;
  vibLastEdgeAt = millis();
}

// true — у цей момент почалась пачка імпульсів (удар)
bool vibrationUpdate() {
  uint32_t t = millis();                 // свіжий час: переривання могло прийти після початку loop()
  uint32_t edges = vibEdges;
  uint32_t fresh = edges - vibEdgesSeen;
  vibEdgesSeen = edges;
  if (fresh) {
    vibBurstEdges += fresh;
    if (!vibBurst && vibBurstEdges >= VIB_MIN_EDGES) {
      vibBurst = true;
      return true;
    }
  } else if ((int32_t)(t - vibLastEdgeAt) > (int32_t)VIB_GAP_MS) {   // зі знаком: переривання могло щойно оновити час
    vibBurst = false;
    vibBurstEdges = 0;
  }
  return false;
}

// ---------- Допоміжне ----------
void setState(State s, uint32_t now) {
  state = s;
  stateSince = now;
  if (s == WATCHING || s == SETTLING) {
    jerkCount = 0;
    radarReady = false;
  }
  digitalWrite(PIN_LED, (s == PLAY_START || s == PLAYING) ? LOW : HIGH);  // LED активний низьким
}

void trigger(bool visitor, uint32_t now) {
  Serial.println(visitor ? F("# VISITOR") : F("# CLIENT"));
  mp3PlayMp3Folder(MP3_TRACK);
  setState(PLAY_START, now);
}

// Ривок зараховано. Потрібно JERKS_TO_TRIGGER ривків за JERK_WINDOW_MS.
void registerJerk(uint32_t now) {
  if (jerkCount == 0 || now - firstJerkAt > JERK_WINDOW_MS) {
    jerkCount = 1;
    firstJerkAt = now;
  } else {
    jerkCount++;
  }
  if (jerkCount >= JERKS_TO_TRIGGER && SENSOR_MODE != MODE_RADAR) {
    if (SENSOR_MODE != MODE_BOTH || personNearRecently(now)) {
      trigger(false, now);
    } else {
      Serial.println(F("# Ривки без людини біля дверей — пропускаю"));
      jerkCount = 0;
    }
  }
}

// Датчик id помітив удар. Удари від різних датчиків у межах JERK_MERGE_MS — це один ривок;
// ривок зараховується, коли його помітили JERK_SENSORS_AGREE різних датчиків.
void jerkFrom(SensorId id, uint32_t now) {
  if (state != WATCHING) return;
  sensorFiredAt[id] = now;
  uint8_t active = 0, agree = 0;
  for (uint8_t s = 0; s < S_COUNT; s++) {
    if (!sensorActive[s]) continue;
    active++;
    if (sensorFiredAt[s] && now - sensorFiredAt[s] <= JERK_MERGE_MS) agree++;
  }
  uint8_t need = JERK_SENSORS_AGREE < active ? JERK_SENSORS_AGREE : active;
  if (agree < need) return;
  if (lastJerkAt && now - lastJerkAt <= JERK_MERGE_MS) return;     // цей удар уже зараховано
  lastJerkAt = now;
  registerJerk(now);
}

bool readArmed(uint32_t now) {
  bool raw = digitalRead(PIN_ARMED) == LOW;
  if (raw != armedLast) {
    armedLast = raw;
    armedChangedAt = now;
  } else if (now - armedChangedAt > 50) {
    armedStable = raw;
  }
  return armedStable;
}

void setup() {
  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_LED, HIGH);
  pinMode(PIN_MP3_BUSY, INPUT_PULLUP);
  pinMode(PIN_ARMED, INPUT_PULLUP);
  pinMode(PIN_RADAR_OUT, INPUT_PULLDOWN);   // без радара вхід не «плаває»
  analogReadResolution(12);

  Serial.begin(115200);
  mp3Serial.begin(9600);
  if (RADAR_USED) radarSerial.begin(256000);

  // --- датчики ривка ---
  if (USE_SW420) {
    pinMode(PIN_SW420, INPUT_PULLUP);       // без модуля вхід стоїть на 3.3 В і не дає імпульсів
    attachInterrupt(digitalPinToInterrupt(PIN_SW420), onVibration, CHANGE);
    sensorActive[S_SW420] = true;
  }
  if (USE_ADXL) {
    Wire.setSDA(PIN_SDA);
    Wire.setSCL(PIN_SCL);
    Wire.begin();
    Wire.setClock(400000);
    sensorActive[S_ADXL] = adxlBegin();
    if (sensorActive[S_ADXL]) adxlDet.reset(readAdxl());
  }
  if (USE_ANALOG) {
    sensorActive[S_ANALOG] = true;
    analogDet.reset(analogRead(PIN_ANALOG));
  }

  delay(2500);                 // модуль MP3 ініціалізує картку, радар стартує
  mp3SetVolume(MP3_VOLUME);
  delay(200);
  bool radarFound = false;
  if (RADAR_USED) {
    if (RADAR_CONFIGURE) radarConfigure();
    for (uint32_t t0 = millis(); millis() - t0 < 1500 && !radarFrameAt; delay(10)) radarPoll(millis());
    radarFound = radarFrameAt != 0;
  }

  // --- що знайдено ---
  Serial.print(F("# Датчики:"));
  if (sensorActive[S_SW420])  Serial.print(F(" SW-420 (якщо підключено)"));
  if (sensorActive[S_ADXL])   Serial.print(F(" ADXL345"));
  if (sensorActive[S_ANALOG]) Serial.print(F(" Холл"));
  if (RADAR_USED)             Serial.print(radarFound ? F(" радар") : F(" радар-НЕ-відповідає"));
  Serial.println();
  if (USE_ADXL && !sensorActive[S_ADXL]) Serial.println(F("# ADXL345 не знайдено (клемник ADXL345: SDA->PB4, SCL->PA8; на модулі CS до VCC, SDO до GND)"));
  if (SENSOR_MODE != MODE_RADAR && !sensorActive[S_SW420] && !sensorActive[S_ADXL] && !sensorActive[S_ANALOG])
    Serial.println(F("# Увага: жоден датчик ривка не ввімкнено"));

  armedLast = digitalRead(PIN_ARMED) == LOW;
  armedChangedAt = millis();
}

void loop() {
  static uint32_t lastSample = 0, lastDebug = 0;
  uint32_t now = millis();

  // --- режим «зачинено / відчинено» ---
  bool armed = readArmed(now);
  if (!armed && state != DISARMED) {
    if (state == PLAY_START || state == PLAYING) mp3Stop();
    setState(DISARMED, now);
  } else if (armed && state == DISARMED) {
    armedAt = now;
    setState(SETTLING, now);
  }

  // --- радар ---
  if (RADAR_USED) {
    radarUpdate(now);
    if (state == WATCHING) {
      // спершу: минуло RADAR_EXIT_MS після «зачинено» і біля дверей порожньо 3 с (власник пішов, відвідувач відійшов)
      if (!radarReady && !present && now - absentSince >= RADAR_CLEAR_MS &&
          now - armedAt >= RADAR_EXIT_MS) radarReady = true;
      if ((SENSOR_MODE == MODE_RADAR || SENSOR_MODE == MODE_ANY) &&
          radarReady && present && now - presentSince >= RADAR_DWELL_MS) {
        trigger(true, now);
      }
    }
  }

  // --- датчики ривка ---
  if (sensorActive[S_SW420] && vibrationUpdate()) jerkFrom(S_SW420, millis());
  if (now - lastSample >= SAMPLE_MS) {
    lastSample = now;
    bool watching = state == WATCHING;
    if (sensorActive[S_ADXL] && adxlDet.update(readAdxl(), now, watching)) jerkFrom(S_ADXL, now);
    if (sensorActive[S_ANALOG] && analogDet.update(analogRead(PIN_ANALOG), now, watching)) jerkFrom(S_ANALOG, now);
  }

  // --- переходи за часом ---
  switch (state) {
    case SETTLING:
      if (now - stateSince > SETTLE_MS) setState(WATCHING, now);
      break;
    case PLAY_START:
      if (mp3Busy()) {
        setState(PLAYING, now);
      } else if (now - stateSince > 1500) {
        Serial.println(F("# MP3 не стартував (картка? файл /mp3/0001.mp3? живлення?)"));
        setState(COOLDOWN, now);
      }
      break;
    case PLAYING:
      if (!mp3Busy() || now - stateSince > MAX_PLAY_MS) setState(COOLDOWN, now);
      break;
    case COOLDOWN:
      if (now - stateSince > COOLDOWN_MS) setState(WATCHING, now);
      break;
    default:
      break;
  }

  // --- налагодження: Tools -> Serial Plotter ---
  if (DEBUG_PLOT && now - lastDebug >= DEBUG_MS) {
    lastDebug = now;
    Serial.print(F("state:")); Serial.print((int)state * 10);
    Serial.print(F(",jerks:")); Serial.print(jerkCount * 20);
    if (sensorActive[S_SW420]) {
      Serial.print(F(",vibration:")); Serial.print(vibBurst ? 100 : 0);
    }
    if (sensorActive[S_ADXL]) {
      Serial.print(F(",adxl_mg:"));   Serial.print(adxlDet.dev, 1);
      Serial.print(F(",adxl_thr:"));  Serial.print(ADXL_THRESHOLD, 1);
    }
    if (sensorActive[S_ANALOG]) {
      Serial.print(F(",analog_dev:")); Serial.print(analogDet.dev, 1);
      Serial.print(F(",analog_thr:")); Serial.print(ANALOG_THRESHOLD, 1);
    }
    if (RADAR_USED) {
      Serial.print(F(",radar_cm:")); Serial.print(radarDistCm);
      Serial.print(F(",present:"));  Serial.print(present ? 200 : 0);
    }
    Serial.println();
  }
}
