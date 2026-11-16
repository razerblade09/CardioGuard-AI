#ifndef WIFI_MANAGER_H
#define WIFI_MANAGER_H

#include <Arduino.h>

void wifiInit();
bool wifiConnect();
bool isWiFiConnected();
void syncNTP();
String getTimestamp();

#endif // WIFI_MANAGER_H
