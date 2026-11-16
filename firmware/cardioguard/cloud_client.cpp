#include "cloud_client.h"
#include "config.h"
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

struct OfflineWindow {
  char ts[25];
  uint16_t samples[WINDOW_SIZE];
};

static OfflineWindow offline_buf[MAX_OFFLINE];
static int off_head = 0;
static int off_tail = 0;
static int off_count = 0;

void cloudClientInit() {
  off_head = 0;
  off_tail = 0;
  off_count = 0;
}

int getOfflineCount() {
  return off_count;
}

void bufferOfflineWindow(const char *timestamp, const uint16_t *samples) {
  if (off_count >= MAX_OFFLINE)
    return;
  strlcpy(offline_buf[off_tail].ts, timestamp, sizeof(offline_buf[off_tail].ts));
  memcpy(offline_buf[off_tail].samples, samples, WINDOW_SIZE * sizeof(uint16_t));
  off_tail = (off_tail + 1) % MAX_OFFLINE;
  off_count++;
}

bool postToCloud(const char *timestamp, const uint16_t *samples, int battery_pct,
                 bool has_loc, float lat, float lng, CloudResponse &resp) {
  if (WiFi.status() != WL_CONNECTED)
    return false;

  // Build JSON payload inline (ArduinoJson)
  StaticJsonDocument<3072> doc;
  doc["device_id"] = DEVICE_ID;
  doc["patient_id"] = PATIENT_ID;
  doc["timestamp"] = timestamp;
  doc["battery"] = battery_pct;
  if (has_loc) {
    doc["lat"] = serialized(String(lat, 6));
    doc["lng"] = serialized(String(lng, 6));
  }
  JsonArray arr = doc.createNestedArray("samples");
  for (int i = 0; i < WINDOW_SIZE; i++)
    arr.add(samples[i]);

  String body;
  serializeJson(doc, body);

  WiFiClientSecure client;
  client.setInsecure(); // Disable cert validation for prototype
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

  String responseStr = http.getString();
  http.end();

  StaticJsonDocument<256> resp_doc;
  if (!deserializeJson(resp_doc, responseStr)) {
    resp.prediction = resp_doc["prediction"].as<String>();
    resp.confidence = resp_doc["confidence"].as<float>();
    resp.heart_rate = resp_doc["heart_rate_bpm"] | 0;
    resp.alert_active = resp_doc["alert_sent"].as<bool>();
    resp.ambulance_dispatched = resp_doc["ambulance_dispatched"] | false;

    Serial.printf("[AI] %s (%.0f%%) HR:%d alert:%s disp:%s\n",
                  resp.prediction.c_str(), resp.confidence * 100,
                  resp.heart_rate, resp.alert_active ? "YES" : "no",
                  resp.ambulance_dispatched ? "YES" : "no");
  }
  return true;
}

void flushOfflineQueue(int battery_pct, bool has_loc, float lat, float lng) {
  while (off_count > 0 && WiFi.status() == WL_CONNECTED) {
    OfflineWindow &w = offline_buf[off_head];
    CloudResponse dummy;
    if (!postToCloud(w.ts, w.samples, battery_pct, has_loc, lat, lng, dummy))
      break;
    off_head = (off_head + 1) % MAX_OFFLINE;
    off_count--;
  }
}
