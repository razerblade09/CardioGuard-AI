"""
CardioGuard AI - ECG Preprocessing Pipeline
============================================
Reads MIT-BIH Arrhythmia Database, filters signals, segments into
256-sample windows, maps labels, and saves ready-to-train .npy arrays.

Output:
  data/processed/X.npy   — shape (N, 256, 1)  float32
  data/processed/y.npy   — shape (N,)          int8
  data/processed/info.txt — class counts and dataset stats

Classes:
  0 = Normal
  1 = Arrhythmia
  2 = At-Risk

Usage:
  .venv\Scripts\python.exe preprocess.py
"""

import os
import numpy as np
import wfdb
from scipy.signal import butter, filtfilt, iirnotch, resample_poly
from collections import Counter

# ─── Config ──────────────────────────────────────────────────────────────────
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
MITBIH_DIR    = os.path.join(BASE_DIR, "data", "mitbih")
OUT_DIR       = os.path.join(BASE_DIR, "data", "processed")
os.makedirs(OUT_DIR, exist_ok=True)

WINDOW_SIZE   = 256       # samples per segment
ORIGINAL_FS   = 360       # MIT-BIH sampling rate (Hz)
TARGET_FS     = 500       # CardioGuard device sampling rate (Hz)
LEAD          = 0         # Lead index: 0 = MLII (primary lead in MIT-BIH)

# Beat label → CardioGuard class mapping
LABEL_MAP = {
    # Class 0: Normal
    "N": 0, "L": 0, "R": 0, "e": 0, "j": 0,
    # Class 1: Arrhythmia (requires urgent alert)
    "A": 1, "a": 1, "J": 1, "S": 1,
    "V": 1, "E": 1, "F": 1,
    # Class 2: At-Risk (requires warning alert)
    "/": 2, "f": 2, "Q": 2,
}

# All 48 MIT-BIH record names
ALL_RECORDS = [
    "100","101","102","103","104","105","106","107","108","109",
    "111","112","113","114","115","116","117","118","119",
    "121","122","123","124",
    "200","201","202","203","205","207","208","209","210",
    "212","213","214","215","217","219","220","221","222","223",
    "228","230","231","232","233","234",
]

# ─── Filters ─────────────────────────────────────────────────────────────────
def bandpass_filter(signal, lowcut=0.5, highcut=100.0, fs=TARGET_FS):
    """Remove baseline wander (< 0.5 Hz) and high-freq noise (> 100 Hz)."""
    nyq = fs / 2.0
    b, a = butter(4, [lowcut / nyq, highcut / nyq], btype="band")
    return filtfilt(b, a, signal)

def notch_filter(signal, freq=60.0, fs=TARGET_FS, quality=30):
    """Remove power line interference (60 Hz hum)."""
    b, a = iirnotch(freq / (fs / 2.0), quality)
    return filtfilt(b, a, signal)

def normalize(segment):
    """Zero mean, unit variance normalization per window."""
    mean = np.mean(segment)
    std  = np.std(segment)
    return (segment - mean) / (std + 1e-8)

# ─── Resample ─────────────────────────────────────────────────────────────────
from math import gcd
def resample_signal(signal, orig_fs=ORIGINAL_FS, target_fs=TARGET_FS):
    """Resample using integer ratio (lossless quality)."""
    g  = gcd(target_fs, orig_fs)
    up = target_fs // g
    dn = orig_fs  // g
    return resample_poly(signal, up, dn).astype(np.float32)

# ─── Main pipeline ────────────────────────────────────────────────────────────
print("=" * 60)
print("CardioGuard - ECG Preprocessing Pipeline")
print("=" * 60)
print(f"Input  : {MITBIH_DIR}")
print(f"Output : {OUT_DIR}")
print(f"Target : {TARGET_FS} Hz | Window: {WINDOW_SIZE} samples ({WINDOW_SIZE/TARGET_FS*1000:.0f} ms)")
print()

all_segments = []
all_labels   = []
all_groups   = []   # source record name per window (for inter-patient split)
skipped_beats = 0
unknown_labels = Counter()

for rec_name in ALL_RECORDS:
    rec_path = os.path.join(MITBIH_DIR, rec_name)

    try:
        record  = wfdb.rdrecord(rec_path)
        annots  = wfdb.rdann(rec_path, "atr")
    except Exception as e:
        print(f"  [WARN] Could not read {rec_name}: {e}")
        continue

    # Use MLII lead (Lead 0); fall back to lead 1 if needed
    raw_signal = record.p_signal[:, LEAD].astype(np.float32)

    # 1. Resample 360 Hz → 500 Hz
    signal = resample_signal(raw_signal, ORIGINAL_FS, TARGET_FS)

    # 2. Filter
    signal = bandpass_filter(signal)
    signal = notch_filter(signal)

    # Scale annotation sample indices to match new sampling rate
    scale = TARGET_FS / ORIGINAL_FS
    scaled_samples = (annots.sample * scale).astype(int)

    # 3. Segment around each annotated beat
    seg_count = 0
    for idx, symbol in zip(scaled_samples, annots.symbol):
        # Map label
        label = LABEL_MAP.get(symbol, -1)
        if label == -1:
            unknown_labels[symbol] += 1
            skipped_beats += 1
            continue

        # Extract window centred on beat
        half  = WINDOW_SIZE // 2
        start = idx - half
        end   = idx + half

        if start < 0 or end > len(signal):
            skipped_beats += 1
            continue

        window = signal[start:end]

        # Sanity check — reject flat lines (bad electrode contact)
        if np.std(window) < 1e-4:
            skipped_beats += 1
            continue

        # 4. Normalize
        window = normalize(window)

        all_segments.append(window)
        all_labels.append(label)
        all_groups.append(rec_name)   # remember which patient/record this came from
        seg_count += 1

    print(f"  [OK] {rec_name}: {seg_count} windows")

# ─── Save ─────────────────────────────────────────────────────────────────────
X = np.array(all_segments, dtype=np.float32).reshape(-1, WINDOW_SIZE, 1)
y = np.array(all_labels,   dtype=np.int8)
groups = np.array(all_groups)   # record name per window (dtype '<U3')

np.save(os.path.join(OUT_DIR, "X.npy"), X)
np.save(os.path.join(OUT_DIR, "y.npy"), y)
np.save(os.path.join(OUT_DIR, "groups.npy"), groups)

# ─── Report ───────────────────────────────────────────────────────────────────
class_names  = {0: "Normal", 1: "Arrhythmia", 2: "At-Risk"}
class_counts = Counter(y.tolist())
total        = len(y)

report = []
report.append("=" * 60)
report.append("PREPROCESSING COMPLETE")
report.append("=" * 60)
report.append(f"Total windows saved : {total:,}")
report.append(f"Skipped beats       : {skipped_beats:,}")
report.append("")
report.append("Class distribution:")
for cls in [0, 1, 2]:
    n   = class_counts[cls]
    pct = n / total * 100
    report.append(f"  [{cls}] {class_names[cls]:<12}: {n:>6,}  ({pct:.1f}%)")
report.append("")
report.append("Array shapes:")
report.append(f"  X: {X.shape}  dtype={X.dtype}")
report.append(f"  y: {y.shape}  dtype={y.dtype}")
if unknown_labels:
    report.append("")
    report.append(f"Unknown/skipped symbols: {dict(unknown_labels)}")
report.append("=" * 60)

report_str = "\n".join(report)
print("\n" + report_str)

with open(os.path.join(OUT_DIR, "info.txt"), "w") as f:
    f.write(report_str)

print(f"\n✅ Saved to {OUT_DIR}")
print("   X.npy      — ECG windows (features)")
print("   y.npy      — Labels (0=Normal, 1=Arrhythmia, 2=At-Risk)")
print("   groups.npy — Source record per window (for inter-patient split)")
print("   info.txt   — Dataset statistics")
print("\nNext step: run  train.py")
