/**
 * Product Explorer state lives in the URL so refresh, Back and shared links keep it.
 * Prices are typed in rupees and converted to minor units only here, at the boundary.
 */
import { formatMoney, parseMajorToMinor } from './money';

export const PAGE_SIZE = 24;

export const SORTS = [
  { value: 'name_asc', label: 'Name (A–Z)' },
  { value: 'name_desc', label: 'Name (Z–A)' },
  { value: 'price_asc', label: 'Listed price: low to high' },
  { value: 'price_desc', label: 'Listed price: high to low' },
  { value: 'delivered_asc', label: 'Confirmed delivered price: low to high' },
  { value: 'delivered_desc', label: 'Confirmed delivered price: high to low' },
  { value: 'rating_desc', label: 'Highest product rating (any store)' },
  { value: 'discount_desc', label: 'Highest advertised discount' },
  { value: 'available_desc', label: 'Most listings marked available' },
  { value: 'offers_desc', label: 'Most store listings' },
] as const;
export type SortKey = (typeof SORTS)[number]['value'];

export const AVAILABILITY_LABELS: Record<string, string> = {
  in_stock: 'In stock',
  limited_stock: 'Limited stock',
  out_of_stock: 'Out of stock',
  unknown: 'Not stated',
};

export interface ExplorerState {
  q: string;
  category: string;
  marketplaces: string[];
  availability: string[];
  min: string;
  max: string;
  productRatingMin: string;
  sellerRatingMin: string;
  freeShipping: boolean;
  discountMin: string;
  discountMax: string;
  deliveredKnown: boolean;
  sort: SortKey;
  page: number;
  view: 'grid' | 'table';
}

/** URL keys that count as filters (changing any of them resets the page). */
export const FILTER_KEYS = ['q', 'category', 'marketplace', 'availability', 'min', 'max', 'prating', 'srating', 'free', 'dmin', 'dmax', 'delivered'];
const RATINGS = ['3', '3.5', '4', '4.5'];

export function readState(p: URLSearchParams): ExplorerState {
  const sort = p.get('sort') as SortKey;
  const page = Number(p.get('page'));
  const rating = (k: string) => (RATINGS.includes(p.get(k) ?? '') ? (p.get(k) as string) : '');
  return {
    q: p.get('q') ?? '',
    category: p.get('category') ?? '',
    marketplaces: p.getAll('marketplace').filter(Boolean),
    availability: p.getAll('availability').filter((a) => a in AVAILABILITY_LABELS),
    min: p.get('min') ?? '',
    max: p.get('max') ?? '',
    productRatingMin: rating('prating'),
    sellerRatingMin: rating('srating'),
    freeShipping: p.get('free') === '1',
    discountMin: p.get('dmin') ?? '',
    discountMax: p.get('dmax') ?? '',
    deliveredKnown: p.get('delivered') === '1',
    sort: SORTS.some((s) => s.value === sort) ? sort : 'name_asc',
    page: Number.isInteger(page) && page >= 1 ? page : 1,
    view: p.get('view') === 'table' ? 'table' : 'grid',
  };
}

/** Set one URL key. Anything except the page itself resets pagination. */
export function withParam(p: URLSearchParams, key: string, value: string | string[] | boolean | null): URLSearchParams {
  const next = new URLSearchParams(p);
  next.delete(key);
  if (Array.isArray(value)) value.filter(Boolean).forEach((v) => next.append(key, v));
  else if (value === true) next.set(key, '1');
  else if (typeof value === 'string' && value !== '') next.set(key, value);
  if (key !== 'page') next.delete('page');
  return next;
}

export function clearAll(p: URLSearchParams): URLSearchParams {
  const next = new URLSearchParams(p);
  [...FILTER_KEYS, 'page'].forEach((k) => next.delete(k));
  return next;
}

export function hasFilters(s: ExplorerState): boolean {
  return Boolean(
    s.q || s.category || s.marketplaces.length || s.availability.length || s.min || s.max || s.productRatingMin || s.sellerRatingMin || s.freeShipping || s.discountMin || s.discountMax || s.deliveredKnown,
  );
}

export function toApiParams(s: ExplorerState, mode: string, currency: string): { params: URLSearchParams; error: string | null } {
  const params = new URLSearchParams({ mode });
  let error: string | null = null;
  if (s.q.trim()) params.set('q', s.q.trim());
  if (s.category) params.set('category', s.category);
  s.marketplaces.forEach((m) => params.append('marketplace', m));
  s.availability.forEach((a) => params.append('availability', a));
  const min = s.min ? parseMajorToMinor(s.min, currency) : null;
  const max = s.max ? parseMajorToMinor(s.max, currency) : null;
  if (s.min && min === null) error = "The minimum price isn't a valid amount in rupees.";
  else if (s.max && max === null) error = "The maximum price isn't a valid amount in rupees.";
  else if (min !== null && max !== null && min > max) error = 'The minimum price is higher than the maximum price.';
  if (min !== null || max !== null) params.set('currency', currency);
  if (min !== null) params.set('price_min_minor', String(min));
  if (max !== null) params.set('price_max_minor', String(max));
  if (s.productRatingMin) params.set('product_rating_min', s.productRatingMin);
  if (s.sellerRatingMin) params.set('seller_rating_min', s.sellerRatingMin);
  if (s.freeShipping) params.set('free_shipping', 'true');
  const pct = (v: string) => (/^\d+(\.\d+)?$/.test(v.trim()) && Number(v) <= 100 ? Number(v) : null);
  const dmin = s.discountMin ? pct(s.discountMin) : null;
  const dmax = s.discountMax ? pct(s.discountMax) : null;
  if (!error && s.discountMin && dmin === null) error = 'The minimum discount must be a percentage from 0 to 100.';
  else if (!error && s.discountMax && dmax === null) error = 'The maximum discount must be a percentage from 0 to 100.';
  else if (!error && dmin !== null && dmax !== null && dmin > dmax) error = 'The minimum discount is higher than the maximum discount.';
  if (dmin !== null) params.set('discount_min', String(dmin));
  if (dmax !== null) params.set('discount_max', String(dmax));
  if (s.deliveredKnown) params.set('delivered_known', 'true');
  params.set('sort', s.sort);
  params.set('page', String(s.page));
  params.set('page_size', String(PAGE_SIZE));
  return { params, error };
}

export interface Chip {
  id: string;
  label: string;
  /** URL key and the value it should have after removing this chip. */
  key: string;
  next: string | string[] | boolean | null;
}

export function activeChips(s: ExplorerState, opts: { categoryLabel: (slug: string) => string; currency?: string }): Chip[] {
  const cur = opts.currency ?? 'INR';
  const money = (v: string) => {
    const minor = parseMajorToMinor(v, cur);
    return minor === null ? v : formatMoney(minor, cur);
  };
  const chips: Chip[] = [];
  if (s.q) chips.push({ id: 'q', label: `Search: ${s.q}`, key: 'q', next: null });
  if (s.category) chips.push({ id: 'category', label: `Category: ${opts.categoryLabel(s.category) || s.category}`, key: 'category', next: null });
  s.marketplaces.forEach((m) =>
    chips.push({ id: `m-${m}`, label: `Store: ${m}`, key: 'marketplace', next: s.marketplaces.filter((x) => x !== m) }),
  );
  s.availability.forEach((a) =>
    chips.push({ id: `a-${a}`, label: `Availability: ${AVAILABILITY_LABELS[a]}`, key: 'availability', next: s.availability.filter((x) => x !== a) }),
  );
  if (s.min && s.max) chips.push({ id: 'price', label: `Base price ${money(s.min)}–${money(s.max)}`, key: 'price', next: null });
  else if (s.min) chips.push({ id: 'price', label: `Base price from ${money(s.min)}`, key: 'min', next: null });
  else if (s.max) chips.push({ id: 'price', label: `Base price up to ${money(s.max)}`, key: 'max', next: null });
  if (s.productRatingMin) chips.push({ id: 'prating', label: `Product rating ${s.productRatingMin}+ (any store)`, key: 'prating', next: null });
  if (s.sellerRatingMin) chips.push({ id: 'srating', label: `Seller rating ${s.sellerRatingMin}+`, key: 'srating', next: null });
  if (s.freeShipping) chips.push({ id: 'free', label: 'Known free shipping', key: 'free', next: null });
  if (s.discountMin && s.discountMax) chips.push({ id: 'disc', label: `Advertised discount ${s.discountMin}–${s.discountMax}%`, key: 'discount', next: null });
  else if (s.discountMin) chips.push({ id: 'disc', label: `Advertised discount from ${s.discountMin}%`, key: 'dmin', next: null });
  else if (s.discountMax) chips.push({ id: 'disc', label: `Advertised discount up to ${s.discountMax}%`, key: 'dmax', next: null });
  if (s.deliveredKnown) chips.push({ id: 'delivered', label: 'Confirmed delivered price only', key: 'delivered', next: null });
  return chips;
}
