"""
CardioGuard AI - CNN-LSTM Training Script
==========================================
Trains a CNN-LSTM hybrid model on preprocessed MIT-BIH ECG windows.

Input:
  data/processed/X.npy  — shape (N, 256, 1)  float32
  data/processed/y.npy  — shape (N,)          int8

Output:
  models/best_model.keras      — best checkpoint
  models/history.json          — training curves
  models/evaluation.txt        — classification report
  models/plots/training_curves.png
  models/plots/confusion_matrix.png

Usage:
  python train.py                    # local CPU (slow)
  python train.py --epochs 50        # fewer epochs for quick test

Google Colab usage:
  Upload X.npy, y.npy, and train.py
  Runtime → Change runtime type → GPU (T4)
  !python train.py
"""

import os
import sys
import json
import argparse
import numpy as np
import warnings
warnings.filterwarnings("ignore")

# ─── Args ────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--epochs",     type=int, default=100)
parser.add_argument("--batch",      type=int, default=64)
parser.add_argument("--lr",         type=float, default=0.001)
parser.add_argument("--data_dir",   type=str, default="data/processed")
parser.add_argument("--output_dir", type=str, default="models")
args = parser.parse_args()

os.makedirs(args.output_dir, exist_ok=True)
os.makedirs(os.path.join(args.output_dir, "plots"), exist_ok=True)

# ─── GPU check ───────────────────────────────────────────────────────────────
import tensorflow as tf

gpus = tf.config.list_physical_devices("GPU")
if gpus:
    print(f"✅ GPU detected: {[g.name for g in gpus]}")
    for gpu in gpus:
        tf.config.experimental.set_memory_growth(gpu, True)
else:
    print("⚠️  No GPU detected — running on CPU.")
    print("   Estimated training time: 4–8 hours for 100 epochs.")
    print("   Recommended: upload X.npy, y.npy, train.py to Google Colab")
    print("   and enable GPU (Runtime → Change runtime type → T4 GPU)\n")

CLASS_NAMES = ["Normal", "Arrhythmia", "At-Risk"]

# ─── 1. Load data ────────────────────────────────────────────────────────────
print("=" * 60)
print("Step 1: Loading preprocessed data")
print("=" * 60)

X = np.load(os.path.join(args.data_dir, "X.npy"))
y = np.load(os.path.join(args.data_dir, "y.npy")).astype(np.int32)

print(f"  X shape: {X.shape}  dtype: {X.dtype}")
print(f"  y shape: {y.shape}  dtype: {y.dtype}")

from collections import Counter
counts = Counter(y.tolist())
total  = len(y)
print("\n  Class distribution:")
for cls, name in enumerate(CLASS_NAMES):
    n = counts[cls]
    print(f"    [{cls}] {name:<12}: {n:>6,}  ({n/total*100:.1f}%)")

# ─── 2. Inter-patient split (BEFORE any balancing) ────────────────────────────
# Split by RECORD, not by beat: no patient appears in more than one set.
# This prevents intra-patient data leakage (the ANSI/AAMI-recommended paradigm)
# and gives an honest estimate of performance on unseen patients.
print("\n" + "=" * 60)
print("Step 2: Inter-patient 70 / 15 / 15 split (by record)")
print("=" * 60)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from split_utils import load_groups, split_by_record

groups = load_groups(args.data_dir)
train_idx, val_idx, test_idx = split_by_record(y, groups, seed=42)

X_train, y_train = X[train_idx], y[train_idx]
X_val,   y_val   = X[val_idx],   y[val_idx]
X_test,  y_test  = X[test_idx],  y[test_idx]

print(f"  Train : {len(X_train):,} samples")
print(f"  Val   : {len(X_val):,} samples")
print(f"  Test  : {len(X_test):,} samples")

# ─── 2b. Augment minority classes (noise + re-normalize) ──────────────────────
# Oversampling the minority classes with lightly noised, re-normalized copies
# (a) adds morphological variety that improves cross-patient generalization and
# (b) rebalances the training set so gentler class weights suffice — which fixes
# the arrhythmia over-prediction (false alarms) seen with aggressive weighting.
# Validation and test sets are NEVER augmented.
def _augment(Xc):
    Xa = Xc + np.random.normal(0, 0.03, Xc.shape).astype(np.float32)
    m = Xa.mean(1, keepdims=True); s = Xa.std(1, keepdims=True) + 1e-8
    return ((Xa - m) / s).astype(np.float32)

_rng = np.random.default_rng(42)
_Xp, _yp = [X_train], [y_train]
for _cls, _copies in [(1, 3), (2, 4)]:          # Arrhythmia x3, At-Risk x4
    _Xc = X_train[y_train == _cls]
    for _ in range(_copies):
        _Xp.append(_augment(_Xc))
        _yp.append(np.full(len(_Xc), _cls, dtype=y_train.dtype))
X_train = np.concatenate(_Xp); y_train = np.concatenate(_yp)
_perm = _rng.permutation(len(y_train)); X_train, y_train = X_train[_perm], y_train[_perm]
_aug_counts = {c: int((y_train == c).sum()) for c in range(len(CLASS_NAMES))}
print(f"  After augmentation: {len(X_train):,} train samples  {_aug_counts}")

# ─── 3. Class weights (gentle — computed on the rebalanced training set) ──────
print("\n" + "=" * 60)
print("Step 3: Computing class weights")
print("=" * 60)

# Formula: weight = train_total / (num_classes * class_count)
num_classes  = len(CLASS_NAMES)
train_counts = Counter(y_train.tolist())
tot_tr       = sum(train_counts.values())
class_weight = {
    cls: tot_tr / (num_classes * train_counts[cls])
    for cls in range(num_classes)
}
print("  Class weights (higher = model penalized more for missing this class):")
for cls, name in enumerate(CLASS_NAMES):
    print(f"    [{cls}] {name:<12}: {class_weight[cls]:.3f}")

# ─── 4. Build CNN-LSTM model ─────────────────────────────────────────────────
print("\n" + "=" * 60)
print("Step 4: Building CNN-LSTM model")
print("=" * 60)

from tensorflow.keras import layers, models, Input

def build_cnn_lstm(input_shape=(256, 1), num_classes=3):
    inp = Input(shape=input_shape)

    # CNN block — extracts local waveform features (P wave, QRS, T wave shape)
    x = layers.Conv1D(64, kernel_size=5, activation="relu", padding="same")(inp)
    x = layers.BatchNormalization()(x)
    x = layers.Conv1D(64, kernel_size=5, activation="relu", padding="same")(x)
    x = layers.BatchNormalization()(x)
    x = layers.MaxPooling1D(pool_size=2)(x)

    x = layers.Conv1D(128, kernel_size=3, activation="relu", padding="same")(x)
    x = layers.BatchNormalization()(x)
    x = layers.MaxPooling1D(pool_size=2)(x)

    # LSTM block — captures temporal rhythm patterns across the window
    x = layers.LSTM(128, return_sequences=False)(x)
    x = layers.Dropout(0.4)(x)

    # Classification head
    x = layers.Dense(64, activation="relu")(x)
    x = layers.Dropout(0.3)(x)
    out = layers.Dense(num_classes, activation="softmax")(x)

    return models.Model(inp, out, name="CardioGuard_CNN_LSTM")

model = build_cnn_lstm()
model.summary()

# ─── 5. Compile ───────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("Step 5: Compiling model")
print("=" * 60)

model.compile(
    optimizer=tf.keras.optimizers.Adam(learning_rate=args.lr),
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"]
)

# ─── 6. Callbacks ─────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("Step 6: Setting up callbacks")
print("=" * 60)

checkpoint_path = os.path.join(args.output_dir, "best_model.keras")

callbacks = [
    # Stop early if val_loss stops improving
    tf.keras.callbacks.EarlyStopping(
        monitor="val_loss", patience=12,
        restore_best_weights=True, verbose=1
    ),
    # Halve learning rate when val_loss plateaus
    tf.keras.callbacks.ReduceLROnPlateau(
        monitor="val_loss", factor=0.5, patience=4,
        min_lr=1e-6, verbose=1
    ),
    # Save the best model automatically (by validation loss)
    tf.keras.callbacks.ModelCheckpoint(
        checkpoint_path, monitor="val_loss",
        save_best_only=True, verbose=1
    ),
]
print(f"  Best model will be saved to: {checkpoint_path}")
print(f"  Early stopping patience: 12 epochs")
print(f"  LR reduction patience:   4 epochs")

# ─── 7. Train ─────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print(f"Step 7: Training ({args.epochs} epochs, batch size {args.batch})")
print("=" * 60)

history = model.fit(
    X_train, y_train,
    validation_data=(X_val, y_val),
    epochs=args.epochs,
    batch_size=args.batch,
    class_weight=class_weight,
    callbacks=callbacks,
    verbose=1
)

# Save training history
history_path = os.path.join(args.output_dir, "history.json")
with open(history_path, "w") as f:
    json.dump({k: [float(v) for v in vals]
               for k, vals in history.history.items()}, f, indent=2)
print(f"\n  Training history saved: {history_path}")

# ─── 8. Evaluate on test set ─────────────────────────────────────────────────
print("\n" + "=" * 60)
print("Step 8: Evaluating on held-out test set")
print("=" * 60)

from sklearn.metrics import classification_report, confusion_matrix

y_pred_probs = model.predict(X_test, verbose=0)
y_pred       = np.argmax(y_pred_probs, axis=1)

report = classification_report(y_test, y_pred, target_names=CLASS_NAMES, digits=4)
print(report)

# Save evaluation
eval_path = os.path.join(args.output_dir, "evaluation.txt")
with open(eval_path, "w") as f:
    f.write("CardioGuard AI - Model Evaluation\n")
    f.write("=" * 60 + "\n\n")
    f.write(f"Test set size: {len(X_test):,} samples\n\n")
    f.write(report)

print(f"  Evaluation saved: {eval_path}")

# ─── 9. Plot training curves ──────────────────────────────────────────────────
print("\n" + "=" * 60)
print("Step 9: Saving plots")
print("=" * 60)

import matplotlib
matplotlib.use("Agg")  # non-interactive backend (works without display)
import matplotlib.pyplot as plt

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

# Accuracy
ax1.plot(history.history["accuracy"],     label="Train Accuracy", color="#4CAF50")
ax1.plot(history.history["val_accuracy"], label="Val Accuracy",   color="#2196F3")
ax1.set_title("Model Accuracy", fontsize=14, fontweight="bold")
ax1.set_xlabel("Epoch"); ax1.set_ylabel("Accuracy")
ax1.legend(); ax1.grid(alpha=0.3)

# Loss
ax2.plot(history.history["loss"],     label="Train Loss", color="#F44336")
ax2.plot(history.history["val_loss"], label="Val Loss",   color="#FF9800")
ax2.set_title("Model Loss", fontsize=14, fontweight="bold")
ax2.set_xlabel("Epoch"); ax2.set_ylabel("Loss")
ax2.legend(); ax2.grid(alpha=0.3)

plt.suptitle("CardioGuard CNN-LSTM — Training History", fontsize=16, fontweight="bold")
plt.tight_layout()
curves_path = os.path.join(args.output_dir, "plots", "training_curves.png")
plt.savefig(curves_path, dpi=150, bbox_inches="tight")
plt.close()
print(f"  Training curves saved: {curves_path}")

# Confusion matrix
cm = confusion_matrix(y_test, y_pred)
fig, ax = plt.subplots(figsize=(8, 6))
im = ax.imshow(cm, interpolation="nearest", cmap="Blues")
plt.colorbar(im)
ax.set_xticks(range(num_classes)); ax.set_xticklabels(CLASS_NAMES, fontsize=12)
ax.set_yticks(range(num_classes)); ax.set_yticklabels(CLASS_NAMES, fontsize=12)
ax.set_xlabel("Predicted", fontsize=13); ax.set_ylabel("Actual", fontsize=13)
ax.set_title("Confusion Matrix — Test Set", fontsize=14, fontweight="bold")

for i in range(num_classes):
    for j in range(num_classes):
        color = "white" if cm[i, j] > cm.max() / 2 else "black"
        ax.text(j, i, f"{cm[i,j]:,}", ha="center", va="center",
                fontsize=13, fontweight="bold", color=color)

plt.tight_layout()
cm_path = os.path.join(args.output_dir, "plots", "confusion_matrix.png")
plt.savefig(cm_path, dpi=150, bbox_inches="tight")
plt.close()
print(f"  Confusion matrix saved: {cm_path}")

# ─── 10. Summary ──────────────────────────────────────────────────────────────
best_val_acc = max(history.history["val_accuracy"])
final_epoch  = len(history.history["loss"])

print("\n" + "=" * 60)
print("TRAINING COMPLETE")
print("=" * 60)
print(f"  Epochs trained     : {final_epoch}")
print(f"  Best val accuracy  : {best_val_acc:.4f} ({best_val_acc*100:.2f}%)")
print(f"  Model saved to     : {checkpoint_path}")
print(f"  Evaluation report  : {eval_path}")
print(f"  Plots              : {os.path.join(args.output_dir, 'plots')}")
print()
print("Next step: run  export_onnx.py  to convert for cloud deployment")
