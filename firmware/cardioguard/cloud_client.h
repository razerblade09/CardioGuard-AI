#ifndef CLOUD_CLIENT_H
#define CLOUD_CLIENT_H

#include <Arduino.h>
#include "ecg_sampler.h"

#define MAX_OFFLINE 120 // ~60 seconds of data

struct CloudResponse {
  String prediction = "Initializing";
  float confidence = 0.0f;
  int heart_rate = 0;
  bool alert_active = false;
  bool ambulance_dispatched = false;
};

void cloudClientInit();
bool postToCloud(const char *timestamp, const uint16_t *samples, int battery_pct,
                 bool has_loc, float lat, float lng, CloudResponse &resp);
void bufferOfflineWindow(const char *timestamp, const uint16_t *samples);
void flushOfflineQueue(int battery_pct, bool has_loc, float lat, float lng);
int getOfflineCount();

#endif // CLOUD_CLIENT_H
