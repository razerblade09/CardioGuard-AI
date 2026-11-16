export default function HRCard({ heartRate, lastSeen }) {
  const hr   = heartRate ?? '--';
  const zone = heartRate
    ? heartRate < 60 ? 'Bradycardia'
    : heartRate > 100 ? 'Tachycardia'
    : 'Normal Sinus'
    : 'Awaiting data';

  // Status dot color based on heart rate zone
  const dotColor = heartRate
    ? heartRate < 60 || heartRate > 100 ? 'var(--amber)' : 'var(--teal)'
    : 'var(--text-muted)';

  return (
    <div className="card hr-card grid-hr">
      <span className="card-title" style={{ marginBottom: 8 }}>Heart Rate</span>

      {/* Teal heart SVG with heartbeat animation */}
      <svg className="hr-heart-svg" viewBox="0 0 100 90" width="64" height="58" style={{ overflow: 'visible' }}>
        <path
          d="M50 82 C 20 60, 4 40, 4 24 C 4 8, 18 2, 30 8 C 38 12, 46 20, 50 28 C 54 20, 62 12, 70 8 C 82 2, 96 8, 96 24 C 96 40, 80 60, 50 82 Z"
          fill="none"
          stroke="var(--teal)"
          strokeWidth="3.5"
          strokeLinejoin="round"
        />
      </svg>

      <span className="hr-value">{hr}</span>
      <span className="hr-unit">BPM</span>

      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '4px' }}>
        <span style={{
          width: '6px',
          height: '6px',
          borderRadius: '50%',
          background: dotColor,
          flexShrink: 0,
        }} />
        <span className="hr-status-text">{zone}</span>
      </div>

      {lastSeen && (
        <span style={{
          fontSize: 10,
          color: 'var(--text-muted)',
          fontFamily: 'JetBrains Mono, monospace',
          marginTop: 4,
        }}>
          {lastSeen}
        </span>
      )}
    </div>
  );
}
