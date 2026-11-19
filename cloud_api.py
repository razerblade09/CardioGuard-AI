"""
CardioGuard AI - Cloud Inference API
======================================
FastAPI endpoint that receives ECG windows from ESP32 via LTE,
runs CNN-LSTM inference, writes to Firebase, and triggers Telegram alerts.

Usage (local test):
  pip install fastapi uvicorn onnxruntime firebase-admin python-telegram-bot
  uvicorn cloud_api:app --host 0.0.0.0 --port 8000

Deploy to cloud:
  - Railway.app: connect GitHub repo, set env vars, auto-deploys
  - Google Cloud Run: docker build + gcloud run deploy
"""

import os
import time
import secrets
import logging
from datetime import datetime, timezone

import numpy as np
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
import onnxruntime as ort

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

# ─── Config (set as environment variables in production) ──────────────────────
ONNX_MODEL_PATH    = os.getenv("ONNX_MODEL_PATH",    "ai/cardioguard_model.onnx")
FIREBASE_CRED_PATH = os.getenv("FIREBASE_CRED_PATH", "firebase_credentials.json")
TELEGRAM_TOKEN     = os.getenv("TELEGRAM_TOKEN",     "")   # your bot token
ALERT_THRESHOLD    = float(os.getenv("ALERT_THRESHOLD", "0.85"))
ALERT_COOLDOWN_S   = int(os.getenv("ALERT_COOLDOWN_S", "300"))   # 5 minutes

# Authentication (see "Authentication" section below)
DEVICE_API_KEY          = os.getenv("DEVICE_API_KEY", "")   # shared secret for ESP32 -> /analyze
DISPATCH_ALLOWED_EMAILS = {                                  # optional doctor allowlist for /dispatch
    e.strip().lower() for e in os.getenv("DISPATCH_ALLOWED_EMAILS", "").split(",") if e.strip()
}

CLASS_NAMES = ["Normal", "Arrhythmia", "At-Risk"]

# ─── Load ONNX model (once on startup, not per request) ───────────────────────
log.info(f"Loading ONNX model from {ONNX_MODEL_PATH} ...")
session = ort.InferenceSession(
    ONNX_MODEL_PATH,
    providers=["CUDAExecutionProvider", "CPUExecutionProvider"]
)
INPUT_NAME = session.get_inputs()[0].name
log.info("ONNX model loaded ✓")

# ─── Firebase setup (supports both file and env var credentials) ──────────────
firebase_db = None
firebase_auth = None
try:
    import json as _json
    import firebase_admin
    from firebase_admin import credentials, db as firebase_db_module, auth as firebase_auth

    # No hardcoded default: falling back to a specific project silently sends
    # data to the wrong database (or a deleted one) whenever the variable is
    # missing. Better to run without Firebase and say so.
    DB_URL = os.getenv("FIREBASE_DB_URL", "")

    # Option 1: JSON string in env var (for Railway / cloud deploys)
    cred_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
    if not DB_URL:
        log.warning("FIREBASE_DB_URL not set — Firebase logging disabled")
    elif cred_json:
        cred = credentials.Certificate(_json.loads(cred_json))
        firebase_admin.initialize_app(cred, {"databaseURL": DB_URL})
        firebase_db = firebase_db_module
        log.info("Firebase connected via env var ✓")
    # Option 2: file on disk (for local dev)
    elif os.path.exists(FIREBASE_CRED_PATH):
        cred = credentials.Certificate(FIREBASE_CRED_PATH)
        firebase_admin.initialize_app(cred, {"databaseURL": DB_URL})
        firebase_db = firebase_db_module
        log.info("Firebase connected via file ✓")
    else:
        log.warning(f"No Firebase credentials found — skipping")
except ImportError:
    log.warning("firebase-admin not installed — Firebase logging disabled")

# ─── Telegram setup ───────────────────────────────────────────────────────────
telegram_bot = None
try:
    if TELEGRAM_TOKEN:
        import telegram
        telegram_bot = telegram.Bot(token=TELEGRAM_TOKEN)
        log.info("Telegram bot connected ✓")
except ImportError:
    log.warning("python-telegram-bot not installed — alerts disabled")

# ─── Alert rate limiter ───────────────────────────────────────────────────────
# Tracks last alert time per device to prevent alert fatigue
last_alert_time: dict[str, float] = {}

# ─── Rolling buffers (per patient) ────────────────────────────────────────────
# Stabilizes predictions and heart rate across multiple 512ms windows.
# Why: A single 512ms window (256 samples) is too short to:
#   - Find 2+ R-peaks for BPM calculation (at 72bpm, 1 beat = 833ms)
#   - Make a reliable arrhythmia prediction (noise causes random flips)
from collections import deque, Counter

CONSENSUS_WINDOW  = 10    # last N predictions for majority vote
HR_PEAK_BUFFER_S  = 5.0   # accumulate R-peaks over this many seconds

# Per-patient buffers
pred_history:  dict[str, deque] = {}   # deque of prediction strings
peak_times:    dict[str, list]  = {}   # list of peak timestamps (seconds)
window_counter: dict[str, int] = {}   # tracks sample position across windows

# ─── FastAPI app ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="CardioGuard AI API",
    description="Real-time ECG arrhythmia classification for CardioGuard devices",
    version="1.0.0"
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ─── Request / Response models ────────────────────────────────────────────────
class ECGPayload(BaseModel):
    device_id : str
    patient_id: str
    timestamp : str               # ISO 8601 e.g. "2026-03-07T20:00:00Z"
    samples   : list[float]       # 256 raw ADC values from ESP32
    lat       : float | None = None   # optional GPS latitude
    lng       : float | None = None   # optional GPS longitude
    battery   : int | None = None     # optional battery percentage (0-100)

    @field_validator("samples")
    @classmethod
    def validate_samples(cls, v):
        if len(v) != 256:
            raise ValueError(f"Expected 256 samples, got {len(v)}")
        return v

class PredictionResponse(BaseModel):
    prediction       : str
    confidence       : float
    heart_rate_bpm   : int | None
    probabilities    : dict
    alert_sent       : bool
    inference_ms     : float
    ambulance_dispatched: bool = False

class DispatchPayload(BaseModel):
    patient_id  : str
    patient_name: str
    lat         : float
    lng         : float
    heart_rate  : int | None = None
    prediction  : str | None = None


# ─── Signal preprocessing (mirrors preprocess.py pipeline) ───────────────────
from scipy.signal import butter, filtfilt, iirnotch

def preprocess(samples: list[float]) -> np.ndarray:
    sig = np.array(samples, dtype=np.float32)

    # Bandpass (0.5–100 Hz)
    b, a = butter(4, [0.5 / 250, 100 / 250], btype="band")
    sig  = filtfilt(b, a, sig).astype(np.float32)

    # Notch 60 Hz
    b, a  = iirnotch(60 / 250, Q=30)
    sig   = filtfilt(b, a, sig).astype(np.float32)

    # Normalize
    sig = (sig - sig.mean()) / (sig.std() + 1e-8)

    return sig.reshape(1, 256, 1)

def estimate_heart_rate(preprocessed_sig: np.ndarray, patient_id: str, fs: int = 500) -> int | None:
    """Accumulate R-peaks across multiple windows to estimate heart rate.
    
    Each window is only 512ms, which is shorter than a single heartbeat (~833ms at 72bpm).
    By tracking peak timestamps across windows, we can build up enough data to calculate BPM.
    """
    try:
        from scipy.signal import find_peaks
        sig = preprocessed_sig.flatten()
        
        # Find peaks in this window
        threshold = sig.mean() + 0.8 * sig.std()
        peaks, _ = find_peaks(sig, height=threshold, distance=int(fs * 0.3))
        
        # Initialize per-patient buffers if needed
        if patient_id not in peak_times:
            peak_times[patient_id] = []
            window_counter[patient_id] = 0
        
        # Convert peak sample indices to absolute time (seconds)
        window_offset_s = window_counter[patient_id] * (256 / fs)
        for p in peaks:
            abs_time = window_offset_s + (p / fs)
            peak_times[patient_id].append(abs_time)
        window_counter[patient_id] += 1
        
        # Trim old peaks (keep only last HR_PEAK_BUFFER_S seconds)
        now_s = window_counter[patient_id] * (256 / fs)
        cutoff = now_s - HR_PEAK_BUFFER_S
        peak_times[patient_id] = [t for t in peak_times[patient_id] if t > cutoff]
        
        # Need at least 3 peaks to estimate reliably
        pts = peak_times[patient_id]
        if len(pts) < 3:
            return None
        
        # Calculate BPM from average RR interval
        rr_intervals = [pts[i+1] - pts[i] for i in range(len(pts)-1)]
        # Filter out unreasonable intervals (< 0.3s or > 2s)
        rr_intervals = [rr for rr in rr_intervals if 0.3 <= rr <= 2.0]
        if not rr_intervals:
            return None
        
        avg_rr = np.median(rr_intervals)  # median is more robust than mean
        bpm = int(60 / avg_rr)
        return bpm if 30 <= bpm <= 220 else None
    except Exception:
        return None

def get_consensus_prediction(patient_id: str, raw_pred: str, raw_conf: float) -> tuple[str, float]:
    """Majority vote over last N predictions to avoid rapid flipping."""
    if patient_id not in pred_history:
        pred_history[patient_id] = deque(maxlen=CONSENSUS_WINDOW)
    
    pred_history[patient_id].append((raw_pred, raw_conf))
    
    # Count votes
    votes = Counter(p for p, c in pred_history[patient_id])
    consensus = votes.most_common(1)[0][0]
    
    # Average confidence of the winning class
    winning_confs = [c for p, c in pred_history[patient_id] if p == consensus]
    avg_conf = sum(winning_confs) / len(winning_confs)
    
    return consensus, avg_conf

# ─── Alert logic ──────────────────────────────────────────────────────────────
async def maybe_send_alert(patient_id: str, prediction: str, confidence: float,
                           heart_rate: int | None, timestamp: str) -> bool:
    """Send Telegram alert if confidence is high and cooldown has passed."""
    if prediction == "Normal":
        return False
    if confidence < ALERT_THRESHOLD:
        return False

    now = time.time()
    if now - last_alert_time.get(patient_id, 0) < ALERT_COOLDOWN_S:
        return False   # still in cooldown period

    last_alert_time[patient_id] = now

    icon = "🚨" if prediction == "Arrhythmia" else "⚠️"
    hr_text = f"\nHR      : {heart_rate} bpm" if heart_rate else ""
    message = (
        f"{icon} CARDIOGUARD ALERT\n"
        f"{'─' * 30}\n"
        f"Patient : {patient_id}\n"
        f"Status  : {prediction} Detected\n"
        f"Confidence: {confidence*100:.1f}%"
        f"{hr_text}\n"
        f"Time    : {timestamp}\n\n"
        f"📋 Action: Contact clinic or go to ER\n"
        f"          if experiencing chest pain."
    )

    # Write alert to Firebase
    if firebase_db:
        try:
            firebase_db.reference(f"alerts/{patient_id}").push({
                "type": prediction, "confidence": confidence,
                "heart_rate": heart_rate, "timestamp": timestamp,
                "acknowledged": False
            })
        except Exception as e:
            log.error(f"Firebase alert write failed: {e}")

    # Send Telegram — get chat IDs from Firebase patient record
    if telegram_bot and firebase_db:
        try:
            patient_ref = firebase_db.reference(f"patients/{patient_id}/contacts").get()
            if patient_ref:
                for role, chat_id in patient_ref.items():
                    await telegram_bot.send_message(chat_id=chat_id, text=message)
                    log.info(f"Alert sent to {role} ({chat_id})")
        except Exception as e:
            log.error(f"Telegram send failed: {e}")

    return True

# ─── Authentication ───────────────────────────────────────────────────────────
# /analyze  : ESP32 devices send a shared secret in the "X-API-Key" header.
# /dispatch : doctors send their Firebase ID token as "Authorization: Bearer <token>".
#             A shared key would be readable in the dashboard's JavaScript, so
#             the token is verified server-side instead.
# (Plain `def` dependencies run in FastAPI's threadpool, so the blocking
#  token verification does not stall the event loop.)
if not DEVICE_API_KEY:
    log.warning("DEVICE_API_KEY is not set — /analyze is UNAUTHENTICATED. "
                "Set it once your devices send the X-API-Key header.")

def require_device_key(x_api_key: str | None = Header(default=None)) -> None:
    if not DEVICE_API_KEY:
        return   # not configured yet: lets existing devices keep working during rollout
    if not x_api_key or not secrets.compare_digest(x_api_key.encode(), DEVICE_API_KEY.encode()):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

def require_doctor(authorization: str | None = Header(default=None)) -> dict:
    if firebase_db is None or firebase_auth is None:
        # Cannot verify anyone, so refuse rather than let the request through.
        raise HTTPException(status_code=503, detail="Authentication service unavailable")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    try:
        claims = firebase_auth.verify_id_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if DISPATCH_ALLOWED_EMAILS and (claims.get("email") or "").lower() not in DISPATCH_ALLOWED_EMAILS:
        raise HTTPException(status_code=403, detail="Not authorized to dispatch")
    return claims

# ─── Routes ───────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "CardioGuard AI API is running", "version": "1.0.0"}

@app.get("/health")
def health():
    return {"status": "ok", "model": ONNX_MODEL_PATH}

@app.post("/dispatch")
async def dispatch_ambulance(payload: DispatchPayload, doctor: dict = Depends(require_doctor)):
    # Construct a gorgeous Telegram alert for the ambulance!
    maps_url = f"https://maps.google.com/?q={payload.lat},{payload.lng}"
    
    icon = "🚨"
    hr_text = f"\nHR      : {payload.heart_rate} bpm" if payload.heart_rate else ""
    status_text = f"\nStatus  : {payload.prediction}" if payload.prediction else ""
    
    message = (
        f"🚑 **AMBULANCE DISPATCH REQUEST** 🚑\n"
        f"{'─' * 30}\n"
        f"**Authorized by:** Dr. Vargas\n"
        f"**Patient:** {payload.patient_name} ({payload.patient_id})\n"
        f"{status_text}{hr_text}\n"
        f"**Location:** {payload.lat:.6f}, {payload.lng:.6f}\n\n"
        f"🗺️ **Google Maps (Click to Navigate):**\n"
        f"{maps_url}\n\n"
        f"⚠️ *Drive safely. Tap the link to launch navigation instantly.*"
    )
    
    # Send both: native location card and direct navigation button message
    if telegram_bot and firebase_db:
        try:
            # We get the chat IDs for patient contacts
            patient_ref = firebase_db.reference(f"patients/{payload.patient_id}/contacts").get()

            dispatched_any = False
            if patient_ref:
                for role, chat_id in patient_ref.items():
                    try:
                        # 1. Send native location pin
                        await telegram_bot.send_location(chat_id=chat_id, latitude=payload.lat, longitude=payload.lng)
                        # 2. Send text message detailing the dispatch
                        await telegram_bot.send_message(chat_id=chat_id, text=message)
                        dispatched_any = True
                        log.info(f"Dispatch alert sent to {role} ({chat_id})")
                    except Exception as child_e:
                        log.error(f"Failed to send to {role} ({chat_id}): {child_e}")
            
            if not dispatched_any:
                # Fallback to test chat ID from environment variables
                test_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
                if test_chat_id:
                    await telegram_bot.send_location(chat_id=test_chat_id, latitude=payload.lat, longitude=payload.lng)
                    await telegram_bot.send_message(chat_id=test_chat_id, text=message)
                    log.info(f"Dispatch alert sent to default test chat ({test_chat_id})")
                    dispatched_any = True

            if not dispatched_any:
                log.warning("No chat IDs available for dispatch notification")
                return {"status": "warning", "message": "Ambulance dispatched, but no active Telegram chat contacts were found."}

            return {"status": "success", "message": f"Ambulance successfully dispatched for {payload.patient_name}!"}
        except Exception as e:
            log.error(f"Telegram dispatch failed: {e}")
            raise HTTPException(status_code=500, detail=f"Telegram dispatch failed: {e}")
    else:
        log.warning("Telegram bot or Firebase not configured, dispatch skipped")
        return {"status": "warning", "message": "Ambulance dispatch completed, but Telegram notification services are currently offline."}


@app.post("/analyze", response_model=PredictionResponse)
async def analyze(payload: ECGPayload, _auth: None = Depends(require_device_key)):
    t_start = time.perf_counter()

    # 1. Preprocess
    try:
        X = preprocess(payload.samples)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Preprocessing error: {e}")

    # 2. Inference (raw per-window prediction)
    outputs   = session.run(None, {INPUT_NAME: X})[0][0]
    pred_idx  = int(np.argmax(outputs))
    raw_pred  = CLASS_NAMES[pred_idx]
    raw_conf  = float(outputs[pred_idx])

    # 3. Consensus prediction (majority vote over last 10 windows)
    pred_name, confidence = get_consensus_prediction(
        payload.patient_id, raw_pred, raw_conf
    )

    inference_ms = (time.perf_counter() - t_start) * 1000

    # 4. Heart rate estimate (accumulates peaks across windows)
    hr = estimate_heart_rate(X, payload.patient_id)

    # 5. Write reading to Firebase
    if firebase_db:
        try:
            # Downsample raw ECG to 64 points for dashboard display
            raw = payload.samples
            step = max(1, len(raw) // 64)
            ecg_display = [round(float(raw[i]), 1) for i in range(0, len(raw), step)][:64]

            reading = {
                "timestamp"   : payload.timestamp,
                "device_id"   : payload.device_id,
                "heart_rate"  : hr,
                "prediction"  : pred_name,
                "confidence"  : round(confidence, 4),
                "inference_ms": round(inference_ms, 2),
                "ecg"         : ecg_display,
            }
            if payload.lat is not None:
                reading["lat"] = payload.lat
            if payload.lng is not None:
                reading["lng"] = payload.lng
            if payload.battery is not None:
                reading["battery"] = payload.battery
            firebase_db.reference(f"readings/{payload.patient_id}").push(reading)
        except Exception as e:
            log.warning(f"Firebase write failed: {e}")

    # 6. Check if an ambulance is dispatched for this patient
    ambulance_dispatched = False
    if firebase_db:
        try:
            dispatch_snap = firebase_db.reference(f"dispatches/{payload.patient_id}").get()
            if dispatch_snap and dispatch_snap.get("dispatched"):
                ambulance_dispatched = True
        except Exception as e:
            log.warning(f"Failed to check dispatch status: {e}")

    # 7. Alert if needed (uses consensus, not raw)
    alert_sent = await maybe_send_alert(
        payload.patient_id, pred_name, confidence, hr, payload.timestamp
    )

    log.info(
        f"[{payload.device_id}] {raw_pred}→{pred_name} ({confidence*100:.1f}%) "
        f"| HR: {hr} bpm | {inference_ms:.1f}ms | alert={alert_sent} | dispatched={ambulance_dispatched}"
    )

    return PredictionResponse(
        prediction     = pred_name,
        confidence     = round(confidence, 4),
        heart_rate_bpm = hr,
        probabilities  = {CLASS_NAMES[i]: round(float(outputs[i]), 4) for i in range(3)},
        alert_sent     = alert_sent,
        inference_ms   = round(inference_ms, 2),
        ambulance_dispatched = ambulance_dispatched,
    )

# ─── Ghost Patient Simulator (patient_003) ────────────────────────────────────
# Generates simulated ECG data every 5 seconds so the demo patient is always
# "online" on the dashboard. Runs as an asyncio background task on startup.
import asyncio, math, random, datetime

GHOST_PATIENT_ID = "patient_003"
GHOST_DEVICE_ID  = "cg_003"
GHOST_INTERVAL   = 5   # seconds between readings
GHOST_LAT        = 14.5995
GHOST_LNG        = 120.9842

# The ghost patient is a demo stream, not a record worth keeping: consumers
# only ever read the newest few readings. Without a cap, push() at 5s adds
# ~17k keys/day (~14 MB) forever, which is what exhausted the 1 GB Realtime
# Database quota and disabled the database. Keeping a fixed window instead
# holds ghost storage at a constant ~25 KB.
GHOST_KEEP_READINGS = 30   # ~2.5 minutes of history
GHOST_KEEP_ALERTS   = 20


def _trim_ghost_node(path: str, keep: int) -> tuple[int, list[str]]:
    """Delete all but the newest `keep` children under `path`.

    Runs once at startup to clear anything left behind by earlier runs or
    restarts, which the in-process ring cannot know about. Push IDs sort
    chronologically, so a plain sort is oldest-first.

    Returns (deleted_count, surviving_keys) so the caller can hand the
    survivors to the ring; otherwise they would sit there untracked forever.
    """
    ref = firebase_db.reference(path)
    keys = ref.get(shallow=True)
    if not keys:
        return 0, []

    ordered = sorted(keys)
    stale, survivors = ordered[:-keep], ordered[-keep:]
    # Chunked so a large backlog cannot produce one oversized request.
    for i in range(0, len(stale), 500):
        ref.update({k: None for k in stale[i:i + 500]})
    return len(stale), survivors

def _generate_ghost_ecg(hr: int, noise: float = 25.0) -> list[float]:
    """Generate a realistic 64-point ECG window."""
    pts = []
    for i in range(64):
        x = (i / 64) * 2
        y = 0
        y += 80  * math.exp(-((x - 0.24) / 0.07)**2)    # P wave
        y -= 60  * math.exp(-((x - 0.58) / 0.024)**2)   # Q dip
        y += 500 * math.exp(-((x - 0.66) / 0.022)**2)   # R peak
        y -= 110 * math.exp(-((x - 0.74) / 0.024)**2)   # S dip
        y += 180 * math.exp(-((x - 1.16) / 0.11)**2)    # T wave
        y += random.gauss(0, noise)
        pts.append(round(y + 2048, 1))
    return pts

async def _ghost_patient_loop():
    """Background loop that pushes simulated data for patient_003."""
    if not firebase_db:
        log.info("Ghost patient disabled — no Firebase connection")
        return

    log.info(f"Ghost patient simulator started for {GHOST_PATIENT_ID}")
    base_hr = 72
    ghost_battery = 98.0

    reading_keys: deque[str] = deque()
    alert_keys: deque[str] = deque()

    # One-off sweep for keys left by previous runs, seeding the rings with the
    # survivors so every key is accounted for. After this the rings keep both
    # nodes bounded without ever listing them again.
    try:
        removed_r, survivors_r = _trim_ghost_node(
            f"readings/{GHOST_PATIENT_ID}", GHOST_KEEP_READINGS)
        removed_a, survivors_a = _trim_ghost_node(
            f"alerts/{GHOST_PATIENT_ID}", GHOST_KEEP_ALERTS)
        reading_keys.extend(survivors_r)
        alert_keys.extend(survivors_a)
        if removed_r or removed_a:
            log.info(
                f"[GHOST] Startup trim removed {removed_r} reading(s) "
                f"and {removed_a} alert(s)")
    except Exception as e:
        # A disabled or over-quota database must not stop the service booting.
        log.warning(f"[GHOST] Startup trim skipped: {e}")

    while True:
        try:
            await asyncio.sleep(GHOST_INTERVAL)

            # Slowly decay battery (0.25% every 5s loop, reset at 25%)
            ghost_battery -= 0.25
            if ghost_battery < 25.0:
                ghost_battery = 98.0

            # Simulate realistic heart rate with gradual drift + occasional spike
            drift = math.sin(time.time() / 120) * 8       # slow ~2min cycle
            jitter = random.gauss(0, 3)                     # beat-to-beat variation
            hr = int(base_hr + drift + jitter)
            hr = max(55, min(hr, 110))                      # clamp to realistic range

            # 5% chance of arrhythmia event
            is_arrhythmia = random.random() < 0.05
            if is_arrhythmia:
                hr = random.randint(130, 165)
                prediction = "Arrhythmia"
                confidence = round(random.uniform(0.82, 0.96), 4)
                noise = 60
            else:
                prediction = "Normal"
                confidence = round(random.uniform(0.90, 0.99), 4)
                noise = 25

            ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
            ecg = _generate_ghost_ecg(hr, noise)

            # Push reading, then drop the oldest so the window stays fixed
            readings_ref = firebase_db.reference(f"readings/{GHOST_PATIENT_ID}")
            reading_keys.append(readings_ref.push({
                "timestamp"   : ts,
                "device_id"   : GHOST_DEVICE_ID,
                "heart_rate"  : hr,
                "prediction"  : prediction,
                "confidence"  : confidence,
                "inference_ms": round(random.uniform(8, 18), 2),
                "lat"         : GHOST_LAT,
                "lng"         : GHOST_LNG,
                "ecg"         : ecg,
                "battery"     : int(ghost_battery),
            }).key)
            while len(reading_keys) > GHOST_KEEP_READINGS:
                readings_ref.child(reading_keys.popleft()).delete()

            # Push alert if arrhythmia
            if is_arrhythmia:
                alerts_ref = firebase_db.reference(f"alerts/{GHOST_PATIENT_ID}")
                alert_keys.append(alerts_ref.push({
                    "type": "Arrhythmia",
                    "confidence": confidence,
                    "heart_rate": hr,
                    "timestamp": ts,
                    "acknowledged": False,
                }).key)
                while len(alert_keys) > GHOST_KEEP_ALERTS:
                    alerts_ref.child(alert_keys.popleft()).delete()
                log.info(f"[GHOST] 🚨 Arrhythmia | HR: {hr} | conf: {confidence}")
            else:
                log.debug(f"[GHOST] ✓ Normal | HR: {hr}")

        except Exception as e:
            log.warning(f"[GHOST] Error: {e}")
            await asyncio.sleep(10)

@app.on_event("startup")
async def start_ghost_patient():
    asyncio.create_task(_ghost_patient_loop())

# ─── Run locally ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
