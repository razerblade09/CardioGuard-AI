/*
  CardioGuard AI — ESP32 Firmware (WiFi)
  ========================================
  Modular Architecture:
    - config.h               : Credentials & device IDs (local / gitignored)
    - battery.h/.cpp         : Voltage divider ADC & percentage calculation
    - wifi_manager.h/.cpp    : WiFi connection, NVS fast AP reconnect, NTP UTC sync
    - geo_locator.h/.cpp     : Google Geolocation API Wi-Fi triangulation
    - ecg_sampler.h/.cpp     : AD8232 500Hz hardware timer interrupt & buffer
    - display_manager.h/.cpp : SSD1306 OLED UI & emergency alerts
    - cloud_client.h/.cpp    : Cloud API HTTPS transmission & offline buffering

  Hardware:
    - AD8232 ECG Sensor  → GPIO34 (ADC signal out)
    - AD8232 LO+         → GPIO32 (lead-off detection)
    - AD8232 LO-         → GPIO33 (lead-off detection)
    - SSD1306 OLED       → I2C (SDA=21, SCL=22)
    - Battery Sense      → GPIO35 (ADC voltage divider)
*/

#include "config.h"
#include "battery.h"
#include "wifi_manager.h"
#include "geo_locator.h"
#include "ecg_sampler.h"
#include "display_manager.h"
#include "cloud_client.h"

// ── Application State ────────────────────────────────────────────────────────
static DisplayState ui_state;
static unsigned long last_location_ms = 0;
static unsigned long dispatch_trigger_ms = 0;
#define LOCATION_INTERVAL_MS 300000UL // refresh every 5 minutes

// ═══════════════════════════════════════════════════════════════════════════
//  setup()
// ═══════════════════════════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);
  Serial.println("\n=== CardioGuard AI v1.0 (WiFi) ===");

  // Initialize hardware & display
  batteryInit();
  displayInit();
  displaySplash("CardioGuard AI", "Connecting...");

  // Networking & initial synchronization
  wifiInit();
  wifiConnect();
  syncNTP();
  geoInit();
  fetchWiFiLocation();

  // Initialize hardware timer & start 500 Hz sampling
  ecgSamplerInit();
  cloudClientInit();

  Serial.println("[MAIN] System initialized and sampling.");
}

// ═══════════════════════════════════════════════════════════════════════════
//  loop()
// ═══════════════════════════════════════════════════════════════════════════
void loop() {
  if (!ecgSamplerIsReady())
    return;

  // Retrieve 256-sample window from the timer ISR buffer
  uint16_t local_samples[WINDOW_SIZE];
  if (!ecgSamplerGetWindow(local_samples))
    return;

  String ts = getTimestamp();
  bool connected = isWiFiConnected();

  // Periodically refresh geolocation when connected
  if (connected && millis() - last_location_ms > LOCATION_INTERVAL_MS) {
    fetchWiFiLocation();
    last_location_ms = millis();
  }

  // Update battery and connection state for UI
  ui_state.battery_pct = getBatteryPercentage();
  ui_state.battery_voltage = getBatteryVoltage();
  ui_state.wifi_connected = connected;

  bool ok = false;
  if (connected) {
    CloudResponse resp;
    ok = postToCloud(ts.c_str(), local_samples, ui_state.battery_pct,
                     isLocationValid(), getDeviceLatitude(), getDeviceLongitude(),
                     resp);
    if (ok) {
      ui_state.prediction = resp.prediction;
      ui_state.confidence = resp.confidence;
      ui_state.heart_rate = resp.heart_rate;
      ui_state.alert_active = resp.alert_active;

      bool prev_dispatch = ui_state.ambulance_dispatched;
      ui_state.ambulance_dispatched = resp.ambulance_dispatched;
      if (ui_state.ambulance_dispatched && !prev_dispatch) {
        dispatch_trigger_ms = millis();
        ui_state.show_dispatch_overlay = true;
      }
    }
  } else {
    wifiConnect();
  }

  // Handle emergency dispatch overlay 5-second timer
  if (ui_state.show_dispatch_overlay && millis() - dispatch_trigger_ms >= 5000) {
    ui_state.show_dispatch_overlay = false;
  }

  // Buffer window locally if offline or POST failed
  if (!ok) {
    bufferOfflineWindow(ts.c_str(), local_samples);
  }

  // Flush offline queue when WiFi recovers
  if (isWiFiConnected() && getOfflineCount() > 0) {
    flushOfflineQueue(ui_state.battery_pct, isLocationValid(),
                      getDeviceLatitude(), getDeviceLongitude());
  }

  ui_state.offline_count = getOfflineCount();
  updateDisplay(ui_state);
}
