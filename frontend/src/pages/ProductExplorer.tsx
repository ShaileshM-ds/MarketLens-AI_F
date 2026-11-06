import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { PageHeader } from './PageHeader';
import { ProductImage, thumbnailSrc } from '../components/ProductImage';
import { CompareTray } from '../components/CompareTray';
import { WatchToggle } from '../components/WatchToggle';
import { useCompare } from '../lib/compareSelection';
import { MODE_LABELS, useDataMode } from '../lib/dataMode';
import {
  AVAILABILITY_LABELS,
  PAGE_SIZE,
  SORTS,
  activeChips,
  clearAll,
  hasFilters,
  readState,
  toApiParams,
  withParam,
  type ExplorerState,
} from '../lib/explorerParams';
import { useProductFilters, useProductList, type FilterMeta, type ProductItem } from '../lib/products';
import { formatMoney } from '../lib/money';
import { formatCount, formatRating } from '../lib/format';

const SEARCH_DEBOUNCE_MS = 400;

export function ProductExplorer() {
  const [params, setParams] = useSearchParams();
  const { mode } = useDataMode();
  const state = readState(params);
  const meta = useProductFilters();
  const currency = meta.data?.currencies[0]?.code ?? 'INR';
  const { params: apiParams, error: inputError } = toApiParams(state, mode, currency);
  const list = useProductList(inputError ? null : apiParams);
  const [drawerOpen, setDrawerOpen] = useState(false);

  // A page number from one workspace means nothing in another.
  const prevMode = useRef(mode);
  useEffect(() => {
    if (prevMode.current === mode) return;
    prevMode.current = mode;
    setParams((p) => withParam(p, 'page', null), { replace: true });
  }, [mode, setParams]);

  const set = (key: string, value: string | string[] | boolean | null) => setParams((p) => withParam(p, key, value));
  const total = list.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const filtered = hasFilters(state);
  const categoryLabel = (slug: string) => meta.data?.categories.find((c) => c.slug === slug)?.label ?? '';
  const chips = activeChips(state, { categoryLabel, currency });

  return (
    <div className="stack-lg">
      <PageHeader
        eyebrow="Follow the evidence"
        title="Product Explorer"
        note="Explore and compare marketplace listings across supported stores."
      />
      <Provenance meta={meta.data} mode={mode} />

      <SearchBar value={state.q} onCommit={(q, replace) => setParams((p) => withParam(p, 'q', q.trim()), { replace })} />

      <div className="explorer">
        <FilterPanel
          id="explorer-filters"
          meta={meta.data}
          state={state}
          set={set}
          setRange={(min, max) => setParams((p) => withParam(withParam(p, 'min', min), 'max', max))}
          setDiscount={(min, max) => setParams((p) => withParam(withParam(p, 'dmin', min), 'dmax', max))}
          clear={() => setParams((p) => clearAll(p))}
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
        />

        <section className="explorer__results" aria-labelledby="results-heading">
          <h2 id="results-heading" className="visually-hidden">
            Results
          </h2>
          <div className="results-bar">
            <button
              type="button"
              className="btn btn--secondary filters-toggle"
              aria-expanded={drawerOpen}
              aria-controls="explorer-filters"
              onClick={() => setDrawerOpen(true)}
            >
              Filters{chips.length ? ` (${chips.length})` : ''}
            </button>
            <p className="results-count" role="status" aria-live="polite">
              {list.data && !inputError ? `${formatCount(total)} ${total === 1 ? 'product' : 'products'}` : ''}
            </p>
            <label className="inline-field">
              <span>Sort by</span>
              <select className="select" value={state.sort} onChange={(e) => set('sort', e.target.value)}>
                {SORTS.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </label>
            <div className="segmented" role="group" aria-label="Layout">
              {(['grid', 'table'] as const).map((v) => (
                <button key={v} type="button" className="segmented__item" aria-pressed={state.view === v} onClick={() => setParams((p) => { const n = new URLSearchParams(p); if (v === 'grid') n.delete('view'); else n.set('view', v); return n; })}>
                  {v === 'grid' ? 'Grid' : 'Table'}
                </button>
              ))}
            </div>
          </div>

          {chips.length > 0 && (
            <div className="chips">
              <ul className="chips__list" aria-label="Active filters">
                {chips.map((c) => (
                  <li key={c.id}>
                    <button
                      type="button"
                      className="chip"
                      aria-label={`Remove filter: ${c.label}`}
                      onClick={() =>
                        setParams((p) =>
                          c.key === 'price'
                            ? withParam(withParam(p, 'min', null), 'max', null)
                            : c.key === 'discount'
                              ? withParam(withParam(p, 'dmin', null), 'dmax', null)
                              : withParam(p, c.key, c.next),
                        )
                      }
                    >
                      {c.label} <span aria-hidden="true">×</span>
                    </button>
                  </li>
                ))}
              </ul>
              <button type="button" className="link-button" onClick={() => setParams((p) => clearAll(p))}>
                Clear all
              </button>
            </div>
          )}

          {inputError && (
            <p className="inline-error" role="alert">
              {inputError}
            </p>
          )}
          {!inputError && (
            <Results
              state={state}
              list={list}
              meta={meta.data}
              mode={mode}
              filtered={filtered}
              pages={pages}
              setPage={(n) => set('page', n === 1 ? null : String(n))}
              clear={() => setParams((p) => clearAll(p))}
            />
          )}
        </section>
      </div>
      <CompareTray />
    </div>
  );
}

function Provenance({ meta, mode }: { meta?: FilterMeta; mode: string }) {
  if (!meta || meta.total_products === 0) return null;
  return (
    <div className="provenance" role="note">
      <span className="mode-badge mode-badge--imported">Showing {MODE_LABELS[mode as keyof typeof MODE_LABELS].name} data</span>
      {meta.data_basis.all_synthetic && <span className="tag tag--synthetic">Synthetic demonstration data</span>}
      {meta.data_basis.snapshot_only && (
        <p className="muted">
          Prices come from a single snapshot per listing without a confirmed timezone. They are not live prices and not a price history.
        </p>
      )}
      {!meta.catalog_status.up_to_date && (
        <p className="inline-error">
          The explorer index covers {formatCount(meta.catalog_status.summarized)} of {formatCount(meta.catalog_status.products)} products. An administrator can rebuild it.
        </p>
      )}
    </div>
  );
}

function SearchBar({ value, onCommit }: { value: string; onCommit: (q: string, replace: boolean) => void }) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  // Debounced while typing; replaces history so Back isn't flooded with keystrokes.
  useEffect(() => {
    if (draft.trim() === value.trim()) return;
    const t = window.setTimeout(() => onCommit(draft, true), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft, value]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    onCommit(draft, false);
  };
  return (
    <form role="search" className="explorer-search" onSubmit={submit}>
      <label htmlFor="explorer-search" className="visually-hidden">
        Search products by name or product ID
      </label>
      <input
        id="explorer-search"
        type="search"
        className="input"
        aria-label="Search products by name or product ID"
        placeholder="Search by product name or ID, for example MCL0001"
        value={draft}
        maxLength={100}
        onChange={(e) => setDraft(e.target.value)}
      />
      {draft && (
        <button
          type="button"
          className="btn btn--secondary"
          aria-label="Clear search"
          onClick={() => {
            setDraft('');
            onCommit('', false);
          }}
        >
          Clear
        </button>
      )}
      <button type="submit" className="btn btn--primary">
        Search
      </button>
    </form>
  );
}

interface PanelProps {
  id: string;
  meta?: FilterMeta;
  state: ExplorerState;
  set: (key: string, value: string | string[] | boolean | null) => void;
  setRange: (min: string, max: string) => void;
  setDiscount: (min: string, max: string) => void;
  clear: () => void;
  open: boolean;
  onClose: () => void;
}

function FilterPanel({ id, meta, state, set, setRange, setDiscount, clear, open, onClose }: PanelProps) {
  const ref = useRef<HTMLElement>(null);
  const [min, setMin] = useState(state.min);
  const [max, setMax] = useState(state.max);
  const [dmin, setDmin] = useState(state.discountMin);
  const [dmax, setDmax] = useState(state.discountMax);
  useEffect(() => setMin(state.min), [state.min]);
  useEffect(() => setMax(state.max), [state.max]);
  useEffect(() => setDmin(state.discountMin), [state.discountMin]);
  useEffect(() => setDmax(state.discountMax), [state.discountMax]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    ref.current?.querySelector<HTMLElement>('button, select, input')?.focus();
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  const toggle = (list: string[], v: string) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  const noAttributes = meta && meta.brands.length === 0 && meta.sizes.length === 0 && meta.colours.length === 0;

  return (
    <>
      {open && <div className="scrim filters-scrim" onClick={onClose} aria-hidden="true" />}
      <aside
        id={id}
        ref={ref}
        className={`filters-panel card${open ? ' filters-panel--open' : ''}`}
        role={open ? 'dialog' : undefined}
        aria-modal={open ? true : undefined}
        aria-label="Filters"
      >
        <div className="filters-panel__head">
          <h2 className="h3">Filters</h2>
          <button type="button" className="link-button" onClick={clear}>
            Clear all
          </button>
          <button type="button" className="btn btn--secondary filters-panel__close" onClick={onClose}>
            Show results
          </button>
        </div>

        <label className="field">
          <span className="field__label">Category</span>
          <select className="select" value={state.category} onChange={(e) => set('category', e.target.value || null)}>
            <option value="">All categories</option>
            {meta?.categories.map((c) => (
              <option key={c.slug} value={c.slug}>
                {c.label} ({formatCount(c.count)})
              </option>
            ))}
          </select>
        </label>

        {meta && meta.marketplaces.length > 0 && (
          <fieldset className="fieldset">
            <legend>Store</legend>
            {meta.marketplaces.map((m) => (
              <label key={m.name} className="checkbox">
                <input type="checkbox" checked={state.marketplaces.includes(m.name)} onChange={() => set('marketplace', toggle(state.marketplaces, m.name))} />
                <span>{m.name}</span>
                <span className="muted count" aria-hidden="true">
                  {formatCount(m.count)}
                </span>
              </label>
            ))}
          </fieldset>
        )}

        <form
          className="fieldset"
          onSubmit={(e) => {
            e.preventDefault();
            setRange(min.trim(), max.trim());
          }}
        >
          <fieldset className="plain-fieldset">
            <legend>Base price (₹)</legend>
            <p className="muted small">Listing price before shipping, coupons and payment offers.</p>
            <div className="range">
              <label className="field">
                <span className="field__label">Minimum price (₹)</span>
                <input className="input" inputMode="decimal" value={min} onChange={(e) => setMin(e.target.value)} placeholder={meta?.currencies[0] ? formatMoney(meta.currencies[0].min_price_minor) : ''} />
              </label>
              <label className="field">
                <span className="field__label">Maximum price (₹)</span>
                <input className="input" inputMode="decimal" value={max} onChange={(e) => setMax(e.target.value)} placeholder={meta?.currencies[0] ? formatMoney(meta.currencies[0].max_price_minor) : ''} />
              </label>
            </div>
            <button type="submit" className="btn btn--secondary">
              Apply price
            </button>
          </fieldset>
        </form>

        {meta && meta.availability.length > 0 && (
          <fieldset className="fieldset">
            <legend>Availability</legend>
            <p className="muted small">As stated by the store. Some listings' stock figures disagree with it.</p>
            {meta.availability.map((a) => (
              <label key={a.value} className="checkbox">
                <input type="checkbox" checked={state.availability.includes(a.value)} onChange={() => set('availability', toggle(state.availability, a.value))} />
                <span>{AVAILABILITY_LABELS[a.value] ?? a.label}</span>
              </label>
            ))}
          </fieldset>
        )}

        <label className="field">
          <span className="field__label">Product rating at least (any one store)</span>
          <select className="select" value={state.productRatingMin} onChange={(e) => set('prating', e.target.value || null)}>
            <option value="">Any</option>
            {['3', '3.5', '4', '4.5'].map((r) => (
              <option key={r} value={r}>
                {r}+
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span className="field__label">Seller rating at least</span>
          <select className="select" value={state.sellerRatingMin} onChange={(e) => set('srating', e.target.value || null)}>
            <option value="">Any</option>
            {['3', '3.5', '4', '4.5'].map((r) => (
              <option key={r} value={r}>
                {r}+
              </option>
            ))}
          </select>
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={state.freeShipping} onChange={(e) => set('free', e.target.checked)} />
          <span>Known free shipping</span>
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={state.deliveredKnown} onChange={(e) => set('delivered', e.target.checked)} />
          <span>Confirmed delivered price only</span>
        </label>

        <form
          className="fieldset"
          onSubmit={(e) => {
            e.preventDefault();
            setDiscount(dmin.trim(), dmax.trim());
          }}
        >
          <fieldset className="plain-fieldset">
            <legend>Advertised discount (%)</legend>
            <p className="muted small">The store's advertised percentage, not a verified saving.</p>
            <div className="range">
              <label className="field">
                <span className="field__label">Minimum discount (%)</span>
                <input className="input" inputMode="decimal" value={dmin} onChange={(e) => setDmin(e.target.value)} />
              </label>
              <label className="field">
                <span className="field__label">Maximum discount (%)</span>
                <input className="input" inputMode="decimal" value={dmax} onChange={(e) => setDmax(e.target.value)} />
              </label>
            </div>
            <button type="submit" className="btn btn--secondary">
              Apply discount
            </button>
          </fieldset>
        </form>
        <p className="muted small">Store filters apply together to the same listing.</p>
        {noAttributes && <p className="muted small">Brand, size and colour aren't in this dataset, so they can't be filtered.</p>}
      </aside>
    </>
  );
}

interface ResultsProps {
  state: ExplorerState;
  list: ReturnType<typeof useProductList>;
  meta?: FilterMeta;
  mode: string;
  filtered: boolean;
  pages: number;
  setPage: (n: number) => void;
  clear: () => void;
}

function Results({ state, list, meta, mode, filtered, pages, setPage, clear }: ResultsProps) {
  const modeName = MODE_LABELS[mode as keyof typeof MODE_LABELS].name;
  if (list.isError) {
    return (
      <div className="card empty-state" role="alert">
        <h3>Couldn't load products</h3>
        <p className="muted">{list.error.message}</p>
        <button type="button" className="btn btn--primary" onClick={() => list.refetch()}>
          Try again
        </button>
      </div>
    );
  }
  if (list.isPending) {
    return (
      <div aria-busy="true">
        <p className="visually-hidden" role="status">
          Loading products…
        </p>
        <ul className="product-grid" aria-hidden="true">
          {Array.from({ length: 6 }, (_, i) => (
            <li key={i} className="card skeleton-card" />
          ))}
        </ul>
      </div>
    );
  }
  const data = list.data!;
  if (data.total === 0) {
    if (!filtered || meta?.total_products === 0) {
      return (
        <div className="card empty-state">
          <h3>No products in {modeName} data</h3>
          <p className="muted">
            {mode === 'demo'
              ? "Demo data hasn't been generated yet. Products appear here once it is."
              : `There are no products in ${modeName} data yet.`}
          </p>
        </div>
      );
    }
    return (
      <div className="card empty-state">
        <h3>No products match</h3>
        <p className="muted">Try removing a filter or searching for something else.</p>
        <button type="button" className="btn btn--secondary" onClick={clear}>
          Clear all filters
        </button>
      </div>
    );
  }
  if (data.items.length === 0) {
    return (
      <div className="card empty-state">
        <h3>This page is past the end of the results</h3>
        <button type="button" className="btn btn--secondary" onClick={() => setPage(1)}>
          Go to page 1
        </button>
      </div>
    );
  }
  return (
    <div className={list.isPlaceholderData ? 'is-refreshing' : undefined} aria-busy={list.isFetching || undefined}>
      {state.view === 'grid' ? (
        <ul className="product-grid">
          {data.items.map((p) => (
            <li key={p.product_id}>
              <ProductCard p={p} />
            </li>
          ))}
        </ul>
      ) : (
        <ProductTable items={data.items} />
      )}
      <nav className="pager" aria-label="Pages">
        <button type="button" className="btn btn--secondary" aria-label="Previous page" disabled={state.page <= 1} onClick={() => setPage(state.page - 1)}>
          Previous
        </button>
        <span className="muted">
          Page {state.page} of {pages}
        </span>
        <button type="button" className="btn btn--secondary" aria-label="Next page" disabled={state.page >= pages} onClick={() => setPage(state.page + 1)}>
          Next
        </button>
      </nav>
    </div>
  );
}

function stores(p: ProductItem): string {
  if (p.matching_offer_count === p.offer_count) return `${p.offer_count} ${p.offer_count === 1 ? 'store' : 'stores'}`;
  return `${p.matching_offer_count} of ${p.offer_count} stores match`;
}

function ratingText(p: ProductItem): string | null {
  const r = p.product_rating;
  if (!r) return null;
  const range = r.min === r.max ? formatRating(r.min) : `${formatRating(r.min)}–${formatRating(r.max)}`;
  return `Product rating ${range} (per store)`;
}

function availabilityText(p: ProductItem): string {
  const parts = (Object.keys(AVAILABILITY_LABELS) as (keyof ProductItem['availability'])[])
    .filter((k) => p.availability[k] > 0)
    .map((k) => `${p.availability[k]} ${AVAILABILITY_LABELS[k].toLowerCase()}`);
  return parts.join(' · ');
}

function PriceBlock({ p }: { p: ProductItem }) {
  const lp = p.lowest_price;
  if (!lp) {
    return (
      <div className="price">
        <p className="price__value price__value--none">Price unavailable</p>
        {p.lowest_price_unavailable_reason && <p className="price__note">{p.lowest_price_unavailable_reason}</p>}
      </div>
    );
  }
  return (
    <div className="price">
      <p className="price__value">From {formatMoney(lp.amount_minor, lp.currency)}</p>
      <p className="price__note">Base listing price, excludes shipping</p>
      {lp.offers_with_unknown_shipping > 0 && (
        <p className="price__note price__note--warn">
          Shipping unknown for {lp.offers_with_unknown_shipping} {lp.offers_with_unknown_shipping === 1 ? 'listing' : 'listings'}
        </p>
      )}
      {lp.out_of_stock && <p className="price__note price__note--warn">Out of stock at this price</p>}
      <DeliveredLine p={p} />
    </div>
  );
}

function DeliveredLine({ p }: { p: ProductItem }) {
  const d = p.lowest_delivered;
  if (!d) return <p className="price__note">Delivered price can't be confirmed (shipping unknown)</p>;
  return (
    <p className="price__delivered">
      Lowest confirmed delivered {formatMoney(d.amount_minor, d.currency)}
      {!d.certain_overall && <span className="price__note price__note--warn"> · may not be the cheapest overall (some shipping unknown)</span>}
    </p>
  );
}

function CompareToggle({ p }: { p: ProductItem }) {
  const { has, add, remove } = useCompare();
  const selected = has(p.product_id);
  return (
    <label className="compare-toggle">
      <input
        type="checkbox"
        checked={selected}
        aria-label={`Add ${p.name} to comparison`}
        onChange={() => (selected ? remove(p.product_id) : add({ id: p.product_id, name: p.name }))}
      />
      <span aria-hidden="true">{selected ? 'In comparison' : 'Compare'}</span>
    </label>
  );
}

function ProductCard({ p }: { p: ProductItem }) {
  const rating = ratingText(p);
  return (
    <article className="card product-card">
      <ProductImage kind={p.image.kind} productId={p.product_id} name={p.name} url={p.image.url} />
      <div className="product-card__body">
        <p className="product-card__meta">
          {p.category_label}
          {p.source_category ? ` · ${p.source_category}` : ''}
        </p>
        <h3 className="product-card__title">{p.name}</h3>
        <p className="mono muted">{p.product_id}</p>
        <PriceBlock p={p} />
        <ul className="product-card__facts">
          <li>{stores(p)}</li>
          {rating && <li>{rating}</li>}
          <li>{availabilityText(p)}</li>
        </ul>
        <div className="product-card__tags">
          {p.synthetic && <span className="tag tag--synthetic">Synthetic</span>}
          {p.has_data_warnings && <span className="tag tag--warn">Data warnings</span>}
        </div>
        <div className="card-actions">
          <CompareToggle p={p} />
          <WatchToggle productId={p.product_id} name={p.name} compact />
        </div>
        <Link to={`/products/${encodeURIComponent(p.product_id)}`} className="stretched-link" aria-label={`View details for ${p.name}`}>
          View details
        </Link>
      </div>
    </article>
  );
}

function ProductTable({ items }: { items: ProductItem[] }) {
  const { mode } = useDataMode();
  return (
    <div className="table-wrap" tabIndex={0} role="region" aria-label="Products table">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Product</th>
            <th scope="col">ID</th>
            <th scope="col" className="num">From (base price)</th>
            <th scope="col">Stores</th>
            <th scope="col">Product rating (per store)</th>
            <th scope="col">Availability</th>
          </tr>
        </thead>
        <tbody>
          {items.map((p) => (
            <tr key={p.product_id}>
              <th scope="row">
                <Link to={`/products/${encodeURIComponent(p.product_id)}`} className="link table-product" aria-label={`View details for ${p.name}`}>
                  {thumbnailSrc(mode, p.product_id, p.image.url) && <img className="table-thumb" src={thumbnailSrc(mode, p.product_id, p.image.url)!} alt="" width={40} height={40} loading="lazy" referrerPolicy="no-referrer" onError={(e) => { e.currentTarget.style.display = 'none'; }} />}
                  <span>{p.name}</span>
                </Link>
              </th>
              <td className="mono">{p.product_id}</td>
              <td className="num">{p.lowest_price ? formatMoney(p.lowest_price.amount_minor, p.lowest_price.currency) : <span className="muted">Unavailable</span>}</td>
              <td>{stores(p)}</td>
              <td>{p.product_rating ? (p.product_rating.min === p.product_rating.max ? formatRating(p.product_rating.min) : `${formatRating(p.product_rating.min)}–${formatRating(p.product_rating.max)}`) : ''}</td>
              <td>{availabilityText(p)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
