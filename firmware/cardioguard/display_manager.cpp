#include "display_manager.h"
#include <Adafruit_SSD1306.h>
#include <Wire.h>

static Adafruit_SSD1306 display(OLED_WIDTH, OLED_HEIGHT, &Wire, -1);

bool displayInit() {
  Wire.begin();
  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
    Serial.println("[OLED] Allocation failed");
    return false;
  }
  display.clearDisplay();
  display.display();
  return true;
}

void displaySplash(const char *title, const char *subtitle) {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(12, 10);
  display.println(title);
  display.setCursor(24, 28);
  display.println(subtitle);
  display.display();
}

void updateDisplay(const DisplayState &state) {
  if (state.show_dispatch_overlay) {
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

  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);

  if (state.prediction == "Initializing") {
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
  if (state.heart_rate > 0)
    display.printf("%d bpm", state.heart_rate);
  else
    display.print("-- bpm");

  // Battery status (top right, size 1)
  display.setTextSize(1);
  int pct = state.battery_pct;
  display.setCursor(92, 0);
  display.printf("%d%%", pct);
  display.drawRect(114, 1, 10, 6, SSD1306_WHITE);
  if (pct > 0) {
    display.fillRect(115, 2, max(1, (8 * pct) / 100), 4, SSD1306_WHITE);
  }
  display.drawRect(124, 3, 1, 2, SSD1306_WHITE);

  // Draw lightning bolt if charging (v >= 4.18V)
  if (state.battery_voltage >= 4.18f) {
    int lx = 84;
    int ly = 0;
    display.drawLine(lx + 2, ly, lx, ly + 3, SSD1306_WHITE);
    display.drawLine(lx, ly + 3, lx + 3, ly + 3, SSD1306_WHITE);
    display.drawLine(lx + 3, ly + 3, lx + 1, ly + 7, SSD1306_WHITE);
  }

  // Status
  display.setTextSize(1);
  display.setCursor(0, 22);
  if (state.prediction == "Normal")
    display.print("Status:  Normal");
  else if (state.prediction == "Arrhythmia")
    display.print("!! ARRHYTHMIA !!");
  else if (state.prediction == "At-Risk")
    display.print("CAUTION: At-Risk");

  // Confidence
  display.setCursor(0, 34);
  display.printf("Conf: %.0f%%", state.confidence * 100);

  // WiFi status
  display.setCursor(0, 46);
  if (state.wifi_connected)
    display.print("WiFi: Connected");
  else
    display.printf("No WiFi Buf:%d", state.offline_count);

  // Alert / Dispatch bar
  if (state.ambulance_dispatched) {
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
  } else if (state.alert_active) {
    display.fillRect(0, 56, OLED_WIDTH, 8, SSD1306_WHITE);
    display.setTextColor(SSD1306_BLACK);
    display.setCursor(4, 57);
    display.print("ALERT SENT - CALL CLINIC");
    display.setTextColor(SSD1306_WHITE);
  }

  display.display();
}
