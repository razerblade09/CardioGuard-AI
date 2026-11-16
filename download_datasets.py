"""
CardioGuard AI - Robust Dataset Downloader
Downloads MIT-BIH record by record with retry logic.
Skips records already downloaded (safe to re-run).
"""

import wfdb
import os
import time

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
MITBIH_DIR = os.path.join(BASE_DIR, "data", "mitbih")
P2017_DIR  = os.path.join(BASE_DIR, "data", "physionet2017")

os.makedirs(MITBIH_DIR, exist_ok=True)
os.makedirs(P2017_DIR,  exist_ok=True)

# All 48 MIT-BIH record names
MITBIH_RECORDS = [
    "100","101","102","103","104","105","106","107","108","109",
    "111","112","113","114","115","116","117","118","119",
    "121","122","123","124",
    "200","201","202","203","205","207","208","209","210",
    "212","213","214","215","217","219","220","221","222","223",
    "228","230","231","232","233","234"
]

# ─── MIT-BIH: download record by record ──────────────────────────────────────
print("=" * 60)
print("Downloading MIT-BIH Arrhythmia Database (48 records)")
print("=" * 60)

success, skipped, failed = 0, 0, []

for rec in MITBIH_RECORDS:
    # Check if already downloaded (all 3 files: .dat, .hea, .atr)
    files_needed = [f"{rec}.dat", f"{rec}.hea", f"{rec}.atr"]
    already_done = all(
        os.path.exists(os.path.join(MITBIH_DIR, f)) for f in files_needed
    )

    if already_done:
        print(f"  [SKIP] {rec} — already downloaded")
        skipped += 1
        continue

    for attempt in range(1, 4):  # up to 3 retries
        try:
            wfdb.dl_files(
                db        = "mitdb",
                dl_dir    = MITBIH_DIR,
                files     = files_needed,
                keep_subdirs = False
            )
            print(f"  [OK]   {rec}")
            success += 1
            break
        except Exception as e:
            print(f"  [RETRY {attempt}/3] {rec}: {e}")
            time.sleep(3)
    else:
        print(f"  [FAIL] {rec} — skipping after 3 attempts")
        failed.append(rec)

print(f"\nMIT-BIH complete: {success} downloaded, {skipped} skipped, {len(failed)} failed")
if failed:
    print(f"Failed records: {failed}")
    print("Re-run this script to retry failed records.")

print(f"\n✓ MIT-BIH saved to: {MITBIH_DIR}")

# ─── PhysioNet 2017 ───────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("Downloading PhysioNet 2017 Challenge Dataset...")
print("(This is ~500 MB; press Ctrl+C to skip and do later)")
print("=" * 60)

try:
    wfdb.dl_database(
        db_dir    = "challenge-2017/1.0.0/training",
        dl_dir    = P2017_DIR,
        overwrite = False
    )
    print(f"\n✓ PhysioNet 2017 saved to: {P2017_DIR}")
except KeyboardInterrupt:
    print("\nSkipped PhysioNet 2017 (re-run to download later).")
except Exception as e:
    print(f"\nPhysioNet 2017 error: {e}")
    print("Re-run this script to retry.")

print("\n✅ Done!")
