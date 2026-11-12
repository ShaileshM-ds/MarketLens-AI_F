import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { analysisDay, endOfDayUtc, useAudit, useSellerSync, type AuditFinding, type ProductAudit, type SellerSync, type SyncPair } from '../lib/history';
import { formatMoney } from '../lib/money';
import { formatDateTime } from '../lib/format';
import type { ProductDetail } from '../lib/products';

const day = (iso: string | null | undefined) => (iso ? iso.slice(0, 10) : null);
const KIND = { observed: ['Observed fact', 'tag--good'], calculated: ['Calculated finding', 'tag--warn'], heuristic: ['Heuristic warning', 'tag--synthetic'] } as const;
const SEVERITY = { high: 'tag--bad', medium: 'tag--warn', low: 'tag--synthetic' } as const;
const RULE_STATUS = { triggered: ['Triggered', 'tag--warn'], not_triggered: ['Not triggered', 'tag--good'], disabled: ['Disabled', 'tag--synthetic'] } as const;
const PAIR_TAG = { pattern: 'tag--warn', occasional: 'tag--synthetic', independent: 'tag--good', no_changes: 'tag--synthetic', insufficient: 'tag--synthetic', not_comparable: 'tag--synthetic' } as const;
const cap = (s: string) => s[0].toUpperCase() + s.slice(1);

function useCutoff(d: ProductDetail) {
  const [params] = useSearchParams();
  const at = analysisDay(params, day(d.price_history.first_verified_at), day(d.price_history.last_verified_at));
  const ewin = Number(params.get('ewin'));
  return { at, win: [30, 90, 180].includes(ewin) ? ewin : 90 };
}

/** Dark-pattern audit (SCOPE §5). Snapshot-only products are audited for observed facts with today's end (UTC) as the cutoff. */
export function AuditSection({ d }: { d: ProductDetail }) {
  const { at, win } = useCutoff(d);
  const [today] = useState(() => new Date().toISOString().slice(0, 10));
  const cutoff = endOfDayUtc(at ?? today);
  const q = useAudit(d.product.product_id, cutoff, win);
  return (
    <section id="audit" className="card section-card stack-md" aria-labelledby="audit-title">
      <div className="section-head">
        <h2 id="audit-title">Pricing practices audit</h2>
        <span className="muted small">Up to {formatDateTime(cutoff)} · {win}-day window</span>
      </div>
      {q.isPending && <p className="muted" role="status">Loading audit…</p>}
      {(q.isError || (q.data && !Array.isArray(q.data.findings))) && <p className="inline-error" role="alert">Couldn't load the audit{q.error ? `: ${q.error.message}` : '.'}</p>}
      {q.data && Array.isArray(q.data.findings) && <AuditBody a={q.data} />}
    </section>
  );
}

function AuditBody({ a }: { a: ProductAudit }) {
  return (
    <div className="stack-md">
      <p className="callout" role="note">{a.note}</p>
      {a.findings.length === 0 ? (
        <p className="empty-inline">No audit rule was triggered by the data up to this cutoff. Disabled rules below couldn't be checked.</p>
      ) : (
        <div className="audit-findings">{a.findings.map((f) => <Finding key={f.rule_id} f={f} />)}</div>
      )}
      <details>
        <summary>Rules checked ({a.rules.length})</summary>
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Audit rules">
          <table className="table table--compact">
            <thead><tr><th scope="col">Rule</th><th scope="col">Type</th><th scope="col">Status</th><th scope="col">Why</th></tr></thead>
            <tbody>
              {a.rules.map((r) => (
                <tr key={r.rule_id}>
                  <td>{r.title}<div className="muted small">{r.version}</div></td>
                  <td className="small">{r.kind}</td>
                  <td><span className={`tag ${RULE_STATUS[r.status][1]}`}>{RULE_STATUS[r.status][0]}</span></td>
                  <td className="small">{r.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
      <p className="muted small">
        Read {a.observations_read.verified} verified and {a.observations_read.snapshot} snapshot observations.
      </p>
    </div>
  );
}

function Finding({ f }: { f: AuditFinding }) {
  return (
    <article className="evidence__card stack-sm audit-finding" aria-labelledby={`f-${f.rule_id}`}>
      <div className="advice__head">
        <h3 id={`f-${f.rule_id}`} className="audit-finding__title">{f.title}</h3>
      </div>
      <div className="row-gap">
        <span className={`tag ${KIND[f.kind][1]}`}>{KIND[f.kind][0]}</span>
        <span className={`tag ${SEVERITY[f.severity]}`}>{cap(f.severity)} severity</span>
        <span className="tag tag--synthetic">{cap(f.confidence.level)} confidence</span>
      </div>
      <p>{f.explanation}</p>
      <p className="muted small">Confidence: {f.confidence.reason} Rule {f.rule_version}.</p>
      <div>
        <h4>Ordinary explanations</h4>
        <ul className="bullets">{f.benign_explanations.map((b) => <li key={b}>{b}</li>)}</ul>
      </div>
      {f.limitations.length > 0 && <p className="muted small">{f.limitations.join(' ')}</p>}
      <details>
        <summary>Supporting observations ({f.supporting_observations.length})</summary>
        <div className="table-wrap" tabIndex={0} role="region" aria-label={`Supporting observations for ${f.title}`}>
          <table className="table table--compact">
            <thead><tr><th scope="col">Time</th><th scope="col">Store</th><th scope="col">Price</th><th scope="col">Reference</th><th scope="col">Advertised</th><th scope="col">Availability / stock</th><th scope="col">Urgency</th></tr></thead>
            <tbody>
              {f.supporting_observations.map((o, i) => (
                <tr key={i}>
                  <td>{o.observed_at ? formatDateTime(o.observed_at) : o.date ? `${o.date} (daily)` : `${o.source_timestamp} (timezone unknown)`}</td>
                  <td>{o.marketplace ?? '—'}</td>
                  <td>{formatMoney(o.price_minor ?? o.value_minor ?? null, o.currency ?? 'INR')}</td>
                  <td>{formatMoney(o.reference_price_minor ?? null, o.currency ?? 'INR')}</td>
                  <td>{o.advertised_discount_percent === null || o.advertised_discount_percent === undefined ? '—' : `${o.advertised_discount_percent}%`}</td>
                  <td>{o.note ?? `${o.availability ?? 'Unknown'} / ${o.stock_quantity ?? 'unknown'}`}</td>
                  <td>{o.urgency_message || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </article>
  );
}

/** Seller synchronization (SCOPE §5): patterns worth investigating, never proof. Needs verified history. */
export function SyncSection({ d }: { d: ProductDetail }) {
  const { at, win } = useCutoff(d);
  const q = useSellerSync(d.product.product_id, at ? endOfDayUtc(at) : null, win);
  return (
    <section id="sync" className="card section-card stack-md" aria-labelledby="sync-title">
      <div className="section-head">
        <h2 id="sync-title">Seller synchronization</h2>
        {at && <span className="muted small">Up to {formatDateTime(endOfDayUtc(at))} · {win}-day window</span>}
      </div>
      {!at && <p className="empty-inline">Insufficient evidence: synchronization needs repeated, verified UTC observations from at least two store listings. This product only has snapshot observations.</p>}
      {at && q.isPending && <p className="muted" role="status">Loading seller synchronization…</p>}
      {at && (q.isError || (q.data && !Array.isArray(q.data.pairs))) && <p className="inline-error" role="alert">Couldn't load seller synchronization{q.error ? `: ${q.error.message}` : '.'}</p>}
      {q.data && Array.isArray(q.data.pairs) && <SyncBody s={q.data} />}
    </section>
  );
}

function SyncBody({ s }: { s: SellerSync }) {
  const [sel, setSel] = useState(0);
  const pair = s.pairs[sel];
  return (
    <div className="stack-md">
      <p className="callout" role="note">{s.note}</p>
      <p className="muted small">
        A change is a move of {s.method.change_percent}% or more between consecutive observed days; two changes match when they go the same way within {s.method.match_days} day.
        A pattern needs {s.method.min_matches}+ matches covering {s.method.min_share * 100}% of the smaller set of changes.
      </p>
      {s.status !== 'available' && <p className="empty-inline">{s.reason}</p>}
      {s.pairs.length > 0 && (
        <ul className="sync-pairs">
          {s.pairs.map((p, i) => (
            <li key={`${p.a.listing_id}|${p.b.listing_id}`}>
              <button type="button" className="sync-pair" aria-pressed={i === sel} onClick={() => setSel(i)}>
                <span className="sync-pair__names">{p.a.marketplace} · {p.a.seller_name ?? p.a.seller_id} ↔ {p.b.marketplace} · {p.b.seller_name ?? p.b.seller_id}</span>
                <span className={`tag ${PAIR_TAG[p.status]}`}>{p.label}</span>
              </button>
              <p className="small sync-pair__summary">{p.summary}</p>
            </li>
          ))}
        </ul>
      )}
      {pair && pair.matched + pair.a.changes.length + pair.b.changes.length > 0 && <PairDetail p={pair} s={s} />}
    </div>
  );
}

function PairDetail({ p, s }: { p: SyncPair; s: SellerSync }) {
  const t = (iso: string) => Date.parse(`${iso}T00:00:00Z`);
  const x0 = t(s.window.start.slice(0, 10));
  const x1 = t(s.window.end.slice(0, 10));
  const X = (iso: string) => 2 + ((t(iso) - x0) / (x1 - x0 || 1)) * 96;
  const matchedA = new Set(p.matches.map((m) => m.date_a));
  const matchedB = new Set(p.matches.map((m) => m.date_b));
  const row = (changes: SyncPair['a']['changes'], matched: Set<string>, y: number) =>
    changes.map((c) => (
      <g key={`${y}-${c.date}`} className={`sync-mark ${matched.has(c.date) ? 'sync-mark--matched' : ''}`}>
        <title>{`${c.date}: ${c.change_percent > 0 ? '+' : ''}${c.change_percent}%`}</title>
        <polygon points={c.change_percent > 0 ? `${X(c.date)},${y - 7} ${X(c.date) - 1.2},${y + 4} ${X(c.date) + 1.2},${y + 4}` : `${X(c.date)},${y + 7} ${X(c.date) - 1.2},${y - 4} ${X(c.date) + 1.2},${y - 4}`} />
      </g>
    ));
  return (
    <section className="stack-sm" aria-labelledby="sync-detail">
      <h3 id="sync-detail" className="h4">Aligned price changes</h3>
      <div className="sync-legend small" aria-hidden="true">
        <span><i className="sync-key sync-key--matched" /> Matched change</span>
        <span><i className="sync-key" /> Unmatched change</span>
        <span>▲ up · ▼ down</span>
      </div>
      <div className="sync-plot">
        <div className="sync-labels small" aria-hidden="true"><span>{p.a.marketplace}</span><span>{p.b.marketplace}</span></div>
        <svg className="sync-timeline" viewBox="0 0 100 60" preserveAspectRatio="none" role="img"
          aria-label={`${p.a.changes.length} changes on ${p.a.marketplace} and ${p.b.changes.length} on ${p.b.marketplace}; ${p.matched} matched.`}>
          <line className="history-grid" x1="0" x2="100" y1="18" y2="18" />
          <line className="history-grid" x1="0" x2="100" y1="44" y2="44" />
          {p.matches.map((m) => <line key={m.date_a} className="sync-link" x1={X(m.date_a)} y1="18" x2={X(m.date_b)} y2="44" />)}
          {row(p.a.changes, matchedA, 18)}
          {row(p.b.changes, matchedB, 44)}
        </svg>
      </div>
      <div className="history-x small" aria-hidden="true"><span>{s.window.start.slice(0, 10)}</span><span>{s.window.end.slice(0, 10)}</span></div>
      <p className="small">
        {p.common_days} days observed for both · {p.matched} matched ({p.same_day} same day, {p.a.marketplace} first {p.a_first}, {p.b.marketplace} first {p.b_first}).
      </p>
      {p.matches.length > 0 && (
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Matched changes region">
          <table className="table table--compact" aria-label="Matched changes">
            <thead><tr><th scope="col">{p.a.marketplace}</th><th scope="col">Change</th><th scope="col">{p.b.marketplace}</th><th scope="col">Change</th></tr></thead>
            <tbody>
              {p.matches.map((m) => (
                <tr key={m.date_a}><td>{m.date_a}</td><td>{m.change_a_percent > 0 ? '+' : ''}{m.change_a_percent}%</td><td>{m.date_b}</td><td>{m.change_b_percent > 0 ? '+' : ''}{m.change_b_percent}%</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {p.benign_explanations.length > 0 && (
        <div>
          <h4>Ordinary explanations</h4>
          <ul className="bullets">{p.benign_explanations.map((b) => <li key={b}>{b}</li>)}</ul>
        </div>
      )}
    </section>
  );
}
