import { useSearchParams } from 'react-router-dom';
import { analysisDay, endOfDayUtc, formatAge, useAdvice, type BuyingAdvice as Advice } from '../lib/history';
import { formatMoney } from '../lib/money';
import { formatDateTime } from '../lib/format';
import type { ProductDetail } from '../lib/products';

const day = (iso: string | null | undefined) => (iso ? iso.slice(0, 10) : null);
const TONE = { buy_now: 'advice--buy', consider_waiting: 'advice--wait', insufficient_evidence: 'advice--none' } as const;
const SUPPORTS = { buy: ['Supports buying', 'tag--good'], wait: ['Supports waiting', 'tag--warn'], neutral: ['Neutral', 'tag--synthetic'] } as const;

/** Buying advice card (SCOPE §5): observed history only, no forecast. Shares the analysis date with Evidence and the Time Machine. */
export function BuyingAdviceCard({ d }: { d: ProductDetail }) {
  const [params, setParams] = useSearchParams();
  const at = analysisDay(params, day(d.price_history.first_verified_at), day(d.price_history.last_verified_at));
  const ewin = Number(params.get('ewin'));
  const win = [30, 90, 180].includes(ewin) ? ewin : 90;
  const basis = params.get('basis') === 'delivered' ? 'delivered' : 'base';
  const q = useAdvice(d.product.product_id, at ? endOfDayUtc(at) : null, win, basis);
  const go = (entries: Record<string, string>) => {
    setParams((p) => { const n = new URLSearchParams(p); Object.entries(entries).forEach(([k, v]) => n.set(k, v)); return n; });
    document.getElementById('analysis')?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
  };
  const a = q.data && q.data.recommendation ? q.data : null;
  const code = !at ? 'insufficient_evidence' : a?.recommendation.code;

  return (
    <section id="advice" className={`card section-card stack-md advice ${code ? TONE[code] : ''}`} aria-labelledby="advice-title">
      <div className="section-head">
        <h2 id="advice-title">Buying advice</h2>
        {at && <span className="muted small">As of {formatDateTime(endOfDayUtc(at))} · {win}-day window · {basis === 'delivered' ? 'confirmed delivered price' : 'base price'}</span>}
      </div>
      {!at && (
        <div className="stack-sm">
          <h3 className="advice__label">Insufficient evidence</h3>
          <p>No recommendation is made. This product only has snapshot observations without a timezone, and advice needs verified UTC history on at least 14 distinct days.</p>
        </div>
      )}
      {at && q.isPending && <p className="muted" role="status">Loading buying advice…</p>}
      {at && (q.isError || (q.data && !a)) && <p className="inline-error" role="alert">Couldn't load buying advice{q.error ? `: ${q.error.message}` : '.'}</p>}
      {a && <AdviceBody a={a} onEvidence={() => go({ tab: 'evidence' })} onTimeline={(date) => go({ tab: 'timeline', at: date })} />}
    </section>
  );
}

function AdviceBody({ a, onEvidence, onTimeline }: { a: Advice; onEvidence: () => void; onTimeline: (date: string) => void }) {
  const r = a.recommendation;
  const money = (m: number | null | undefined) => formatMoney(m, a.price?.currency ?? 'INR');
  return (
    <div className="stack-md">
      <div className="advice__head">
        <h3 className="advice__label">{r.label}</h3>
        {a.confidence.level && <span className={`tag ${a.confidence.level === 'high' ? 'tag--good' : a.confidence.level === 'medium' ? 'tag--warn' : 'tag--bad'}`}>{a.confidence.level[0].toUpperCase() + a.confidence.level.slice(1)} confidence</span>}
      </div>
      <p className="advice__reason">{r.reason}</p>

      {a.price && a.coverage && a.freshness && (
        <dl className="stats advice__stats">
          <div className="stats__item"><dt>Current price</dt><dd>{money(a.price.current_minor)}</dd></div>
          <div className="stats__item"><dt>Usual price (median)</dt><dd>{money(a.price.usual_minor)}</dd></div>
          <div className="stats__item"><dt>Genuine Discount Score</dt><dd>{a.score.value === null ? 'Unavailable' : `${a.score.value} / 100`}</dd></div>
          <div className="stats__item"><dt>Coverage</dt><dd className="advice__small-dd">{a.coverage.observed_days} observed days in the {a.coverage.window_days}-day window{a.coverage.missing_days ? `, ${a.coverage.missing_days} missing` : ''}</dd></div>
          <div className="stats__item"><dt>Freshness</dt><dd className="advice__small-dd">Latest observation: {a.freshness.marketplace}, {formatAge(a.freshness.age_hours * 3600)}</dd></div>
        </dl>
      )}

      <div className="advice__cols">
        <section aria-labelledby="advice-why">
          <h4 id="advice-why">Why</h4>
          <ul className="bullets">{a.reasons.map((x) => <li key={x}>{x}</li>)}</ul>
          {a.signals.length > 0 && (
            <ul className="advice__signals" aria-label="Signals">
              {a.signals.map((s) => (
                <li key={s.key}><span>{s.label}: <strong>{s.value}</strong></span> <span className={`tag ${SUPPORTS[s.supports][1]}`}>{SUPPORTS[s.supports][0]}</span></li>
              ))}
            </ul>
          )}
        </section>
        <section aria-labelledby="advice-against">
          <h4 id="advice-against">Disagreeing signals</h4>
          {a.disagreeing.length ? (
            <ul className="bullets">{a.disagreeing.map((s) => <li key={s.key}><strong>{s.label}.</strong> {s.detail}</li>)}</ul>
          ) : (
            <p className="muted small">None found in the evidence.</p>
          )}
          {a.confidence.level && (
            <>
              <h4>Confidence</h4>
              <ul className="bullets">{a.confidence.reasons.map((x) => <li key={x}>{x}</li>)}</ul>
            </>
          )}
        </section>
      </div>

      <p className="callout" role="note">{a.forecast.note}</p>
      {a.forecast.expectation ? (
        <section className="advice__forecast stack-sm" aria-labelledby="advice-fc">
          <h4 id="advice-fc">Forecast-based expectation ({a.forecast.expectation.horizon_days} days)</h4>
          <p className="fc-value">{formatMoney(a.forecast.expectation.value_minor, a.forecast.expectation.currency)}</p>
          <p className="small">
            Estimate for {a.forecast.expectation.date}; nominal {a.forecast.expectation.interval.level_percent}% range {formatMoney(a.forecast.expectation.low_minor, a.forecast.expectation.currency)} to{' '}
            {formatMoney(a.forecast.expectation.high_minor, a.forecast.expectation.currency)}
            {a.forecast.expectation.interval.measured_coverage_percent !== null && ` (measured coverage ${a.forecast.expectation.interval.measured_coverage_percent}%)`}.
          </p>
          <p className="muted small">
            {a.forecast.expectation.model_label}. Backtest mean error {formatMoney(a.forecast.expectation.mae_minor, a.forecast.expectation.currency)} vs{' '}
            {formatMoney(a.forecast.expectation.baseline_mae_minor, a.forecast.expectation.currency)} for the last-price baseline, over {a.forecast.expectation.backtest_points} points.
          </p>
          <p className="muted small">{a.forecast.expectation.note}</p>
        </section>
      ) : (
        a.forecast.expectation_note && <p className="muted small">{a.forecast.expectation_note}</p>
      )}
      {a.limitations.length > 0 && (
        <details>
          <summary>Data-quality limitations ({a.limitations.length})</summary>
          <ul className="bullets">{a.limitations.map((x) => <li key={x}>{x}</li>)}</ul>
        </details>
      )}
      <div className="row-gap">
        <button type="button" className="btn btn--secondary btn--small" onClick={onEvidence}>See the evidence</button>
        {a.freshness && (
          <button type="button" className="btn btn--secondary btn--small" aria-label="Open the latest observation in the Time Machine" onClick={() => onTimeline(a.freshness!.observed_at.slice(0, 10))}>
            Open in Time Machine
          </button>
        )}
      </div>
      <p className="muted small">Rules {a.method.version}. A decision aid based on observed prices, not a savings guarantee.</p>
    </div>
  );
}
