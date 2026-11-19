import { useState, useEffect } from 'react';
import { ref, onValue, set } from 'firebase/database';
import { db, auth } from '../firebase';

function fmtTime(ts) {
  if (!ts) return 'N/A';
  try {
    return new Date(ts).toLocaleTimeString('en-PH', {
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  } catch { return ts; }
}

export default function LocationPanel({ lat, lng, timestamp, patientId, patientName, heartRate, prediction }) {
  const [copied, setCopied] = useState(false);
  const [dispatchStatus, setDispatchStatus] = useState(null);
  const [dispatching, setDispatching] = useState(false);

  const hasData  = lat != null && lng != null;
  const mapsUrl  = hasData
    ? `https://maps.google.com/?q=${lat},${lng}`
    : null;
  const coordStr = hasData
    ? `${lat.toFixed(6)}, ${lng.toFixed(6)}`
    : null;

  const isDispatched = dispatchStatus?.dispatched === true;

  // Real-time listener for dispatch status in Firebase database
  useEffect(() => {
    if (!patientId) return;
    const dispatchRef = ref(db, `dispatches/${patientId}`);
    const unsub = onValue(dispatchRef, (snap) => {
      if (snap.exists()) {
        setDispatchStatus(snap.val());
      } else {
        setDispatchStatus(null);
      }
    });
    return unsub;
  }, [patientId]);

  function handleCopy() {
    if (!coordStr) return;
    navigator.clipboard.writeText(coordStr).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  async function handleDispatch() {
    if (!patientId || !hasData || dispatching || isDispatched) return;

    if (!window.confirm(`Are you sure you want to dispatch an emergency ambulance to this patient's current coordinates (${coordStr})?`)) {
      return;
    }

    setDispatching(true);
    try {
      // Direct POST request to FastAPI backend dispatch endpoint
      const apiUrl = import.meta.env.VITE_CLOUD_API_URL || 'https://cardioguard-api-production-c451.up.railway.app';
      // The API verifies this Firebase ID token to confirm a signed-in doctor is asking.
      const user = auth.currentUser;
      if (!user) throw new Error('You must be signed in to dispatch an ambulance');
      const token = await user.getIdToken();

      const response = await fetch(`${apiUrl}/dispatch`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          patient_id: patientId,
          patient_name: patientName || patientId,
          lat: lat,
          lng: lng,
          heart_rate: heartRate || null,
          prediction: prediction || null
        }),
      });

      if (!response.ok) {
        throw new Error(`Server returned error code: ${response.status}`);
      }

      // Write active dispatch state directly to Firebase database so it synchronizes on all dashboards
      const dispatchRef = ref(db, `dispatches/${patientId}`);
      await set(dispatchRef, {
        dispatched: true,
        dispatched_at: new Date().toISOString(),
        lat: lat,
        lng: lng
      });

    } catch (err) {
      console.error('Failed to dispatch ambulance:', err);
      alert(`Failed to dispatch ambulance via Telegram: ${err.message}. The command has been logged.`);
    } finally {
      setDispatching(false);
    }
  }

  async function handleClearDispatch() {
    if (!patientId) return;
    if (window.confirm("Mark this emergency ambulance dispatch as resolved/completed?")) {
      const dispatchRef = ref(db, `dispatches/${patientId}`);
      await set(dispatchRef, null); // Deletes record, reverting UI to standard status
    }
  }

  return (
    <div className="card location-panel grid-location">
      <div className="card-header">
        <span className="card-title">Patient Location</span>
        {hasData && <span className="card-badge">GPS</span>}
      </div>

      <div className="location-coords">
        <div className="coord-row">
          <span className="coord-label">Latitude</span>
          <span className={`coord-value ${!hasData ? 'no-data' : ''}`}>
            {hasData ? lat.toFixed(6) : 'No data'}
          </span>
        </div>
        <div className="coord-row">
          <span className="coord-label">Longitude</span>
          <span className={`coord-value ${!hasData ? 'no-data' : ''}`}>
            {hasData ? lng.toFixed(6) : 'No data'}
          </span>
        </div>
      </div>

      <div className="location-actions">
        {hasData ? (
          <a
            id="btn-open-maps"
            href={mapsUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-maps"
          >
            Open in Maps
          </a>
        ) : (
          <span className="btn-maps disabled">No location data</span>
        )}
        <button
          id="btn-copy-coords"
          className={`btn-copy ${copied ? 'copied' : ''}`}
          onClick={handleCopy}
          disabled={!hasData}
          title="Copy coordinates"
        >
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>

      {/* Ambulance Dispatch Button & Real-time Alert Banner */}
      {hasData && (
        <div style={{
          marginTop: '14px',
          borderTop: '1px solid var(--border)',
          paddingTop: '14px',
        }}>
          {isDispatched ? (
            <div style={{
              background: 'var(--red-dim)',
              border: '1px solid rgba(229, 62, 62, 0.2)',
              borderRadius: 'var(--radius)',
              padding: '12px',
              display: 'flex',
              flexDirection: 'column',
              gap: '6px',
            }}>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                fontSize: '12px',
                fontWeight: 500,
                color: 'var(--accent)',
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
              }}>
                <span style={{
                  width: '8px',
                  height: '8px',
                  borderRadius: '50%',
                  background: 'var(--accent)',
                  animation: 'pulse-dot 1.5s infinite',
                }} />
                Ambulance Dispatch Active
              </div>
              <p style={{
                margin: 0,
                fontSize: '11px',
                color: 'var(--text-secondary)',
              }}>
                Emergency response requested at: <strong style={{ color: 'var(--text-primary)' }}>{fmtTime(dispatchStatus?.dispatched_at)}</strong>
              </p>
              <button
                className="btn-clear-dispatch"
                onClick={handleClearDispatch}
                style={{
                  marginTop: '4px',
                  background: 'none',
                  border: 'none',
                  color: 'var(--teal)',
                  fontSize: '11px',
                  textDecoration: 'underline',
                  cursor: 'pointer',
                  textAlign: 'left',
                  padding: 0,
                  fontFamily: 'inherit',
                }}
              >
                Mark as Resolved / Cancel
              </button>
            </div>
          ) : (
            <button
              id="btn-dispatch-ambulance"
              onClick={handleDispatch}
              disabled={dispatching}
              style={{
                width: '100%',
                padding: '9px 14px',
                borderRadius: 'var(--radius)',
                border: '1px solid var(--accent)',
                background: 'transparent',
                color: 'var(--accent)',
                fontWeight: 500,
                cursor: dispatching ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                fontSize: '12px',
                fontFamily: 'inherit',
                letterSpacing: '0.02em',
                transition: 'background 150ms ease',
                opacity: dispatching ? 0.5 : 1,
              }}
              onMouseOver={(e) => { if (!dispatching) e.target.style.background = 'var(--red-dim)'; }}
              onMouseOut={(e) => { if (!dispatching) e.target.style.background = 'transparent'; }}
            >
              {dispatching ? 'Dispatching...' : 'Dispatch Ambulance'}
            </button>
          )}
        </div>
      )}

      {timestamp && (
        <p className="location-last-seen" style={{ marginTop: 12 }}>
          Last updated: {fmtTime(timestamp)}
        </p>
      )}

      {!hasData && (
        <p style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', marginTop: 12 }}>
          Location will appear when GPS data is received from the device
        </p>
      )}
    </div>
  );
}
