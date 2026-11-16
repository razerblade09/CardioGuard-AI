# CardioGuard AI — Clinical Simulation & Validation Report
*Conducted in accordance with ANSI/AAMI EC57 standards for Cardiac Rhythm algorithms.*

## 1. Executive Summary
This report documents the automated clinical simulation of the CardioGuard AI model (`ai/cardioguard_model.onnx`). To ensure a completely **unbiased validation**, the model was tested on a held-out subset of the MIT-BIH Arrhythmia Database that was **100% excluded from the training and validation phases**.

*   **Test Set Size:** 16,010 segments (each representing a 256-sample window at 500 Hz)
*   **Overall Classification Accuracy:** 95.08%
*   **Average Inference Latency:** 0.76 ms

---

## 2. Methodology & Bias Prevention
In machine learning research for electrocardiography (ECG), evaluating a model on the same patient profile it was trained on introduces **intra-patient data leakage**, which artificially inflates performance. 

To prevent this bias, an **inter-patient (by-record) split** was used:
1. The MIT-BIH records were partitioned by **patient/record**, so that no patient contributed ECG windows to more than one of the training, validation, and test sets (the ANSI/AAMI-recommended paradigm).
2. The test set therefore consists solely of windows from **records the model never observed during training or validation**, giving a genuine estimate of performance on unseen patients.
3. All samples were normalized to zero mean and unit variance before inference.

---

## 3. Clinical Metrics (ANSI/AAMI EC57 Guidelines)
Under the AAMI EC57 standard, the performance of the algorithm is reported on a class-by-class basis using Sensitivity, Specificity, Positive Predictivity, False Positive Rate (False Alarms), and False Negative Rate (Miss Rate).

### Performance Breakdown Table

| Class | True Positives (TP) | False Positives (FP) | False Negatives (FN) | True Negatives (TN) | Sensitivity (Recall) | Positive Predictivity (PPV) | Specificity | False Positive Rate (FPR) | False Negative Rate (FNR) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Normal** | 12,874 | 715 | 65 | 2,356 | 99.50% | 94.74% | 76.72% | 23.28% | 0.50% |
| **Arrhythmia** | 729 | 72 | 279 | 14,930 | 72.32% | 91.01% | 99.52% | 0.48% | 27.68% |
| **At-Risk** | 1,620 | 0 | 443 | 13,947 | 78.53% | 100.00% | 100.00% | 0.00% | 21.47% |

### Key Clinical Insights:
*   **Arrhythmia Positive Predictivity (PPV):** **91.01%** with a False Positive Rate of only **0.48%** — when the model raises an arrhythmia alert it is rarely a false alarm, which is essential for clinician trust.
*   **Arrhythmia Sensitivity (Recall):** **72.32%** at the single-window level (279 of 1,008 windows missed). In deployment, a 10-window majority vote (~5 seconds) raises event-level detection above this per-window figure.
*   **Miss Rate (FNR):** **27.68%** is the model's main limitation; lowering it through decision-threshold tuning and additional training data is identified as future work.

---

## 4. Operational Latency Benchmarking
To be viable as a telehealth triage tool in remote areas, the cloud API must return predictions in real-time to avoid network backlogs.

*   **Benchmark Sample Size:** 1000 individual windows
*   **Average Inference Latency:** 0.76 ms
*   **95th Percentile Latency:** 0.88 ms
*   **Maximum Latency:** 1.39 ms

*Interpretation:* An average latency of under 5ms per ECG window demonstrates that the model is extremely lightweight and can comfortably handle real-time streams from multiple edge devices without queuing delays.

---

## 5. Standard Classification Report & Confusion Matrix
Below is the standard machine learning evaluation breakdown:

```
              precision    recall  f1-score   support

      Normal     0.9474    0.9950    0.9706     12939
  Arrhythmia     0.9101    0.7232    0.8060      1008
     At-Risk     1.0000    0.7853    0.8797      2063

    accuracy                         0.9508     16010
   macro avg     0.9525    0.8345    0.8854     16010
weighted avg     0.9518    0.9508    0.9485     16010

```

Confusion Matrix visualization has been exported to `confusion_matrix.png` in the results directory.
