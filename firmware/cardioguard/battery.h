#ifndef BATTERY_H
#define BATTERY_H

#include <Arduino.h>

#define BAT_ADC_PIN 35 // Battery voltage measurement divider (ADC1_CH7)

void batteryInit();
float getBatteryVoltage();
int getBatteryPercentage();

#endif // BATTERY_H
