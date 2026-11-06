import { useId, useState, type ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';
import { EVIDENCE_WINDOWS, analysisDay, endOfDayUtc, useEvidence, type PriceEvidence } from '../lib/history';
import { formatMoney } from '../lib/money';
import { formatDateTime } from '../lib/format';
import type { ProductDetail } from '../lib/products';

const day = (iso: string | null | undefined) => (iso ? iso.slice(0, 10) : null);
const pct = (n: number | null | undefined) => (n === null || n === undefined ? 'Unknown' : `${n}%`);
const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? '' : 's'}`;

const TERMS: Record<string, string> = {
  'usual price': 'The median of the lowest price observed each day in the window, with the current observation left out. Half of the observed days were above it and half below.',
  'real savings': '100 × (usual price − current price) ÷ usual price. Measured from observed prices, not from the seller’s reference price. Negative means the price is above usual.',
  'advertised discount': 'The discount percent the seller displayed, calculated from the seller’s own reference (MRP) price. It is shown as reported and is never used as proof.',
  'reference price': 'The “original” or MRP price supplied by the seller. A reference price that rises while the price stays the same makes a discount look larger.',
  'Genuine Discount Score': '0–100. 60% real savings, 25% price percentile (how many observed days were more expensive), 15% agreement between the advertised discount and real savings.',
  'price percentile': 'The share of observed days in the window when the price was higher than now. Ties count half.',
  cutoff: 'The analysis uses only observations at or before this UTC time. Nothing observed later is read.',
};

/** Small accessible tooltip: opens on hover, focus or click; closes on Escape, blur or leaving. */
function Term({ term, children }: { term: keyof typeof TERMS; children?: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <span className="term" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      {children ?? term}
      <button type="button" className="term__btn" aria-label={`What is ${term}?`} aria-expanded={open} aria-describedby={open ? id : undefined}
        onClick={() => setOpen(true)} onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}
        onKeyDown={(e) => e.key === 'Escape' && setOpen(false)}>
        i
      </button>
      {open && <span role="tooltip" id={id} className="term__tip">{TERMS[term]}</span>}
    </span>
  );
}

const VERDICT_TAG = { below_usual: 'tag--good', around_usual: 'tag--warn', above_usual: 'tag--bad' } as const;
const SUPPORT = {
  supported: ['Supported', 'tag--good'],
  partly_supported: ['Partly supported', 'tag--warn'],
  not_supported: ['Not supported', 'tag--bad'],
  no_advertised_discount: ['No advertised discount', 'tag--synthetic'],
} as const;
const COMPONENT_LABEL = { savings: 'Real savings', percentile: 'Price percentile', agreement: 'Advertised agreement' } as const;

export function EvidencePanel({ d }: { d: ProductDetail }) {
  const [params, setParams] = useSearchParams();
  const h = d.price_history;
  const first = day(h.first_verified_at);
  const last = day(h.last_verified_at);
  const at = analysisDay(params, first, last);
  const ewin = Number(params.get('ewin')) || 90;
  const win = (EVIDENCE_WINDOWS as readonly number[]).includes(ewin) ? ewin : 90;
  const basis = params.get('basis') === 'delivered' ? 'delivered' : 'base';
  const q = useEvidence(d.product.product_id, at ? endOfDayUtc(at) : null, win, basis);
  const set = (entries: Record<string, string>, replace = true) =>
    setParams((p) => { const n = new URLSearchParams(p); Object.entries(entries).forEach(([k, v]) => n.set(k, v)); return n; }, { replace });
  const openInTimeMachine = (date: string) => set({ tab: 'timeline', at: date }, false);

  if (!at) {
    return (
      <div className="stack-sm">
        <p className="empty-inline">Insufficient historical evidence. The Real Price Detector and Genuine Discount Score need verified UTC observations on at least 14 distinct days.</p>
        <p className="muted small">This product only has snapshot observations without a timezone, which are never used as history.</p>
      </div>
    );
  }

  return (
    <div className="stack-md evidence">
      <div className="evidence__controls">
        <label className="field">
          <span className="field__label">Evidence as of (<Term term="cutoff">UTC cutoff</Term>)</span>
          <input type="date" className="input" min={first!} max={last!} value={at} onChange={(e) => e.target.value && set({ at: e.target.value })} />
        </label>
        <div className="segmented" role="group" aria-label="Evidence window">
          {EVIDENCE_WINDOWS.map((w) => (
            <button key={w} type="button" className="segmented__item" aria-pressed={win === w} onClick={() => set({ ewin: String(w) })}>{w}D</button>
          ))}
        </div>
        <div className="segmented" role="group" aria-label="Evidence price basis">
          <button type="button" className="segmented__item" aria-pressed={basis === 'base'} onClick={() => set({ basis: 'base' })}>Base price</button>
          <button type="button" className="segmented__item" aria-pressed={basis === 'delivered'} onClick={() => set({ basis: 'delivered' })}>Confirmed delivered</button>
        </div>
      </div>
      <p className="muted small">Uses only verified observations up to {formatDateTime(endOfDayUtc(at))}, over the {win} days ending then. The date is shared with the Time Machine.</p>
      {q.isPending && <p className="muted" role="status">Loading price evidence…</p>}
      {q.isError && <p className="inline-error" role="alert">Couldn't load the price evidence: {q.error.message}</p>}
      {q.data && <EvidenceResult e={q.data} onOpen={openInTimeMachine} />}
    </div>
  );
}

function EvidenceResult({ e, onOpen }: { e: PriceEvidence; onOpen: (date: string) => void }) {
  const det = e.detector;
  const ev = e.evidence;
  const cur = det?.currency ?? ev?.current_observation.currency ?? 'INR';
  const money = (m: number | null | undefined) => formatMoney(m, cur);
  return (
    <div className="stack-md">
      {!det || !ev ? (
        <div className="stack-sm">
          <p className="empty-inline">{e.reason}</p>
          <p className="muted small">Score unavailable. {e.score.reason}</p>
        </div>
      ) : (
        <>
          <div className="evidence__verdict">
            <span className={`tag ${VERDICT_TAG[det.verdict]}`}>Real Price Detector</span>
            <h3>{det.label}</h3>
            <p>{det.explanation}</p>
            <p className="muted small">
              Lowest current {e.basis === 'delivered' ? 'confirmed delivered price' : 'price'}: {ev.marketplace}
              {e.headline?.seller_name ? ` · ${e.headline.seller_name}` : ''} · observed {formatDateTime(ev.current_observation.observed_at)}{' '}
              <button type="button" className="link-button" aria-label="Open the current observation in the Time Machine" onClick={() => onOpen(ev.current_observation.observed_at.slice(0, 10))}>
                View in Time Machine
              </button>
            </p>
          </div>
          <div className="evidence__grid">
            <ScoreCard e={e} />
            <section className="evidence__card stack-sm" aria-labelledby="ev-adv">
              <h4 id="ev-adv">Advertised vs observed</h4>
              <dl className="stats evidence__pair">
                <div className="stats__item"><dt><Term term="advertised discount">Advertised discount</Term></dt><dd>{pct(det.advertised_discount_percent)}</dd></div>
                <div className="stats__item"><dt><Term term="real savings">Real savings</Term></dt><dd>{pct(det.savings_percent)}</dd></div>
              </dl>
              <p><span className={`tag ${SUPPORT[det.advertised_support][1]}`}>{SUPPORT[det.advertised_support][0]}</span> {det.advertised_note}</p>
              <PriceLadder rows={[
                ['Seller reference price', det.reference.current_minor, 'ref'],
                ['Usual price (median)', det.baseline_minor, 'usual'],
                ['Current price', det.current_minor, 'current'],
              ]} money={money} />
              <p className="muted small"><Term term="usual price">Usual price</Term> {money(det.baseline_minor)} · <Term term="reference price">Reference</Term> {money(det.reference.current_minor)}</p>
              {det.reference.increased ? (
                <p className="callout callout--warn" role="note"><strong>Reference price increase.</strong> {det.reference.note}</p>
              ) : (
                <p className="muted small">{det.reference.note}</p>
              )}
            </section>
          </div>
          <section className="stack-sm" aria-labelledby="ev-used">
            <h4 id="ev-used">Evidence used</h4>
            <dl className="kv evidence__kv">
              <div><dt>Window</dt><dd>{formatDateTime(e.window.start)} → {formatDateTime(e.cutoff)} ({e.window.days} days)</dd></div>
              <div><dt>Store listing</dt><dd>{ev.marketplace} · {ev.listing_id}</dd></div>
              <div><dt>Baseline days</dt><dd>{ev.baseline_days} observed days, {ev.first_date} to {ev.last_date}</dd></div>
              <div><dt>Missing days</dt><dd>{ev.missing_dates.length ? `${plural(ev.missing_dates.length, 'missing day')} (gaps, not filled)` : 'None'}</dd></div>
              <div><dt>Daily range</dt><dd>{money(ev.lowest_minor)} – {money(ev.highest_minor)}</dd></div>
              <div><dt>Current observation</dt><dd>{money(ev.current_observation.value_minor)} · {ev.current_observation.availability ?? 'Availability unknown'}{e.basis === 'delivered' ? ` · shipping ${money(ev.current_observation.shipping_minor)}` : ''}</dd></div>
              <div><dt>Comparison basis</dt><dd>{e.basis === 'delivered' ? 'Confirmed delivered price (base + known shipping)' : 'Base price (excludes shipping)'}; same store listing, seller and currency</dd></div>
              <div><dt>Source</dt><dd>{e.source.synthetic && <span className="tag tag--synthetic">Synthetic data</span>} {e.source.source_labels.join(', ')}{e.source.source_files.length ? ` · ${e.source.source_files.join(', ')}` : ''}</dd></div>
            </dl>
            <details className="evidence__daily">
              <summary>Daily observed prices ({ev.daily.length} days)</summary>
              <div className="table-wrap" tabIndex={0} role="region" aria-label="Daily observed prices">
                <table className="table table--compact">
                  <thead><tr><th scope="col">Date (UTC)</th><th scope="col">Lowest observed</th><th scope="col">Seller reference</th><th scope="col">Observations</th><th scope="col"><span className="visually-hidden">Time Machine</span></th></tr></thead>
                  <tbody>
                    {[...ev.daily].reverse().map((p) => (
                      <tr key={p.date}>
                        <td>{p.date}</td><td>{money(p.value_minor)}</td><td>{money(p.reference_minor)}</td><td>{p.observations}</td>
                        <td><button type="button" className="link-button" aria-label={`View ${p.date} in the Time Machine`} onClick={() => onOpen(p.date)}>View</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          </section>
        </>
      )}
      <ListingsTable e={e} />
      {e.limitations.length > 0 && (
        <section aria-labelledby="ev-lim">
          <h4 id="ev-lim">Limitations</h4>
          <ul className="bullets">{e.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
        </section>
      )}
      <p className="muted small">
        Method {e.method.version}: verdict thresholds ±{e.method.savings_threshold}%, at least {e.method.min_days} distinct observed days, reference increase ≥ {e.method.reference_increase}%.
        A decision aid, not a savings guarantee.
      </p>
    </div>
  );
}

function ScoreCard({ e }: { e: PriceEvidence }) {
  const s = e.score;
  if (s.status !== 'available' || s.value === null) {
    return <section className="evidence__card"><h4>Genuine Discount Score</h4><p className="muted">Score unavailable. {s.reason}</p></section>;
  }
  return (
    <section className="evidence__card stack-sm" aria-labelledby="ev-score">
      <h4 id="ev-score"><Term term="Genuine Discount Score" /></h4>
      <div className="score">
        <span className="score__value">{s.value}<small> / 100</small></span>
        <span className={`tag ${s.band === 'strong' ? 'tag--good' : s.band === 'moderate' ? 'tag--warn' : 'tag--bad'}`}>{s.label}</span>
      </div>
      <div className="score__meter" role="meter" aria-label="Genuine Discount Score" aria-valuemin={0} aria-valuemax={100} aria-valuenow={s.value} aria-valuetext={`${s.value} out of 100, ${s.label}`}>
        <span className="score__band score__band--weak" /><span className="score__band score__band--moderate" /><span className="score__band score__band--strong" />
        <span className="score__marker" style={{ left: `${s.value}%` }} />
      </div>
      <div className="score__scale muted small" aria-hidden="true"><span>0 Little</span><span>40 Some</span><span>70 Strong</span></div>
      <ul className="score__parts">
        {s.components.map((c) => (
          <li key={c.key}>
            <div className="score__part-head">
              <span>{c.key === 'percentile' ? <Term term="price percentile">{COMPONENT_LABEL[c.key]}</Term> : COMPONENT_LABEL[c.key]} <span className="muted small">({c.weight}%)</span></span>
              <span className="small">{c.available ? `${c.points} pts` : 'Not available'}</span>
            </div>
            <div className="score__bar" aria-hidden="true"><span style={{ width: `${c.value ?? 0}%` }} /></div>
            <p className="muted small">{c.explanation}</p>
          </li>
        ))}
      </ul>
      {s.weight_used < 100 && <p className="muted small">Missing components are disclosed: the score uses {s.weight_used}% of its weight, rescaled to 100.</p>}
    </section>
  );
}

function PriceLadder({ rows, money }: { rows: [string, number | null, string][]; money: (m: number | null) => string }) {
  const max = Math.max(...rows.map(([, v]) => v ?? 0), 1);
  return (
    <ul className="ladder" aria-label="Reference, usual and current price">
      {rows.map(([label, v, k]) => (
        <li key={k}>
          <span className="ladder__label small">{label}</span>
          <span className="ladder__track" aria-hidden="true"><span className={`ladder__fill ladder__fill--${k}`} style={{ width: `${v ? (v / max) * 100 : 0}%` }} /></span>
          <span className="ladder__value small">{money(v)}</span>
        </li>
      ))}
    </ul>
  );
}

function ListingsTable({ e }: { e: PriceEvidence }) {
  if (!e.listings.length) return null;
  return (
    <section className="stack-sm" aria-labelledby="ev-listings">
      <h4 id="ev-listings">Each store listing</h4>
      <div className="table-wrap" tabIndex={0} role="region" aria-label="Evidence per store listing">
        <table className="table table--compact">
          <thead><tr><th scope="col">Store</th><th scope="col">Current</th><th scope="col">Usual</th><th scope="col">Real savings</th><th scope="col">Days</th><th scope="col">Notes</th></tr></thead>
          <tbody>
            {e.listings.map((l) => (
              <tr key={l.listing_id}>
                <td>{l.marketplace}<div className="muted small">{l.seller_name ?? l.seller_id}</div></td>
                <td>{l.current_minor === null ? '—' : formatMoney(l.current_minor, l.currency ?? 'INR')}</td>
                <td>{l.baseline_minor === null ? '—' : formatMoney(l.baseline_minor, l.currency ?? 'INR')}</td>
                <td>{l.savings_percent === null ? '—' : `${l.savings_percent}%`}</td>
                <td>{l.observed_days}</td>
                <td className="small">{l.status === 'available' ? 'Result available' : l.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
