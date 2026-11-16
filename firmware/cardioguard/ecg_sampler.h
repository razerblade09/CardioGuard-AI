#ifndef ECG_SAMPLER_H
#define ECG_SAMPLER_H

#include <Arduino.h>

// ── Pin Definitions ──────────────────────────────────────────────────────────
#define ECG_PIN 34  // AD8232 analog output (ADC1_CH6 — input only pin)
#define LO_PLUS 32  // Lead-off detection +
#define LO_MINUS 33 // Lead-off detection -

// ── Sampling Parameters ──────────────────────────────────────────────────────
#define SAMPLE_RATE 500                   // Hz — matches cloud model training
#define WINDOW_SIZE 256                   // samples per window (~512ms)
#define SAMPLE_US (1000000 / SAMPLE_RATE) // 2000 µs

void ecgSamplerInit();
bool ecgSamplerIsReady();
bool ecgSamplerGetWindow(uint16_t *dest);

#endif // ECG_SAMPLER_H
