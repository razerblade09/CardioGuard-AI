#ifndef DISPLAY_MANAGER_H
#define DISPLAY_MANAGER_H

#include <Arduino.h>

#define OLED_WIDTH 128
#define OLED_HEIGHT 64
#define OLED_ADDR 0x3C

struct DisplayState {
  String prediction = "Initializing";
  float confidence = 0.0f;
  int heart_rate = 0;
  bool alert_active = false;
  bool ambulance_dispatched = false;
  bool show_dispatch_overlay = false;
  int battery_pct = 0;
  float battery_voltage = 0.0f;
  bool wifi_connected = false;
  int offline_count = 0;
};

bool displayInit();
void displaySplash(const char *title, const char *subtitle);
void updateDisplay(const DisplayState &state);

#endif // DISPLAY_MANAGER_H
