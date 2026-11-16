import { useEffect, useRef } from 'react';

/**
 * ECGChart — Smooth continuously-scrolling ECG waveform
 * ======================================================
 * Renders a raw SVG polyline that scrolls left like a hospital monitor.
 *
 * Architecture:
 *   1. Firebase pushes 64-point ECG windows every ~5 seconds
 *   2. New points are ENQUEUED (not plotted instantly)
 *   3. The rAF loop EMITS one point every 75ms from the queue
 *      → 64 pts × 75ms = 4.8s of smooth drawing per burst
 *   4. All coordinates are VIEWPORT-RELATIVE (not world-space):
 *      newest point = right edge, oldest = left edge
 *   5. Between emissions, a sub-pixel interpolation offset slides
 *      ALL points smoothly to the left at ~60fps
 *
 * Result: continuous, butter-smooth left-scrolling motion with zero
 * viewBox manipulation, zero jumps, and zero snapping.
 */

const SVG_H       = 130;
const Y_MID       = SVG_H / 2;
const Y_AMP       = SVG_H / 2 - 10;
const PX_PER_PT   = 2;       // px between consecutive samples
const EMIT_MS     = 75;      // emit 1 point every 75ms
const MAX_BUF     = 500;     // max points kept in display buffer

const NORM_COLOR    = 'var(--teal, #00B5A4)';     // normal rhythm
const ABN_COLOR     = 'var(--accent, #E53E3E)';   // matches dashboard alert red
const OFFLINE_COLOR = 'var(--border, #1E2D3D)';

// A reading window is "abnormal" when its consensus prediction is anything
// other than Normal (Arrhythmia / At-Risk both alert in the backend).
function isAbnormal(label) {
  return !!label && label !== 'Normal' && label !== 'Normal Sinus Rhythm';
}

export default function ECGChart({ heartRate, ecgSamples, ecgLabels, isLive }) {
  const containerRef = useRef(null);
  const svgRef       = useRef(null);
  const groupRef     = useRef(null);   // <g> holding the pooled segment polylines
  const polyPool     = useRef([]).current;  // reused polyline DOM nodes (no per-frame alloc)
  const rafRef       = useRef(null);

  // All mutable state in a single ref — no React re-renders needed
  const S = useRef({
    buf: [],           // display buffer of normalized values (newest at end)
    queue: [],         // incoming points waiting to be emitted
    lastEmit: 0,       // perf timestamp of last emission
    lastFrame: null,   // previous rAF timestamp
    prevFP: '',        // fingerprint of last seen window (for diffing)
    seeded: false,     // whether initial data has been placed
    w: 800,            // container width (measured)
  }).current;

  const hasData = !!(ecgSamples?.length > 0 && isLive);

  /* ── Measure container width ────────────────────────────────── */
  useEffect(() => {
    const m = () => { if (containerRef.current) S.w = containerRef.current.clientWidth; };
    m();
    window.addEventListener('resize', m);
    return () => window.removeEventListener('resize', m);
  }, []);

  /* ── Helpers ─────────────────────────────────────────────────── */
  function normalize(win) {
    const mean = win.reduce((a, b) => a + b, 0) / win.length;
    const std  = Math.sqrt(win.reduce((a, b) => a + (b - mean) ** 2, 0) / win.length) || 1;
    return win.map(v => Math.max(-3, Math.min(3, (v - mean) / std)));
  }

  function fingerprint(win) {
    return win?.length ? `${win.length}:${win[0]}:${win[win.length - 1]}` : '';
  }

  /* ── Ingest new ECG data from Firebase ──────────────────────── */
  useEffect(() => {
    if (!ecgSamples || ecgSamples.length === 0) return;

    // First data: seed buffer directly (instant display, no queue delay).
    // Each sample carries its window's abnormal flag so it can be colored
    // independently as it scrolls (ab travels through queue → buffer).
    if (!S.seeded) {
      S.seeded = true;
      const all = ecgSamples.flatMap((w, i) =>
        Array.isArray(w)
          ? normalize(w).map(v => ({ v, ab: isAbnormal(ecgLabels?.[i]) }))
          : []
      );
      S.buf = all.slice(-MAX_BUF);
      S.prevFP = fingerprint(ecgSamples[ecgSamples.length - 1]);
      S.lastEmit = performance.now();
      return;
    }

    // Subsequent: only enqueue the last window if genuinely new
    const lastWin = ecgSamples[ecgSamples.length - 1];
    if (!Array.isArray(lastWin) || lastWin.length === 0) return;
    const fp = fingerprint(lastWin);
    if (fp === S.prevFP) return;
    S.prevFP = fp;

    // Tag every sample of this window with the window's prediction label
    const lastAb = isAbnormal(ecgLabels?.[ecgLabels.length - 1]);

    // Reset emit timer if queue was empty (prevents catch-up burst)
    const wasEmpty = S.queue.length === 0;
    S.queue.push(...normalize(lastWin).map(v => ({ v, ab: lastAb })));
    if (wasEmpty) S.lastEmit = performance.now();
  }, [ecgSamples, ecgLabels]);

  /* ── Reset when offline / patient switch ────────────────────── */
  useEffect(() => {
    if (!isLive) {
      S.buf = [];
      S.queue = [];
      S.lastEmit = 0;
      S.lastFrame = null;
      S.prevFP = '';
      S.seeded = false;
    }
  }, [isLive]);

  /* ── Animation loop (runs at ~60fps) ────────────────────────── */
  useEffect(() => {
    // Grab (or lazily create) the i-th pooled polyline segment.
    // Pool is reused across frames → zero DOM allocation in steady state.
    const getPoly = (i) => {
      const g = groupRef.current;
      while (polyPool.length <= i && g) {
        const el = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
        el.setAttribute('fill', 'none');
        el.setAttribute('stroke-linejoin', 'round');
        el.setAttribute('stroke-linecap', 'round');
        g.appendChild(el);
        polyPool.push(el);
      }
      return polyPool[i];
    };

    const tick = (now) => {
      S.lastFrame = now;
      const svg = svgRef.current;
      const g   = groupRef.current;

      if (!svg || !g) {
        rafRef.current = requestAnimationFrame(tick);
        return;
      }

      const w = S.w;
      let segCount = 0;  // how many pooled polylines were used this frame

      if (hasData && (S.buf.length > 0 || S.queue.length > 0)) {
        /* ── 1. Emit points from queue at steady cadence ────── */
        if (S.lastEmit === 0) S.lastEmit = now;

        // Cap emissions per frame to prevent burst catch-up
        let emitsLeft = 3;
        while (now - S.lastEmit >= EMIT_MS && S.queue.length > 0 && emitsLeft-- > 0) {
          S.buf.push(S.queue.shift());
          if (S.buf.length > MAX_BUF) S.buf.shift();
          S.lastEmit += EMIT_MS;
        }

        /* ── 2. Sub-pixel interpolation for smooth motion ───── */
        // Between emissions, smoothly slide all points left
        // frac goes from 0 → 1 over EMIT_MS, then resets on next emit
        const frac = S.queue.length > 0
          ? Math.min(1, (now - S.lastEmit) / EMIT_MS)
          : 0;  // freeze when queue empty (no sliding into void)
        const subPx = frac * PX_PER_PT;

        /* ── 3. Build colored segments (viewport-relative coords) ──
         * One <polyline> per contiguous run of same-class samples.
         * Normal runs → teal, abnormal runs → red. A run boundary shares
         * its boundary point with the next run so the line never gaps. */
        const n = S.buf.length;
        let curPts = '';
        let curAb  = null;

        const flush = () => {
          if (!curPts) return;
          const el = getPoly(segCount++);
          el.setAttribute('points', curPts);
          el.setAttribute('stroke', curAb ? ABN_COLOR : NORM_COLOR);
          el.setAttribute('stroke-width', '1.5');
          el.style.display = '';
        };

        for (let i = 0; i < n; i++) {
          // Newest point (i = n-1) → right edge; older points further left;
          // subPx smoothly shifts everything leftward between emissions
          const x = w - (n - 1 - i) * PX_PER_PT - subPx;
          if (x < -PX_PER_PT || x > w + PX_PER_PT) continue;  // off-screen
          const y  = Y_MID - (S.buf[i].v * Y_AMP / 3);
          const ab = !!S.buf[i].ab;

          if (curAb === null) {
            curAb = ab;
            curPts = `${x},${y} `;
          } else if (ab !== curAb) {
            // Color change: end current run AT this point, then start the
            // new run AT the same point → segments stay visually connected.
            curPts += `${x},${y} `;
            flush();
            curPts = `${x},${y} `;
            curAb = ab;
          } else {
            curPts += `${x},${y} `;
          }
        }
        flush();

        // Nothing on screen yet → draw a flat baseline so it isn't blank
        if (segCount === 0) {
          const el = getPoly(segCount++);
          el.setAttribute('points', `0,${Y_MID} ${w},${Y_MID}`);
          el.setAttribute('stroke', NORM_COLOR);
          el.setAttribute('stroke-width', '1.5');
          el.style.display = '';
        }
      } else {
        // Offline / no data: flat line
        const el = getPoly(segCount++);
        el.setAttribute('points', `0,${Y_MID} ${w},${Y_MID}`);
        el.setAttribute('stroke', OFFLINE_COLOR);
        el.setAttribute('stroke-width', '1');
        el.style.display = '';
      }

      // Hide any pooled polylines not used this frame
      for (let k = segCount; k < polyPool.length; k++) {
        polyPool[k].style.display = 'none';
      }

      // viewBox is always fixed — no scrolling needed
      svg.setAttribute('viewBox', `0 0 ${w} ${SVG_H}`);
      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(rafRef.current);
      S.lastFrame = null;
    };
  }, [hasData]);

  /* ── Render ─────────────────────────────────────────────────── */
  const badge = hasData ? 'LIVE' : 'OFFLINE';

  return (
    <div className="card ecg-panel grid-ecg">
      <div className="card-header">
        <span className="card-title">ECG WAVEFORM</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {heartRate && (
            <span style={{
              fontSize: '28px', fontWeight: 300,
              color: 'var(--text-primary)',
              fontVariantNumeric: 'tabular-nums', lineHeight: 1,
            }}>
              {heartRate}
              <span style={{
                fontSize: '11px', fontWeight: 500,
                color: 'var(--text-muted)',
                letterSpacing: '0.12em', marginLeft: '6px',
              }}>BPM</span>
            </span>
          )}
          <span className={`card-badge ${hasData ? '' : 'offline-badge'}`}>{badge}</span>
        </div>
      </div>

      <div className="ecg-canvas-wrapper" ref={containerRef}>
        <svg
          ref={svgRef}
          className="ecg-canvas"
          viewBox={`0 0 800 ${SVG_H}`}
          preserveAspectRatio="none"
          style={{ display: 'block', width: '100%', height: '100%' }}
        >
          {/* Waveform is drawn as pooled <polyline> segments injected
              imperatively by the rAF loop (see getPoly), so each contiguous
              normal/abnormal run can be stroked its own color. */}
          <g ref={groupRef} />
        </svg>
        <div style={{
          position: 'absolute', inset: 0, pointerEvents: 'none',
          background: 'linear-gradient(90deg, #060A12 0%, transparent 6%, transparent 94%, #060A12 100%)',
        }} />
      </div>
    </div>
  );
}
