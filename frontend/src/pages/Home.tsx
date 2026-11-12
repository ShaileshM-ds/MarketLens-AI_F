import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useCategories } from '../lib/useCategories';
import { apiGet } from '../lib/api';
import { useDataMode } from '../lib/dataMode';
import { formatMoney } from '../lib/money';
import { ProductImage } from '../components/ProductImage';

const FEATURES = [
  { letter: 'P', tone: 'blue', title: 'Price comparison', sub: 'Across three stores', to: '/products' },
  { letter: 'B', tone: 'green', title: 'Buying advice', sub: 'Buy now or wait?', to: '/methodology' },
  { letter: 'P', tone: 'purple', title: 'Price tracker', sub: 'Track and get alerts', to: '/watchlist' },
  { letter: 'R', tone: 'peach', title: 'Real discount check', sub: 'Is the discount genuine?', to: '/methodology' },
];

const TONES = ['blue', 'pink', 'purple', 'mint', 'peach', 'blue', 'grey', 'sky'];

/** Fixed order and labels; counts come from the API for the active mode. */
const CATEGORY_ORDER = [
  { slug: 'mens-clothing', label: "Men's clothing" },
  { slug: 'womens-clothing', label: "Women's clothing" },
  { slug: 'cameras', label: 'Cameras' },
  { slug: 'smart-home', label: 'Smart home' },
  { slug: 'wearables', label: 'Wearables' },
  { slug: 'mobile-phones', label: 'Mobile phones' },
  { slug: 'home-appliances', label: 'Home appliances' },
  { slug: 'computer-accessories', label: 'Computer accessories' },
];

const countFormat = new Intl.NumberFormat('en-IN');

export function Home() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const categories = useCategories();

  const onSearch = (e: FormEvent) => {
    e.preventDefault();
    const q = query.trim();
    navigate(q ? `/products?q=${encodeURIComponent(q)}` : '/products');
  };

  const countFor = (slug: string): string => {
    if (categories.isPending) return 'Loading…';
    if (categories.isError) return 'Count unavailable';
    const n = categories.data?.categories.find((c) => c.slug === slug)?.product_count ?? 0;
    if (n <= 0) return 'Data coming';
    return `${countFormat.format(n)} ${n === 1 ? 'product' : 'products'}`;
  };

  return (
    <div className="stack-lg">
      <section className="card hero" aria-labelledby="hero-title">
        <div className="hero__copy">
          <p className="eyebrow">Your market, in focus</p>
          <h1 id="hero-title" className="hero__title">
            Compare prices.
            <br />
            Track deals.
            <br />
            <span className="accent">Shop with evidence.</span>
          </h1>
          <p className="hero__lead">
            Find the best price across Amazon, Flipkart and Myntra, and see whether the discount is genuine.
          </p>
          <form className="search" role="search" onSubmit={onSearch}>
            <label htmlFor="home-search" className="visually-hidden">
              Search for a product, brand or style
            </label>
            <input
              id="home-search"
              type="search"
              className="search__input"
              placeholder="Search for a product, brand or style"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button type="submit" className="btn btn--primary search__button">
              Search
            </button>
          </form>
        </div>
        <HeroArt />
      </section>

      <section aria-label="What you can do">
        <ul className="feature-grid">
          {FEATURES.map((f) => (
            <li key={f.title}>
              <Link to={f.to} className="card tile tile--row">
                <span className={`letter-icon letter-icon--${f.tone}`} aria-hidden="true">
                  {f.letter}
                </span>
                <span>
                  <span className="tile__title">{f.title}</span>
                  <span className="tile__sub">{f.sub}</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <FeaturedDemo />

      <section aria-labelledby="categories-title">
        <div className="section-head">
          <h2 id="categories-title">Shop by category</h2>
          <Link to="/products" className="link">
            View all categories
          </Link>
        </div>
        {categories.isError && (
          <p className="inline-error" role="alert">
            Couldn't load product counts: {categories.error.message}{' '}
            <button type="button" className="link-button" onClick={() => categories.refetch()}>
              Try again
            </button>
          </p>
        )}
        <ul className="category-grid">
          {CATEGORY_ORDER.map((c, i) => (
            <li key={c.slug}>
              <Link to={`/products?category=${c.slug}`} className="card tile tile--col">
                <span className={`letter-icon letter-icon--${TONES[i]}`} aria-hidden="true">
                  {c.label[0]}
                </span>
                <span className="tile__title">{c.label}</span>
                <span className="tile__sub">{countFor(c.slug)}</span>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

/** One product per category in Demo mode, with its synthetic artwork. Nothing is shown in other modes. */
const FEATURED = ['DEMO-P-001', 'DEMO-P-007', 'DEMO-P-012', 'DEMO-P-016', 'DEMO-P-021', 'DEMO-P-026', 'DEMO-P-031', 'DEMO-P-036'];

function FeaturedDemo() {
  const { mode } = useDataMode();
  const q = useQuery({
    queryKey: ['featured', mode],
    queryFn: () => apiGet<{ items: { product_id: string; name: string; category_label: string; lowest_price: { amount_minor: number; currency: string } | null }[] }>('/api/v1/products', { mode, page_size: '60' }),
    enabled: mode === 'demo',
  });
  if (mode !== 'demo') return null;
  const items = (q.data?.items ?? []).filter((p) => FEATURED.includes(p.product_id)).sort((a, b) => FEATURED.indexOf(a.product_id) - FEATURED.indexOf(b.product_id));
  return (
    <section aria-labelledby="featured-title">
      <div className="section-head">
        <h2 id="featured-title">Featured products</h2>
      </div>
      {q.isPending && <p className="muted" role="status">Loading demo products…</p>}
      {q.isError && <p className="inline-error" role="alert">Couldn't load demo products: {q.error.message}</p>}
      {q.data && items.length === 0 && <p className="empty-inline">No Demo data yet. An administrator can generate it under Data administration.</p>}
      {items.length > 0 && (
        <ul className="featured-grid">
          {items.map((p) => (
            <li key={p.product_id}>
              <Link to={`/products/${encodeURIComponent(p.product_id)}`} className="card featured-card">
                <ProductImage productId={p.product_id} name={p.name} />
                <span className="featured-card__name">
                  {p.name}
                  <span className="tile__sub">
                    {p.category_label}
                    {p.lowest_price ? ` · from ${formatMoney(p.lowest_price.amount_minor, p.lowest_price.currency)}` : ''}
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function HeroArt() {
  return (
    <div className="hero__art" aria-hidden="true">
      <svg viewBox="0 0 240 160" className="hero__svg">
        <rect x="1" y="17" width="230" height="142" rx="16" className="art-card" />
        <rect x="26" y="106" width="26" height="40" rx="4" className="art-bar1" />
        <rect x="66" y="82" width="26" height="64" rx="4" className="art-bar2" />
        <rect x="106" y="58" width="26" height="88" rx="4" className="art-bar3" />
        <polyline points="26,86 70,70 116,48 202,34" className="art-line" />
        <circle cx="202" cy="34" r="6" className="art-dot" />
      </svg>
    </div>
  );
}
