// API-shaped fixtures matching the real backend contract (values from the imported sample).

export const health = {
  status: 'ok',
  service: 'api',
  version: '0.1.0',
  checked_at: '2026-11-05T00:00:00Z',
  mongo: 'ok',
  modes: {
    demo: { database: 'marketlens_demo', available: true, reason: null },
    imported: { database: 'marketlens_imported', available: true, reason: null },
    live: { database: 'marketlens_live', available: false, reason: 'Live data is off: no live provider is configured.' },
  },
};

export function item(overrides: Record<string, unknown> = {}) {
  return {
    product_id: 'MCL0001',
    name: "Nike Men's Black Crew-Neck T-Shirt - Size S (Style 001)",
    category: 'mens-clothing',
    category_label: "Men's clothing",
    source_category: 'T-Shirts',
    brand: null,
    size: null,
    colour: null,
    image: { kind: 'generic_placeholder' },
    synthetic: true,
    source_label: 'Generated for project demonstration',
    offer_count: 3,
    matching_offer_count: 3,
    matching_marketplaces: ['Amazon', 'Flipkart', 'Myntra'],
    lowest_price: {
      amount_minor: 137000,
      currency: 'INR',
      basis: 'base_listing_price',
      excludes_shipping: true,
      marketplaces: ['Flipkart'],
      offers_with_unknown_shipping: 0,
      out_of_stock: false,
    },
    lowest_price_unavailable_reason: null,
    availability: { in_stock: 3, limited_stock: 0, out_of_stock: 0, unknown: 0 },
    product_rating: { min: 3.5, max: 4.2, stores: 3 },
    review_count: 3,
    has_data_warnings: false,
    verified_history: false,
    lowest_delivered: { amount_minor: 143000, currency: 'INR', marketplaces: ['Flipkart'], certain_overall: true },
    available_offer_count: 3,
    max_advertised_discount: 13.75,
    ...overrides,
  };
}

export function listResponse(items: unknown[], total = items.length, page = 1, mode = 'imported') {
  return { mode, total, page, page_size: 24, sort: 'name_asc', items, semantics: {} };
}

export function filtersResponse(mode = 'imported', total = 500) {
  const empty = total === 0;
  return {
    mode,
    total_products: total,
    categories: empty ? [] : [{ slug: 'mens-clothing', label: "Men's clothing", count: 500 }],
    marketplaces: empty ? [] : [
      { name: 'Amazon', count: 500 },
      { name: 'Flipkart', count: 500 },
      { name: 'Myntra', count: 500 },
    ],
    currencies: empty ? [] : [{ code: 'INR', min_price_minor: 51000, max_price_minor: 536000 }],
    availability: empty ? [] : [
      { value: 'in_stock', label: 'In stock', count: 1341 },
      { value: 'limited_stock', label: 'Limited stock', count: 109 },
      { value: 'out_of_stock', label: 'Out of stock', count: 50 },
    ],
    conditions: empty ? [] : ['New'],
    brands: [],
    sizes: [],
    colours: [],
    product_rating_range: empty ? null : [3.5, 4.8],
    seller_rating_range: empty ? null : [3.6, 4.8],
    sorts: ['name_asc', 'name_desc', 'price_asc', 'price_desc', 'rating_desc', 'offers_desc'],
    catalog_status: { products: total, summarized: total, up_to_date: true },
    data_basis: { verified_history: false, snapshot_only: !empty, all_synthetic: !empty },
  };
}

const tzWarning = { code: 'timezone_unknown', message: "The observation time has no timezone, so it can't be part of a verified price history." };

function offer(o: Record<string, unknown>) {
  const base: Record<string, unknown> = {
    seller_name: 'Seller',
    product_url: null,
    observation_count: 1,
    current_observation: {
      source_timestamp: '2026-11-04T10:30:00',
      timestamp_quality: 'timezone_unknown',
      observed_at: null,
      source_last_updated: '2026-11-04T10:30:00',
      basis: 'single_snapshot_timezone_unknown',
    },
    currency: 'INR',
    reference_price_minor: 160000,
    advertised_discount_percent: 13.75,
    shipping_known: true,
    free_shipping: false,
    coupon_discount_minor: 0,
    payment_offer: 'No payment offer',
    availability: 'In Stock',
    availability_class: 'in_stock',
    stock_quantity: 8,
    seller_rating: 4.3,
    product_rating: 3.5,
    delivery_information: 'Delivery in 2-4 days',
    urgency_message: null,
    seller_location: 'Bengaluru, Karnataka',
    condition: 'New',
    warnings: [tzWarning],
    purchasable: true,
    synthetic: true,
    source_label: 'Generated for project demonstration',
    is_lowest_base: false,
    is_lowest_delivered: false,
    flags: [],
    ...o,
  };
  // Derived exactly as the API derives them.
  const price = base.price_minor as number | null;
  const shipping = base.shipping_minor as number | null;
  const ref = base.reference_price_minor as number | null;
  const adv = base.advertised_discount_percent as number | null;
  const delivered = price !== null && base.shipping_known && shipping !== null ? price + shipping : null;
  const calc = price !== null && ref ? Math.round(((ref - price) / ref) * 10000) / 100 : null;
  const diff = calc !== null && adv !== null ? Math.round((adv - calc) * 100) / 100 : null;
  return {
    delivered_price_minor: delivered,
    delivered_status: price === null ? 'no_price' : delivered !== null ? 'confirmed' : 'cannot_be_confirmed',
    discount: {
      reference_price_minor: ref,
      price_minor: price,
      advertised_percent: adv,
      calculated_percent: calc,
      difference_points: diff,
      material: diff !== null && Math.abs(diff) > 0.5,
      status: ref === null ? 'no_reference' : adv === null ? 'no_advertised' : diff !== null && Math.abs(diff) > 0.5 ? 'differs' : 'consistent',
      note: 'note',
    },
    ...base,
  };
}

function designation(amount: number | null, ids: string[], markets: string[], extra: Record<string, unknown> = {}) {
  return { amount_minor: amount, currency: 'INR', listing_ids: ids, marketplaces: markets, considered_count: 3, certain_overall: true, note: 'Designation note.', ...extra };
}

export function pricing(overrides: Record<string, unknown> = {}) {
  return {
    currency: 'INR',
    lowest_listed: designation(137000, ['FLI-CLO-LIST-000002'], ['Flipkart']),
    lowest_confirmed_delivered: designation(143000, ['FLI-CLO-LIST-000002'], ['Flipkart']),
    lowest_confirmed_delivered_available: designation(143000, ['FLI-CLO-LIST-000002'], ['Flipkart'], { excluded: [] }),
    ...overrides,
  };
}

export const qualityLabels = [
  { code: 'synthetic_dataset', label: 'Synthetic dataset', description: 'Generated demonstration data, not real marketplace records.' },
  { code: 'timezone_unknown', label: 'Timezone unknown', description: "Observation times have no timezone, so they can't form a verified price history." },
  { code: 'missing_product_metadata', label: 'Missing product metadata', description: "Brand, size and colour aren't supplied; they are never guessed from the name." },
];

export function compareProduct(id: string, name: string, overrides: Record<string, unknown> = {}) {
  return {
    product_id: id,
    name,
    category: 'mens-clothing',
    category_label: "Men's clothing",
    source_category: 'T-Shirts',
    image: { kind: 'generic_placeholder' },
    synthetic: true,
    source_label: 'Generated for project demonstration',
    marketplaces: ['Amazon', 'Flipkart', 'Myntra'],
    offer_count: 3,
    available_offer_count: 3,
    availability_summary: { in_stock: 3, limited_stock: 0, out_of_stock: 0, unknown: 0, contradictions: 0 },
    pricing: pricing(),
    reference_price_range: { min: 160000, max: 160000, currency: 'INR' },
    advertised_discount_range: { min: 7.5, max: 14.38 },
    calculated_reduction_range: { min: 7.5, max: 14.38 },
    discount_differences: 0,
    product_rating_range: { min: 3.5, max: 4.2 },
    seller_rating_range: { min: 4.1, max: 4.3 },
    reviews_summary: { count: 3, rated_count: 3, average_review_rating: 3.67 },
    conditions: ['New'],
    quality_labels: qualityLabels,
    price_history: { status: 'unavailable', reason: 'Verified historical price data is not available for this product yet. Current comparisons use imported snapshot observations.' },
    ...overrides,
  };
}

export function compareResponse(products: unknown[]) {
  return { mode: 'imported', products, missing: [] as string[], comparability_warnings: [] as string[] };
}

export function detail(extraOffers: Record<string, unknown>[] = [], overrides: Record<string, unknown> = {}) {
  return {
    mode: 'imported',
    product: {
      product_id: 'MCL0001',
      name: "Nike Men's Black Crew-Neck T-Shirt - Size S (Style 001)",
      category: 'mens-clothing',
      category_label: "Men's clothing",
      source_category: 'T-Shirts',
      brand: null,
      size: null,
      colour: null,
      image: { kind: 'generic_placeholder' },
      synthetic: true,
      source_label: 'Generated for project demonstration',
      source_type: 'Synthetic',
      offer_count: 3 + extraOffers.length,
      marketplaces: ['Amazon', 'Flipkart', 'Myntra'],
    },
    offers: [
      offer({ listing_id: 'AMA-CLO-LIST-000001', marketplace: 'Amazon', seller_id: 'CLSEL00001', seller_name: 'Amazon Fashion Seller 1', price_minor: 138000, shipping_minor: 6000, total_minor: 144000 }),
      offer({ listing_id: 'FLI-CLO-LIST-000002', marketplace: 'Flipkart', seller_id: 'CLSEL00002', seller_name: 'Flipkart Fashion Seller 1', price_minor: 137000, shipping_minor: 6000, total_minor: 143000, is_lowest_base: true, is_lowest_delivered: true }),
      offer({ listing_id: 'MYN-CLO-LIST-000003', marketplace: 'Myntra', seller_id: 'CLSEL00003', seller_name: 'Myntra Fashion Seller 1', price_minor: 148000, shipping_minor: 0, total_minor: 148000, free_shipping: true }),
      ...extraOffers.map((o) => offer(o)),
    ],
    comparison: {
      currency: 'INR',
      lowest_base_price_minor: 137000,
      lowest_delivered_price_minor: 143000,
      offers_with_unknown_shipping: 0,
      excluded: [],
      note: 'Lowest prices consider listings that are in stock or limited stock, with a current price and no stock warning.',
    },
    reviews_summary: { count: 3, rated_count: 3, average_review_rating: 4, distribution: { '1': 0, '2': 0, '3': 1, '4': 1, '5': 1 }, formula: 'Arithmetic mean of the individual review ratings (1 to 5).' },
    price_history: {
      status: 'unavailable',
      reason: 'Verified historical price data is not available for this product yet. Current comparisons use imported snapshot observations.',
      verified_observation_count: 0,
      timezone_unknown_observation_count: 3,
    },
    provenance: { synthetic: true, source_labels: ['Generated for project demonstration'], source_types: ['Synthetic'] },
    pricing: pricing(),
    availability_summary: { in_stock: 3 + extraOffers.length, limited_stock: 0, out_of_stock: 0, unknown: 0, contradictions: 0 },
    quality_labels: qualityLabels,
    ...overrides,
  };
}

export function reviewsResponse(items?: unknown[]) {
  const list = items ?? [
    { listing_id: 'AMA-CLO-LIST-000001', marketplace: 'Amazon', review_rating: 3, text: '<b>Not bold</b> plain text only', review_source: 'Synthetic (generated sample review)', reviewer_name: null, review_date: null, synthetic: true, source_label: 'x', observation_source_timestamp: '2026-11-04T10:30:00', observation_timestamp_quality: 'timezone_unknown' },
  ];
  return { mode: 'imported', total: list.length, page: 1, page_size: 10, items: list };
}
