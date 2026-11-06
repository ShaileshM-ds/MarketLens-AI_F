import { useState, type ReactNode } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { WatchToggle } from '../components/WatchToggle';
import { AlertDialog } from '../components/AlertDialog';
import { useMe } from '../lib/auth';
import { ProductImage } from '../components/ProductImage';
import { CompareTray } from '../components/CompareTray';
import { AnalysisTabs, HistorySection } from '../components/ProductAnalysis';
import { BuyingAdviceCard } from '../components/BuyingAdvice';
import { AuditSection, SyncSection } from '../components/PatternsSections';
import { HBarChart } from '../components/HBarChart';
import { ApiError } from '../lib/api';
import { useCompare } from '../lib/compareSelection';
import { useProductDetail, useProductReviews, type Designation, type Offer, type ProductDetail } from '../lib/products';
import { formatMoney } from '../lib/money';
import { formatCount, formatObservedAt, formatRating } from '../lib/format';

const SECTIONS = [
  ['overview', 'Overview'],
  ['advice', 'Buying advice'],
  ['offers', 'Store offers'],
  ['delivered', 'Delivered prices'],
  ['discounts', 'Discounts'],
  ['ratings', 'Ratings and reviews'],
  ['shipping', 'Shipping and delivery'],
  ['availability', 'Stock and availability'],
  ['provenance', 'Data provenance'],
  ['history', 'Price history'],
  ['analysis', 'Timeline, Evidence, Forecast'],
  ['audit', 'Pricing audit'],
  ['sync', 'Seller synchronization'],
] as const;

const AVAIL_LABEL: Record<string, string> = { in_stock: 'In stock', limited_stock: 'Limited stock', out_of_stock: 'Out of stock', unknown: 'Not reported' };

export function ProductPage() {
  const { productId = '' } = useParams();
  const q = useProductDetail(productId);

  if (q.isPending) {
    return (
      <p className="muted" role="status">
        Loading product…
      </p>
    );
  }
  if (q.isError) {
    const notFound = q.error instanceof ApiError && q.error.status === 404;
    return (
      <section className="card empty-state" role="alert">
        <h1 className="h2">{notFound ? 'Product not found' : "Couldn't load this product"}</h1>
        <p className="muted">{q.error.message}</p>
        <p className="row-gap">
          {!notFound && (
            <button type="button" className="btn btn--primary" onClick={() => q.refetch()}>
              Try again
            </button>
          )}
          <Link to="/products" className="btn btn--secondary">
            Back to Product Explorer
          </Link>
        </p>
      </section>
    );
  }
  const d = q.data;
  return (
    <div className="stack-lg product-page">
      <nav aria-label="Breadcrumb" className="breadcrumb">
        <ol>
          <li>
            <Link to="/">Home</Link>
          </li>
          <li>
            <Link to="/products">Product Explorer</Link>
          </li>
          <li aria-current="page">{d.product.name}</li>
        </ol>
      </nav>
      <nav aria-label="Product sections" className="section-nav">
        <ul>
          {SECTIONS.map(([id, label]) => (
            <li key={id}>
              <a href={`#${id}`}>{label}</a>
            </li>
          ))}
        </ul>
      </nav>
      <Overview d={d} />
      <BuyingAdviceCard d={d} />
      <Section id="offers" title="Store offers" note="Each card is one store listing from the imported snapshot. Open “More details” for everything stored about it.">
        <ul className="offer-grid">
          {d.offers.map((o) => (
            <li key={o.listing_id}>
              <OfferCard o={o} d={d} />
            </li>
          ))}
        </ul>
      </Section>
      <DeliveredSection d={d} />
      <DiscountSection d={d} />
      <RatingsSection d={d} productId={productId} />
      <ShippingSection d={d} />
      <AvailabilitySection d={d} />
      <ProvenanceSection d={d} />
      <HistorySection d={d} />
      <AnalysisTabs d={d} />
      <AuditSection d={d} />
      <SyncSection d={d} />
      <CompareTray />
    </div>
  );
}

function Section({ id, title, note, children }: { id: string; title: string; note?: ReactNode; children: ReactNode }) {
  return (
    <section id={id} className="card section-card stack-md" aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`}>{title}</h2>
      {note && <p className="muted small">{note}</p>}
      {children}
    </section>
  );
}

function AddToCompare({ d }: { d: ProductDetail }) {
  const { has, add, remove } = useCompare();
  const id = d.product.product_id;
  const selected = has(id);
  return (
    <button
      type="button"
      className={`btn ${selected ? 'btn--secondary' : 'btn--primary'}`}
      aria-pressed={selected}
      onClick={() => (selected ? remove(id) : add({ id, name: d.product.name }))}
    >
      {selected ? 'In comparison (remove)' : 'Add to comparison'}
    </button>
  );
}

function SetAlert({ d }: { d: ProductDetail }) {
  const me = useMe();
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [saved, setSaved] = useState(false);
  const currency = d.pricing.currency;
  if (!currency) return null; // mixed or unknown currency: an alert can't be compared safely
  return (
    <>
      <button
        type="button"
        className="btn btn--secondary"
        onClick={() => (me.data ? setOpen(true) : navigate(`/signin?next=${encodeURIComponent(location.pathname + location.search)}`))}
      >
        Set price alert
      </button>
      {saved && (
        <span className="small" role="status">
          Alert saved. Manage it in <Link to="/watchlist" className="link">Watchlist &amp; alerts</Link>.
        </span>
      )}
      {open && (
        <AlertDialog
          product={{ id: d.product.product_id, name: d.product.name, marketplaces: d.product.marketplaces, currency }}
          onClose={() => setOpen(false)}
          onSaved={() => setSaved(true)}
        />
      )}
    </>
  );
}

function Overview({ d }: { d: ProductDetail }) {
  const p = d.product;
  const attrs = [
    ['Brand', p.brand],
    ['Size', p.size],
    ['Colour', p.colour],
  ].filter(([, v]) => v) as [string, string][];
  return (
    <section id="overview" className="card product-hero" aria-labelledby="overview-title">
      <ProductImage kind={p.image.kind} productId={p.product_id} name={p.name} url={p.image.url} caption />
      <div className="stack-md">
        <div>
          <p className="product-card__meta">
            {p.category_label}
            {p.source_category ? ` · ${p.source_category}` : ''}
          </p>
          <h1 id="overview-title" className="product-hero__title">
            {p.name}
          </h1>
          <p className="mono muted">Product ID {p.product_id}</p>
        </div>
        <div className="product-card__tags">
          {d.provenance.synthetic && <span className="tag tag--synthetic">Synthetic demonstration data</span>}
          {d.price_history.timezone_unknown_observation_count > 0 && d.price_history.verified_observation_count === 0 && (
            <span className="tag">Snapshot, timezone not stated</span>
          )}
          <span className="tag">
            {p.offer_count} {p.offer_count === 1 ? 'store listing' : 'store listings'}
          </span>
        </div>
        {attrs.length > 0 ? (
          <dl className="facts">
            {attrs.map(([k, v]) => (
              <div key={k} className="facts__item">
                <dt>{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="muted small">Brand, size and colour aren't provided in this dataset, so none are shown.</p>
        )}
        <p className="muted small">
          Source: {d.provenance.source_labels.join(', ')}. Imported snapshot, not live or verified marketplace prices.
        </p>
        <div className="row-gap">
          <AddToCompare d={d} />
          <WatchToggle productId={p.product_id} name={p.name} />
          <SetAlert d={d} />
        </div>
      </div>
    </section>
  );
}

function money(v: number | null | undefined, cur: string | null | undefined) {
  return v === null || v === undefined ? '' : formatMoney(v, cur ?? 'INR');
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="offer__field">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

const UNKNOWN = <span className="muted">Unknown</span>;

function OfferCard({ o, d }: { o: Offer; d: ProductDetail }) {
  const cur = o.currency ?? 'INR';
  const p = d.pricing;
  const isListed = p.lowest_listed.listing_ids.includes(o.listing_id);
  const isDelivered = p.lowest_confirmed_delivered.listing_ids.includes(o.listing_id);
  const isAvailable = p.lowest_confirmed_delivered_available.listing_ids.includes(o.listing_id);
  const shipping = !o.shipping_known ? UNKNOWN : o.shipping_minor === 0 ? 'Free' : formatMoney(o.shipping_minor, cur);
  const outOfStock = o.availability_class === 'out_of_stock';
  return (
    <article className={`card offer${o.purchasable ? '' : ' offer--muted'}`} aria-labelledby={`offer-${o.listing_id}`}>
      <header className="offer__head">
        <h3 id={`offer-${o.listing_id}`}>{o.marketplace}</h3>
        <div className="product-card__tags">
          {isListed && <span className="tag tag--good">Lowest listed price</span>}
          {isDelivered && <span className="tag tag--good">Lowest confirmed delivered price</span>}
          {isAvailable && <span className="tag tag--good">Lowest confirmed delivered (available)</span>}
          {outOfStock && <span className="tag tag--bad">Out of stock</span>}
        </div>
      </header>
      <dl className="offer__fields">
        <Field label="Base price">{o.price_minor !== null ? <strong>{formatMoney(o.price_minor, cur)}</strong> : <span className="muted">Not available</span>}</Field>
        <Field label="Shipping">{shipping}</Field>
        <Field label="Delivered total">
          {o.delivered_price_minor !== null ? (
            <strong className="offer__total">{formatMoney(o.delivered_price_minor, cur)}</strong>
          ) : (
            <>
              <span className="muted">Total incomplete</span>
              <span className="sub">Delivered total can't be confirmed because shipping is unknown.</span>
            </>
          )}
        </Field>
        <Field label="Availability (imported snapshot)">{o.availability ?? <span className="muted">Not reported</span>}</Field>
      </dl>
      {o.warnings.some((w) => w.code !== 'timezone_unknown') && (
        <ul className="offer__warnings" aria-label={`Data notes for ${o.marketplace}`}>
          {o.warnings
            .filter((w) => w.code !== 'timezone_unknown')
            .map((w) => (
              <li key={w.code} className="note-warning">
                {w.message}
              </li>
            ))}
        </ul>
      )}
      <details className="offer__more">
        <summary>More details</summary>
        <dl className="offer__fields">
          <Field label="Reference price (seller-provided)">{o.reference_price_minor !== null ? formatMoney(o.reference_price_minor, cur) : UNKNOWN}</Field>
          <Field label="Advertised discount">{o.advertised_discount_percent !== null ? `${o.advertised_discount_percent}% (advertised)` : UNKNOWN}</Field>
          <Field label="Stock quantity">{o.stock_quantity !== null ? String(o.stock_quantity) : UNKNOWN}</Field>
          <Field label="Seller rating">{o.seller_rating !== null ? `${formatRating(o.seller_rating)} / 5` : UNKNOWN}</Field>
          <Field label="Product rating (this store)">{o.product_rating !== null ? `${formatRating(o.product_rating)} / 5` : UNKNOWN}</Field>
          <Field label="Delivery estimate">{o.delivery_information ?? UNKNOWN}</Field>
          <Field label="Coupon (conditional, not applied)">{o.coupon_discount_minor ? `${formatMoney(o.coupon_discount_minor, cur)} coupon` : 'None stated'}</Field>
          <Field label="Payment offer (conditional, not applied)">{o.payment_offer ?? UNKNOWN}</Field>
          <Field label="Seller">{o.seller_name ?? UNKNOWN}</Field>
          <Field label="Seller ID">
            <span className="mono">{o.seller_id}</span>
          </Field>
          <Field label="Listing ID">
            <span className="mono">{o.listing_id}</span>
          </Field>
          <Field label="Condition">{o.condition ?? UNKNOWN}</Field>
          <Field label="Data source">{o.synthetic ? 'Synthetic imported snapshot' : 'Imported snapshot'}</Field>
          <Field label="Observed">
            {o.current_observation ? (
              formatObservedAt(o.current_observation.source_timestamp, o.current_observation.timestamp_quality, o.current_observation.observed_at)
            ) : (
              <span className="muted">No current observation</span>
            )}
          </Field>
        </dl>
      </details>
      <p className="offer__link">
        {o.product_url ? (
          <a href={o.product_url} target="_blank" rel="noopener noreferrer nofollow" className="btn btn--secondary">
            Visit {o.marketplace} (external site, not affiliated)
          </a>
        ) : (
          <span className="muted small">No store link in this dataset.</span>
        )}
      </p>
    </article>
  );
}

function DesignationItem({ label, des }: { label: string; des: Designation }) {
  return (
    <div className="summary__item">
      <dt>{label}</dt>
      <dd>
        {des.amount_minor !== null ? (
          <>
            <span className="summary__value">{formatMoney(des.amount_minor, des.currency ?? 'INR')}</span>
            <span className="muted"> at {des.marketplaces.join(', ')}</span>
          </>
        ) : (
          <span className="muted">Not available</span>
        )}
        <span className="sub">{des.note}</span>
      </dd>
    </div>
  );
}

function DeliveredSection({ d }: { d: ProductDetail }) {
  const p = d.pricing;
  const cur = p.currency ?? 'INR';
  const fmt = (v: number) => formatMoney(v, cur);
  const unknown = d.offers.filter((o) => o.price_minor !== null && o.delivered_price_minor === null);
  return (
    <Section id="delivered" title="Delivered price comparison" note="Delivered price = base price + known shipping. Coupons and payment offers are conditional and never subtracted.">
      <dl className="summary summary--three">
        <DesignationItem label="Lowest listed price" des={p.lowest_listed} />
        <DesignationItem label="Lowest confirmed delivered price" des={p.lowest_confirmed_delivered} />
        <DesignationItem label="Lowest confirmed delivered price among offers marked available" des={p.lowest_confirmed_delivered_available} />
      </dl>
      {!p.lowest_confirmed_delivered.certain_overall && p.lowest_confirmed_delivered.amount_minor !== null && (
        <p className="callout callout--warn" role="note">
          The cheapest delivered price overall can't be determined: some listings have unknown shipping and a lower base price.
        </p>
      )}
      <div className="chart-grid">
        <HBarChart
          title="Confirmed delivered price by store"
          summary={
            unknown.length
              ? `${unknown.length} listing(s) with unknown shipping are listed but not charted.`
              : 'All listings have known shipping.'
          }
          series={[{ key: 'delivered', label: 'Delivered price', tone: 'a' }]}
          rows={d.offers.map((o) => ({
            label: o.marketplace,
            values: { delivered: o.delivered_price_minor },
            note: o.price_minor !== null && o.delivered_price_minor === null ? 'Shipping unknown, not charted' : undefined,
            badge: p.lowest_confirmed_delivered.listing_ids.includes(o.listing_id) ? 'Lowest' : undefined,
          }))}
          format={fmt}
        />
        <HBarChart
          title="Price composition"
          summary="Each bar is base price plus known shipping. Conditional offers are not savings and are not shown as reductions."
          stacked
          series={[
            { key: 'base', label: 'Base price', tone: 'a' },
            { key: 'shipping', label: 'Shipping', tone: 'c' },
          ]}
          rows={d.offers.map((o) => ({
            label: o.marketplace,
            values: { base: o.price_minor, shipping: o.shipping_known ? o.shipping_minor : null },
            note: o.price_minor !== null && !o.shipping_known ? 'Base price only; shipping unknown' : undefined,
          }))}
          format={fmt}
        />
      </div>
    </Section>
  );
}

const STATUS_TEXT: Record<string, (diff: number | null) => string> = {
  consistent: () => 'Consistent',
  differs: (diff) => `Differs by ${Math.abs(diff ?? 0).toFixed(2)} points`,
  no_reference: () => 'No reference price',
  no_advertised: () => 'No advertised discount',
  price_above_reference: () => 'Price above reference',
  no_price: () => 'No current price',
};

function pctText(v: number | null) {
  return v === null ? '' : `${v.toFixed(2)}%`;
}

function DiscountSection({ d }: { d: ProductDetail }) {
  const cur = d.pricing.currency ?? 'INR';
  const conditional = d.offers.filter((o) => o.coupon_discount_minor || (o.payment_offer && o.payment_offer !== 'No payment offer'));
  return (
    <Section
      id="discounts"
      title="Discount transparency"
      note="The reference price (M.R.P.) is a seller-provided reference price, not a verified past selling price. Differences are shown for transparency, not as a judgement of the store."
    >
      <div className="table-wrap" tabIndex={0} role="region" aria-label="Discount comparison table">
        <table className="table">
          <thead>
            <tr>
              <th scope="col">Store</th>
              <th scope="col" className="num">Reference price</th>
              <th scope="col" className="num">Listed price</th>
              <th scope="col" className="num">Advertised discount</th>
              <th scope="col" className="num">Calculated reduction</th>
              <th scope="col">Comparison</th>
            </tr>
          </thead>
          <tbody>
            {d.offers.map((o) => {
              const a = o.discount;
              return (
                <tr key={o.listing_id}>
                  <th scope="row">{o.marketplace}</th>
                  <td className="num">{a.reference_price_minor !== null ? formatMoney(a.reference_price_minor, cur) : 'Unknown'}</td>
                  <td className="num">{money(a.price_minor, cur)}</td>
                  <td className="num">{pctText(a.advertised_percent) || 'Unknown'}</td>
                  <td className="num">{pctText(a.calculated_percent) || 'Not available'}</td>
                  <td>
                    <span className={a.material ? 'note-warning' : undefined}>{STATUS_TEXT[a.status](a.difference_points)}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <HBarChart
        title="Advertised vs calculated discount"
        summary="Advertised promotion compared with the reduction calculated from the seller-provided reference price, per store."
        series={[
          { key: 'adv', label: 'Advertised', tone: 'b' },
          { key: 'calc', label: 'Calculated from reference', tone: 'a' },
        ]}
        rows={d.offers.map((o) => ({ label: o.marketplace, values: { adv: o.discount.advertised_percent, calc: o.discount.calculated_percent } }))}
        format={(v) => `${v.toFixed(2)}%`}
        max={100}
      />
      <div className="stack-sm">
        <h3>Conditional offers</h3>
        {conditional.length === 0 ? (
          <p className="muted small">No coupons or payment offers are recorded for these listings.</p>
        ) : (
          <ul className="bullets small">
            {conditional.flatMap((o) => [
              o.coupon_discount_minor ? (
                <li key={`${o.listing_id}-c`}>
                  {o.marketplace}: {formatMoney(o.coupon_discount_minor, cur)} coupon (conditional), not included in any total.
                </li>
              ) : null,
              o.payment_offer && o.payment_offer !== 'No payment offer' ? (
                <li key={`${o.listing_id}-p`}>
                  {o.marketplace}: {o.payment_offer} (conditional payment offer), not included in any total.
                </li>
              ) : null,
            ])}
          </ul>
        )}
      </div>
    </Section>
  );
}

function RatingsSection({ d, productId }: { d: ProductDetail; productId: string }) {
  return (
    <Section id="ratings" title="Ratings and reviews" note="Seller rating, each store's product rating and individual review ratings are different measures and are never combined.">
      <HBarChart
        title="Ratings by store"
        summary="Product rating for this store and seller rating, each out of 5, as stated in the imported snapshot."
        series={[
          { key: 'product', label: 'Product rating (this store)', tone: 'a' },
          { key: 'seller', label: 'Seller rating', tone: 'd' },
        ]}
        rows={d.offers.map((o) => ({ label: o.marketplace, values: { product: o.product_rating, seller: o.seller_rating } }))}
        format={(v) => `${formatRating(v)} / 5`}
        max={5}
      />
      <Reviews d={d} productId={productId} />
    </Section>
  );
}

function ShippingSection({ d }: { d: ProductDetail }) {
  const cur = d.pricing.currency ?? 'INR';
  return (
    <Section id="shipping" title="Shipping and delivery">
      <div className="table-wrap" tabIndex={0} role="region" aria-label="Shipping and delivery table">
        <table className="table">
          <thead>
            <tr>
              <th scope="col">Store</th>
              <th scope="col" className="num">Shipping</th>
              <th scope="col">Delivery estimate</th>
              <th scope="col">Seller location</th>
            </tr>
          </thead>
          <tbody>
            {d.offers.map((o) => (
              <tr key={o.listing_id}>
                <th scope="row">{o.marketplace}</th>
                <td className="num">{!o.shipping_known ? 'Unknown' : o.shipping_minor === 0 ? 'Free (known)' : money(o.shipping_minor, cur)}</td>
                <td>{o.delivery_information ?? 'Unknown'}</td>
                <td>{o.seller_location ?? 'Unknown'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function AvailabilitySection({ d }: { d: ProductDetail }) {
  const s = d.availability_summary;
  return (
    <Section id="availability" title="Stock and availability" note="Availability reported in imported snapshot. It is not a live stock check.">
      {s.contradictions > 0 && (
        <p className="callout callout--warn" role="note">
          {s.contradictions} listing's availability disagrees with its stock quantity. Both values are shown as supplied and the listing is not treated as purchasable.
        </p>
      )}
      <HBarChart
        title="Listings by reported availability"
        summary={`${d.offers.length} listings: ${(['in_stock', 'limited_stock', 'out_of_stock', 'unknown'] as const).map((k) => `${s[k]} ${AVAIL_LABEL[k].toLowerCase()}`).join(', ')}.`}
        series={[{ key: 'n', label: 'Listings', tone: 'b' }]}
        rows={(['in_stock', 'limited_stock', 'out_of_stock', 'unknown'] as const).map((k) => ({ label: AVAIL_LABEL[k], values: { n: s[k] } }))}
        format={(v) => formatCount(v)}
        max={Math.max(1, d.offers.length)}
      />
      <ul className="avail-list">
        {d.offers.map((o) => (
          <li key={o.listing_id}>
            <strong>{o.marketplace}</strong>: availability reported in imported snapshot: {o.availability ?? 'not reported'}; stock {o.stock_quantity ?? 'unknown'}
            {o.flags.includes('stock_availability_contradiction') && <span className="note-warning"> · Availability and reported stock quantity disagree.</span>}
          </li>
        ))}
      </ul>
    </Section>
  );
}

function ProvenanceSection({ d }: { d: ProductDetail }) {
  return (
    <Section id="provenance" title="Data provenance">
      <ul className="quality-labels">
        {d.quality_labels.map((q) => (
          <li key={q.code} className="quality-label">
            <span className={`tag ${q.code === 'verified_history' ? 'tag--good' : 'tag--warn'}`}>{q.label}</span>
            <span className="muted small">{q.description}</span>
          </li>
        ))}
      </ul>
      <dl className="offer__fields">
        <Field label="Source">{d.provenance.source_labels.join(', ')}</Field>
        <Field label="Source type">{(d.provenance.source_types ?? []).join(', ') || 'Unknown'}</Field>
        {d.offers.map((o) => (
          <Field key={o.listing_id} label={`${o.marketplace} observation`}>
            {o.current_observation
              ? formatObservedAt(o.current_observation.source_timestamp, o.current_observation.timestamp_quality, o.current_observation.observed_at)
              : 'No current observation'}
          </Field>
        ))}
      </dl>
    </Section>
  );
}

function Reviews({ d, productId }: { d: ProductDetail; productId: string }) {
  const [page, setPage] = useState(1);
  const q = useProductReviews(productId, page);
  const s = d.reviews_summary;
  const pages = q.data ? Math.max(1, Math.ceil(q.data.total / q.data.page_size)) : 1;
  return (
    <div className="stack-md">
      <h3>Customer reviews</h3>
      {s.average_review_rating !== null && (
        <div>
          <p>
            <strong>
              Average review rating {s.average_review_rating.toFixed(2)} / 5 from {formatCount(s.rated_count)} {s.rated_count === 1 ? 'review' : 'reviews'}
            </strong>
          </p>
          <p className="muted small">
            {s.formula}
            {s.rated_count < 10 ? ' Small sample: treat this average with caution.' : ''}
            {d.provenance.synthetic ? ' These are synthetic sample reviews, not real customer opinions.' : ''}
          </p>
        </div>
      )}
      {q.isPending && <p className="muted">Loading reviews…</p>}
      {q.isError && (
        <p className="inline-error" role="alert">
          Couldn't load reviews: {q.error.message}{' '}
          <button type="button" className="link-button" onClick={() => q.refetch()}>
            Try again
          </button>
        </p>
      )}
      {q.data && q.data.total === 0 && <p className="muted">No reviews for this product.</p>}
      {q.data && q.data.items.length > 0 && (
        <ul className="reviews">
          {q.data.items.map((r, i) => (
            <li key={`${r.listing_id}-${page}-${i}`} className="review">
              <p className="review__head">
                <strong>{r.review_rating !== null ? `Review rating ${r.review_rating} / 5` : 'No rating given'}</strong>
                {r.marketplace && <span className="muted"> · {r.marketplace}</span>}
                {r.synthetic && <span className="tag tag--synthetic">Synthetic sample review</span>}
              </p>
              {/* Plain text only: React escapes it; never rendered as HTML or Markdown. */}
              <p className="review__text">{r.text}</p>
            </li>
          ))}
        </ul>
      )}
      {pages > 1 && (
        <nav className="pager" aria-label="Review pages">
          <button type="button" className="btn btn--secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            Previous
          </button>
          <span className="muted">
            Page {page} of {pages}
          </span>
          <button type="button" className="btn btn--secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>
            Next
          </button>
        </nav>
      )}
    </div>
  );
}
