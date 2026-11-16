#ifndef GEO_LOCATOR_H
#define GEO_LOCATOR_H

#include <Arduino.h>

void geoInit();
bool fetchWiFiLocation();
bool isLocationValid();
float getDeviceLatitude();
float getDeviceLongitude();

#endif // GEO_LOCATOR_H
