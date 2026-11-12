import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { PageHeader } from './PageHeader';
import { HBarChart } from '../components/HBarChart';
import { apiGet } from '../lib/api';
import { useDataMode } from '../lib/dataMode';
import { endOfDayUtc } from '../lib/history';
import { formatMoney } from '../lib/money';
import { formatCount, formatDateTime } from '../lib/format';

interface Meta { latest_verified_at: string | null; categories: string[]; marketplaces: string[]; windows: number[] }
interface Horizon { days: number; available: number; model_chosen: number; baseline_chosen: number; mean_mae_baseline_minor: number | null; mean_mae_model_minor: number | null; mean_mape_baseline_percent: number | null; mean_mape_model_percent: number | null; mean_measured_coverage_percent: number | null; coverage_note: string }
interface Row { product_id: string; name: string; category: string; status: string; verdict: string | null; savings_percent: number | null; score: number | null; band: string | null; advice: string; advice_confidence: string | null; lowest_marketplace: string | null; audit: string[]; sync_patterns: number }
interface Dash {
  cutoff: string; window: { days: number }; cache: { hit: boolean; computed_at: string };
  totals: { products: number; listings: number; verified_observations: number; snapshot_observations: number; rejected_records: number; ingestion_runs: number };
  quality: { stock_contradiction_observations: number; discount_mismatch_observations: number; unknown_shipping_observations: number; note: string };
  provenance: { synthetic: boolean; source_labels: string[] };
  marketplaces: { marketplace: string; listings: number; verified_observations: number; snapshot_observations: number; lowest_current_price_products: number }[];
  historical: {
    status: 'available' | 'no_verified_history'; reason?: string; truncated?: boolean; max_products?: number; products_analyzed: number; products_insufficient: number;
    detector?: Record<string, number>; score_bands?: Record<string, number>; advice?: Record<string, number>; savings_distribution?: { label: string; count: number }[];
    audit?: { by_rule: Record<string, { title: string; kind: string; count: number; products: { product_id: string; name: string; severity: string }[] }>; note: string };
    sync?: { pairs: Record<string, number>; pattern_products: { product_id: string; name: string; pairs: number }[]; note: string };
    forecast?: { horizons: Horizon[]; note: string }; trend?: { date: string; index: number; products: number }[]; trend_note?: string; products: Row[];
  };
}

const VERDICT = { below_usual: 'Genuine price reduction', around_usual: 'No real reduction', above_usual: 'Above usual price' } as const;
const ADVICE = { buy_now: 'Buy now', consider_waiting: 'Consider waiting', insufficient_evidence: 'Insufficient evidence' } as const;
const BAND = { strong: 'Strong evidence', moderate: 'Some evidence', weak: 'Little evidence' } as const;
const SYNC = { pattern: 'Pattern worth investigating', occasional: 'Occasional', independent: 'Independent', no_changes: 'No price changes', insufficient: 'Insufficient', not_comparable: 'Not comparable' } as const;
const label = (m: Record<string, string>, k: string) => m[k] ?? k;
const count = (v: number) => formatCount(v);

export function AnalystDashboard() {
  const { mode, unavailableReason } = useDataMode();
  const [params, setParams] = useSearchParams();
  const blocked = unavailableReason(mode);
  const meta = useQuery({ queryKey: ['dash-meta', mode], queryFn: () => apiGet<Meta>('/api/v1/dashboard/meta', { mode }), enabled: !blocked });
  const today = new Date().toISOString().slice(0, 10);
  const day = params.get('cutoff') ?? (meta.data ? (meta.data.latest_verified_at?.slice(0, 10) ?? today) : null);
  const win = [30, 90, 180].includes(Number(params.get('window'))) ? Number(params.get('window')) : 90;
  const category = params.get('category') ?? '';
  const marketplace = params.get('store') ?? '';
  const cutoff = day ? endOfDayUtc(day) : null;
  const q = useQuery({
    queryKey: ['dashboard', mode, cutoff, win, category, marketplace],
    queryFn: () => apiGet<Dash>('/api/v1/dashboard', { mode, cutoff: cutoff!, window: String(win), ...(category ? { category } : {}), ...(marketplace ? { marketplace } : {}) }),
    enabled: cutoff !== null && !blocked,
  });
  const set = (k: string, v: string) => setParams((p) => { const n = new URLSearchParams(p); if (v) n.set(k, v); else n.delete(k); return n; }, { replace: true });

  return (
    <div className="stack-lg dashboard">
      <PageHeader eyebrow="Analyst" title="Analyst dashboard" note="Summaries of the active workspace only. Historical figures use verified UTC observations up to the cutoff; snapshot data is counted separately." />
      {blocked && <p className="empty-inline">{blocked}</p>}
      {meta.isError && <p className="inline-error" role="alert">Couldn't load the dashboard: {meta.error.message}</p>}
      {meta.data && (
        <section className="card section-card dash-filters" aria-label="Dashboard filters">
          <label className="field">
            <span className="field__label">Cutoff (UTC, end of day)</span>
            <input type="date" className="input" value={day ?? ''} max={today} onChange={(e) => e.target.value && set('cutoff', e.target.value)} />
          </label>
          <label className="field">
            <span className="field__label">Category</span>
            <select className="input" value={category} onChange={(e) => set('category', e.target.value)}>
              <option value="">All categories</option>
              {meta.data.categories.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
          <label className="field">
            <span className="field__label">Store</span>
            <select className="input" value={marketplace} onChange={(e) => set('store', e.target.value)}>
              <option value="">All stores</option>
              {meta.data.marketplaces.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </label>
          <div className="segmented" role="group" aria-label="Historical window">
            {[30, 90, 180].map((w) => <button key={w} type="button" className="segmented__item" aria-pressed={win === w} onClick={() => set('window', String(w))}>{w}D</button>)}
          </div>
        </section>
      )}
      {q.isPending && cutoff && !blocked && <p className="muted" role="status">Computing the dashboard… The first load for new filters can take a few seconds; results are then cached until the next import.</p>}
      {q.isError && <p className="inline-error" role="alert">Couldn't load the dashboard: {q.error.message}</p>}
      {q.data && <Body d={q.data} />}
    </div>
  );
}

function Body({ d }: { d: Dash }) {
  const h = d.historical;
  return (
    <>
      <section className="card section-card stack-md" aria-labelledby="dash-data">
        <div className="section-head">
          <h2 id="dash-data">Data analysed</h2>
          <span className="muted small">Up to {formatDateTime(d.cutoff)} · {d.window.days}-day window</span>
        </div>
        <dl className="stats">
          <div className="stats__item"><dt>Products</dt><dd>{count(d.totals.products)}</dd></div>
          <div className="stats__item"><dt>Store listings</dt><dd>{count(d.totals.listings)}</dd></div>
          <div className="stats__item"><dt>Verified observations</dt><dd>{count(d.totals.verified_observations)}</dd></div>
          <div className="stats__item"><dt>Snapshot observations (no timezone)</dt><dd>{count(d.totals.snapshot_observations)}</dd></div>
          <div className="stats__item"><dt>Stock contradictions</dt><dd>{count(d.quality.stock_contradiction_observations)}</dd></div>
          <div className="stats__item"><dt>Quarantined rows</dt><dd>{count(d.totals.rejected_records)}</dd></div>
        </dl>
        <p className="muted small">
          {d.quality.note} Discount-label mismatches: {count(d.quality.discount_mismatch_observations)}. Unknown shipping: {count(d.quality.unknown_shipping_observations)}.
          {d.provenance.source_labels.length > 0 && ` Sources: ${d.provenance.source_labels.join(', ')}.`} {d.cache.hit ? 'Served from cache' : 'Computed'} at {formatDateTime(d.cache.computed_at)}.
        </p>
        {d.marketplaces.length > 0 && (
          <HBarChart title="Stores" summary="Listings per store, and how often each store had the lowest current price among products with verified history."
            series={[{ key: 'listings', label: 'Listings', tone: 'a' }, { key: 'lowest', label: 'Lowest current price', tone: 'd' }]}
            rows={d.marketplaces.map((m) => ({ label: m.marketplace, values: { listings: m.listings, lowest: h.status === 'available' ? m.lowest_current_price_products : null } }))}
            format={count} />
        )}
      </section>
      {h.status !== 'available' ? (
        <section className="card section-card"><p className="empty-inline">{h.reason}</p></section>
      ) : (
        <Historical h={h} />
      )}
    </>
  );
}

function Historical({ h }: { h: Dash['historical'] }) {
  const rows = (m: Record<string, string>, data: Record<string, number> = {}) => Object.keys(m).map((k) => ({ label: m[k], values: { n: data[k] ?? 0 } }));
  return (
    <>
      <section className="card section-card stack-md" aria-labelledby="dash-evidence">
        <div className="section-head">
          <h2 id="dash-evidence">Price evidence and advice</h2>
          <span className="muted small">{h.products_analyzed} products analysed · {h.products_insufficient} with insufficient evidence{h.truncated ? ` · first ${h.max_products} products only` : ''}</span>
        </div>
        <div className="dash-grid">
          <HBarChart title="Real Price Detector" summary="Current price vs each product's usual (median) price in the window." series={[{ key: 'n', label: 'Products', tone: 'b' }]} rows={rows(VERDICT, h.detector)} format={count} />
          <HBarChart title="Buying advice" summary="From observed history only; forecasts never decide advice." series={[{ key: 'n', label: 'Products', tone: 'a' }]} rows={rows(ADVICE, h.advice)} format={count} />
          <HBarChart title="Genuine Discount Score" summary="Products by score band." series={[{ key: 'n', label: 'Products', tone: 'd' }]} rows={rows(BAND, h.score_bands)} format={count} />
          <HBarChart title="Real savings distribution" summary="Real savings vs usual price (negative = above usual)." series={[{ key: 'n', label: 'Products', tone: 'c' }]}
            rows={(h.savings_distribution ?? []).map((b) => ({ label: b.label, values: { n: b.count } }))} format={count} />
        </div>
        {h.trend && h.trend.length > 1 && <Trend points={h.trend} note={h.trend_note ?? ''} />}
      </section>
      <section className="card section-card stack-md" aria-labelledby="dash-audit">
        <h2 id="dash-audit">Pricing audit findings</h2>
        <p className="callout" role="note">{h.audit?.note}</p>
        {Object.keys(h.audit?.by_rule ?? {}).length === 0 ? <p className="muted">No audit rule was triggered.</p> : (
          <ul className="dash-findings">
            {Object.entries(h.audit!.by_rule).map(([id, r]) => (
              <li key={id} className="evidence__card">
                <strong>{r.title}</strong> <span className="tag tag--synthetic">{r.kind}</span> <span className="muted small">{r.count} product{r.count === 1 ? '' : 's'}</span>
                <details>
                  <summary>Products</summary>
                  <ul className="bullets">{r.products.slice(0, 50).map((p) => <li key={p.product_id}><Link to={`/products/${encodeURIComponent(p.product_id)}#audit`}>{p.name}</Link> <span className="muted small">{p.severity} severity</span></li>)}</ul>
                </details>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="card section-card stack-md" aria-labelledby="dash-sync">
        <h2 id="dash-sync">Seller synchronization</h2>
        <p className="callout" role="note">{h.sync?.note}</p>
        <HBarChart title="Store-listing pairs" summary="Every pair of a product's store listings, by result." series={[{ key: 'n', label: 'Pairs', tone: 'b' }]} rows={rows(SYNC, h.sync?.pairs)} format={count} />
        {(h.sync?.pattern_products.length ?? 0) > 0 && (
          <p className="small">Patterns worth investigating: {h.sync!.pattern_products.map((p, i) => <span key={p.product_id}>{i ? ', ' : ''}<Link to={`/products/${encodeURIComponent(p.product_id)}#sync`}>{p.name}</Link> ({p.pairs})</span>)}</p>
        )}
      </section>
      {h.forecast && (
        <section className="card section-card stack-md" aria-labelledby="dash-fc">
          <h2 id="dash-fc">Forecast accuracy (backtests)</h2>
          <p className="muted small">{h.forecast.note}</p>
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Forecast accuracy region">
            <table className="table table--compact" aria-label="Forecast accuracy">
              <thead><tr><th scope="col">Horizon</th><th scope="col">Products</th><th scope="col">Model used / baseline used</th><th scope="col">Mean abs. error: baseline vs model</th><th scope="col">MAPE: baseline vs model</th><th scope="col">Range coverage</th></tr></thead>
              <tbody>
                {h.forecast.horizons.map((x) => (
                  <tr key={x.days}>
                    <td>{x.days} days</td><td>{x.available}</td><td>{x.model_chosen} / {x.baseline_chosen}</td>
                    <td>{formatMoney(x.mean_mae_baseline_minor === null ? null : Math.round(x.mean_mae_baseline_minor))} vs {formatMoney(x.mean_mae_model_minor === null ? null : Math.round(x.mean_mae_model_minor))}</td>
                    <td>{x.mean_mape_baseline_percent}% vs {x.mean_mape_model_percent}%</td>
                    <td className="small">{x.coverage_note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      <section className="card section-card stack-md" aria-labelledby="dash-products">
        <h2 id="dash-products">Products</h2>
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Products analysed region">
          <table className="table table--compact" aria-label="Products analysed">
            <thead><tr><th scope="col">Product</th><th scope="col">Detector</th><th scope="col">Real savings</th><th scope="col">Score</th><th scope="col">Advice</th><th scope="col">Audit</th><th scope="col">Sync patterns</th></tr></thead>
            <tbody>
              {h.products.map((r) => (
                <tr key={r.product_id}>
                  <td><Link to={`/products/${encodeURIComponent(r.product_id)}?tab=evidence`}>{r.name}</Link><div className="muted small">{r.category}</div></td>
                  <td>{r.verdict ? label(VERDICT, r.verdict) : 'Insufficient'}</td>
                  <td>{r.savings_percent === null ? '—' : `${r.savings_percent}%`}</td>
                  <td>{r.score ?? '—'}</td>
                  <td>{label(ADVICE, r.advice)}{r.advice_confidence ? ` (${r.advice_confidence})` : ''}</td>
                  <td className="small">{r.audit.length ? r.audit.join(', ') : '—'}</td>
                  <td>{r.sync_patterns || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

function Trend({ points, note }: { points: { date: string; index: number }[]; note: string }) {
  const W = 600, H = 160;
  const lo = Math.min(...points.map((p) => p.index), 95);
  const hi = Math.max(...points.map((p) => p.index), 105);
  const X = (i: number) => (i / (points.length - 1)) * W;
  const Y = (v: number) => H - ((v - lo) / (hi - lo || 1)) * H;
  const d = points.map((p, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(p.index).toFixed(1)}`).join(' ');
  const last = points[points.length - 1];
  return (
    <figure className="chart">
      <figcaption className="chart__title">Price index trend</figcaption>
      <p className="chart__summary muted small">{note} Latest: {last.index} on {last.date}.</p>
      <div className="history-plot">
        <div className="history-y" aria-hidden="true"><span>{hi.toFixed(0)}</span><span>{lo.toFixed(0)}</span></div>
        <div className="history-canvas">
          <svg className="history-chart dash-trend" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={`Price index from ${points[0].date} to ${last.date}; latest ${last.index}.`}>
            <line className="history-grid" x1="0" x2={W} y1={Y(100)} y2={Y(100)} />
            <path className="history-line" d={d} />
          </svg>
          <div className="history-x" aria-hidden="true"><span>{points[0].date}</span><span>{last.date}</span></div>
        </div>
      </div>
    </figure>
  );
}
