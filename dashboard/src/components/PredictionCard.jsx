const STATES = {
  Normal:      { cls: 'normal',      label: 'Normal Sinus Rhythm' },
  Arrhythmia:  { cls: 'arrhythmia',  label: 'Arrhythmia Detected' },
  'At-Risk':   { cls: 'at-risk',     label: 'At-Risk — Monitor Closely' },
  default:     { cls: 'init',        label: 'Awaiting prediction…' },
};

// Small colored status dot instead of emoji icons
const DOT_COLORS = {
  normal:     'var(--green)',
  arrhythmia: 'var(--accent)',
  'at-risk':  'var(--amber)',
  init:       'var(--text-muted)',
};

export default function PredictionCard({ prediction, confidence, inferenceMs }) {
  const state = STATES[prediction] ?? STATES.default;
  const pct   = confidence != null ? Math.round(confidence * 100) : null;
  const dotColor = DOT_COLORS[state.cls] ?? 'var(--text-muted)';

  return (
    <div className="card prediction-card grid-prediction">
      <div className="card-header">
        <span className="card-title">AI Prediction</span>
      </div>

      <div className="prediction-status">
        <span style={{
          width: '10px',
          height: '10px',
          borderRadius: '50%',
          background: dotColor,
          flexShrink: 0,
        }} />
        <div>
          <div className={`prediction-label ${state.cls}`}>
            {prediction ?? 'Initializing'}
          </div>
          <div className="prediction-sublabel">{state.label}</div>
        </div>
      </div>

      {pct != null && (
        <div className="confidence-bar-wrapper">
          <div className="confidence-bar-label">
            <span>Confidence</span>
            <span>{pct}%</span>
          </div>
          <div className="confidence-bar-track">
            <div
              className={`confidence-bar-fill ${state.cls}`}
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      )}

      {inferenceMs != null && (
        <div className="inference-time">
          {inferenceMs.toFixed(1)} ms inference
        </div>
      )}
    </div>
  );
}
