import { useState } from 'react';
import { ref, update } from 'firebase/database';
import { db } from '../firebase';

function fmtTime(ts) {
  if (!ts) return '';
  try {
    return new Date(ts).toLocaleTimeString('en-PH', {
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  } catch {
    return ts;
  }
}

const META = {
  Arrhythmia: { cls: 'arrhythmia' },
  'At-Risk':  { cls: 'at-risk'   },
  Normal:     { cls: 'normal'     },
};

// Small dot colors for alert severity
const DOT_COLORS = {
  arrhythmia: 'var(--accent)',
  'at-risk':  'var(--amber)',
  normal:     'var(--green)',
};

export default function AlertFeed({ alerts, patientId }) {
  const sorted = [...(alerts ?? [])].reverse(); // newest first
  const [expandedKey, setExpandedKey] = useState(null);
  const [noteText, setNoteText] = useState('');
  const [saving, setSaving] = useState(false);

  const unacknowledgedCount = sorted.filter(a => !a.acknowledged).length;

  // Mark alert as acknowledged in Firebase
  function handleAcknowledge(alertKey) {
    if (!patientId || !alertKey) return;
    const alertRef = ref(db, `alerts/${patientId}/${alertKey}`);
    update(alertRef, {
      acknowledged: true,
      acknowledged_at: new Date().toISOString(),
    });
  }

  // Save doctor's note to Firebase
  function handleSaveNote(alertKey) {
    if (!patientId || !alertKey || !noteText.trim()) return;
    setSaving(true);
    const alertRef = ref(db, `alerts/${patientId}/${alertKey}`);
    update(alertRef, {
      doctor_note: noteText.trim(),
      acknowledged: true,
      acknowledged_at: new Date().toISOString(),
    }).then(() => {
      setSaving(false);
      setExpandedKey(null);
      setNoteText('');
    });
  }

  // Toggle expand for notes
  function toggleExpand(key, existingNote) {
    if (expandedKey === key) {
      setExpandedKey(null);
      setNoteText('');
    } else {
      setExpandedKey(key);
      setNoteText(existingNote || '');
    }
  }

  return (
    <div className="card alert-feed grid-alerts">
      <div className="card-header">
        <span className="card-title">Alerts</span>
        {unacknowledgedCount > 0 && (
          <span className="card-badge alert-count-badge">{unacknowledgedCount} new</span>
        )}
      </div>

      <div className="alert-list" id="alert-list">
        {sorted.length === 0 ? (
          <p className="alert-empty">No alerts recorded yet</p>
        ) : (
          sorted.map((a) => {
            const m = META[a.type] ?? META.Normal;
            const isExpanded = expandedKey === a.key;
            const dotColor = DOT_COLORS[m.cls] ?? 'var(--text-muted)';

            return (
              <div
                key={a.key}
                className={`alert-item ${m.cls} ${a.acknowledged ? 'ack' : 'unack'}`}
              >
                {/* Main alert row */}
                <div className="alert-row">
                  <span className="alert-icon" style={{
                    width: '8px',
                    height: '8px',
                    borderRadius: '50%',
                    background: dotColor,
                    fontSize: 0,
                    display: 'inline-block',
                  }} />
                  <div className="alert-body">
                    <div className={`alert-type ${m.cls}`}>
                      {a.type}
                      {a.heart_rate && (
                        <span className="alert-hr"> · {a.heart_rate} BPM</span>
                      )}
                    </div>
                    <div className="alert-meta">
                      {fmtTime(a.timestamp)}
                      {a.acknowledged && <span className="alert-ack-badge">Reviewed</span>}
                    </div>
                  </div>

                  {/* Action buttons */}
                  <div className="alert-actions">
                    {a.confidence != null && (
                      <span className="alert-conf">
                        {Math.round(a.confidence * 100)}%
                      </span>
                    )}
                    {!a.acknowledged && (
                      <button
                        className="btn-ack"
                        onClick={() => handleAcknowledge(a.key)}
                        title="Mark as reviewed"
                      >
                        ✓
                      </button>
                    )}
                    <button
                      className={`btn-note ${isExpanded ? 'active' : ''}`}
                      onClick={() => toggleExpand(a.key, a.doctor_note)}
                      title="Add doctor's note"
                    >
                      +
                    </button>
                  </div>
                </div>

                {/* Doctor's existing note */}
                {a.doctor_note && !isExpanded && (
                  <div className="alert-doctor-note">
                    <span className="note-label">Note:</span> {a.doctor_note}
                  </div>
                )}

                {/* Expanded note editor */}
                {isExpanded && (
                  <div className="alert-note-editor">
                    <textarea
                      className="note-input"
                      placeholder="Write your clinical assessment..."
                      value={noteText}
                      onChange={(e) => setNoteText(e.target.value)}
                      rows={3}
                    />
                    <div className="note-actions">
                      <button
                        className="btn-save-note"
                        onClick={() => handleSaveNote(a.key)}
                        disabled={saving || !noteText.trim()}
                      >
                        {saving ? 'Saving...' : 'Save & Acknowledge'}
                      </button>
                      <button
                        className="btn-cancel-note"
                        onClick={() => { setExpandedKey(null); setNoteText(''); }}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
