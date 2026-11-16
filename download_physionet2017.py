"""
CardioGuard AI - PhysioNet 2017 Bulk Downloader
Downloads the training.zip from PhysioNet 2017 Challenge directly,
then extracts it. Much more reliable than file-by-file download.

NOTE: PhysioNet requires a free account for credentialed databases.
The 2017 Challenge training set is open-access (no login needed).
"""

import os
import sys
import time
import zipfile
import urllib.request
import urllib.error

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
P2017_DIR = os.path.join(BASE_DIR, "data", "physionet2017")
os.makedirs(P2017_DIR, exist_ok=True)

ZIP_PATH  = os.path.join(BASE_DIR, "data", "training2017.zip")

# Direct download URL for the training set zip
URLS_TO_TRY = [
    "https://physionet.org/files/challenge-2017/1.0.0/training2017.zip",
    "https://storage.googleapis.com/physionet-challenge/2017/training2017.zip",
]

# ── Show progress during download ─────────────────────────────────────────────
def progress_hook(count, block_size, total_size):
    if total_size > 0:
        pct   = min(int(count * block_size * 100 / total_size), 100)
        done  = int(50 * pct / 100)
        bar   = "#" * done + "-" * (50 - done)
        mb    = count * block_size / 1_048_576
        total = total_size / 1_048_576
        print(f"\r  [{bar}] {pct}%  {mb:.1f}/{total:.1f} MB", end="", flush=True)

# ── Skip if already extracted ─────────────────────────────────────────────────
mat_files = [f for f in os.listdir(P2017_DIR) if f.endswith(".mat")]
if len(mat_files) > 100:
    print(f"✅ PhysioNet 2017 already extracted ({len(mat_files)} files found).")
    sys.exit(0)

# ── Skip if zip already downloaded ───────────────────────────────────────────
if os.path.exists(ZIP_PATH) and os.path.getsize(ZIP_PATH) > 10_000_000:
    print(f"Zip already exists ({os.path.getsize(ZIP_PATH)/1_048_576:.0f} MB). Skipping download.")
else:
    print("=" * 60)
    print("Downloading PhysioNet 2017 training2017.zip (~150 MB)")
    print("=" * 60)

    downloaded = False
    for url in URLS_TO_TRY:
        try:
            print(f"\nTrying: {url}")
            urllib.request.urlretrieve(url, ZIP_PATH, reporthook=progress_hook)
            print()  # newline after progress bar
            print(f"✓ Downloaded: {os.path.getsize(ZIP_PATH)/1_048_576:.1f} MB")
            downloaded = True
            break
        except urllib.error.URLError as e:
            print(f"\n  Failed: {e}")
            time.sleep(2)

    if not downloaded:
        if os.path.exists(ZIP_PATH):
            os.remove(ZIP_PATH)
        print("\n⚠  Could not download PhysioNet 2017 automatically.")
        print("\nManual download steps:")
        print("  1. Open: https://physionet.org/content/challenge-2017/1.0.0/")
        print("  2. Click 'Files' tab → download 'training2017.zip'")
        print(f"  3. Save it to: {ZIP_PATH}")
        print("  4. Re-run this script to extract it.")
        sys.exit(1)

# ── Extract zip ───────────────────────────────────────────────────────────────
print(f"\nExtracting to {P2017_DIR} ...")
with zipfile.ZipFile(ZIP_PATH, 'r') as zf:
    members = zf.namelist()
    for i, member in enumerate(members):
        zf.extract(member, P2017_DIR)
        if i % 500 == 0:
            print(f"\r  Extracting... {i}/{len(members)}", end="", flush=True)

print(f"\r  Extracting... {len(members)}/{len(members)} ✓")

# Move files out of nested folder if needed
inner = os.path.join(P2017_DIR, "training2017")
if os.path.isdir(inner):
    import shutil
    for f in os.listdir(inner):
        shutil.move(os.path.join(inner, f), P2017_DIR)
    os.rmdir(inner)

mat_count = len([f for f in os.listdir(P2017_DIR) if f.endswith(".mat")])
print(f"✅ PhysioNet 2017 ready: {mat_count} ECG recordings in {P2017_DIR}")

# ── Final summary ─────────────────────────────────────────────────────────────
mitbih_count = len([f for f in os.listdir(os.path.join(BASE_DIR, "data", "mitbih"))
                     if f.endswith(".dat")])
print("\n" + "=" * 60)
print("DATASET SUMMARY")
print("=" * 60)
print(f"  MIT-BIH records:        {mitbih_count}/48  {'✅' if mitbih_count == 48 else '⚠ incomplete'}")
print(f"  PhysioNet 2017 records: {mat_count}  {'✅' if mat_count > 0 else '⚠ not downloaded'}")
