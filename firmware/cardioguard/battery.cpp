#include "battery.h"

void batteryInit() {
  pinMode(BAT_ADC_PIN, INPUT);
}

float getBatteryVoltage() {
  // Read raw analog ADC value (12-bit, 0-4095)
  int raw = analogRead(BAT_ADC_PIN);
  // Convert to voltage: Lolin D32 has a 100k/100k voltage divider on GPIO35.
  // The voltage is halved, so we multiply by 2. ADC reference is ~3.3V.
  float voltage = (raw / 4095.0f) * 3.3f * 2.0f;
  // Apply a typical ESP32 ADC non-linearity calibration scale factor (1.05x)
  return voltage * 1.05f;
}

int getBatteryPercentage() {
  float v = getBatteryVoltage();
  if (v >= 4.15f) return 100;
  if (v <= 3.20f) return 0;
  return (int)((v - 3.20f) / (4.15f - 3.20f) * 100.0f);
}
