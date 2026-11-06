import { useQuery } from '@tanstack/react-query';
import { apiGet } from './api';
import { useDataMode, type DataMode } from './dataMode';

export interface Warning {
  code: string;
  message: string;
}

export interface LowestPrice {
  amount_minor: number;
  currency: string;
  basis: 'base_listing_price';
  excludes_shipping: true;
  marketplaces: string[];
  offers_with_unknown_shipping: number;
  out_of_stock: boolean;
}

export interface ProductItem {
  product_id: string;
  name: string;
  category: string;
  category_label: string;
  source_category: string | null;
  brand: string | null;
  size: string | null;
  colour: string | null;
  image: { kind: string };
  synthetic: boolean | null;
  source_label: string | null;
  offer_count: number;
  matching_offer_count: number;
  matching_marketplaces: string[];
  lowest_price: LowestPrice | null;
  lowest_price_unavailable_reason: string | null;
  availability: Record<'in_stock' | 'limited_stock' | 'out_of_stock' | 'unknown', number>;
  product_rating: { min: number; max: number; stores: number } | null;
  review_count: number;
  has_data_warnings: boolean;
  verified_history: boolean;
  lowest_delivered: { amount_minor: number; currency: string; marketplaces: string[]; certain_overall: boolean } | null;
  available_offer_count: number;
  max_advertised_discount: number | null;
}

export interface ProductList {
  mode: DataMode;
  total: number;
  page: number;
  page_size: number;
  sort: string;
  items: ProductItem[];
}

export interface FilterMeta {
  mode: DataMode;
  total_products: number;
  categories: { slug: string; label: string; count: number }[];
  marketplaces: { name: string; count: number }[];
  currencies: { code: string; min_price_minor: number; max_price_minor: number }[];
  availability: { value: string; label: string; count: number }[];
  conditions: string[];
  brands: string[];
  sizes: string[];
  colours: string[];
  catalog_status: { products: number; summarized: number; up_to_date: boolean };
  data_basis: { verified_history: boolean; snapshot_only: boolean; all_synthetic: boolean };
}

export interface CurrentObservation {
  source_timestamp: string;
  timestamp_quality: 'timezone_unknown' | 'utc' | 'offset_converted';
  observed_at: string | null;
  source_last_updated: string | null;
  basis: string;
}

export interface Offer {
  listing_id: string;
  marketplace: string;
  seller_id: string;
  seller_name: string | null;
  product_url: string | null;
  observation_count: number;
  current_observation: CurrentObservation | null;
  currency: string | null;
  price_minor: number | null;
  reference_price_minor: number | null;
  advertised_discount_percent: number | null;
  shipping_minor: number | null;
  shipping_known: boolean;
  total_minor: number | null;
  free_shipping: boolean;
  coupon_discount_minor: number | null;
  payment_offer: string | null;
  availability: string | null;
  availability_class: string;
  stock_quantity: number | null;
  seller_rating: number | null;
  product_rating: number | null;
  delivery_information: string | null;
  urgency_message: string | null;
  seller_location: string | null;
  condition: string | null;
  warnings: Warning[];
  purchasable: boolean;
  synthetic: boolean | null;
  is_lowest_base: boolean;
  is_lowest_delivered: boolean;
  flags: string[];
  delivered_price_minor: number | null;
  delivered_status: 'confirmed' | 'cannot_be_confirmed' | 'no_price';
  discount: DiscountAnalysis;
}

export interface DiscountAnalysis {
  reference_price_minor: number | null;
  price_minor: number | null;
  advertised_percent: number | null;
  calculated_percent: number | null;
  difference_points: number | null;
  material: boolean;
  status: 'consistent' | 'differs' | 'no_reference' | 'no_advertised' | 'price_above_reference' | 'no_price';
  note: string;
}

export interface Designation {
  amount_minor: number | null;
  currency: string | null;
  listing_ids: string[];
  marketplaces: string[];
  considered_count: number;
  certain_overall: boolean;
  note: string;
  excluded?: { listing_id: string; marketplace: string | null; reason: string }[];
}

export interface Pricing {
  currency: string | null;
  lowest_listed: Designation;
  lowest_confirmed_delivered: Designation;
  lowest_confirmed_delivered_available: Designation;
}

export interface QualityLabel {
  code: string;
  label: string;
  description: string;
}

export type AvailabilitySummary = Record<'in_stock' | 'limited_stock' | 'out_of_stock' | 'unknown' | 'contradictions', number>;

export interface CompareProduct {
  product_id: string;
  name: string;
  category: string;
  category_label: string;
  source_category: string | null;
  image: { kind: string };
  synthetic: boolean | null;
  source_label: string | null;
  marketplaces: string[];
  offer_count: number;
  available_offer_count: number;
  availability_summary: AvailabilitySummary;
  pricing: Pricing;
  reference_price_range: { min: number; max: number; currency: string } | null;
  advertised_discount_range: { min: number; max: number } | null;
  calculated_reduction_range: { min: number; max: number } | null;
  discount_differences: number;
  product_rating_range: { min: number; max: number } | null;
  seller_rating_range: { min: number; max: number } | null;
  reviews_summary: { count: number; rated_count: number; average_review_rating: number | null };
  conditions: string[];
  quality_labels: QualityLabel[];
  price_history: { status: string; reason: string };
}

export interface CompareResult {
  mode: DataMode;
  products: CompareProduct[];
  missing: string[];
  comparability_warnings: string[];
}

export interface ProductDetail {
  mode: DataMode;
  product: {
    product_id: string;
    name: string;
    category: string;
    category_label: string;
    source_category: string | null;
    brand: string | null;
    size: string | null;
    colour: string | null;
    image: { kind: string };
    synthetic: boolean | null;
    source_label: string | null;
    source_type: string | null;
    offer_count: number;
    marketplaces: string[];
  };
  offers: Offer[];
  comparison: {
    currency: string | null;
    lowest_base_price_minor: number | null;
    lowest_delivered_price_minor: number | null;
    offers_with_unknown_shipping: number;
    excluded: { listing_id: string; marketplace: string; reason: string }[];
    note: string;
  };
  reviews_summary: { count: number; rated_count: number; average_review_rating: number | null; distribution: Record<string, number>; formula: string };
  price_history: {
    status: 'unavailable' | 'available';
    reason: string;
    verified_observation_count: number;
    timezone_unknown_observation_count: number;
    first_verified_at?: string | null;
    last_verified_at?: string | null;
  };
  provenance: { synthetic: boolean; source_labels: string[]; source_types?: string[] };
  pricing: Pricing;
  availability_summary: AvailabilitySummary;
  quality_labels: QualityLabel[];
}

export interface Review {
  listing_id: string;
  marketplace: string | null;
  review_rating: number | null;
  text: string;
  review_source: string | null;
  reviewer_name: string | null;
  review_date: string | null;
  synthetic: boolean | null;
  observation_source_timestamp: string | null;
  observation_timestamp_quality: string | null;
}

export interface ReviewPage {
  total: number;
  page: number;
  page_size: number;
  items: Review[];
}

export function useProductFilters() {
  const { mode, unavailableReason } = useDataMode();
  return useQuery({
    queryKey: ['products', 'filters', mode],
    queryFn: () => apiGet<FilterMeta>('/api/v1/products/filters', { mode }),
    enabled: unavailableReason(mode) === null,
  });
}

/** Results for one workspace never show another workspace's data, even as a placeholder. */
export function useProductList(params: URLSearchParams | null) {
  const { mode, unavailableReason } = useDataMode();
  return useQuery({
    queryKey: ['products', 'list', mode, params?.toString() ?? ''],
    queryFn: () => apiGet<ProductList>('/api/v1/products', params!),
    enabled: params !== null && unavailableReason(mode) === null,
    placeholderData: (prev, prevQuery) => (prevQuery?.queryKey[2] === mode ? prev : undefined),
  });
}

export function useProductDetail(productId: string) {
  const { mode, unavailableReason } = useDataMode();
  return useQuery({
    queryKey: ['products', 'detail', mode, productId],
    queryFn: () => apiGet<ProductDetail>(`/api/v1/products/${encodeURIComponent(productId)}`, { mode }),
    enabled: unavailableReason(mode) === null,
  });
}

export function useProductReviews(productId: string, page: number) {
  const { mode, unavailableReason } = useDataMode();
  return useQuery({
    queryKey: ['products', 'reviews', mode, productId, page],
    queryFn: () =>
      apiGet<ReviewPage>(`/api/v1/products/${encodeURIComponent(productId)}/reviews`, { mode, page: String(page), page_size: '10' }),
    enabled: unavailableReason(mode) === null,
    placeholderData: (prev, prevQuery) => (prevQuery?.queryKey[2] === mode && prevQuery?.queryKey[3] === productId ? prev : undefined),
  });
}

export function useCompareProducts(ids: string[]) {
  const { mode, unavailableReason } = useDataMode();
  const params = new URLSearchParams({ mode });
  ids.forEach((id) => params.append('ids', id));
  return useQuery({
    queryKey: ['compare', mode, ids.join('|')],
    queryFn: () => apiGet<CompareResult>('/api/v1/compare', params),
    enabled: ids.length > 0 && unavailableReason(mode) === null,
    placeholderData: (prev, prevQuery) => (prevQuery?.queryKey[1] === mode ? prev : undefined),
  });
}
