/*
  CardioGuard AI — ESP32 Firmware (WiFi) — Patient 2 Version
  ==========================================================
  This is the second CardioGuard sketch, dedicated to Patient 2.
  It compiles independently in its own folder for easier deployment.
*/

#include "config.h"
#include <Adafruit_SSD1306.h>
#include <Arduino.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <Preferences.h> // NVS storage for last-known AP (fast reconnect)
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <Wire.h>
#include <time.h> // NTP real-time clock

// ── Pin Definitions ──────────────────────────────────────────────────────────
#define ECG_PIN 34     // AD8232 analog output (ADC1_CH6 — input only pin)
#define LO_PLUS 32     // Lead-off detection +
#define LO_MINUS 33    // Lead-off detection -
#define BAT_ADC_PIN 35 // Battery voltage measurement divider (ADC1_CH7)

// ── Battery Sensing ──────────────────────────────────────────────────────────
float getBatteryVoltage() {
  // Read raw analog ADC value (12-bit, 0-4095)
  int raw = analogRead(BAT_ADC_PIN);
  // Convert to voltage: Lolin D32 has a 100k/100k voltage divider on GPIO35.
  // The voltage is halved, so we multiply by 2.
  // ADC reference voltage is ~3.3V.
  float voltage = (raw / 4095.0) * 3.3 * 2.0;
  // Apply a typical ESP32 ADC non-linearity calibration scale factor (1.05x)
  return voltage * 1.05f;
}

int getBatteryPercentage() {
  float v = getBatteryVoltage();
  if (v >= 4.15f)
    return 100;
  if (v <= 3.20f)
    return 0;
  return (int)((v - 3.20f) / (4.15f - 3.20f) * 100.0f);
}

// ── Sampling ─────────────────────────────────────────────────────────────────
#define SAMPLE_RATE 500                   // Hz — matches cloud model training
#define WINDOW_SIZE 256                   // samples per window (~512ms)
#define SAMPLE_US (1000000 / SAMPLE_RATE) // 2000 µs

// ── OLED ─────────────────────────────────────────────────────────────────────
#define OLED_WIDTH 128
#define OLED_HEIGHT 64
#define OLED_ADDR 0x3C
Adafruit_SSD1306 display(OLED_WIDTH, OLED_HEIGHT, &Wire, -1);

// ── Sampling buffer (filled by timer ISR) ────────────────────────────────────
volatile uint16_t ecg_buf[WINDOW_SIZE];
volatile int buf_idx = 0;
volatile bool buf_ready = false;

hw_timer_t *sample_timer = nullptr;
portMUX_TYPE timer_mux = portMUX_INITIALIZER_UNLOCKED;

// ── Prediction state ─────────────────────────────────────────────────────────
String prediction = "Initializing";
float confidence = 0.0f;
int heart_rate = 0;
bool alert_active = false;
bool ambulance_dispatched = false;
unsigned long dispatch_trigger_ms = 0;
bool show_dispatch_overlay = false;

// ── Location (WiFi-based geolocation, refreshed every 5 min) ─────────────────
float device_lat = 0.0f;
float device_lng = 0.0f;
bool location_valid = false;
unsigned long last_location_ms = 0;
#define LOCATION_INTERVAL_MS 300000UL // refresh every 5 minutes

// ── Offline buffer (stores windows when WiFi drops) ──────────────────────────
#define MAX_OFFLINE 120 // ~60 seconds of data
struct OfflineWindow {
  char ts[25];
  uint16_t samples[WINDOW_SIZE];
};
OfflineWindow offline_buf[MAX_OFFLINE];
int off_head = 0, off_tail = 0, off_count = 0;

// ═══════════════════════════════════════════════════════════════════════════
//  Timer ISR — fires every 2ms, reads AD8232 ADC
// ═══════════════════════════════════════════════════════════════════════════
void IRAM_ATTR onTimer() {
  portENTER_CRITICAL_ISR(&timer_mux);
  if (!buf_ready) {
    // Lead-off: if electrodes detached, insert midpoint (flat line)
    ecg_buf[buf_idx] = (digitalRead(LO_PLUS) || digitalRead(LO_MINUS))
                           ? 2048
                           : (uint16_t)analogRead(ECG_PIN);
    if (++buf_idx >= WINDOW_SIZE) {
      buf_idx = 0;
      buf_ready = true;
    }
  }
  portEXIT_CRITICAL_ISR(&timer_mux);
}

// ═══════════════════════════════════════════════════════════════════════════
//  WiFi helpers
// ═══════════════════════════════════════════════════════════════════════════
// Persists the last-connected AP's channel + BSSID so the next connect can go
// straight to that access point instead of sweeping every channel for the SSID.
Preferences wifiPrefs;

// Remember the current AP (channel + BSSID) for a fast reconnect next time.
void saveWiFiFastInfo() {
  uint8_t *bssid = WiFi.BSSID();
  if (!bssid)
    return;
  wifiPrefs.begin("wifi", false);
  wifiPrefs.putUChar("chan", WiFi.channel());
  wifiPrefs.putBytes("bssid", bssid, 6);
  wifiPrefs.end();
}

bool wifiConnect() {
  if (WiFi.status() == WL_CONNECTED)
    return true;

  WiFi.mode(WIFI_STA);
  WiFi.persistent(false);

  // ── Fast path: reconnect straight to the last-known AP (skips channel scan)
  // ──
  wifiPrefs.begin("wifi", true); // read-only
  uint8_t chan = wifiPrefs.getUChar("chan", 0);
  uint8_t bssid[6];
  size_t got = wifiPrefs.getBytes("bssid", bssid, sizeof(bssid));
  wifiPrefs.end();

  if (chan >= 1 && chan <= 13 && got == 6) {
    Serial.printf("[WiFi] Fast-connecting to %s (saved ch %d) ...\n", WIFI_SSID,
                  chan);
    WiFi.begin(WIFI_SSID, WIFI_PASS, chan, bssid);
    unsigned long tf = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - tf < 4000) {
      delay(100);
      Serial.print(".");
    }
    if (WiFi.status() == WL_CONNECTED) {
      Serial.printf("\n[WiFi] Fast-connected: %s\n",
                    WiFi.localIP().toString().c_str());
      return true;
    }
    Serial.println("\n[WiFi] Saved AP not found — doing a full scan");
    WiFi.disconnect();
  }

  // ── Fallback: normal connect (ESP32 scans all channels for the SSID) ──
  Serial.printf("[WiFi] Connecting to %s ...\n", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  unsigned long t = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t < 10000) {
    delay(250);
    Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[WiFi] Connected: %s\n",
                  WiFi.localIP().toString().c_str());
    saveWiFiFastInfo(); // remember this AP for next time
    return true;
  }
  Serial.println("\n[WiFi] Failed");
  return false;
}

// ═══════════════════════════════════════════════════════════════════════════
//  High-Precision Geolocation — Google Maps Geolocation API (Wi-Fi
//  Triangulation) Accuracy: street/building level (~10-50m) — same as food
//  delivery apps
// ═══════════════════════════════════════════════════════════════════════════
void getWiFiLocation() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[GEO] WiFi not connected, skipping scan");
    return;
  }

  // Check if GOOGLE_GEO_KEY is configured
  String apiKey = String(GOOGLE_GEO_KEY);
  if (apiKey == "" || apiKey == "YOUR_GOOGLE_API_KEY_HERE") {
    Serial.println("[GEO] Google API key not set in config.h!");
    return;
  }

  Serial.println("[GEO] Scanning WiFi networks for triangulation...");
  // WiFi.scanNetworks(async, show_hidden, passive, max_ms_per_channel)
  int n = WiFi.scanNetworks(false, false, false, 150);
  if (n <= 0) {
    Serial.println("[GEO] No nearby WiFi networks found for triangulation");
    return;
  }

  Serial.printf("[GEO] Found %d networks, constructing Google API request...\n",
                n);

  // Format request JSON payload (ArduinoJson v6)
  // Limit to top 8 networks to avoid huge payload size & save memory
  StaticJsonDocument<2048> doc;
  JsonArray ap_arr = doc.createNestedArray("wifiAccessPoints");
  int count = 0;

  for (int i = 0; i < n && count < 8; i++) {
    String bssid = WiFi.BSSIDstr(i);
    // Ignore invalid or empty BSSID
    if (bssid == "00:00:00:00:00:00")
      continue;

    JsonObject ap = ap_arr.createNestedObject();
    ap["macAddress"] = bssid;
    ap["signalStrength"] = WiFi.RSSI(i);
    ap["channel"] = WiFi.channel(i);
    count++;
  }

  // Clear scan results to free RAM
  WiFi.scanDelete();

  if (count == 0) {
    Serial.println("[GEO] No valid WiFi access points scanned");
    return;
  }

  String body;
  serializeJson(doc, body);

  // HTTPS POST to Google Geolocation API
  WiFiClientSecure client;
  client
      .setInsecure(); // Disable certificate validation for prototype simplicity
  HTTPClient http;

  String url =
      "https://www.googleapis.com/geolocation/v1/geolocate?key=" + apiKey;
  if (!http.begin(client, url)) {
    Serial.println("[GEO] HTTPS begin failed");
    return;
  }

  http.addHeader("Content-Type", "application/json");
  http.setTimeout(10000);

  int code = http.POST(body);
  if (code == 200) {
    String resp = http.getString();
    StaticJsonDocument<512> resp_doc;
    if (!deserializeJson(resp_doc, resp)) {
      if (resp_doc.containsKey("location")) {
        device_lat = resp_doc["location"]["lat"].as<float>();
        device_lng = resp_doc["location"]["lng"].as<float>();
        float accuracy = resp_doc["accuracy"].as<float>();
        location_valid = true;
        Serial.printf(
            "[GEO] Google Triangulation: %.6f, %.6f (accuracy: %.1f meters)\n",
            device_lat, device_lng, accuracy);
      } else {
        Serial.println("[GEO] Google API response missing location object");
      }
    } else {
      Serial.println("[GEO] Failed to parse Google response JSON");
    }
  } else {
    Serial.printf("[GEO] Google API error %d: %s\n", code,
                  http.getString().c_str());
  }
  http.end();
}

// ═══════════════════════════════════════════════════════════════════════════
//  HTTPS POST to cloud_api.py /analyze
// ═══════════════════════════════════════════════════════════════════════════
bool postToCloud(const char *timestamp, uint16_t *samples) {
  if (WiFi.status() != WL_CONNECTED)
    return false;

  // Build JSON payload inline (ArduinoJson)
  StaticJsonDocument<3072> doc;
  doc["device_id"] = DEVICE_ID;
  doc["patient_id"] = PATIENT_ID;
  doc["timestamp"] = timestamp;
  doc["battery"] = getBatteryPercentage();
  if (location_valid) {
    doc["lat"] = serialized(String(device_lat, 6));
    doc["lng"] = serialized(String(device_lng, 6));
  }
  JsonArray arr = doc.createNestedArray("samples");
  for (int i = 0; i < WINDOW_SIZE; i++)
    arr.add(samples[i]);

  String body;
  serializeJson(doc, body);

  // HTTPS client — skip cert validation for prototype (add cert in production)
  WiFiClientSecure client;
  client.setInsecure(); // TODO: set root CA cert for production
  HTTPClient http;

  String url = String(CLOUD_API_URL) + "/analyze";
  if (!http.begin(client, url)) {
    Serial.println("[HTTP] begin failed");
    return false;
  }

  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Key", DEVICE_KEY);
  http.setTimeout(5000);

  int code = http.POST(body);
  if (code != 200) {
    Serial.printf("[HTTP] POST failed: %d\n", code);
    http.end();
    return false;
  }

  // Parse response
  String resp = http.getString();
  http.end();

  StaticJsonDocument<256> resp_doc;
  if (!deserializeJson(resp_doc, resp)) {
    prediction = resp_doc["prediction"].as<String>();
    confidence = resp_doc["confidence"].as<float>();
    heart_rate = resp_doc["heart_rate_bpm"] | 0;
    alert_active = resp_doc["alert_sent"].as<bool>();

    bool prev_dispatched = ambulance_dispatched;
    ambulance_dispatched = resp_doc["ambulance_dispatched"] | false;
    if (ambulance_dispatched && !prev_dispatched) {
      dispatch_trigger_ms = millis();
      show_dispatch_overlay = true;
    }

    Serial.printf("[AI] %s (%.0f%%) HR:%d alert:%s disp:%s\n",
                  prediction.c_str(), confidence * 100, heart_rate,
                  alert_active ? "YES" : "no",
                  ambulance_dispatched ? "YES" : "no");
  }
  return true;
}

// ═══════════════════════════════════════════════════════════════════════════
//  OLED Display
// ═══════════════════════════════════════════════════════════════════════════
void updateOLED() {
  if (show_dispatch_overlay) {
    if (millis() - dispatch_trigger_ms >= 5000) {
      show_dispatch_overlay = false;
    } else {
      display.clearDisplay();
      display.setTextColor(SSD1306_WHITE);
      display.setTextSize(1);
      display.setCursor(16, 4);
      display.println("=== EMERGENCY ===");
      display.setTextSize(2);
      display.setCursor(10, 18);
      display.println("AMBULANCE");
      display.setCursor(6, 36);
      display.println("DISPATCHED");
      display.setTextSize(1);
      display.setCursor(8, 54);
      display.println("Please remain calm!");
      display.display();
      return;
    }
  }

  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);

  if (prediction == "Initializing") {
    display.setTextSize(1);
    display.setCursor(12, 10);
    display.println("CardioGuard AI");
    display.setCursor(28, 28);
    display.println("Starting...");
    display.display();
    return;
  }

  // Heart rate (large)
  display.setTextSize(2);
  display.setCursor(0, 0);
  if (heart_rate > 0)
    display.printf("%d bpm", heart_rate);
  else
    display.print("-- bpm");

  // Battery status (top right, size 1)
  display.setTextSize(1);
  int pct = getBatteryPercentage();
  display.setCursor(92, 0);
  display.printf("%d%%", pct);
  display.drawRect(114, 1, 10, 6, SSD1306_WHITE);
  if (pct > 0) {
    display.fillRect(115, 2, max(1, (8 * pct) / 100), 4, SSD1306_WHITE);
  }
  display.drawRect(124, 3, 1, 2, SSD1306_WHITE);

  // Draw lightning bolt if charging (v >= 4.18V)
  if (getBatteryVoltage() >= 4.18f) {
    int lx = 84;
    int ly = 0;
    display.drawLine(lx + 2, ly, lx, ly + 3, SSD1306_WHITE);
    display.drawLine(lx, ly + 3, lx + 3, ly + 3, SSD1306_WHITE);
    display.drawLine(lx + 3, ly + 3, lx + 1, ly + 7, SSD1306_WHITE);
  }

  // Status
  display.setTextSize(1);
  display.setCursor(0, 22);
  if (prediction == "Normal")
    display.print("Status:  Normal");
  else if (prediction == "Arrhythmia")
    display.print("!! ARRHYTHMIA !!");
  else if (prediction == "At-Risk")
    display.print("CAUTION: At-Risk");

  // Confidence
  display.setCursor(0, 34);
  display.printf("Conf: %.0f%%", confidence * 100);

  // WiFi status
  display.setCursor(0, 46);
  if (WiFi.status() == WL_CONNECTED)
    display.print("WiFi: Connected");
  else
    display.printf("No WiFi Buf:%d", off_count);

  // Alert / Dispatch bar
  if (ambulance_dispatched) {
    bool flash = (millis() / 1000) % 2 == 0;
    display.fillRect(0, 56, OLED_WIDTH, 8, SSD1306_WHITE);
    display.setTextColor(SSD1306_BLACK);
    display.setCursor(2, 57);
    if (flash) {
      display.print("<< AMBULANCE EN ROUTE >>");
    } else {
      display.print("** HELP IS ON THE WAY **");
    }
    display.setTextColor(SSD1306_WHITE);
  } else if (alert_active) {
    display.fillRect(0, 56, OLED_WIDTH, 8, SSD1306_WHITE);
    display.setTextColor(SSD1306_BLACK);
    display.setCursor(4, 57);
    display.print("ALERT SENT - CALL CLINIC");
    display.setTextColor(SSD1306_WHITE);
  }

  display.display();
}

// ═══════════════════════════════════════════════════════════════════════════
//  Timestamp — NTP synced real UTC time
// ═══════════════════════════════════════════════════════════════════════════
void syncNTP() {
  // NTP servers — uses pool + Google as fallback
  configTime(0, 0, "pool.ntp.org", "time.google.com");
  Serial.print("[NTP] Syncing time");
  struct tm timeinfo;
  unsigned long start = millis();
  while (!getLocalTime(&timeinfo) && millis() - start < 10000) {
    delay(500);
    Serial.print(".");
  }
  if (getLocalTime(&timeinfo)) {
    Serial.printf("\n[NTP] Time synced: %04d-%02d-%02dT%02d:%02d:%02dZ\n",
                  timeinfo.tm_year + 1900, timeinfo.tm_mon + 1,
                  timeinfo.tm_mday, timeinfo.tm_hour, timeinfo.tm_min,
                  timeinfo.tm_sec);
  } else {
    Serial.println("\n[NTP] Sync failed — timestamps will be approximate");
  }
}

String getTimestamp() {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) {
    // Fallback: relative time from boot if NTP not available
    unsigned long s = millis() / 1000;
    char buf[30];
    snprintf(buf, sizeof(buf), "1970-01-01T%02lu:%02lu:%02luZ", (s / 3600) % 24,
             (s / 60) % 60, s % 60);
    return String(buf);
  }
  char buf[25];
  snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02dZ",
           timeinfo.tm_year + 1900, timeinfo.tm_mon + 1, timeinfo.tm_mday,
           timeinfo.tm_hour, timeinfo.tm_min, timeinfo.tm_sec);
  return String(buf);
}

// ═══════════════════════════════════════════════════════════════════════════
//  setup()
// ═══════════════════════════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);
  Serial.println("\n=== CardioGuard AI v1.0 (WiFi) ===");

  // ADC + lead-off pins
  pinMode(LO_PLUS, INPUT);
  pinMode(LO_MINUS, INPUT);
  pinMode(BAT_ADC_PIN, INPUT);
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);

  // OLED
  Wire.begin();
  if (display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(12, 10);
    display.println("CardioGuard AI");
    display.setCursor(24, 28);
    display.println("Connecting...");
    display.display();
  }

  // WiFi + NTP + Location
  wifiConnect();
  syncNTP();         // real UTC timestamps
  getWiFiLocation(); // initial location fix

  // 500 Hz sampling timer
  sample_timer = timerBegin(1000000); // 1 MHz → 1 tick = 1 µs
  timerAttachInterrupt(sample_timer, &onTimer);
  timerAlarm(sample_timer, SAMPLE_US, true, 0); // fires every 2000 µs = 500 Hz
  Serial.println("[MAIN] Sampling at 500 Hz");
}

// ═══════════════════════════════════════════════════════════════════════════
//  loop()
// ═══════════════════════════════════════════════════════════════════════════
void loop() {
  if (!buf_ready)
    return;

  // Copy buffer safely
  uint16_t local_buf[WINDOW_SIZE];
  portENTER_CRITICAL(&timer_mux);
  memcpy(local_buf, (void *)ecg_buf, WINDOW_SIZE * sizeof(uint16_t));
  buf_ready = false;
  portEXIT_CRITICAL(&timer_mux);

  String ts = getTimestamp();
  bool ok = false;

  // Refresh location every 5 minutes
  if (WiFi.status() == WL_CONNECTED &&
      millis() - last_location_ms > LOCATION_INTERVAL_MS) {
    getWiFiLocation();
    last_location_ms = millis();
  }

  // Try to send to cloud
  if (WiFi.status() == WL_CONNECTED) {
    ok = postToCloud(ts.c_str(), local_buf);
  } else {
    wifiConnect();
  }

  // Buffer window locally if offline
  if (!ok && off_count < MAX_OFFLINE) {
    strlcpy(offline_buf[off_tail].ts, ts.c_str(), 25);
    memcpy(offline_buf[off_tail].samples, local_buf,
           WINDOW_SIZE * sizeof(uint16_t));
    off_tail = (off_tail + 1) % MAX_OFFLINE;
    off_count++;
  }

  // Flush offline buffer when WiFi recovers
  while (off_count > 0 && WiFi.status() == WL_CONNECTED) {
    OfflineWindow &w = offline_buf[off_head];
    if (!postToCloud(w.ts, w.samples))
      break;
    off_head = (off_head + 1) % MAX_OFFLINE;
    off_count--;
  }

  updateOLED();
}
