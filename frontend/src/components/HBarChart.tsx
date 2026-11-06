/**
 * Small accessible horizontal bar chart (no chart library). Values are drawn only
 * when known; unknown values get a written note instead of a bar. Every chart has
 * a summary and a Table view with the exact figures.
 */
import { useId, useState, type ReactNode } from 'react';

export interface Series {
  key: string;
  label: string;
  tone: 'a' | 'b' | 'c' | 'd';
}
export interface Row {
  label: string;
  values: Record<string, number | null>;
  /** Shown instead of bars when nothing can be charted for this row. */
  note?: string;
  badge?: string;
}

interface Props {
  title: string;
  summary: ReactNode;
  series: Series[];
  rows: Row[];
  format: (v: number) => string;
  /** Stack series into one bar (composition) instead of one bar per series. */
  stacked?: boolean;
  max?: number;
}

export function HBarChart({ title, summary, series, rows, format, stacked = false, max }: Props) {
  const [view, setView] = useState<'chart' | 'table'>('chart');
  const id = useId();
  const totals = rows.map((r) =>
    stacked ? series.reduce((s, x) => s + (r.values[x.key] ?? 0), 0) : Math.max(0, ...series.map((x) => r.values[x.key] ?? 0)),
  );
  const scale = max ?? Math.max(1, ...totals);

  return (
    <figure className="chart" aria-labelledby={`${id}-title`}>
      <div className="chart__head">
        <figcaption id={`${id}-title`} className="chart__title">
          {title}
        </figcaption>
        <div className="segmented" role="group" aria-label={`${title} view`}>
          {(['chart', 'table'] as const).map((v) => (
            <button key={v} type="button" className="segmented__item" aria-pressed={view === v} onClick={() => setView(v)}>
              {v === 'chart' ? 'Chart' : 'Table'}
            </button>
          ))}
        </div>
      </div>
      <p className="chart__summary muted small">{summary}</p>
      {series.length > 1 && (
        <ul className="chart__legend" aria-hidden="true">
          {series.map((s) => (
            <li key={s.key}>
              <span className={`swatch swatch--${s.tone}`} /> {s.label}
            </li>
          ))}
        </ul>
      )}
      {view === 'chart' ? (
        <ul className="chart__rows">
          {rows.map((r) => {
            const known = series.filter((s) => r.values[s.key] !== null && r.values[s.key] !== undefined);
            return (
              <li key={r.label} className="chart__row">
                <span className="chart__label">
                  {r.label}
                  {r.badge && <span className="chart__badge">{r.badge}</span>}
                </span>
                {known.length === 0 || r.note ? (
                  <span className="chart__note">{r.note ?? 'Not available'}</span>
                ) : stacked ? (
                  <span className="chart__bars">
                    <span className="chart__stack" aria-hidden="true">
                      {series.map((s) => {
                        const v = r.values[s.key];
                        return v ? <span key={s.key} className={`bar bar--${s.tone}`} style={{ width: `${(v / scale) * 100}%` }} /> : null;
                      })}
                    </span>
                    <span className="chart__value">{series.map((s) => `${s.label} ${r.values[s.key] === null ? 'unknown' : format(r.values[s.key] as number)}`).join(' + ')}</span>
                  </span>
                ) : (
                  <span className="chart__bars">
                    {series.map((s) => {
                      const v = r.values[s.key];
                      return (
                        <span key={s.key} className="chart__bar-line">
                          <span className="chart__track" aria-hidden="true">
                            {v !== null && v !== undefined && (
                              <span className={`bar bar--${s.tone}`} style={{ width: `${(Math.max(0, v) / scale) * 100}%` }} />
                            )}
                          </span>
                          <span className="chart__value">
                            {series.length > 1 ? `${s.label}: ` : ''}
                            {v === null || v === undefined ? 'Unknown' : format(v)}
                          </span>
                        </span>
                      );
                    })}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      ) : (
        <div className="table-wrap">
          <table className="table table--compact">
            <thead>
              <tr>
                <th scope="col">Store</th>
                {series.map((s) => (
                  <th key={s.key} scope="col" className="num">
                    {s.label}
                  </th>
                ))}
                {stacked && <th scope="col" className="num">Total</th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.label}>
                  <th scope="row">{r.label}</th>
                  {series.map((s) => (
                    <td key={s.key} className="num">
                      {r.values[s.key] === null || r.values[s.key] === undefined ? (r.note ?? 'Unknown') : format(r.values[s.key] as number)}
                    </td>
                  ))}
                  {stacked && <td className="num">{r.note ? 'Total incomplete' : format(totals[i])}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </figure>
  );
}
