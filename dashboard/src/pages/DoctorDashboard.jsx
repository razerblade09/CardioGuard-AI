import { useEffect, useRef, useState } from 'react';
import { ref, onValue, query, limitToLast, orderByKey } from 'firebase/database';
import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid,
} from 'recharts';
import { auth, db } from '../firebase';
import Navbar        from '../components/Navbar';
import ECGChart      from '../components/ECGChart';
import HRCard        from '../components/HRCard';
import PredictionCard from '../components/PredictionCard';
import AlertFeed     from '../components/AlertFeed';
import LocationPanel from '../components/LocationPanel';

// ── Patient list (extend as needed) ──────────────────
const PATIENTS = [
  { id: 'patient_001', name: 'Patient 001' },
  { id: 'patient_002', name: 'Patient 002' },
  { id: 'patient_003', name: 'Patient 003 (Demo)' },
];

function fmtTimestamp(ts) {
  if (!ts) return null;
  try {
    return new Date(ts).toLocaleTimeString('en-PH', {
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  } catch { return ts; }
}

function timeSince(ts, serverOffset = 0) {
  if (!ts) return null;
  const diff = Math.floor(((Date.now() + serverOffset) - new Date(ts).getTime()) / 1000);
  if (diff < 5)  return 'just now';
  if (diff < 60) return `${diff}s ago`;
  return `${Math.floor(diff / 60)}m ago`;
}

// Per-point dot for HR trend — red accent when that reading was non-Normal.
// (Recharts draws the line itself as one path; coloring individual dots is the
//  simple, low-risk way to flag abnormal readings without a custom path engine.)
function TrendDot({ cx, cy, payload }) {
  if (cx == null || cy == null) return null;
  const abnormal = payload?.status && payload.status !== 'Normal';
  return (
    <circle
      cx={cx}
      cy={cy}
      r={abnormal ? 3 : 2}
      fill={abnormal ? 'var(--accent)' : 'var(--teal)'}
    />
  );
}

// Custom tooltip for HR trend chart
function TrendTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: 'var(--bg-surface)', border: '1px solid var(--border)',
      borderRadius: 4, padding: '6px 12px', fontSize: 12,
    }}>
      <span style={{ color: 'var(--teal)' }}>{payload[0].value} BPM</span>
    </div>
  );
}

export default function DoctorDashboard() {
  const [selectedPatient, setSelectedPatient] = useState(PATIENTS[0].id);

  // Latest reading
  const [heartRate,    setHeartRate]    = useState(null);
  const [prediction,   setPrediction]   = useState(null);
  const [confidence,   setConfidence]   = useState(null);
  const [inferenceMs,  setInferenceMs]  = useState(null);
  const [lat,          setLat]          = useState(null);
  const [lng,          setLng]          = useState(null);
  const [lastTs,       setLastTs]       = useState(null);
  const [isLive,       setIsLive]       = useState(false);
  const [deviceId,     setDeviceId]     = useState('--');
  const [battery,      setBattery]      = useState(null);

  // Alert log
  const [alerts, setAlerts] = useState([]);

  // HR trend (last 30 readings)
  const [hrTrend, setHrTrend] = useState([]);

  // Real ECG samples from Firebase (array of 64-point windows)
  const [ecgSamples, setEcgSamples] = useState([]);
  // Per-window prediction label aligned 1:1 with ecgSamples (window-level granularity)
  const [ecgLabels, setEcgLabels] = useState([]);

  // Server time offset to correct for clock skew
  const [serverOffset, setServerOffset] = useState(0);
  const [tick, setTick] = useState(0);
  const latestTsMsRef = useRef(0);

  // ── Sync server offset ──────────────────────────────
  useEffect(() => {
    const offsetRef = ref(db, ".info/serverTimeOffset");
    const unsub = onValue(offsetRef, (snap) => {
      const val = snap.val() || 0;
      console.log("[Firebase] serverTimeOffset updated:", val);
      setServerOffset(val);
    });
    return () => unsub();
  }, []);

  // ── Periodic freshness checker (every 5s) ──────────
  useEffect(() => {
    const interval = setInterval(() => {
      setTick(t => t + 1);
      const nowEstimated = Date.now() + serverOffset;
      const age = nowEstimated - latestTsMsRef.current;
      console.log("[Freshness] age:", age, "isLive:", age < 45000, "latestTsMs:", latestTsMsRef.current);
      setIsLive(age < 45000); // live if data is < 45s old
    }, 5000);
    return () => clearInterval(interval);
  }, [serverOffset]);

  // ── Firebase listener: latest readings ─────────────
  useEffect(() => {
    console.log("[Firebase] Subscribing to readings for patient:", selectedPatient);
    const readRef = query(
      ref(db, `readings/${selectedPatient}`),
      orderByKey(),
      limitToLast(30)
    );

    // Reset live state when switching patients
    latestTsMsRef.current = 0;
    setIsLive(false);

    const unsub = onValue(readRef, (snap) => {
      let childCount = 0;
      snap.forEach(() => { childCount++; });
      console.log("[Firebase] onValue snapshot details:", snap.key, "exists:", snap.exists(), "children:", childCount);
      if (!snap.exists()) {
        setHeartRate(null);
        setPrediction(null);
        setConfidence(null);
        setInferenceMs(null);
        setLat(null);
        setLng(null);
        setLastTs(null);
        setDeviceId('--');
        setBattery(null);
        setHrTrend([]);
        setEcgSamples([]);
        setEcgLabels([]);
        return;
      }

      const entries = [];
      snap.forEach(child => {
        entries.push(child.val());
      });
      console.log("[Firebase] parsed entries length:", entries.length);

      // Most recent
      const latest = entries[entries.length - 1];
      if (latest) {
        console.log("[Firebase] latest reading details:", latest);
        setHeartRate(latest.heart_rate ?? null);
        setPrediction(latest.prediction ?? null);
        setConfidence(latest.confidence ?? null);
        setInferenceMs(latest.inference_ms ?? null);
        setLat(latest.lat ?? null);
        setLng(latest.lng ?? null);
        setLastTs(latest.timestamp ?? null);
        setDeviceId(latest.device_id ?? '--');
        setBattery(latest.battery ?? null);

        // Parse timestamp and update ref + live state immediately
        const tsRaw = latest.timestamp;
        const tsMs  = tsRaw
          ? (typeof tsRaw === 'number' ? tsRaw : new Date(tsRaw).getTime())
          : 0;
        if (!isNaN(tsMs) && tsMs > 0) {
          latestTsMsRef.current = tsMs;
        }
        const nowEstimated = Date.now() + serverOffset;
        const dataAge = nowEstimated - latestTsMsRef.current;
        console.log("[Firebase] dataAge calculated immediately:", dataAge, "isLive:", dataAge < 45000);
        setIsLive(dataAge < 45000);
      }

      // HR trend
      const trend = entries
        .filter(e => e.heart_rate != null)
        .map(e => ({
          bpm:    e.heart_rate,
          t:      fmtTimestamp(e.timestamp) ?? '',
          status: e.prediction ?? null,   // for per-point dot coloring
        }));
      console.log("[Firebase] setting hrTrend length:", trend.length);
      setHrTrend(trend);

      // Collect ECG samples (last 6 windows = ~6 seconds of data).
      // Keep the per-window prediction label aligned 1:1 so the chart can
      // color each window's segment (window-level granularity — see backend).
      const ecgEntries = entries
        .filter(e => e.ecg && Array.isArray(e.ecg))
        .slice(-6);
      setEcgSamples(ecgEntries.map(e => e.ecg));
      setEcgLabels(ecgEntries.map(e => e.prediction ?? null));
    });

    return () => {
      console.log("[Firebase] Unsubscribed from readings for patient:", selectedPatient);
      unsub();
    };
  }, [selectedPatient, serverOffset]);

  // ── Firebase listener: alerts ───────────────────────
  useEffect(() => {
    const alertRef = query(
      ref(db, `alerts/${selectedPatient}`),
      orderByKey(),
      limitToLast(20)
    );

    const unsub = onValue(alertRef, (snap) => {
      if (!snap.exists()) { setAlerts([]); return; }
      const arr = [];
      snap.forEach(child => arr.push({ key: child.key, ...child.val() }));
      setAlerts(arr);
    });

    return unsub;
  }, [selectedPatient]);

  const patientName = PATIENTS.find(p => p.id === selectedPatient)?.name ?? selectedPatient;

  return (
    <>
      <Navbar user={auth.currentUser} />

      <main className="dashboard">

        {/* ── Status Bar ────────────────────────────── */}
        <div className="status-bar">
          <div className="patient-select-wrapper">
            <span className="patient-select-label">Patient</span>
            <select
              id="patient-selector"
              className="patient-select"
              value={selectedPatient}
              onChange={e => setSelectedPatient(e.target.value)}
            >
              {PATIENTS.map(p => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>

          <div className={`status-pill ${isLive ? 'live' : 'offline'}`}>
            <span className={`status-dot ${isLive ? 'pulse' : ''}`} />
            {isLive ? `Live · ${timeSince(lastTs, serverOffset)}` : 'Offline'}
          </div>

          {deviceId !== '--' && (
            <span className="status-chip">{deviceId}</span>
          )}

          {battery !== null && (
            <span className="status-chip" style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                style={{
                  color: battery > 25 ? 'var(--teal)' : battery > 15 ? 'var(--amber)' : 'var(--accent)',
                  marginRight: '2px'
                }}
              >
                <rect x="2" y="7" width="16" height="10" rx="2" ry="2" />
                <line x1="22" y1="11" x2="22" y2="13" />
                <rect x="4" y="9" width={Math.max(1, (12 * battery) / 100)} height="6" fill="currentColor" stroke="none" />
              </svg>
              {battery}%
            </span>
          )}
        </div>

        {/* ── Main Grid ─────────────────────────────── */}
        <div className="dashboard-grid">

          {/* ECG Waveform */}
          <ECGChart heartRate={heartRate} ecgSamples={ecgSamples} ecgLabels={ecgLabels} isLive={isLive} />

          {/* Heart Rate */}
          <HRCard
            heartRate={heartRate}
            lastSeen={timeSince(lastTs, serverOffset)}
          />

          {/* AI Prediction */}
          <PredictionCard
            prediction={prediction}
            confidence={confidence}
            inferenceMs={inferenceMs}
          />

          {/* HR Trend Chart */}
          <div className="card trend-panel grid-trend">
            <div className="card-header">
              <span className="card-title">Heart Rate Trend (Last 30 readings)</span>
              {heartRate && (
                <span style={{
                  fontSize: 11,
                  color: 'var(--text-secondary)',
                  fontFamily: 'JetBrains Mono, monospace',
                  fontVariantNumeric: 'tabular-nums',
                }}>
                  Current: {heartRate} BPM
                </span>
              )}
            </div>
            <div className="trend-chart-wrapper">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={hrTrend} margin={{ top: 4, right: 8, bottom: 0, left: -10 }}>
                  <CartesianGrid stroke="rgba(30,45,61,0.6)" strokeDasharray="3 3" />
                  <XAxis dataKey="t" tick={{ fontSize: 9, fill: 'var(--text-muted)' }} interval="preserveStartEnd" />
                  <YAxis domain={[dataMin => Math.max(40, dataMin - 10), dataMax => dataMax + 10]} tickCount={4} tick={{ fontSize: 10, fill: 'var(--text-muted)' }} />
                  <Tooltip content={<TrendTooltip />} />
                  <Line
                    type="monotone"
                    dataKey="bpm"
                    stroke="var(--teal)"
                    strokeWidth={1.5}
                    dot={<TrendDot />}
                    activeDot={{ r: 4, fill: 'var(--teal)' }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Alert Feed */}
          <AlertFeed alerts={alerts} patientId={selectedPatient} />

          {/* Location */}
          <LocationPanel
            lat={lat}
            lng={lng}
            timestamp={lastTs}
            patientId={selectedPatient}
            patientName={patientName}
            heartRate={heartRate}
            prediction={prediction}
          />


        </div>
      </main>
    </>
  );
}
