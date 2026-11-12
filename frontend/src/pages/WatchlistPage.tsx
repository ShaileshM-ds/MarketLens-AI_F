import { useState } from 'react';
import { Link } from 'react-router-dom';
import { PageHeader } from './PageHeader';
import { ProductImage } from '../components/ProductImage';
import { AlertDialog, type AlertProduct } from '../components/AlertDialog';
import { useMe } from '../lib/auth';
import { MODE_LABELS, useDataMode } from '../lib/dataMode';
import { formatMoney } from '../lib/money';
import { formatDateTime, formatObservedAt } from '../lib/format';
import { alertTypeLabel, usePersonalMutation, useNotifications, useRules, useWatchlist, watchApi, type AlertRule, type AppNotification, type WatchItem } from '../lib/watch';

const OUTCOMES: Record<string, string> = {
  notified: 'Notified',
  suppressed_not_armed: 'Qualified, waiting to re-arm',
  suppressed_cooldown: 'Qualified, in cooldown',
  not_qualifying: 'Above target',
  excluded: 'Not comparable',
  baseline_recorded: 'Baseline recorded (no notification)',
  no_change: 'No change',
  insufficient: 'Insufficient evidence',
};
const REASONS: Record<string, string> = {
  shipping_unknown: 'shipping unknown',
  out_of_stock: 'reported out of stock',
  stock_availability_contradiction: 'stock contradiction',
  availability_not_reported: 'availability not reported',
  currency_mismatch: 'different currency',
  watch_period_ended: 'watch period ended',
  no_price: 'no price',
};
const BASIS = { base: 'Base price', delivered: 'Confirmed delivered price' } as const;

export function WatchlistPage() {
  const me = useMe();
  const { mode } = useDataMode();
  const [dialog, setDialog] = useState<{ product: AlertProduct; rule?: AlertRule } | null>(null);
  const [saved, setSaved] = useState<AlertRule | null>(null);

  if (me.isPending) return <p className="muted" role="status">Checking your account…</p>;
  if (!me.data) {
    return (
      <div className="stack-lg">
        <PageHeader title="Watchlist & alerts" note="Targets are entered in rupees. Alerts arrive in the app." />
        <section className="card empty-state">
          <h2>Sign in to use your watchlist</h2>
          <p className="muted">Your watchlist, price alerts and notifications are private to your account.</p>
          <p>
            <Link to={`/signin?next=${encodeURIComponent('/watchlist')}`} className="btn btn--primary">
              Sign in
            </Link>
          </p>
        </section>
      </div>
    );
  }

  return (
    <div className="stack-lg">
      <PageHeader title="Watchlist & alerts" note={`Targets are entered in rupees. Alerts arrive in the app. Showing ${MODE_LABELS[mode].name} data.`} />
      <p className="callout" role="note">
        Alerts are checked when new observations are imported. There's no continuous live monitoring, and existing snapshot prices never trigger an alert.
      </p>
      {saved && (
        <section className="callout callout--ok" role="status" aria-label="Alert saved">
          <p>
            <strong>Alert saved.</strong>
          </p>
          {saved.current_context && (
            <>
              <p className="small">{saved.current_context.note}</p>
              {saved.current_context.qualifying_now.length > 0 ? (
                <ul className="bullets small">
                  {saved.current_context.qualifying_now.map((q) => (
                    <li key={q.listing_id}>
                      {q.marketplace} {formatMoney(q.value_minor, saved.currency ?? undefined)}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="small">No current snapshot listing is at or below this target.</p>
              )}
            </>
          )}
          <button type="button" className="link-button" onClick={() => setSaved(null)}>
            Close message
          </button>
        </section>
      )}
      <WatchedProducts onCreateAlert={(product) => setDialog({ product })} />
      <Rules onEdit={(product, rule) => setDialog({ product, rule })} />
      <Notifications />
      {dialog && <AlertDialog product={dialog.product} rule={dialog.rule} onClose={() => setDialog(null)} onSaved={setSaved} />}
    </div>
  );
}

function toAlertProduct(i: WatchItem): AlertProduct {
  return {
    id: i.product_id,
    name: i.product?.name ?? i.product_id,
    marketplaces: i.product?.marketplaces ?? [],
    currency: i.product?.pricing.currency ?? 'INR',
  };
}

function WatchedProducts({ onCreateAlert }: { onCreateAlert: (p: AlertProduct) => void }) {
  const q = useWatchlist();
  const remove = usePersonalMutation((id: string, m) => watchApi.remove(id, m));
  const [confirming, setConfirming] = useState<string | null>(null);
  return (
    <section className="card section-card stack-md" aria-labelledby="watched-title">
      <h2 id="watched-title">Watched products</h2>
      {q.isPending && <p className="muted" role="status">Loading your watchlist…</p>}
      {q.isError && <p className="inline-error" role="alert">Couldn't load your watchlist: {q.error.message}</p>}
      {q.data && q.data.items.length === 0 && (
        <p className="muted">
          Your watchlist is empty. Use <strong>Watch</strong> on a product in the <Link to="/products" className="link">Product Explorer</Link>.
        </p>
      )}
      {q.data && q.data.items.length > 0 && (
        <ul className="watch-grid">
          {q.data.items.map((i) => {
            const p = i.product;
            const name = p?.name ?? i.product_id;
            const listed = p?.pricing.lowest_listed;
            const delivered = p?.pricing.lowest_confirmed_delivered;
            const a = p?.availability_summary;
            return (
              <li key={i.product_id}>
                <article className="card watch-card" aria-labelledby={`w-${i.product_id}`}>
                  <ProductImage kind={p?.image.kind} productId={i.product_id} name={p?.name} />
                  <div className="stack-sm">
                    <p className="product-card__meta">{p?.category_label}</p>
                    <h3 id={`w-${i.product_id}`} className="product-card__title">
                      {name}
                    </h3>
                    <p className="mono muted small">{i.product_id}</p>
                    {!p && <p className="inline-error small">This product isn't in this workspace any more.</p>}
                    <dl className="watch-prices">
                      <div>
                        <dt>Lowest listed</dt>
                        <dd>{listed?.amount_minor != null ? formatMoney(listed.amount_minor, listed.currency ?? 'INR') : <span className="muted">Not available</span>}</dd>
                      </div>
                      <div>
                        <dt>Lowest confirmed delivered</dt>
                        <dd>{delivered?.amount_minor != null ? formatMoney(delivered.amount_minor, delivered.currency ?? 'INR') : <span className="muted">Can't be confirmed</span>}</dd>
                      </div>
                    </dl>
                    {a && (
                      <p className="small muted">
                        Imported snapshot: {a.in_stock} in stock, {a.limited_stock} limited, {a.out_of_stock} out of stock
                        {a.contradictions ? `, ${a.contradictions} with a stock contradiction` : ''}
                      </p>
                    )}
                    <p className="small">
                      {i.alerts.active === 0 && i.alerts.paused === 0
                        ? 'No alerts'
                        : [i.alerts.active && `${i.alerts.active} active alert${i.alerts.active === 1 ? '' : 's'}`, i.alerts.paused && `${i.alerts.paused} paused`].filter(Boolean).join(' · ')}
                    </p>
                    {p && (
                      <div className="product-card__tags">
                        {p.quality_labels.filter((ql) => ql.code !== 'synthetic_dataset').map((ql) => (
                          <span key={ql.code} className="tag tag--warn" title={ql.description}>
                            {ql.label}
                          </span>
                        ))}
                      </div>
                    )}
                    {i.notes && <p className="small">Note: {i.notes}</p>}
                    <div className="row-gap">
                      <Link to={`/products/${encodeURIComponent(i.product_id)}`} className="btn btn--secondary btn--small" aria-label={`View details for ${name}`}>
                        View details
                      </Link>
                      {p && (
                        <button type="button" className="btn btn--primary btn--small" aria-label={`Create alert for ${name}`} onClick={() => onCreateAlert(toAlertProduct(i))}>
                          Create alert
                        </button>
                      )}
                      {confirming === i.product_id ? (
                        <>
                          <button type="button" className="btn btn--secondary btn--small" aria-label={`Confirm remove ${name}`} onClick={() => remove.mutate(i.product_id)}>
                            Confirm remove{i.alerts.active + i.alerts.paused ? ' (also deletes its alerts)' : ''}
                          </button>
                          <button type="button" className="link-button small" onClick={() => setConfirming(null)}>
                            Cancel
                          </button>
                        </>
                      ) : (
                        <button type="button" className="btn btn--secondary btn--small" aria-label={`Remove ${name} from watchlist`} onClick={() => setConfirming(i.product_id)}>
                          Remove
                        </button>
                      )}
                    </div>
                  </div>
                </article>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function Rules({ onEdit }: { onEdit: (p: AlertProduct, r: AlertRule) => void }) {
  const q = useRules();
  const watch = useWatchlist();
  const patch = usePersonalMutation(({ id, body }: { id: string; body: Record<string, unknown> }, m) => watchApi.patchRule(id, body, m));
  const del = usePersonalMutation((id: string, m) => watchApi.deleteRule(id, m));
  const [confirming, setConfirming] = useState<string | null>(null);

  const productFor = (r: AlertRule): AlertProduct => {
    const w = watch.data?.items.find((i) => i.product_id === r.product_id);
    return w ? toAlertProduct(w) : { id: r.product_id, name: r.product_name ?? r.product_id, marketplaces: r.marketplace ? [r.marketplace] : [], currency: r.currency ?? 'INR' };
  };

  return (
    <section className="card section-card stack-md" aria-labelledby="rules-title">
      <h2 id="rules-title">Price alerts</h2>
      {q.isPending && <p className="muted" role="status">Loading alerts…</p>}
      {q.isError && <p className="inline-error" role="alert">Couldn't load alerts: {q.error.message}</p>}
      {(patch.isError || del.isError) && <p className="inline-error" role="alert">That change couldn't be saved.</p>}
      {q.data && q.data.rules.length === 0 && <p className="muted">No price alerts yet. Add a product to your watchlist and create a target-price alert.</p>}
      {q.data && q.data.rules.length > 0 && (
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Price alerts table">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Product</th>
                <th scope="col">Store</th>
                <th scope="col">Basis</th>
                <th scope="col" className="num">Target</th>
                <th scope="col">Status</th>
                <th scope="col">Last evaluated</th>
                <th scope="col">Last notified</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {q.data.rules.map((r) => {
                const name = r.product_name ?? r.product_id;
                const le = r.last_evaluated;
                return (
                  <tr key={r.id}>
                    <th scope="row">
                      <Link to={`/products/${encodeURIComponent(r.product_id)}`} className="link">
                        {name}
                      </Link>
                    </th>
                    <td>
                      {r.marketplace ?? (['below_target', 'new_low', 'restock'].includes(r.type) ? 'Any store' : '—')}
                      <span className="sub">{alertTypeLabel(r.type)}</span>
                    </td>
                    <td>{r.basis ? BASIS[r.basis] : '—'}</td>
                    <td className="num">
                      {r.type === 'below_target' ? (
                        <>
                          {formatMoney(r.target_price_minor, r.currency ?? 'INR')}
                          <span className="sub">{r.currency}</span>
                        </>
                      ) : r.type === 'meaningful_discount' ? `Score ≥ ${r.min_score}` : '—'}
                    </td>
                    <td>
                      <span className={`status ${r.enabled ? 'status--completed' : 'status--profiled'}`}>{r.enabled ? 'Active' : 'Paused'}</span>
                      {r.enabled && !r.armed && <span className="sub">Waiting to re-arm</span>}
                    </td>
                    <td>
                      {le ? (
                        <>
                          {OUTCOMES[le.outcome] ?? le.outcome}
                          {le.reason ? ` (${REASONS[le.reason] ?? le.reason})` : ''}
                          <span className="sub">{formatDateTime(le.at)}</span>
                        </>
                      ) : (
                        <span className="muted">Not yet evaluated</span>
                      )}
                    </td>
                    <td>{r.last_triggered_at ? formatDateTime(r.last_triggered_at) : <span className="muted">Never</span>}</td>
                    <td>
                      <div className="row-gap row-gap--tight">
                        <button type="button" className="btn btn--secondary btn--small" aria-label={`Edit alert for ${name}`} onClick={() => onEdit(productFor(r), r)}>
                          Edit
                        </button>
                        <button
                          type="button"
                          className="btn btn--secondary btn--small"
                          aria-label={`${r.enabled ? 'Pause' : 'Resume'} alert for ${name}`}
                          onClick={() => patch.mutate({ id: r.id, body: { enabled: !r.enabled } })}
                        >
                          {r.enabled ? 'Pause' : 'Resume'}
                        </button>
                        {r.enabled && !r.armed && (
                          <button type="button" className="btn btn--secondary btn--small" aria-label={`Re-arm alert for ${name}`} onClick={() => patch.mutate({ id: r.id, body: { rearm: true } })}>
                            Re-arm
                          </button>
                        )}
                        {confirming === r.id ? (
                          <button type="button" className="btn btn--secondary btn--small" aria-label={`Confirm delete alert for ${name}`} onClick={() => del.mutate(r.id)}>
                            Confirm delete
                          </button>
                        ) : (
                          <button type="button" className="btn btn--secondary btn--small" aria-label={`Delete alert for ${name}`} onClick={() => setConfirming(r.id)}>
                            Delete
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function evidenceLink(n: AppNotification): string {
  const base = `/products/${encodeURIComponent(n.product_id)}`;
  const day = String(n.evidence?.cutoff ?? '').slice(0, 10);
  if (n.type === 'audit_finding') return `${base}#audit`;
  if (n.type === 'synchronization_anomaly') return `${base}#sync`;
  if (n.type === 'meaningful_discount' || n.type === 'advice_change') return `${base}?tab=evidence${day ? `&at=${day}` : ''}`;
  return `${base}?tab=timeline${day ? `&at=${day}` : ''}`;
}

function NotificationItem({ n }: { n: AppNotification }) {
  const read = usePersonalMutation((id: string, m) => watchApi.read(id, m));
  const dismiss = usePersonalMutation((id: string, m) => watchApi.dismiss(id, m));
  const basis = n.basis === 'base' ? 'base price' : 'confirmed delivered price';
  return (
    <li className={`notification${n.read ? '' : ' notification--unread'}`}>
      <p className="notification__head">
        <strong>{n.title}</strong>
        {!n.read && <span className="tag tag--good">Unread</span>}
      </p>
      <p>
        <Link to={`/products/${encodeURIComponent(n.product_id)}`} className="link">
          {n.product_name ?? n.product_id}
        </Link>
      </p>
      {n.type && n.type !== 'below_target' ? (
        <>
          <p>{n.message}</p>
          <p className="small muted">
            {alertTypeLabel(n.type)} · analysis {String(n.evidence?.analysis_version ?? '')} · cutoff {formatDateTime(String(n.evidence?.cutoff ?? ''))} · import{' '}
            {n.ingestion_run_id?.slice(0, 8)} · notified {formatDateTime(n.created_at)}{' '}
            <Link to={evidenceLink(n)} className="link">View the evidence</Link>
          </p>
        </>
      ) : (
        <>
          <p>
            {n.marketplace} · {basis} {formatMoney(n.observed_minor, n.currency ?? 'INR')} is at or below your target {formatMoney(n.target_minor, n.currency ?? 'INR')}
          </p>
          <p className="small muted">
            Observed {formatObservedAt(n.source_timestamp, n.timestamp_quality, n.observed_at)} · listing {n.listing_id} · import {n.ingestion_run_id?.slice(0, 8)} ·
            notified {formatDateTime(n.created_at)}
          </p>
        </>
      )}
      <p className="small muted">{n.email?.status === 'not_sent' ? 'Email not sent (local outbox only)' : ''}</p>
      <div className="row-gap">
        {!n.read && (
          <button type="button" className="btn btn--secondary btn--small" onClick={() => read.mutate(n.id)}>
            Mark as read
          </button>
        )}
        <button type="button" className="btn btn--secondary btn--small" onClick={() => dismiss.mutate(n.id)}>
          Dismiss
        </button>
      </div>
    </li>
  );
}

function Notifications() {
  const [status, setStatus] = useState<'active' | 'unread' | 'all'>('active');
  const [page, setPage] = useState(1);
  const q = useNotifications(status, page);
  const readAll = usePersonalMutation((_: void, m) => watchApi.readAll(m));
  const pages = q.data ? Math.max(1, Math.ceil(q.data.total / q.data.page_size)) : 1;
  return (
    <section id="notifications" className="card section-card stack-md" aria-labelledby="notes-title">
      <div className="section-head">
        <h2 id="notes-title">Notifications</h2>
        <div className="row-gap">
          <div className="segmented" role="group" aria-label="Show notifications">
            {(['active', 'unread', 'all'] as const).map((s) => (
              <button key={s} type="button" className="segmented__item" aria-pressed={status === s} onClick={() => { setStatus(s); setPage(1); }}>
                {s === 'active' ? 'Current' : s === 'unread' ? 'Unread' : 'All, incl. dismissed'}
              </button>
            ))}
          </div>
          <button type="button" className="btn btn--secondary btn--small" onClick={() => readAll.mutate()} disabled={!q.data?.unread}>
            Mark all as read
          </button>
        </div>
      </div>
      {q.isPending && <p className="muted" role="status">Loading notifications…</p>}
      {q.isError && <p className="inline-error" role="alert">Couldn't load notifications: {q.error.message}</p>}
      {q.data && q.data.items.length === 0 && (
        <p className="muted">No notifications. You'll be told here when a newly imported observation meets one of your alerts.</p>
      )}
      {q.data && q.data.items.length > 0 && (
        <ul className="notifications" aria-live="polite">
          {q.data.items.map((n) => (
            <NotificationItem key={n.id} n={n} />
          ))}
        </ul>
      )}
      {pages > 1 && (
        <nav className="pager" aria-label="Notification pages">
          <button type="button" className="btn btn--secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
          <span className="muted">Page {page} of {pages}</span>
          <button type="button" className="btn btn--secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</button>
        </nav>
      )}
    </section>
  );
}
