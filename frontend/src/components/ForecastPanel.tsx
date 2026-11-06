import { useState, type KeyboardEvent, type MouseEvent } from 'react';
import { useSearchParams } from 'react-router-dom';
import { analysisDay, endOfDayUtc, useForecast, type ForecastHorizon, type PriceMemory, type ProductForecast } from '../lib/history';
import { formatMoney } from '../lib/money';
import { formatDateTime } from '../lib/format';
import type { ProductDetail } from '../lib/products';

const HORIZONS = [7, 14, 30] as const;
const day = (iso: string | null | undefined) => (iso ? iso.slice(0, 10) : null);
const OUTCOME = { returned: 'Returned', stayed_low: 'Stayed low', fell_further: 'Fell further', not_completed: 'Not yet completed', no_observation: 'No observation' } as const;

export function ForecastPanel({ d }: { d: ProductDetail }) {
  const [params, setParams] = useSearchParams();
  const at = analysisDay(params, day(d.price_history.first_verified_at), day(d.price_history.last_verified_at));
  const raw = Number(params.get('h'));
  const h = (HORIZONS as readonly number[]).includes(raw) ? raw : 7;
  const basis = params.get('basis') === 'delivered' ? 'delivered' : 'base';
  const q = useForecast(d.product.product_id, at ? endOfDayUtc(at) : null, basis);
  const set = (k: string, v: string) => setParams((p) => { const n = new URLSearchParams(p); n.set(k, v); return n; }, { replace: true });

  if (!at) {
    return (
      <div className="stack-sm">
        <p className="empty-inline">No forecast. Forecasts need verified UTC history; this product only has snapshot observations without a timezone, which are never used as history.</p>
      </div>
    );
  }
  return (
    <div className="stack-md forecast">
      <div className="evidence__controls">
        <div className="segmented" role="group" aria-label="Forecast horizon">
          {HORIZONS.map((x) => (
            <button key={x} type="button" className="segmented__item" aria-pressed={h === x} onClick={() => set('h', String(x))}>{x} days</button>
          ))}
        </div>
        <div className="segmented" role="group" aria-label="Forecast price basis">
          <button type="button" className="segmented__item" aria-pressed={basis === 'base'} onClick={() => set('basis', 'base')}>Base price</button>
          <button type="button" className="segmented__item" aria-pressed={basis === 'delivered'} onClick={() => set('basis', 'delivered')}>Confirmed delivered</button>
        </div>
      </div>
      <p className="muted small">Trained and backtested only on verified observations up to {formatDateTime(endOfDayUtc(at))}. The date is shared with Evidence and the Time Machine.</p>
      {q.isPending && <p className="muted" role="status">Loading the forecast…</p>}
      {(q.isError || (q.data && !Array.isArray(q.data.horizons))) && <p className="inline-error" role="alert">Couldn't load the forecast{q.error ? `: ${q.error.message}` : '.'}</p>}
      {q.data && Array.isArray(q.data.horizons) && <ForecastResult f={q.data} h={h} />}
    </div>
  );
}

function ForecastResult({ f, h }: { f: ProductForecast; h: number }) {
  const money = (m: number | null | undefined) => formatMoney(m, f.currency ?? 'INR');
  if (f.status !== 'available') return <p className="empty-inline">{f.reason}</p>;
  const hz = f.horizons.find((x) => x.days === h);
  return (
    <div className="stack-md">
      {hz && hz.status === 'available' && hz.forecast ? (
        <>
          <div className="evidence__grid">
            <section className="evidence__card stack-sm" aria-labelledby="fc-est">
              <div className="advice__head">
                <h3 id="fc-est" className="fc-title">Estimated {h}-day price</h3>
                <span className="tag tag--warn">Forecast, not observed</span>
                {f.source.synthetic && <span className="tag tag--synthetic">Synthetic data</span>}
              </div>
              <p className="fc-value">{money(hz.forecast.value_minor)}</p>
              <p className="muted small">
                For {hz.forecast.date}, {h} days after the last observation ({hz.forecast.from_date}) on {f.headline?.marketplace}. {hz.chosen_label}.
              </p>
              <p>
                Nominal {hz.forecast.interval.level_percent}% range:{' '}
                {hz.forecast.low_minor === null || hz.forecast.high_minor === null
                  ? <strong>unavailable (too few past errors to calibrate a range)</strong>
                  : <strong>{money(hz.forecast.low_minor)} – {money(hz.forecast.high_minor)}</strong>}
              </p>
              {hz.forecast.interval.measured_coverage_percent !== null && hz.forecast.interval.measured_coverage_percent < hz.forecast.interval.level_percent && (
                <p className="callout callout--warn" role="note">
                  Not calibrated: in backtests this range contained the actual price only {hz.forecast.interval.measured_coverage_percent}% of the time, so it is not a calibrated {hz.forecast.interval.level_percent}% range.
                </p>
              )}
              <p className="muted small">
                {hz.forecast.interval.measured_coverage_percent === null
                  ? 'Range coverage could not be measured yet (too few backtest points).'
                  : `${hz.forecast.interval.measured_coverage_percent}% measured coverage on ${hz.forecast.interval.measured_on} backtest points (the target is ${hz.forecast.interval.level_percent}%)` +
                    (hz.forecast.interval.mean_width_percent != null ? `; average width ${hz.forecast.interval.mean_width_percent}% of the price.` : '.') +
                    (hz.forecast.interval.previous_method?.measured_coverage_percent != null
                      ? ` The previous method covered ${hz.forecast.interval.previous_method.measured_coverage_percent}% with ${hz.forecast.interval.previous_method.mean_width_percent}% width; better coverage comes with wider ranges.`
                      : '')}
              </p>
            </section>
            <Evaluation hz={hz} money={money} />
          </div>
          <ForecastChart f={f} hz={hz} money={money} />
        </>
      ) : (
        <p className="empty-inline">{hz?.reason ?? 'No forecast for this horizon.'}</p>
      )}
      <section className="stack-sm" aria-labelledby="fc-method">
        <h4 id="fc-method">How this is calculated</h4>
        <p className="small">
          Two simple models predict the price of this store listing {h} days ahead: the last observed price (the baseline) and the median of the last 14 observed days.
          Each is tested on past data in date order: at every past day it sees only earlier prices, and its guess is compared with the price actually observed {h} days later.
          The median is used only if its average error is at least {f.method.min_improvement_percent}% lower than the baseline's; otherwise the baseline stays in use.
          The range comes from past errors, and its coverage is measured the same way.
        </p>
        {f.coverage && f.freshness && (
          <p className="muted small">
            History: {f.coverage.observed_days} observed days, {f.coverage.first_date} to {f.coverage.last_date}
            {f.coverage.missing_days ? `, ${f.coverage.missing_days} missing` : ''}. Latest observation {f.freshness.age_days} day{f.freshness.age_days === 1 ? '' : 's'} before the cutoff.
          </p>
        )}
      </section>
      {f.memory && <Memory m={f.memory} money={money} />}
      {f.limitations.length > 0 && (
        <section aria-labelledby="fc-lim">
          <h4 id="fc-lim">Uncertainty and limitations</h4>
          <ul className="bullets">{f.limitations.map((x) => <li key={x}>{x}</li>)}</ul>
        </section>
      )}
    </div>
  );
}

function Evaluation({ hz, money }: { hz: ForecastHorizon; money: (m: number | null) => string }) {
  return (
    <section className="evidence__card stack-sm" aria-labelledby="fc-eval">
      <h4 id="fc-eval">Backtest vs baseline ({hz.days} days ahead)</h4>
      <div className="table-wrap" tabIndex={0} role="region" aria-label="Backtest results region">
        <table className="table table--compact" aria-label="Backtest results">
          <thead><tr><th scope="col">Model</th><th scope="col">Points</th><th scope="col">Mean abs. error</th><th scope="col">MAPE</th></tr></thead>
          <tbody>
            {hz.models.map((m) => (
              <tr key={m.key}>
                <td>{m.label}{hz.chosen === m.key && <> <span className="tag tag--good">Used</span></>}</td>
                <td>{m.n}</td>
                <td>{money(m.mae_minor)}</td>
                <td>{m.mape_percent === null ? '—' : `${m.mape_percent}%`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="small">{hz.note}</p>
      <p className="muted small">Backtest origins {hz.backtest_first} to {hz.backtest_last}, in date order.</p>
    </section>
  );
}

const W = 600;
const H = 220;

function ForecastChart({ f, hz, money }: { f: ProductForecast; hz: ForecastHorizon; money: (m: number | null) => string }) {
  const hist = f.history.slice(-60);
  const fc = hz.forecast!;
  const t = (iso: string) => Date.parse(`${iso}T00:00:00Z`);
  const x0 = t(hist[0].date);
  const x1 = t(fc.date);
  const vals = [...hist.map((p) => p.value_minor), fc.value_minor, ...(fc.low_minor !== null && fc.high_minor !== null ? [fc.low_minor, fc.high_minor] : [])];
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const pad = (hi - lo) * 0.08 || hi * 0.05 || 1;
  const yMin = lo - pad;
  const yMax = hi + pad;
  const X = (iso: string) => 4 + ((t(iso) - x0) / (x1 - x0 || 1)) * (W - 12); // keep the estimate marker inside the frame
  const Y = (v: number) => H - ((v - yMin) / (yMax - yMin)) * H;
  const last = hist[hist.length - 1];
  const points = [...hist.map((p) => ({ ...p, kind: 'Observed' as const })), { date: fc.date, value_minor: fc.value_minor, kind: 'Forecast' as const }];
  const [sel, setSel] = useState(points.length - 1);
  const cur = points[Math.min(sel, points.length - 1)];
  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'ArrowLeft') setSel((s) => Math.max(0, s - 1));
    else if (e.key === 'ArrowRight') setSel((s) => Math.min(points.length - 1, s + 1));
    else return;
    e.preventDefault();
  };
  const onMove = (e: MouseEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const xv = ((e.clientX - r.left) / r.width) * W;
    let best = 0;
    points.forEach((p, i) => { if (Math.abs(X(p.date) - xv) < Math.abs(X(points[best].date) - xv)) best = i; });
    setSel(best);
  };
  const obsPath = hist.map((p, i) => `${i ? 'L' : 'M'}${X(p.date).toFixed(1)},${Y(p.value_minor).toFixed(1)}`).join(' ');

  return (
    <section className="stack-sm" aria-labelledby="fc-chart-title">
      <h4 id="fc-chart-title">Observed history and {hz.days}-day estimate</h4>
      <div className="fc-legend small" aria-hidden="true">
        <span><i className="fc-key fc-key--obs" /> Observed daily price</span>
        <span><i className="fc-key fc-key--pred" /> Estimate (not observed)</span>
        <span><i className="fc-key fc-key--band" /> Nominal {fc.interval.level_percent}% range</span>
      </div>
      <div className="history-plot">
        <div className="history-y" aria-hidden="true"><span>{money(Math.round(yMax))}</span><span>{money(Math.round(yMin))}</span></div>
        <div className="history-canvas">
          <svg className="history-chart fc-chart" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" tabIndex={0}
            aria-label={`Observed prices to ${last.date} and an estimate of ${money(fc.value_minor)} for ${fc.date}. Use left and right arrow keys to read values.`}
            onMouseMove={onMove} onKeyDown={onKey}>
            <line className="history-grid" x1={X(last.date)} x2={X(last.date)} y1={0} y2={H} />
            {fc.low_minor !== null && fc.high_minor !== null && (
              <polygon className="fc-band" points={`${X(last.date)},${Y(last.value_minor)} ${X(fc.date)},${Y(fc.high_minor)} ${X(fc.date)},${Y(fc.low_minor)}`} />
            )}
            <path className="history-line fc-observed" d={obsPath} />
            <line className="fc-predicted" x1={X(last.date)} y1={Y(last.value_minor)} x2={X(fc.date)} y2={Y(fc.value_minor)} />
            <circle className="fc-dot" cx={X(fc.date)} cy={Y(fc.value_minor)} r={5} />
            <line className="fc-cursor" x1={X(cur.date)} x2={X(cur.date)} y1={0} y2={H} />
          </svg>
          <div className="history-x" aria-hidden="true"><span>{hist[0].date}</span><span>Last observed {last.date}</span><span>{fc.date}</span></div>
        </div>
      </div>
      <p className="fc-readout small" role="status" aria-live="polite">
        <span className={`tag ${cur.kind === 'Forecast' ? 'tag--warn' : 'tag--good'}`}>{cur.kind === 'Forecast' ? 'Estimate' : 'Observed'}</span>{' '}
        {cur.date}: <strong>{money(cur.value_minor)}</strong>
        {cur.kind === 'Forecast' && fc.low_minor !== null && fc.high_minor !== null && ` (range ${money(fc.low_minor)} to ${money(fc.high_minor)})`}
      </p>
    </section>
  );
}

function Memory({ m, money }: { m: PriceMemory; money: (v: number | null) => string }) {
  const days = Object.keys(m.summary);
  return (
    <section className="stack-sm" aria-labelledby="fc-mem">
      <h4 id="fc-mem">Future Price Memory</h4>
      <p className="small">{m.definition}</p>
      {m.current_event && (
        <p className="callout callout--warn" role="note">
          The latest price is in a similar drop: {m.current_event.drop_percent}% below the previous median since {m.current_event.date}.
        </p>
      )}
      {m.events.length === 0 ? (
        <p className="muted small">No similar drops were observed in this history.</p>
      ) : (
        <>
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Outcomes after past drops">
            <table className="table table--compact">
              <thead><tr><th scope="col">After</th><th scope="col">Returned</th><th scope="col">Stayed low</th><th scope="col">Fell further</th><th scope="col">Not yet completed</th></tr></thead>
              <tbody>
                {days.map((k) => {
                  const s = m.summary[k];
                  return (
                    <tr key={k}>
                      <th scope="row">{k} day{k === '1' ? '' : 's'}</th>
                      <td>{s.returned} of {s.completed} completed</td>
                      <td>{s.stayed_low} of {s.completed}</td>
                      <td>{s.fell_further} of {s.completed}</td>
                      <td>{s.pending}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <details>
            <summary>Past drops ({m.events.length})</summary>
            <ul className="bullets">
              {m.events.map((e) => (
                <li key={e.date}>
                  {e.date}: {money(e.value_minor)}, {e.drop_percent}% below the previous median {money(e.before_median_minor)}.{' '}
                  {days.map((k) => `${k}d: ${OUTCOME[e.outcomes[k].outcome]}`).join(' · ')}
                </li>
              ))}
            </ul>
          </details>
        </>
      )}
      <p className="muted small">{m.note}</p>
    </section>
  );
}
