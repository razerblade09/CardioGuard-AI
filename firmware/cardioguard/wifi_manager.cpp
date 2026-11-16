#include "wifi_manager.h"
#include "config.h"
#include <WiFi.h>
#include <Preferences.h>
#include <time.h>

// Persists the last-connected AP's channel + BSSID so the next connect can go
// straight to that access point instead of sweeping every channel for the SSID.
static Preferences wifiPrefs;

static void saveWiFiFastInfo() {
  uint8_t *bssid = WiFi.BSSID();
  if (!bssid)
    return;
  wifiPrefs.begin("wifi", false);
  wifiPrefs.putUChar("chan", WiFi.channel());
  wifiPrefs.putBytes("bssid", bssid, 6);
  wifiPrefs.end();
}

void wifiInit() {
  WiFi.mode(WIFI_STA);
  WiFi.persistent(false);
}

bool isWiFiConnected() {
  return WiFi.status() == WL_CONNECTED;
}

bool wifiConnect() {
  if (isWiFiConnected())
    return true;

  WiFi.mode(WIFI_STA);
  WiFi.persistent(false);

  // ── Fast path: reconnect straight to the last-known AP (skips channel scan) ──
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

void syncNTP() {
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
