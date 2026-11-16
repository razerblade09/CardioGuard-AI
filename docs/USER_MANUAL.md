# CardioGuard AI — User's Manual
### Installation, Setup, and Operation Guide

**System:** CardioGuard AI — Portable ECG Arrhythmia Detection and Remote Monitoring System
**Version:** 1.0
**Document Date:** July 2026

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [System Overview](#2-system-overview)
3. [Requirements](#3-requirements)
4. [Part A — Hardware Assembly](#part-a--hardware-assembly)
5. [Part B — Cloud Services Setup](#part-b--cloud-services-setup)
6. [Part C — Backend API Installation](#part-c--backend-api-installation)
7. [Part D — Device Firmware Installation](#part-d--device-firmware-installation)
8. [Part E — Web Dashboard Installation](#part-e--web-dashboard-installation)
9. [Part F — AI Model Pipeline (Optional)](#part-f--ai-model-pipeline-optional)
10. [Operating the System](#10-operating-the-system)
11. [Troubleshooting](#11-troubleshooting)
12. [Safety and Limitations](#12-safety-and-limitations)
13. [Appendix — Quick Reference](#13-appendix--quick-reference)

---

## 1. Introduction

### 1.1 Purpose of This Manual

This manual guides a user through the complete installation, configuration, and operation of the **CardioGuard AI** system. It is written for two audiences:

- **Technical installers** (researchers, IT staff, panel evaluators) who need to build, deploy, and reproduce the system from source.
- **End users** (patients, guardians, doctors) who only need to wear the device and read the dashboard. End users may skip directly to [Section 10, Operating the System](#10-operating-the-system).

### 1.2 What CardioGuard AI Does

CardioGuard AI is a wearable ECG monitoring system that:

1. Continuously captures a single-lead ECG signal from the patient using an AD8232 sensor.
2. Streams the signal in 512-millisecond windows over Wi-Fi to a cloud inference server.
3. Classifies each window with a trained **CNN-LSTM** deep learning model into **Normal**, **Arrhythmia**, or **At-Risk**.
4. Stores every reading in a Firebase Realtime Database.
5. Sends automatic **Telegram alerts** to the patient's doctor and family when a sustained abnormal rhythm is detected.
6. Displays live ECG waveforms, heart rate, battery level, and patient location on a **React web dashboard** for the attending physician.
7. Allows the doctor to trigger an **ambulance dispatch** message containing the patient's GPS/Wi-Fi-derived coordinates.

---

## 2. System Overview

### 2.1 Architecture

```
   PATIENT                      CLOUD                        CAREGIVERS
   ───────                      ─────                        ──────────

 ┌───────────┐   HTTPS    ┌──────────────┐   write    ┌──────────────────┐
 │  ESP32    │  512 ms    │  FastAPI     │───────────▶│ Firebase         │
 │  Lolin D32│──windows──▶│  /analyze    │            │ Realtime DB      │
 │  + AD8232 │            │              │            └────────┬─────────┘
 │  + OLED   │◀──result───│  ONNX        │                     │ realtime
 │  + LiPo   │            │  CNN-LSTM    │                     ▼
 └───────────┘            └──────┬───────┘            ┌──────────────────┐
                                 │                    │ React Dashboard  │
                                 │ alert              │ (Doctor view)    │
                                 ▼                    └──────────────────┘
                          ┌──────────────┐
                          │ Telegram Bot │──▶ Doctor / Family / Ambulance
                          └──────────────┘
```

### 2.2 The Four Installable Layers

| Layer | Location in repository | Technology | Installed in |
|---|---|---|---|
| **1. Device firmware** | `firmware/cardioguard/`, `firmware/cardioguard_patient2/` | Arduino C++ (ESP32) | [Part D](#part-d--device-firmware-installation) |
| **2. Cloud inference API** | `cloud_api.py` | Python 3.12, FastAPI, ONNX Runtime | [Part C](#part-c--backend-api-installation) |
| **3. Web dashboard** | `dashboard/` | React 19, Vite, Recharts, Firebase | [Part E](#part-e--web-dashboard-installation) |
| **4. AI training pipeline** | `preprocess.py`, `train.py`, `export_onnx.py` | TensorFlow / Keras, wfdb, scikit-learn | [Part F](#part-f--ai-model-pipeline-optional) |

> **Recommended installation order:** Part A → Part B → Part C → Part D → Part E. Part F is only required if you wish to retrain the AI model; a pre-trained model (`ai/cardioguard_model.onnx`) is already included.

---

## 3. Requirements

### 3.1 Hardware Bill of Materials

| # | Component | Specification | Qty |
|---|---|---|---|
| 1 | ESP32 Lolin D32 | Wi-Fi MCU with onboard LiPo charger and JST port | 1 per patient |
| 2 | AD8232 ECG Sensor Module | Single-lead, with 3.5 mm jack and 3-lead cable | 1 |
| 3 | SSD1306 OLED Display | 0.96", 128×64, I²C, address `0x3C` | 1 |
| 4 | Li-ion Battery | LP803860 or equivalent, 3.7 V 2000 mAh, JST-PH plug | 1 |
| 5 | Disposable ECG Electrodes | 3-lead snap-on pads | 3 per session |
| 6 | Wiring | Breadboard or perfboard, 22–24 AWG jumper wire | as needed |
| 7 | Enclosure | Plastic project box or 3D-printed case | 1 |
| 8 | Micro-USB cable | Data-capable (not charge-only) | 1 |

**Tools:** soldering iron (30–60 W), 63/37 rosin-core solder, multimeter, small screwdriver set.

### 3.2 Software Requirements

| Software | Minimum Version | Purpose |
|---|---|---|
| **Python** | 3.12 | Backend API and AI pipeline |
| **Node.js + npm** | Node 18 LTS or newer | Web dashboard build |
| **Arduino IDE** | 2.x | Flashing ESP32 firmware |
| **Git** | any recent | Cloning the repository |
| **Web browser** | Chrome / Edge / Firefox, current | Dashboard access |

### 3.3 Online Accounts Required (all free tier)

| Service | Used for | Sign-up |
|---|---|---|
| **Firebase** (Google) | Realtime Database, Authentication, Hosting | https://console.firebase.google.com |
| **Railway.app** | Hosting the FastAPI inference server | https://railway.app |
| **Telegram** | Bot for emergency alerts | Telegram app → `@BotFather` |
| **Google Cloud** | Geolocation API key (Wi-Fi based location) | https://console.cloud.google.com |

### 3.4 Obtaining the Source Code

```bash
git clone <your-repository-url> Thesis
cd Thesis
```

If you received the project as a folder (e.g. on a USB drive), simply copy it to your computer and open a terminal inside that folder. All commands in this manual assume your terminal's working directory is the project root.

---

## Part A — Hardware Assembly

> ⚠️ **Before you begin:** disconnect the battery and USB cable while wiring. Never wear the device while it is plugged into mains-powered USB.

### A.1 Wiring Table

Connect the components exactly as follows. The ESP32 operates at 3.3 V logic, so both the sensor and display are powered from the ESP32's **3.3V** pin — **not 5V**.

| Component Pin | → ESP32 Lolin D32 Pin | Function |
|---|---|---|
| **AD8232 ECG Sensor** | | |
| `OUTPUT` | `GPIO 34` | Analog ECG signal (ADC1) |
| `LO+` | `GPIO 32` | Lead-off detection, positive |
| `LO-` | `GPIO 33` | Lead-off detection, negative |
| `3.3V` | `3.3V` | Sensor power |
| `GND` | `GND` | Common ground |
| **SSD1306 OLED** | | |
| `SDA` | `GPIO 21` | I²C data |
| `SCL` | `GPIO 22` | I²C clock |
| `VCC` | `3.3V` | Display power |
| `GND` | `GND` | Common ground |
| **Battery** | | |
| JST connector | Onboard JST port | 3.7 V LiPo input + charging |

The firmware additionally reads the onboard battery divider on `GPIO 35` for the battery-percentage indicator; no external wiring is needed for this on the Lolin D32.

### A.2 Battery Polarity Check

> 🛑 **CAUTION — Read before plugging in the battery.**
> Compare the red (`+`) and black (`−`) wires of your battery's JST plug against the small `+` / `−` markings printed on the Lolin D32 next to the connector. Many aftermarket batteries ship with **reversed** polarity, which will permanently damage the board.
> If reversed: use tweezers or a pin to lift the small retention tab on each metal crimp, slide both crimps out of the white housing, and swap their positions.

### A.3 Assembly Steps

1. Solder header pins to the AD8232 module and the OLED display if they are not pre-soldered.
2. Mount the ESP32, AD8232, and OLED on a breadboard (for testing) or solder to perfboard (for final assembly).
3. Wire all connections per the table in [A.1](#a1-wiring-table).
4. Verify with a multimeter: continuity on every ground connection, and 3.3 V present at the AD8232 and OLED power pins once USB is connected.
5. **Optional but recommended:** place a 10 µF capacitor between the AD8232 `OUTPUT` line and ground to smooth ADC noise.
6. Perform the polarity check in [A.2](#a2-battery-polarity-check), then plug in the battery.
7. Fit everything into the enclosure, leaving the 3.5 mm ECG jack and the micro-USB port accessible.

### A.4 Electrode Placement (3-Lead)

| Cable colour | Placement on body |
|---|---|
| **Red (RA)** | Right side of chest, just below the collarbone |
| **Yellow (LA)** | Left side of chest, just below the collarbone |
| **Green (RL)** | Lower left abdomen / lower left rib area |

Clean and dry the skin before applying the disposable electrodes. Press each pad firmly for a few seconds to ensure adhesion.

---

## Part B — Cloud Services Setup

Complete this part **before** deploying the backend, as the backend needs the credentials produced here.

### B.1 Firebase Project

1. Go to https://console.firebase.google.com and click **Add project**. Name it (e.g. `cardioguard-ai`) and finish the wizard.
2. In the left sidebar, open **Build → Realtime Database → Create Database**.
   - Choose a region (this project uses `asia-southeast1`).
   - Start in **locked mode**, then set rules appropriate to your deployment.
3. Copy the database URL shown at the top — it looks like:
   `https://<your-project>-default-rtdb.asia-southeast1.firebasedatabase.app`
4. Open **Build → Authentication → Get started**, and enable the **Email/Password** provider.
5. Under the **Users** tab, click **Add user** and create the doctor's login account (e.g. `doctor@hospital.com` with a password of your choice). This is the account used to sign into the dashboard.

### B.2 Firebase Service Account Key (for the backend)

1. Click the ⚙️ gear icon → **Project settings → Service accounts**.
2. Click **Generate new private key** and confirm. A JSON file downloads.
3. Rename it to `firebase_credentials.json` and place it in the **project root** (next to `cloud_api.py`).

> 🔐 This file grants full administrative access to your database. It is already listed in `.gitignore` — **never commit it to Git and never share it publicly.**

### B.3 Firebase Web Config (for the dashboard)

1. In **Project settings → General**, scroll to *Your apps* and click the **Web** icon (`</>`).
2. Register the app (nickname: `cardioguard-dashboard`).
3. Copy the `firebaseConfig` values shown — you will paste them into the dashboard's environment file in [Part E](#part-e--web-dashboard-installation).

### B.4 Telegram Bot

1. Open Telegram and start a chat with **@BotFather**.
2. Send `/newbot`, then follow the prompts to name your bot.
3. BotFather replies with a **bot token** of the form `123456789:AAE...`. Save it — this becomes `TELEGRAM_TOKEN`.
4. Open a chat with **your new bot** and send it any message (this is required before the bot may message you).
5. To find your numeric **chat ID**, start a chat with **@userinfobot** and send `/start`; it replies with your ID.
6. Repeat step 5 for every person who should receive alerts (doctor, family member).

### B.5 Registering Patients and Alert Contacts

The alert system looks up recipients at `patients/<patient_id>/contacts` in the database. A helper script populates this structure.

1. Open [`add_patient_contacts.py`](../add_patient_contacts.py) in a text editor.
2. Replace the placeholder chat ID with your real Telegram chat IDs, and adjust patient names as needed:

```python
MY_TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID"   # ← replace with your real chat ID

patients_data = {
    "patient_001": {
        "name": "Juan Dela Cruz",
        "contacts": {
            "doctor": "<doctor chat id>",
            "family": "<family chat id>",
        }
    },
    ...
}
```

3. Also update the `databaseURL` in that file to your own Realtime Database URL.
4. Run it once (after completing [Part C.1](#c1-create-the-python-environment)):

```bash
python add_patient_contacts.py
```

Expected output: `Patients list and Telegram contacts populated successfully!`

### B.6 Google Geolocation API Key

Used by the device to determine its location from surrounding Wi-Fi access points, with no GPS module required.

1. Go to https://console.cloud.google.com and create (or select) a project.
2. Navigate to **APIs & Services → Library**, search for **Geolocation API**, and click **Enable**.
3. Go to **APIs & Services → Credentials → Create credentials → API key**.
4. Copy the key. For security, click **Restrict key** and limit it to the Geolocation API only.
5. Save this key — it becomes `GOOGLE_GEO_KEY` in the firmware config.

---

## Part C — Backend API Installation

The backend is a FastAPI service that loads the ONNX model, classifies incoming ECG windows, writes results to Firebase, and dispatches Telegram alerts.

### C.1 Create the Python Environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

This installs FastAPI, Uvicorn, ONNX Runtime, NumPy, SciPy, `firebase-admin`, and `python-telegram-bot` at the pinned versions in [`requirements.txt`](../requirements.txt).

### C.2 Environment Variables

The API reads its configuration from environment variables, all of which have working defaults for local testing:

| Variable | Default | Description |
|---|---|---|
| `ONNX_MODEL_PATH` | `ai/cardioguard_model.onnx` | Path to the exported model |
| `FIREBASE_CRED_PATH` | `firebase_credentials.json` | Service account key file (local dev) |
| `FIREBASE_CREDENTIALS_JSON` | *(unset)* | Full key contents as a JSON string (cloud deploys) |
| `FIREBASE_DB_URL` | project default | Realtime Database URL |
| `TELEGRAM_TOKEN` | *(empty)* | Bot token from BotFather; alerts disabled if empty |
| `TELEGRAM_CHAT_ID` | *(empty)* | Fallback chat ID when a patient has no registered contacts |
| `ALERT_THRESHOLD` | `0.85` | Minimum model confidence required to raise an alert |
| `ALERT_COOLDOWN_S` | `300` | Minimum seconds between alerts per device (anti-alert-fatigue) |

Set them in PowerShell for the current session like this:

```powershell
$env:TELEGRAM_TOKEN = "123456789:AAE..."
```

### C.3 Run the Server Locally

```bash
uvicorn cloud_api:app --host 0.0.0.0 --port 8000
```

On a successful start the log shows:

```
Loading ONNX model from ai/cardioguard_model.onnx ...
ONNX model loaded ✓
Firebase connected via file ✓
Telegram bot connected ✓
```

Verify in a browser:

- http://localhost:8000/ → `{"status":"CardioGuard AI API is running","version":"1.0.0"}`
- http://localhost:8000/health → `{"status":"ok", ...}`
- http://localhost:8000/docs → interactive Swagger documentation for all endpoints

### C.4 API Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Service banner / liveness check |
| `GET` | `/health` | Health probe, reports the loaded model path |
| `POST` | `/analyze` | Receives a 256-sample ECG window from the device, returns the classification and heart rate |
| `POST` | `/dispatch` | Sends an ambulance-dispatch Telegram alert with the patient's map location |

### C.5 Deploy to Railway (Production)

The device must reach the API over the public internet, so a hosted deployment is required for normal operation.

1. Push the repository to GitHub.
2. At https://railway.app, choose **New Project → Deploy from GitHub repo** and select it.
3. Railway detects [`nixpacks.toml`](../nixpacks.toml) and builds with Python 3.12, then starts the process defined in [`Procfile`](../Procfile):
   `uvicorn cloud_api:app --host 0.0.0.0 --port $PORT`
4. Open the service's **Variables** tab and add:
   - `FIREBASE_CREDENTIALS_JSON` — paste the **entire contents** of `firebase_credentials.json` as one line.
   - `FIREBASE_DB_URL` — your database URL.
   - `TELEGRAM_TOKEN` — your bot token.
   - `TELEGRAM_CHAT_ID` — your fallback chat ID.
5. Under **Settings → Networking**, click **Generate Domain**. You receive a public URL such as:
   `https://cardioguard-api-production-xxxx.up.railway.app`
6. Confirm the deployment by visiting `<your-url>/health`.
7. **Record this URL** — it is required for the firmware config in [Part D](#part-d--device-firmware-installation).

---

## Part D — Device Firmware Installation

### D.1 Prepare the Arduino IDE

1. Install **Arduino IDE 2.x** from https://www.arduino.cc/en/software.
2. Add ESP32 board support: **File → Preferences → Additional Board Manager URLs**, paste
   `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
3. Open **Tools → Board → Boards Manager**, search `esp32`, and install **esp32 by Espressif Systems** (version 3.x).
4. Open **Tools → Manage Libraries** and install:
   - `Adafruit SSD1306`
   - `Adafruit GFX Library`
   - `ArduinoJson`
   (When prompted to install dependencies, accept.)

### D.2 Configure the Device

Each physical device requires its own `config.h`. This file holds secrets and is excluded from Git.

1. Open the folder `firmware/cardioguard/`.
2. Copy `config.h.example` to `config.h` in the same folder.
3. Edit `config.h` and fill in every value:

```c
#define WIFI_SSID       "YourNetworkName"
#define WIFI_PASS       "YourPassword"
#define CLOUD_API_URL   "https://your-app.up.railway.app"   // no trailing slash
#define DEVICE_KEY      "changeme_secret_key"
#define PATIENT_ID      "patient_001"     // must match a key in Firebase
#define DEVICE_ID       "cg_001"          // unique per physical unit
#define GOOGLE_GEO_KEY  "YOUR_GOOGLE_API_KEY_HERE"
```

> **Wi-Fi note:** the ESP32 supports **2.4 GHz networks only**. It cannot connect to a 5 GHz-only SSID. Mobile hotspots work well for demonstrations.

> **Second device:** a pre-configured second unit lives in `firmware/cardioguard_patient2/`, already set to `PATIENT_ID "patient_002"` / `DEVICE_ID "cg_002"`. Edit its `config.h` the same way. Every device must have a **unique** `PATIENT_ID` and `DEVICE_ID`.

### D.3 Flash the Firmware

1. Connect the ESP32 to your computer with a **data-capable** micro-USB cable.
2. In Arduino IDE, open `firmware/cardioguard/cardioguard.ino`.
3. Set **Tools → Board → ESP32 Arduino → WEMOS LOLIN32** (or *LOLIN D32*).
4. Set **Tools → Port** to the COM port that appeared when you plugged in the board (e.g. `COM5` on Windows, `/dev/ttyUSB0` on Linux).
5. Leave the upload speed at `921600` (drop to `115200` if uploads fail).
6. Click **Upload** (→ arrow). If the IDE stalls at *Connecting…*, hold the **BOOT** button on the board until uploading begins.
7. Open **Tools → Serial Monitor** at **115200 baud** to watch the startup log.

### D.4 Verify the Device

Expected behaviour after a successful flash:

| Stage | OLED shows | Serial log shows |
|---|---|---|
| Boot | CardioGuard splash | Firmware banner |
| Wi-Fi | `Connecting…` | SSID and assigned IP address |
| Time sync | — | NTP time acquired |
| Running | Live BPM, status, battery % | `POST /analyze → 200` responses |
| Electrodes off | `Leads Off` | lead-off detection warning |

The firmware samples at **500 Hz**, sends a **256-sample (512 ms)** window on each POST, and buffers up to ~60 seconds of data locally if the network drops.

---

## Part E — Web Dashboard Installation

### E.1 Install Dependencies

```bash
cd dashboard
npm install
```

### E.2 Configure Firebase Credentials

1. Copy the template:

   **Windows (PowerShell):**
   ```powershell
   Copy-Item .env.local.example .env.local
   ```
   **macOS / Linux:**
   ```bash
   cp .env.local.example .env.local
   ```

2. Open `dashboard/.env.local` and fill in the values from [Part B.3](#b3-firebase-web-config-for-the-dashboard):

```
VITE_FIREBASE_API_KEY=your_api_key_here
VITE_FIREBASE_AUTH_DOMAIN=your_project_id.firebaseapp.com
VITE_FIREBASE_DATABASE_URL=https://your_project_id-default-rtdb.firebaseio.com
VITE_FIREBASE_PROJECT_ID=your_project_id
VITE_FIREBASE_STORAGE_BUCKET=your_project_id.appspot.com
VITE_FIREBASE_MESSAGING_SENDER_ID=your_sender_id
VITE_FIREBASE_APP_ID=your_app_id
```

> Variables **must** keep the `VITE_` prefix — Vite only exposes prefixed variables to the browser. Restart the dev server after any change to this file.

### E.3 Run in Development

```bash
npm run dev
```

Open the printed URL (typically http://localhost:5173) and sign in with the doctor account created in [Part B.1](#b1-firebase-project).

### E.4 Build and Deploy to Firebase Hosting

```bash
npm run build
npx firebase login
npx firebase deploy --only hosting
```

The build output goes to `dashboard/dist/`, which [`firebase.json`](../dashboard/firebase.json) publishes with SPA rewrites so client-side routes resolve correctly. On success, Firebase prints the live hosting URL.

---

## Part F — AI Model Pipeline (Optional)

A trained model (`ai/cardioguard_model.onnx`) ships with the project. Follow this part only to reproduce or retrain it.

> Training requires additional packages not in `requirements.txt`: `tensorflow`, `wfdb`, `scikit-learn`, `imbalanced-learn`, `matplotlib`, and `tf2onnx`. Install them into the same virtual environment before proceeding.

### F.1 Download the Datasets

```bash
python download_datasets.py
```

Downloads all 48 MIT-BIH Arrhythmia Database records into `data/mitbih/`. The script retries on failure and skips records already present, so it is safe to re-run after an interruption. For the atrial-fibrillation dataset:

```bash
python download_physionet2017.py
```

### F.2 Preprocess

```bash
python preprocess.py
```

This bandpass- and notch-filters each signal, resamples from the dataset's 360 Hz to the device's **500 Hz**, segments into **256-sample** windows, and maps annotations to three classes:

| Label | Class |
|---|---|
| `0` | Normal |
| `1` | Arrhythmia |
| `2` | At-Risk |

Outputs `data/processed/X.npy`, `y.npy`, and `info.txt` (class counts and dataset statistics).

### F.3 Train

```bash
python train.py
python train.py --epochs 50        # shorter run for a quick check
```

Training on CPU is slow; a GPU runtime (Google Colab, *Runtime → Change runtime type → GPU*) is strongly recommended. Outputs land in `ai/`:

- `best_model.keras` — best checkpoint by validation performance
- `history.json` — per-epoch training curves
- `evaluation.txt` — classification report
- `plots/training_curves.png`, `plots/confusion_matrix.png`

The data split is **inter-patient**: records in the test set never appear in training, so reported accuracy reflects performance on unseen patients rather than unseen beats from known patients.

### F.4 Export to ONNX

```bash
python export_onnx.py
```

Converts `ai/best_model.keras` → `ai/cardioguard_model.onnx`. ONNX Runtime executes on CPU without TensorFlow installed, keeping the deployed API small and inexpensive to host. Restart the backend afterwards so it loads the new model.

### F.5 Clinical Validation Run

```bash
python clinical_testing/run_clinical_tests.py
```

Replays the held-out preprocessed data through the exported ONNX model following an AAMI EC57-based protocol and writes a report plus confusion matrix to `clinical_testing/results/`.

---

## 10. Operating the System

### 10.1 Daily Use — Patient

1. **Charge** the device via micro-USB. The OLED shows a lightning-bolt icon while charging; charge until the battery indicator reads 100%.
2. **Apply electrodes** to clean, dry skin per the placement table in [A.4](#a4-electrode-placement-3-lead). Use fresh pads each session — dried adhesive is the most common cause of noisy signals.
3. **Connect** the 3.5 mm lead cable to the AD8232 jack.
4. **Power on.** The device connects to Wi-Fi automatically; it remembers the last successful access point for faster reconnection.
5. **Wear** the enclosure clipped to a belt or in a pocket. Keep the cable slack so movement does not tug the electrodes.
6. **Read the OLED** for live heart rate, rhythm status, and battery level.

Unplug the device from USB before wearing it, and remove it before bathing or swimming.

### 10.2 Reading the OLED Display

| Display | Meaning | Action |
|---|---|---|
| `Connecting…` | Joining Wi-Fi | Wait; check credentials if it persists |
| Heart rate + `Normal` | Rhythm within normal parameters | None |
| Heart rate + `Arrhythmia` | Abnormal rhythm detected | Rest; alerts sent automatically |
| `Leads Off` | One or more electrodes lost contact | Re-seat or replace the pads |
| ⚡ icon | Charging | None |
| Low battery indicator | Battery nearly depleted | Charge the device |

### 10.3 Using the Doctor Dashboard

1. Open the deployed dashboard URL and sign in with the doctor account.
2. Select a patient from the list.
3. The dashboard displays:
   - **Live ECG waveform** — scrolling real-time trace
   - **Heart rate card** — current BPM
   - **Prediction card** — classification with model confidence
   - **Alert feed** — chronological history of abnormal events
   - **Location panel** — Wi-Fi-derived position, refreshed every 5 minutes
   - **Battery level** for the patient's device
4. In an emergency, use the **ambulance dispatch** control. This calls `POST /dispatch`, which sends every registered contact a Telegram message containing the patient's name, status, heart rate, coordinates, and a tappable Google Maps navigation link.

### 10.4 Understanding Alerts

An alert fires only when **both** conditions hold:

- Model confidence for an abnormal class exceeds `ALERT_THRESHOLD` (default **0.85**), and
- The device has not already alerted within `ALERT_COOLDOWN_S` (default **300 seconds**).

Predictions are additionally stabilised by a **majority vote over the last 10 windows**, and heart rate is computed from R-peaks accumulated over a rolling ~5-second buffer. These measures prevent a single noisy 512 ms window from triggering a false alarm.

---

## 11. Troubleshooting

### 11.1 Device

| Symptom | Likely cause | Resolution |
|---|---|---|
| Board not listed under **Tools → Port** | Charge-only cable, or missing USB driver | Use a data cable; install the CP210x/CH340 driver for your board |
| Upload stalls at *Connecting…* | Board not in bootloader mode | Hold **BOOT** until the upload starts; lower speed to 115200 |
| OLED stays blank | I²C wiring or address | Verify SDA→21, SCL→22, 3.3 V power; confirm the display is at `0x3C` |
| Never connects to Wi-Fi | 5 GHz network, or wrong credentials | Use a 2.4 GHz SSID; re-check `WIFI_SSID` / `WIFI_PASS` in `config.h` |
| Constant `Leads Off` | Poor electrode contact | Replace pads; clean the skin; check the 3.5 mm jack is fully seated |
| Very noisy waveform | Powerline or motion interference | Run on battery instead of USB; keep still; add the 10 µF ADC capacitor |
| `config.h: No such file` at compile time | Template not copied | Copy `config.h.example` → `config.h` and fill it in |

### 11.2 Backend

| Symptom | Likely cause | Resolution |
|---|---|---|
| `No Firebase credentials found — skipping` | Key file missing | Place `firebase_credentials.json` in the project root, or set `FIREBASE_CREDENTIALS_JSON` |
| `firebase-admin not installed` | Incomplete install | Re-run `pip install -r requirements.txt` inside the activated venv |
| Model fails to load on startup | Wrong path or missing file | Confirm `ai/cardioguard_model.onnx` exists, or set `ONNX_MODEL_PATH` |
| Telegram alerts never arrive | Token unset, or the recipient never messaged the bot | Set `TELEGRAM_TOKEN`; each recipient must send the bot a message once; verify chat IDs in `patients/<id>/contacts` |
| Device receives HTTP errors | Wrong URL or unreachable service | Check `CLOUD_API_URL` has no trailing slash; open `<url>/health` in a browser |

### 11.3 Dashboard

| Symptom | Likely cause | Resolution |
|---|---|---|
| Blank page or `PLACEHOLDER` config in console | `.env.local` missing or unprefixed keys | Create `.env.local` with `VITE_`-prefixed values, then restart `npm run dev` |
| Login rejected | Email/Password provider disabled, or no such user | Enable the provider and create the user in the Firebase console |
| No live data | No device posting, or database URL mismatch | Confirm the device serial log shows successful POSTs and that both layers point at the same database |
| Blank page after deploying | Missing SPA rewrite | Ensure `firebase.json` rewrites `**` → `/index.html` |
| `npm install` fails | Node version too old | Install Node 18 LTS or newer |

---

## 12. Safety and Limitations

> ⚠️ **CardioGuard AI is an academic research prototype. It is NOT a certified medical device and must not be used for clinical diagnosis or treatment decisions.**

- The system does not replace a 12-lead clinical ECG or professional medical evaluation. Any concerning result must be confirmed by a licensed physician.
- Never wear the device while it is connected to a mains-powered USB charger. Charge it separately, then wear it on battery power.
- Use only intact, undamaged LiPo batteries. Discontinue use immediately if a battery swells, becomes hot, or is punctured.
- Single-lead ECG captures far less information than a full clinical recording, and its accuracy degrades under motion artefact and poor electrode contact.
- Alerts depend on Wi-Fi connectivity and Telegram availability. The device buffers roughly 60 seconds of data offline; longer outages result in data loss. **Do not rely on this system as the sole means of emergency notification.**
- Do not use the device on patients with implanted pacemakers or defibrillators without physician supervision.
- The system processes identifiable health data. Restrict database access rules, keep credential files private, and handle all recordings in accordance with the Philippine Data Privacy Act of 2012 (R.A. 10173) and your institution's ethics approval.

---

## 13. Appendix — Quick Reference

### 13.1 Full Installation Checklist

- [ ] Repository cloned; terminal open at project root
- [ ] Hardware wired per [A.1](#a1-wiring-table); battery polarity verified
- [ ] Firebase project created; Realtime Database and Email/Password auth enabled
- [ ] Doctor user account created in Firebase Authentication
- [ ] `firebase_credentials.json` placed in project root
- [ ] Telegram bot created; token and chat IDs recorded
- [ ] `add_patient_contacts.py` edited and run successfully
- [ ] Google Geolocation API enabled; key obtained
- [ ] Python venv created; `requirements.txt` installed
- [ ] Backend runs locally; `/health` returns OK
- [ ] Backend deployed to Railway; public URL recorded
- [ ] `firmware/cardioguard/config.h` created from the example and filled in
- [ ] Firmware flashed; serial log shows Wi-Fi connection and successful POSTs
- [ ] `dashboard/.env.local` created and populated
- [ ] `npm install` completed; `npm run dev` shows live data
- [ ] Dashboard deployed to Firebase Hosting

### 13.2 Command Summary

| Task | Command |
|---|---|
| Create Python environment (Windows) | `python -m venv .venv; .venv\Scripts\Activate.ps1` |
| Install backend dependencies | `pip install -r requirements.txt` |
| Run backend locally | `uvicorn cloud_api:app --host 0.0.0.0 --port 8000` |
| Seed patients and contacts | `python add_patient_contacts.py` |
| Install dashboard dependencies | `cd dashboard; npm install` |
| Run dashboard | `npm run dev` |
| Build dashboard | `npm run build` |
| Deploy dashboard | `npx firebase deploy --only hosting` |
| Download datasets | `python download_datasets.py` |
| Preprocess ECG data | `python preprocess.py` |
| Train the model | `python train.py` |
| Export to ONNX | `python export_onnx.py` |
| Run clinical validation | `python clinical_testing/run_clinical_tests.py` |

### 13.3 Key Files and Locations

| Path | Contents |
|---|---|
| `cloud_api.py` | FastAPI inference server |
| `requirements.txt` | Backend Python dependencies |
| `Procfile`, `nixpacks.toml` | Railway deployment configuration |
| `firebase_credentials.json` | Firebase admin key *(you create this; never commit)* |
| `firmware/cardioguard/config.h` | Device 1 secrets *(you create this; never commit)* |
| `firmware/cardioguard_patient2/config.h` | Device 2 secrets |
| `dashboard/.env.local` | Dashboard Firebase config *(you create this; never commit)* |
| `ai/cardioguard_model.onnx` | Deployed inference model |
| `ai/best_model.keras` | Trained Keras checkpoint |
| `data/processed/` | Preprocessed training arrays |
| `docs/pinouts.md` | Detailed wiring diagram |
| `docs/materials.md` | Full bill of materials with prices |

### 13.4 Key System Parameters

| Parameter | Value |
|---|---|
| ECG sampling rate | 500 Hz |
| Window size | 256 samples (512 ms) |
| Offline buffer | ~60 seconds |
| Location refresh interval | 5 minutes |
| Prediction consensus window | 10 windows (majority vote) |
| Heart-rate peak buffer | 5 seconds |
| Alert confidence threshold | 0.85 |
| Alert cooldown | 300 seconds |
| Output classes | Normal, Arrhythmia, At-Risk |

---

*End of User's Manual — CardioGuard AI v1.0*
