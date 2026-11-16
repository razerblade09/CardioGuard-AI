#include "geo_locator.h"
#include "config.h"
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

static float s_device_lat = 0.0f;
static float s_device_lng = 0.0f;
static bool s_location_valid = false;

void geoInit() {
  s_device_lat = 0.0f;
  s_device_lng = 0.0f;
  s_location_valid = false;
}

bool isLocationValid() {
  return s_location_valid;
}

float getDeviceLatitude() {
  return s_device_lat;
}

float getDeviceLongitude() {
  return s_device_lng;
}

bool fetchWiFiLocation() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[GEO] WiFi not connected, skipping scan");
    return false;
  }

  // Check if GOOGLE_GEO_KEY is configured
  String apiKey = String(GOOGLE_GEO_KEY);
  if (apiKey == "" || apiKey == "YOUR_GOOGLE_API_KEY_HERE") {
    Serial.println("[GEO] Google API key not set in config.h!");
    return false;
  }

  Serial.println("[GEO] Scanning WiFi networks for triangulation...");
  int n = WiFi.scanNetworks(false, false, false, 150);
  if (n <= 0) {
    Serial.println("[GEO] No nearby WiFi networks found for triangulation");
    return false;
  }

  Serial.printf("[GEO] Found %d networks, constructing Google API request...\n", n);

  // Format request JSON payload (ArduinoJson v6)
  // Limit to top 8 networks to avoid huge payload size & save memory
  StaticJsonDocument<2048> doc;
  JsonArray ap_arr = doc.createNestedArray("wifiAccessPoints");
  int count = 0;

  for (int i = 0; i < n && count < 8; i++) {
    String bssid = WiFi.BSSIDstr(i);
    if (bssid == "00:00:00:00:00:00")
      continue;

    JsonObject ap = ap_arr.createNestedObject();
    ap["macAddress"] = bssid;
    ap["signalStrength"] = WiFi.RSSI(i);
    ap["channel"] = WiFi.channel(i);
    count++;
  }

  WiFi.scanDelete();

  if (count == 0) {
    Serial.println("[GEO] No valid WiFi access points scanned");
    return false;
  }

  String body;
  serializeJson(doc, body);

  WiFiClientSecure client;
  client.setInsecure(); // Disable certificate validation for prototype simplicity
  HTTPClient http;

  String url = "https://www.googleapis.com/geolocation/v1/geolocate?key=" + apiKey;
  if (!http.begin(client, url)) {
    Serial.println("[GEO] HTTPS begin failed");
    return false;
  }

  http.addHeader("Content-Type", "application/json");
  http.setTimeout(10000);

  int code = http.POST(body);
  bool success = false;
  if (code == 200) {
    String resp = http.getString();
    StaticJsonDocument<512> resp_doc;
    if (!deserializeJson(resp_doc, resp)) {
      if (resp_doc.containsKey("location")) {
        s_device_lat = resp_doc["location"]["lat"].as<float>();
        s_device_lng = resp_doc["location"]["lng"].as<float>();
        float accuracy = resp_doc["accuracy"].as<float>();
        s_location_valid = true;
        success = true;
        Serial.printf(
            "[GEO] Google Triangulation: %.6f, %.6f (accuracy: %.1f meters)\n",
            s_device_lat, s_device_lng, accuracy);
      } else {
        Serial.println("[GEO] Google API response missing location object");
      }
    } else {
      Serial.println("[GEO] Failed to parse Google response JSON");
    }
  } else {
    Serial.printf("[GEO] Google API error %d: %s\n", code, http.getString().c_str());
  }
  http.end();
  return success;
}
