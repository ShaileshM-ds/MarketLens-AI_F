import { useState } from 'react';
import { formatMoney } from '../lib/money';
import type { HistoryPoint, ProductHistory } from '../lib/history';

const W = 640;
const H = 220;
const PAD = { l: 4, r: 8, t: 10, b: 10 };

/** Split into runs of consecutive days so missing days stay visible gaps. */
function segments(series: HistoryPoint[]): HistoryPoint[][] {
  const out: HistoryPoint[][] = [];
  let cur: HistoryPoint[] = [];
  let prev: number | null = null;
  for (const p of series) {
    const t = Date.parse(`${p.date}T00:00:00Z`);
    if (prev !== null && t - prev > 86400000) {
      out.push(cur);
      cur = [];
    }
    cur.push(p);
    prev = t;
  }
  if (cur.length) out.push(cur);
  return out;
}

/** Area chart of verified observations only. Every value comes from the API; nothing is interpolated. */
export function PriceHistoryChart({ h }: { h: ProductHistory }) {
  const [view, setView] = useState<'chart' | 'table'>('chart');
  const cur = h.currency ?? 'INR';
  const fmt = (v: number) => formatMoney(v, cur);
  const s = h.series;
  const start = Date.parse(h.window.start) || Date.parse(`${s[0].date}T00:00:00Z`);
  const end = Date.parse(`${h.cutoff.slice(0, 10)}T00:00:00Z`);
  const span = Math.max(1, end - start);
  const vals = s.map((p) => p.value_minor);
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const pad = Math.max(1, Math.round((hi - lo) * 0.1));
  const yMin = lo - pad;
  const yMax = hi + pad;
  const x = (d: string) => PAD.l + ((Date.parse(`${d}T00:00:00Z`) - start) / span) * (W - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + (1 - (v - yMin) / Math.max(1, yMax - yMin)) * (H - PAD.t - PAD.b);
  const segs = segments(s);
  const low = s.find((p) => p.value_minor === lo)!;
  const high = s.find((p) => p.value_minor === hi)!;
  const missing = h.coverage.missing_dates.length;
  const summary = `${h.coverage.days_with_data} day${h.coverage.days_with_data === 1 ? '' : 's'} with verified observations from ${h.coverage.first_date} to ${h.coverage.last_date}${missing ? `, ${missing} missing day${missing === 1 ? '' : 's'} shown as gaps` : ''}. Lowest observed ${fmt(lo)} on ${low.date}; highest observed ${fmt(hi)} on ${high.date}.`;

  return (
    <div className="history-chart-wrap">
      <div className="chart__head">
        <p className="muted small">{summary}</p>
        <div className="segmented" role="group" aria-label="Price history view">
          <button type="button" className="segmented__item" aria-pressed={view === 'chart'} aria-label="Price history chart view" onClick={() => setView('chart')}>
            Chart
          </button>
          <button type="button" className="segmented__item" aria-pressed={view === 'table'} aria-label="Price history table view" onClick={() => setView('table')}>
            Table
          </button>
        </div>
      </div>
      {view === 'chart' ? (
        <div className="history-plot">
          {/* Axis labels are HTML so they never shrink below 12px with the chart. */}
          <div className="history-y" aria-hidden="true">
            {[yMax, (yMax + yMin) / 2, yMin].map((v, i) => (
              <span key={i}>{fmt(Math.round(v))}</span>
            ))}
          </div>
          <div className="history-canvas">
        <svg className="history-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Price history chart. ${summary}`} preserveAspectRatio="none">
          {[yMax, (yMax + yMin) / 2, yMin].map((v, i) => (
            <line key={i} x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} className="history-grid" />
          ))}
          {segs.map((seg, i) => {
            const line = seg.map((p, k) => `${k ? 'L' : 'M'}${x(p.date).toFixed(1)},${y(p.value_minor).toFixed(1)}`).join(' ');
            const area = seg.length > 1 ? `${line} L${x(seg[seg.length - 1].date).toFixed(1)},${H - PAD.b} L${x(seg[0].date).toFixed(1)},${H - PAD.b} Z` : '';
            return (
              <g key={i}>
                {area && <path d={area} className="history-area" />}
                <path d={line} className="history-line" />
              </g>
            );
          })}
          {s.map((p) => (
            <circle key={p.date} cx={x(p.date)} cy={y(p.value_minor)} r={s.length > 60 ? 1.6 : 3} className="history-dot">
              <title>{`${p.date}: ${fmt(p.value_minor)} (${p.marketplaces.join(', ')})`}</title>
            </circle>
          ))}
        </svg>
            <div className="history-x" aria-hidden="true">
              <span>{(h.window.start || s[0].date).slice(0, 10)}</span>
              <span>{h.cutoff.slice(0, 10)}</span>
            </div>
          </div>
        </div>
      ) : (
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Price history table">
          <table className="table table--compact" aria-label="Price history data">
            <thead>
              <tr>
                <th scope="col">Date (UTC)</th>
                <th scope="col" className="num">Lowest observed</th>
                <th scope="col">Store</th>
              </tr>
            </thead>
            <tbody>
              {s.map((p) => (
                <tr key={p.date}>
                  <th scope="row">{p.date}</th>
                  <td className="num">{fmt(p.value_minor)}</td>
                  <td>{p.marketplaces.join(', ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
