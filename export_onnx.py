"""
CardioGuard AI - ONNX Export Script
=====================================
Converts best_model.keras → cardioguard_model.onnx
for fast cloud inference via FastAPI.

ONNX runs on CPU without TensorFlow installed,
making it much lighter for cloud deployment.

Usage:
  python export_onnx.py
  python export_onnx.py --model_path ai/best_model.keras
"""

import os
import argparse
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument("--model_path", type=str, default="ai/best_model.keras")
parser.add_argument("--output_dir", type=str, default="ai")
args = parser.parse_args()

OUT_PATH = os.path.join(args.output_dir, "cardioguard_model.onnx")
os.makedirs(args.output_dir, exist_ok=True)

# ─── Step 1: Load the trained Keras model ────────────────────────────────────
print("=" * 60)
print("CardioGuard - ONNX Export")
print("=" * 60)
print(f"\nStep 1: Loading model from {args.model_path} ...")

import tensorflow as tf
model = tf.keras.models.load_model(args.model_path)
model.summary()

# ─── Step 2: Convert to ONNX ─────────────────────────────────────────────────
print("\nStep 2: Converting to ONNX ...")

try:
    import tf2onnx
    import onnx

    # Input signature: batch of 256-sample, 1-channel ECG windows
    input_signature = [
        tf.TensorSpec(shape=(None, 256, 1), dtype=tf.float32, name="ecg_input")
    ]

    onnx_model, _ = tf2onnx.convert.from_keras(
        model,
        input_signature=input_signature,
        opset=13,           # ONNX opset 13 — widely supported
        output_path=OUT_PATH
    )

    size_mb = os.path.getsize(OUT_PATH) / 1_048_576
    print(f"✅ ONNX model saved: {OUT_PATH}  ({size_mb:.1f} MB)")

except ImportError:
    print("tf2onnx not installed. Installing...")
    os.system("pip install tf2onnx onnx -q")
    print("Re-run this script after install completes.")
    exit(1)

# ─── Step 3: Verify ONNX model ───────────────────────────────────────────────
print("\nStep 3: Verifying ONNX model output ...")

try:
    import onnxruntime as ort

    session = ort.InferenceSession(OUT_PATH, providers=["CPUExecutionProvider"])

    # Create a dummy ECG window (sine wave approximating a heartbeat)
    t        = np.linspace(0, 2 * np.pi, 256).astype(np.float32)
    dummy    = (np.sin(t) + 0.1 * np.sin(5 * t)).reshape(1, 256, 1)

    # Keras prediction
    keras_out = model.predict(dummy, verbose=0)[0]

    # ONNX prediction
    onnx_out  = session.run(None, {"ecg_input": dummy})[0][0]

    print("  Keras output :", [f"{v:.4f}" for v in keras_out])
    print("  ONNX  output :", [f"{v:.4f}" for v in onnx_out])

    # Check outputs match within tolerance
    max_diff = np.max(np.abs(keras_out - onnx_out))
    if max_diff < 0.001:
        print(f"  ✅ Outputs match (max diff: {max_diff:.6f}) — model verified!")
    else:
        print(f"  ⚠️  Outputs differ by {max_diff:.4f} — check conversion")

except ImportError:
    print("onnxruntime not installed. Run: pip install onnxruntime")

# ─── Step 4: Single inference timing ─────────────────────────────────────────
print("\nStep 4: Benchmarking inference latency ...")

try:
    import time
    session = ort.InferenceSession(OUT_PATH, providers=["CPUExecutionProvider"])
    dummy   = np.random.randn(1, 256, 1).astype(np.float32)

    # Warm-up
    for _ in range(5):
        session.run(None, {"ecg_input": dummy})

    # Timed runs
    times = []
    for _ in range(100):
        start = time.perf_counter()
        session.run(None, {"ecg_input": dummy})
        times.append((time.perf_counter() - start) * 1000)

    avg_ms = np.mean(times)
    p95_ms = np.percentile(times, 95)
    print(f"  Average inference: {avg_ms:.2f} ms")
    print(f"  P95 inference:     {p95_ms:.2f} ms")
    if avg_ms < 50:
        print(f"  ✅ Well within 200ms cloud target")
    elif avg_ms < 200:
        print(f"  ✅ Within 200ms cloud target")
    else:
        print(f"  ⚠️  Exceeds 200ms target — consider model pruning")

except Exception as e:
    print(f"  Benchmark error: {e}")

# ─── Summary ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("EXPORT COMPLETE")
print("=" * 60)
print(f"  ONNX model : {OUT_PATH}")
print(f"  Next step  : run  python cloud_api.py  to start FastAPI server")
