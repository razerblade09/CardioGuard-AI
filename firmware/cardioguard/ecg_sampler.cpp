#include "ecg_sampler.h"

// ── Sampling buffer (filled by timer ISR) ────────────────────────────────────
static volatile uint16_t ecg_buf[WINDOW_SIZE];
static volatile int buf_idx = 0;
static volatile bool buf_ready = false;

static hw_timer_t *sample_timer = nullptr;
static portMUX_TYPE timer_mux = portMUX_INITIALIZER_UNLOCKED;

// ═══════════════════════════════════════════════════════════════════════════
//  Timer ISR — fires every 2ms, reads AD8232 ADC
// ═══════════════════════════════════════════════════════════════════════════
static void IRAM_ATTR onTimer() {
  portENTER_CRITICAL_ISR(&timer_mux);
  if (!buf_ready) {
    // Lead-off: if electrodes detached, insert midpoint (flat line)
    ecg_buf[buf_idx] = (digitalRead(LO_PLUS) || digitalRead(LO_MINUS))
                           ? 2048
                           : (uint16_t)analogRead(ECG_PIN);
    if (++buf_idx >= WINDOW_SIZE) {
      buf_idx = 0;
      buf_ready = true;
    }
  }
  portEXIT_CRITICAL_ISR(&timer_mux);
}

void ecgSamplerInit() {
  pinMode(LO_PLUS, INPUT);
  pinMode(LO_MINUS, INPUT);
  pinMode(ECG_PIN, INPUT);
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);

  // 500 Hz sampling timer
  sample_timer = timerBegin(1000000); // 1 MHz → 1 tick = 1 µs
  timerAttachInterrupt(sample_timer, &onTimer);
  timerAlarm(sample_timer, SAMPLE_US, true, 0); // fires every 2000 µs = 500 Hz
  Serial.println("[ECG] Sampling at 500 Hz");
}

bool ecgSamplerIsReady() {
  return buf_ready;
}

bool ecgSamplerGetWindow(uint16_t *dest) {
  if (!buf_ready || !dest)
    return false;

  portENTER_CRITICAL(&timer_mux);
  memcpy(dest, (const void *)ecg_buf, WINDOW_SIZE * sizeof(uint16_t));
  buf_ready = false;
  portEXIT_CRITICAL(&timer_mux);
  return true;
}
