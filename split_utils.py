"""
CardioGuard AI - Patient-wise (inter-patient) split utility
============================================================
Ensures ECG windows from the same MIT-BIH record never appear in more than
one of the train / validation / test sets.

This is the ANSI/AAMI-recommended "inter-patient" paradigm (cf. de Chazal
DS1/DS2). It prevents *intra-patient data leakage* — the situation where a
model sees some beats from a patient during training and is then evaluated on
other beats from that *same* patient, which artificially inflates accuracy.

Both train.py and run_clinical_tests.py import this so they reconstruct the
IDENTICAL test set for a given seed.
"""
import os
import numpy as np


def load_groups(data_dir):
    """Load per-window record labels saved by preprocess.py."""
    path = os.path.join(data_dir, "groups.npy")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"groups.npy not found in '{data_dir}'.\n"
            f"Re-run preprocess.py to regenerate the processed arrays with "
            f"per-record grouping (X.npy, y.npy, groups.npy)."
        )
    return np.load(path, allow_pickle=True)


def split_by_record(y, groups, seed=42, val_frac=0.15, test_frac=0.15, verbose=True):
    """Return (train_idx, val_idx, test_idx) with NO record shared across splits.

    Records are bucketed by their dominant class, then each bucket is
    distributed across the three splits. Bucketing by dominant class keeps every
    split populated with all classes (important for the small paced/At-Risk
    class, which lives in only a handful of records). Deterministic per seed.
    """
    y = np.asarray(y)
    groups = np.asarray(groups)
    num_classes = int(y.max()) + 1
    rng = np.random.default_rng(seed)

    records = np.unique(groups)

    # Dominant (most frequent) class for each record
    dominant = {}
    for r in records:
        cls = y[groups == r]
        dominant[r] = int(np.bincount(cls, minlength=num_classes).argmax())

    buckets = {c: [] for c in range(num_classes)}
    for r in records:
        buckets[dominant[r]].append(r)

    train_recs, val_recs, test_recs = [], [], []
    for c in range(num_classes):
        recs = list(buckets[c])
        rng.shuffle(recs)
        n = len(recs)
        if n == 0:
            continue
        n_test = max(1, round(n * test_frac)) if n >= 2 else 0
        remaining = n - n_test
        n_val = max(1, round(n * val_frac)) if remaining >= 2 else 0
        test_recs += recs[:n_test]
        val_recs += recs[n_test:n_test + n_val]
        train_recs += recs[n_test + n_val:]

    train_set, val_set, test_set = set(train_recs), set(val_recs), set(test_recs)

    # Safety: guarantee no record leaks across splits
    assert not (train_set & val_set), "record leak train/val"
    assert not (train_set & test_set), "record leak train/test"
    assert not (val_set & test_set), "record leak val/test"

    train_idx = np.where(np.isin(groups, list(train_set)))[0]
    val_idx = np.where(np.isin(groups, list(val_set)))[0]
    test_idx = np.where(np.isin(groups, list(test_set)))[0]

    if verbose:
        def dist(idx):
            c = np.bincount(y[idx], minlength=num_classes)
            return "  ".join(f"c{k}:{c[k]:,}" for k in range(num_classes))
        print(f"  [inter-patient split] records -> "
              f"train:{len(train_set)}  val:{len(val_set)}  test:{len(test_set)}")
        print(f"    Test records : {sorted(test_set)}")
        print(f"    Train windows: {len(train_idx):>7,}   ({dist(train_idx)})")
        print(f"    Val   windows: {len(val_idx):>7,}   ({dist(val_idx)})")
        print(f"    Test  windows: {len(test_idx):>7,}   ({dist(test_idx)})")

    return train_idx, val_idx, test_idx
