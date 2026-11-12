import { useEffect, useRef, type KeyboardEvent } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PriceHistoryChart } from './PriceHistoryChart';
import { EvidencePanel } from './EvidencePanel';
import { ForecastPanel } from './ForecastPanel';
import { WINDOWS, addDays, endOfDayUtc, formatAge, useAsOf, useHistory, type AsOf } from '../lib/history';
import { formatMoney } from '../lib/money';
import { formatCount, formatDateTime } from '../lib/format';
import type { ProductDetail } from '../lib/products';

const day = (iso: string | null | undefined) => (iso ? iso.slice(0, 10) : null);

/** Price History card: a chart of verified observations, or a plain unavailable state. */
export function HistorySection({ d }: { d: ProductDetail }) {
  const h = d.price_history;
  const [params, setParams] = useSearchParams();
  const last = day(h.last_verified_at);
  const range = Number(params.get('range')) || 30;
  const win = (WINDOWS as readonly number[]).includes(range) ? range : 30;
  const basis = params.get('basis') === 'delivered' ? 'delivered' : 'base';
  const q = useHistory(d.product.product_id, last ? endOfDayUtc(last) : null, win, basis);
  const set = (k: string, v: string) => setParams((p) => { const n = new URLSearchParams(p); n.set(k, v); return n; }, { replace: true });

  return (
    <section id="history" className="card section-card stack-md" aria-labelledby="history-title">
      <h2 id="history-title">Price History</h2>
      {!last ? (
        <div className="empty-inline">
          <p>{h.reason}</p>
          <p className="muted small">
            {formatCount(h.verified_observation_count)} verified UTC observations · {formatCount(h.timezone_unknown_observation_count)} snapshot observations
            without a timezone. No chart is drawn and no trend, high, low or average is calculated from snapshots.
          </p>
        </div>
      ) : (
        <>
          <div className="row-gap">
            <div className="segmented" role="group" aria-label="History range">
              {WINDOWS.map((w) => (
                <button key={w} type="button" className="segmented__item" aria-pressed={win === w} onClick={() => set('range', String(w))}>
                  {w}D
                </button>
              ))}
            </div>
            <div className="segmented" role="group" aria-label="Price basis">
              <button type="button" className="segmented__item" aria-pressed={basis === 'base'} onClick={() => set('basis', 'base')}>Base price</button>
              <button type="button" className="segmented__item" aria-pressed={basis === 'delivered'} onClick={() => set('basis', 'delivered')}>Confirmed delivered</button>
            </div>
          </div>
          <p className="muted small">
            Up to {formatDateTime(endOfDayUtc(last))} (latest verified observation day). Daily value = lowest verified observation that day across stores.
          </p>
          {q.isPending && <p className="muted" role="status">Loading price history…</p>}
          {q.isError && <p className="inline-error" role="alert">Couldn't load price history: {q.error.message}</p>}
          {q.data && q.data.status !== 'available' && <p className="empty-inline">{q.data.reason}</p>}
          {q.data && q.data.status === 'available' && <PriceHistoryChart h={q.data} />}
          {q.data && (
            <p className="muted small">
              {q.data.excluded.timezone_unknown > 0 && `${q.data.excluded.timezone_unknown} snapshot observations without a timezone are excluded. `}
              {q.data.excluded.unknown_shipping_observations > 0 && `${q.data.excluded.unknown_shipping_observations} observations with unknown shipping have no delivered value.`}
            </p>
          )}
        </>
      )}
    </section>
  );
}

const TABS = [
  { id: 'timeline', label: 'Timeline' },
  { id: 'evidence', label: 'Evidence' },
  { id: 'forecast', label: 'Forecast' },
] as const;
type TabId = (typeof TABS)[number]['id'];

export function AnalysisTabs({ d }: { d: ProductDetail }) {
  const [params, setParams] = useSearchParams();
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const raw = params.get('tab');
  const tab: TabId = TABS.some((t) => t.id === raw) ? (raw as TabId) : 'timeline';
  const select = (id: TabId) => setParams((p) => { const n = new URLSearchParams(p); n.set('tab', id); return n; });
  const onKey = (e: KeyboardEvent, i: number) => {
    const delta = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
    if (!delta) return;
    e.preventDefault();
    const n = (i + delta + TABS.length) % TABS.length;
    select(TABS[n].id);
    refs.current[n]?.focus();
  };
  const h = d.price_history;
  const verified = h.verified_observation_count;
  const none = 'Needs verified UTC observations. This product only has snapshot observations without a timezone, which are never used as history.';

  return (
    <section id="analysis" className="card section-card" aria-label="Timeline, Evidence and Forecast">
      <div role="tablist" aria-label="Product analysis" className="tabs">
        {TABS.map((t, i) => (
          <button
            key={t.id}
            ref={(el) => (refs.current[i] = el)}
            type="button"
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            tabIndex={tab === t.id ? 0 : -1}
            className="tabs__tab"
            onClick={() => select(t.id)}
            onKeyDown={(e) => onKey(e, i)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} className="tabs__panel" tabIndex={0}>
        {tab === 'timeline' && (verified ? <TimeMachine d={d} /> : <p className="muted">{none}</p>)}
        {tab === 'evidence' && <EvidencePanel d={d} />}
        {tab === 'forecast' && <ForecastPanel d={d} />}
      </div>
    </section>
  );
}

const COMPARE = [
  ['price_minor', 'Price'],
  ['shipping_minor', 'Shipping'],
  ['availability', 'Availability'],
  ['stock_quantity', 'Stock'],
] as const;

function cell(o: AsOf['listings'][number]['observation'], k: (typeof COMPARE)[number][0]): string {
  if (!o) return '';
  const cur = o.currency ?? 'INR';
  if (k === 'price_minor') return o.price_minor === null ? 'Unknown' : formatMoney(o.price_minor, cur);
  if (k === 'shipping_minor') return !o.shipping_known ? 'Unknown' : o.shipping_minor === 0 ? 'Free' : formatMoney(o.shipping_minor, cur);
  if (k === 'stock_quantity') return o.stock_quantity === null ? 'Unknown' : String(o.stock_quantity);
  return o.availability ?? 'Not reported';
}

/** Observed state on a chosen date, with an explicit end-of-day UTC cutoff. Nothing later is ever requested. */
function TimeMachine({ d }: { d: ProductDetail }) {
  const [params, setParams] = useSearchParams();
  const first = day(d.price_history.first_verified_at)!;
  const last = day(d.price_history.last_verified_at)!;
  const clamp = (x: string) => (x < first ? first : x > last ? last : x);
  const at = clamp(params.get('at') ?? last);
  const vs = clamp(params.get('vs') ?? addDays(at, -1));
  const setDay = (k: 'at' | 'vs', v: string) => setParams((p) => { const n = new URLSearchParams(p); n.set(k, clamp(v)); return n; }, { replace: k === 'vs' });
  const playing = params.get('play') === '1';
  const A = useAsOf(d.product.product_id, endOfDayUtc(at));
  const B = useAsOf(d.product.product_id, endOfDayUtc(vs));
  const totalDays = Math.round((Date.parse(last) - Date.parse(first)) / 86400000);
  const index = Math.round((Date.parse(at) - Date.parse(first)) / 86400000);

  useEffect(() => {
    if (!playing) return;
    if (at >= last) {
      setParams((p) => { const n = new URLSearchParams(p); n.delete('play'); return n; }, { replace: true });
      return;
    }
    const t = window.setTimeout(() => setDay('at', addDays(at, 1)), 1000);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, at]);

  const rowsB = new Map((B.data?.listings ?? []).map((l) => [l.listing_id, l]));
  return (
    <div className="stack-md time-machine">
      <p className="muted small">
        Reconstructs observed state from stored observations (not archived web pages). Requested: {formatDateTime(endOfDayUtc(at))}. Only observations at or before this time are used.
      </p>
      <div className="tm-controls">
        <label className="field">
          <span className="field__label">Show the observed state on</span>
          <input type="date" className="input" min={first} max={last} value={at} onChange={(e) => e.target.value && setDay('at', e.target.value)} />
        </label>
        <label className="field tm-scrub">
          <span className="field__label">Scrub through verified history</span>
          <input type="range" min={0} max={totalDays} value={index} onChange={(e) => setDay('at', addDays(first, Number(e.target.value)))} aria-valuetext={at} />
        </label>
        <div className="row-gap">
          <button type="button" className="btn btn--secondary btn--small" onClick={() => setDay('at', addDays(at, -1))} disabled={at <= first} aria-label="Previous day">◀ Previous</button>
          <button type="button" className="btn btn--secondary btn--small" aria-pressed={playing} disabled={at >= last && !playing}
            onClick={() => setParams((p) => { const n = new URLSearchParams(p); if (playing) n.delete('play'); else n.set('play', '1'); return n; }, { replace: true })}>
            {playing ? 'Pause' : 'Play'}
          </button>
          <button type="button" className="btn btn--secondary btn--small" onClick={() => setDay('at', addDays(at, 1))} disabled={at >= last} aria-label="Next day">Next ▶</button>
        </div>
        <label className="field">
          <span className="field__label">Compare with</span>
          <input type="date" className="input" min={first} max={last} value={vs} onChange={(e) => e.target.value && setDay('vs', e.target.value)} />
        </label>
      </div>
      {(A.isError || B.isError) && <p className="inline-error" role="alert">Couldn't load the observed state.</p>}
      {A.data && (
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Observed state comparison">
          <table className="table table--compact">
            <thead>
              <tr>
                <th scope="col">Store</th>
                <th scope="col">On {at}</th>
                <th scope="col">On {vs}</th>
              </tr>
            </thead>
            <tbody>
              {A.data.listings.map((l) => {
                const b = rowsB.get(l.listing_id);
                return (
                  <tr key={l.listing_id}>
                    <th scope="row">{l.marketplace}<span className="sub mono">{l.listing_id}</span></th>
                    <td>
                      {l.observation ? (
                        <>
                          <span className="sub">Observed {formatDateTime(l.observation.observed_at)} · {formatAge(l.age_seconds)}</span>
                          <dl className="tm-fields">
                            {COMPARE.map(([k, label]) => {
                              const changed = !!b?.observation && cell(l.observation, k) !== cell(b.observation, k);
                              return (
                                <div key={k} className={changed ? 'tm-changed' : undefined}>
                                  <dt>{label}</dt>
                                  <dd>{cell(l.observation, k)}{changed && <span className="tag tag--warn">Changed</span>}</dd>
                                </div>
                              );
                            })}
                          </dl>
                        </>
                      ) : (
                        <span className="muted small">{l.reason}</span>
                      )}
                    </td>
                    <td>
                      {b?.observation ? (
                        <>
                          <span className="sub">Observed {formatDateTime(b.observation.observed_at)} · {formatAge(b.age_seconds)}</span>
                          <dl className="tm-fields">
                            {COMPARE.map(([k, label]) => (
                              <div key={k}>
                                <dt>{label}</dt>
                                <dd>{cell(b.observation, k)}</dd>
                              </div>
                            ))}
                          </dl>
                        </>
                      ) : (
                        <span className="muted small">{b?.reason ?? ''}</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
