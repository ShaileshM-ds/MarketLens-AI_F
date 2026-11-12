import { useEffect, useState, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { PageHeader } from './PageHeader';
import { ProductImage } from '../components/ProductImage';
import { apiGet } from '../lib/api';
import { MAX_COMPARE, useCompare } from '../lib/compareSelection';
import { MODE_LABELS, useDataMode } from '../lib/dataMode';
import { useCompareProducts, type CompareProduct, type Designation, type ProductList } from '../lib/products';
import { formatMoney } from '../lib/money';
import { formatRating } from '../lib/format';

function priceCell(d: Designation): ReactNode {
  if (d.amount_minor === null) return <span className="muted">Not available</span>;
  return (
    <>
      <strong>{formatMoney(d.amount_minor, d.currency ?? 'INR')}</strong>
      <span className="sub">{d.marketplaces.join(', ')}</span>
      {!d.certain_overall && <span className="sub note-warning">May not be cheapest overall (unknown shipping)</span>}
    </>
  );
}

const range = (r: { min: number; max: number } | null, f: (v: number) => string) =>
  r ? (r.min === r.max ? f(r.min) : `${f(r.min)}–${f(r.max)}`) : <span className="muted">Unknown</span>;

const ROWS: { label: string; cell: (p: CompareProduct) => ReactNode }[] = [
  { label: 'Category', cell: (p) => `${p.category_label}${p.source_category ? ` · ${p.source_category}` : ''}` },
  { label: 'Stores', cell: (p) => (p.marketplaces.length ? p.marketplaces.join(', ') : <span className="muted">None</span>) },
  { label: 'Listings', cell: (p) => String(p.offer_count) },
  { label: 'Listings marked available', cell: (p) => `${p.available_offer_count} of ${p.offer_count}` },
  {
    label: 'Availability (imported snapshot)',
    cell: (p) => {
      const a = p.availability_summary;
      const parts = [
        a.in_stock && `${a.in_stock} in stock`,
        a.limited_stock && `${a.limited_stock} limited`,
        a.out_of_stock && `${a.out_of_stock} out of stock`,
        a.unknown && `${a.unknown} not reported`,
      ].filter(Boolean);
      return (
        <>
          {parts.join(' · ')}
          {a.contradictions > 0 && <span className="sub note-warning">{a.contradictions} with a stock contradiction</span>}
        </>
      );
    },
  },
  { label: 'Lowest listed price', cell: (p) => priceCell(p.pricing.lowest_listed) },
  { label: 'Lowest confirmed delivered price', cell: (p) => priceCell(p.pricing.lowest_confirmed_delivered) },
  { label: 'Lowest confirmed delivered price (available offers)', cell: (p) => priceCell(p.pricing.lowest_confirmed_delivered_available) },
  { label: 'Reference price (seller-provided)', cell: (p) => range(p.reference_price_range, (v) => formatMoney(v, p.reference_price_range?.currency ?? 'INR')) },
  { label: 'Advertised discount', cell: (p) => range(p.advertised_discount_range, (v) => `${v.toFixed(2)}%`) },
  { label: 'Calculated reduction from reference', cell: (p) => range(p.calculated_reduction_range, (v) => `${v.toFixed(2)}%`) },
  {
    label: 'Discount differences',
    cell: (p) => (p.discount_differences ? <span className="note-warning">{p.discount_differences} listing(s) differ by more than 0.5 points</span> : 'None'),
  },
  { label: 'Product rating (per store)', cell: (p) => range(p.product_rating_range, (v) => `${formatRating(v)} / 5`) },
  { label: 'Seller rating', cell: (p) => range(p.seller_rating_range, (v) => `${formatRating(v)} / 5`) },
  {
    label: 'Review rating average',
    cell: (p) =>
      p.reviews_summary.average_review_rating !== null
        ? `${p.reviews_summary.average_review_rating.toFixed(2)} / 5 (${p.reviews_summary.rated_count} reviews)`
        : <span className="muted">No reviews</span>,
  },
  {
    label: 'Data quality',
    cell: (p) => (
      <span className="product-card__tags">
        {p.quality_labels.filter((q) => q.code !== 'synthetic_dataset').map((q) => (
          <span key={q.code} className="tag tag--warn" title={q.description}>
            {q.label}
          </span>
        ))}
      </span>
    ),
  },
  { label: 'Price history', cell: (p) => <span className="small muted">{p.price_history.reason}</span> },
];

export function ComparePage() {
  const [params, setParams] = useSearchParams();
  const ids = [...new Set(params.getAll('ids').filter(Boolean))].slice(0, MAX_COMPARE);
  const { mode } = useDataMode();
  const { setAll, error: selectionError } = useCompare();
  const q = useCompareProducts(ids);
  const [replacing, setReplacing] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const products = q.data?.products ?? [];
  // Keep the tray in step with what is on screen.
  useEffect(() => {
    if (!q.data) return;
    setAll(ids.map((id) => ({ id, name: q.data!.products.find((p) => p.product_id === id)?.name ?? id })));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q.data, ids.join('|')]);

  const writeIds = (next: string[]) => {
    const p = new URLSearchParams();
    next.forEach((id) => p.append('ids', id));
    setParams(p);
  };
  const remove = (id: string) => {
    setNotice(null);
    if (replacing === id) setReplacing(null);
    writeIds(ids.filter((x) => x !== id));
  };
  const pick = (id: string, name: string) => {
    setNotice(null);
    if (replacing) {
      if (ids.includes(id)) {
        setNotice(`${name} is already in the comparison.`);
        return;
      }
      writeIds(ids.map((x) => (x === replacing ? id : x)));
      setReplacing(null);
      return;
    }
    if (ids.includes(id)) return setNotice(`${name} is already in the comparison.`);
    if (ids.length >= MAX_COMPARE) return setNotice(`You're comparing ${MAX_COMPARE} products, the maximum. Remove or replace one to add another.`);
    writeIds([...ids, id]);
  };

  return (
    <div className="stack-lg">
      <PageHeader eyebrow="Side by side" title="Compare products" note={`Up to ${MAX_COMPARE} products from ${MODE_LABELS[mode].name} data, matched only by product ID.`} />

      <AddProduct ids={ids} replacing={replacing ? products.find((p) => p.product_id === replacing)?.name ?? replacing : null} onPick={pick} onCancelReplace={() => setReplacing(null)} />
      {(notice || selectionError) && (
        <p className="inline-error" role="alert">
          {notice ?? selectionError}
        </p>
      )}
      {ids.length >= MAX_COMPARE && !replacing && (
        <p className="muted small">You're comparing {MAX_COMPARE} products, the maximum. Remove or replace one to add another.</p>
      )}

      {ids.length === 0 ? (
        <section className="card empty-state">
          <h2>No products selected</h2>
          <p className="muted">
            Choose up to {MAX_COMPARE} products in the <Link to="/products" className="link">Product Explorer</Link>, or search above.
          </p>
        </section>
      ) : q.isError ? (
        <section className="card empty-state" role="alert">
          <h2>Couldn't load the comparison</h2>
          <p className="muted">{q.error.message}</p>
          <button type="button" className="btn btn--primary" onClick={() => q.refetch()}>
            Try again
          </button>
        </section>
      ) : q.isPending ? (
        <p className="muted" role="status">
          Loading comparison…
        </p>
      ) : (
        <>
          {q.data.missing.map((id) => (
            <p key={id} className="callout callout--warn" role="note">
              {id} isn't in {MODE_LABELS[mode].name} data.{' '}
              <button type="button" className="link-button" onClick={() => remove(id)}>
                Remove it
              </button>
            </p>
          ))}
          {q.data.comparability_warnings.map((w) => (
            <p key={w} className="callout callout--warn" role="note">
              {w}
            </p>
          ))}
          {products.length > 0 && (
            <div className="table-wrap compare-wrap" tabIndex={0} role="region" aria-label="Product comparison table">
              <table className="table compare-table">
                <thead>
                  <tr>
                    <td />
                    {products.map((p) => (
                      <th key={p.product_id} scope="col" className={`compare-col${replacing === p.product_id ? ' compare-col--replacing' : ''}`}>
                        <ProductImage kind={p.image.kind} productId={p.product_id} name={p.name} url={p.image.url} />
                        <Link to={`/products/${encodeURIComponent(p.product_id)}`} className="link compare-col__name">
                          {p.name}
                        </Link>
                        <span className="mono muted small">{p.product_id}</span>
                        <span className="row-gap compare-col__actions">
                          <button type="button" className="btn btn--secondary btn--small" aria-label={`Replace ${p.name}`} aria-pressed={replacing === p.product_id} onClick={() => setReplacing(replacing === p.product_id ? null : p.product_id)}>
                            {replacing === p.product_id ? 'Choosing…' : 'Replace'}
                          </button>
                          <button type="button" className="btn btn--secondary btn--small" aria-label={`Remove ${p.name} from comparison`} onClick={() => remove(p.product_id)}>
                            Remove
                          </button>
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {ROWS.map((r) => (
                    <tr key={r.label}>
                      <th scope="row">{r.label}</th>
                      {products.map((p) => (
                        <td key={p.product_id}>{r.cell(p)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="row-gap">
            <button type="button" className="btn btn--secondary" onClick={() => writeIds([])}>
              Clear comparison
            </button>
            <Link to="/products" className="btn btn--secondary">
              Back to Product Explorer
            </Link>
          </p>
        </>
      )}
    </div>
  );
}

function AddProduct({ ids, replacing, onPick, onCancelReplace }: { ids: string[]; replacing: string | null; onPick: (id: string, name: string) => void; onCancelReplace: () => void }) {
  const { mode, unavailableReason } = useDataMode();
  const [text, setText] = useState('');
  const [q, setQ] = useState('');
  useEffect(() => {
    const t = window.setTimeout(() => setQ(text.trim()), 300);
    return () => window.clearTimeout(t);
  }, [text]);
  const results = useQuery({
    queryKey: ['compare-search', mode, q],
    queryFn: () => apiGet<ProductList>('/api/v1/products', { mode, q, page_size: '5' }),
    enabled: q.length > 0 && unavailableReason(mode) === null,
  });
  return (
    <section className="card section-card stack-sm" aria-labelledby="add-title">
      <h2 id="add-title" className="h3">
        {replacing ? `Replace ${replacing}` : 'Add a product'}
      </h2>
      <div className="explorer-search">
        <label htmlFor="compare-search" className="visually-hidden">
          Find a product to add
        </label>
        <input id="compare-search" type="search" className="input" placeholder="Search by product name or ID" value={text} maxLength={100} onChange={(e) => setText(e.target.value)} />
        {replacing && (
          <button type="button" className="btn btn--secondary" onClick={onCancelReplace}>
            Cancel replace
          </button>
        )}
      </div>
      {results.isFetching && <p className="muted small">Searching…</p>}
      {results.data && results.data.items.length === 0 && <p className="muted small">No products match.</p>}
      {results.data && results.data.items.length > 0 && (
        <ul className="pick-list">
          {results.data.items.map((p) => (
            <li key={p.product_id}>
              <span>
                {p.name} <span className="mono muted small">{p.product_id}</span>
              </span>
              <button
                type="button"
                className="btn btn--secondary btn--small"
                aria-label={replacing ? `Replace ${replacing} with ${p.name}` : `Add ${p.name} to comparison`}
                disabled={!replacing && ids.includes(p.product_id)}
                onClick={() => onPick(p.product_id, p.name)}
              >
                {ids.includes(p.product_id) ? 'Already added' : replacing ? 'Use instead' : 'Add'}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
