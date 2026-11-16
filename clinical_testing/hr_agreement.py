"""
Heart-rate agreement analysis: CardioGuard AI vs automatic digital BP monitor.

Compares the pulse rate reported by the reference instrument (an automatic
digital blood pressure monitor / electronic sphygmomanometer) against the heart
rate estimated by the CardioGuard prototype from R-peak intervals.

Only pulse rate is compared. The reference device also reports systolic and
diastolic pressure, but the prototype has no equivalent output -- the AD8232
acquires the heart's electrical activity and does not measure blood pressure.
Baseline BP values belong in the participant characteristics table, not here.

Fill in clinical_testing/hr_readings.csv, then run:
    python clinical_testing/hr_agreement.py
"""

import csv
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ─── Config ──────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(BASE_DIR, "clinical_testing", "hr_readings.csv")
RESULTS_DIR = os.path.join(BASE_DIR, "clinical_testing", "results")

os.makedirs(RESULTS_DIR, exist_ok=True)


def load_readings(path):
    """Read paired BPM values, skipping rows that have not been filled in yet."""
    rows, skipped = [], 0
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cuff, device = row["cuff_bpm"].strip(), row["cardioguard_bpm"].strip()
            if not cuff or not device:
                skipped += 1
                continue
            rows.append({
                "participant": row["participant_id"].strip(),
                "age": row["age"].strip(),
                "sex": row["sex"].strip(),
                "session": row["session"].strip(),
                "cuff": float(cuff),
                "device": float(device),
            })
    return rows, skipped


def main():
    print("=" * 68)
    print("CARDIOGUARD AI - HEART RATE AGREEMENT ANALYSIS")
    print("Reference instrument: automatic digital blood pressure monitor")
    print("=" * 68)

    if not os.path.exists(CSV_PATH):
        print(f"Error: {CSV_PATH} not found.")
        return

    rows, skipped = load_readings(CSV_PATH)
    if skipped:
        print(f"\nNote: {skipped} row(s) still blank and were skipped.")
    if len(rows) < 2:
        print("\nNot enough paired readings to analyze. Fill in hr_readings.csv "
              "with the cuff pulse rate and the CardioGuard BPM taken at the "
              "same moment, then run this again.")
        return

    cuff = np.array([r["cuff"] for r in rows], dtype=float)
    device = np.array([r["device"] for r in rows], dtype=float)
    diff = device - cuff              # positive => prototype reads higher
    mean = (device + cuff) / 2.0

    n = len(rows)
    bias = diff.mean()
    sd = diff.std(ddof=1) if n > 1 else 0.0
    mae = np.abs(diff).mean()
    rmse = float(np.sqrt((diff ** 2).mean()))
    loa_lo, loa_hi = bias - 1.96 * sd, bias + 1.96 * sd
    r = float(np.corrcoef(cuff, device)[0, 1]) if n > 1 else float("nan")

    # ─── Per-reading table ───────────────────────────────────────────────────
    print(f"\nPaired readings (n = {n})\n")
    hdr = f"{'ID':<5}{'Age':>4}{'Sex':>4}{'Sess':>6}{'Cuff':>7}{'Device':>8}{'Diff':>7}"
    print(hdr)
    print("-" * len(hdr))
    for row, d in zip(rows, diff):
        print(f"{row['participant']:<5}{row['age']:>4}{row['sex']:>4}"
              f"{row['session']:>6}{row['cuff']:>7.0f}{row['device']:>8.0f}{d:>+7.1f}")

    # ─── Summary statistics ──────────────────────────────────────────────────
    print("\nAgreement statistics")
    print("-" * 46)
    print(f"  Mean reference pulse rate     : {cuff.mean():.1f} bpm")
    print(f"  Mean prototype heart rate     : {device.mean():.1f} bpm")
    print(f"  Mean bias (prototype - ref)   : {bias:+.2f} bpm")
    print(f"  SD of differences             : {sd:.2f} bpm")
    print(f"  Mean absolute error (MAE)     : {mae:.2f} bpm")
    print(f"  Root mean squared error       : {rmse:.2f} bpm")
    print(f"  95% limits of agreement       : {loa_lo:+.2f} to {loa_hi:+.2f} bpm")
    print(f"  Pearson correlation (r)       : {r:.4f}")

    # ─── Bland-Altman + scatter ──────────────────────────────────────────────
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5))

    ax1.scatter(mean, diff, s=70, alpha=0.8, edgecolor="black", zorder=3)
    ax1.axhline(bias, color="tab:blue", lw=1.6,
                label=f"Bias {bias:+.2f} bpm")
    ax1.axhline(loa_hi, color="tab:red", ls="--", lw=1.3,
                label=f"+1.96 SD ({loa_hi:+.2f})")
    ax1.axhline(loa_lo, color="tab:red", ls="--", lw=1.3,
                label=f"-1.96 SD ({loa_lo:+.2f})")
    ax1.axhline(0, color="grey", lw=0.8, alpha=0.5, zorder=1)
    ax1.set_xlabel("Mean of the two measurements (bpm)")
    ax1.set_ylabel("Prototype - reference (bpm)")
    ax1.set_title(f"Bland-Altman Plot (n = {n})")
    ax1.legend(fontsize=8, loc="best")
    ax1.grid(alpha=0.25, zorder=0)

    lo = float(min(cuff.min(), device.min())) - 5
    hi = float(max(cuff.max(), device.max())) + 5
    ax2.plot([lo, hi], [lo, hi], color="grey", ls="--", lw=1.2,
             label="Line of equality")
    ax2.scatter(cuff, device, s=70, alpha=0.8, edgecolor="black", zorder=3)
    ax2.set_xlim(lo, hi)
    ax2.set_ylim(lo, hi)
    ax2.set_xlabel("Reference pulse rate (bpm)")
    ax2.set_ylabel("CardioGuard heart rate (bpm)")
    ax2.set_title(f"Measurement Agreement (r = {r:.4f})")
    ax2.legend(fontsize=8, loc="best")
    ax2.grid(alpha=0.25, zorder=0)

    fig.suptitle("CardioGuard AI Heart Rate vs Automatic Digital BP Monitor Pulse Rate",
                 fontsize=12, y=0.99)
    fig.tight_layout()
    plot_path = os.path.join(RESULTS_DIR, "hr_agreement.png")
    fig.savefig(plot_path, dpi=150)
    plt.close(fig)

    # ─── Markdown summary for Chapter 4 ──────────────────────────────────────
    md_path = os.path.join(RESULTS_DIR, "hr_agreement_report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Heart Rate Agreement: CardioGuard AI vs Reference Instrument\n\n")
        f.write("Reference instrument: automatic digital blood pressure monitor "
                "(electronic sphygmomanometer), pulse rate reading only.\n\n")
        f.write("## Paired Readings\n\n")
        f.write("| Participant | Age | Sex | Session | Reference (bpm) | "
                "CardioGuard (bpm) | Difference (bpm) |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for row, d in zip(rows, diff):
            f.write(f"| {row['participant']} | {row['age']} | {row['sex']} | "
                    f"{row['session']} | {row['cuff']:.0f} | "
                    f"{row['device']:.0f} | {d:+.1f} |\n")
        f.write("\n## Agreement Statistics\n\n")
        f.write("| Metric | Value |\n|---|---|\n")
        f.write(f"| Paired readings (n) | {n} |\n")
        f.write(f"| Mean reference pulse rate | {cuff.mean():.1f} bpm |\n")
        f.write(f"| Mean prototype heart rate | {device.mean():.1f} bpm |\n")
        f.write(f"| Mean bias (prototype - reference) | {bias:+.2f} bpm |\n")
        f.write(f"| SD of differences | {sd:.2f} bpm |\n")
        f.write(f"| Mean absolute error | {mae:.2f} bpm |\n")
        f.write(f"| Root mean squared error | {rmse:.2f} bpm |\n")
        f.write(f"| 95% limits of agreement | {loa_lo:+.2f} to {loa_hi:+.2f} bpm |\n")
        f.write(f"| Pearson correlation (r) | {r:.4f} |\n")
        f.write("\n## Limitations\n\n")
        f.write("- The reference device reports peripheral pulse rate, which is not "
                "identical to the electrical heart rate. In irregular rhythms, weak "
                "beats may not generate a detectable pulse wave, causing the "
                "reference to underread.\n")
        f.write("- This comparison validates heart rate estimation only. It provides "
                "no evidence regarding the arrhythmia classification performance of "
                "the model, which is evaluated separately against annotated MIT-BIH "
                "records under ANSI/AAMI EC57.\n")
        f.write(f"- All participants were measured at rest, so agreement at elevated "
                f"heart rates was not assessed.\n")

    print(f"\nSaved plot   -> {plot_path}")
    print(f"Saved report -> {md_path}")
    print("\nDone.")


if __name__ == "__main__":
    main()
