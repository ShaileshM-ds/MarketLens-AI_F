import { useQuery } from '@tanstack/react-query';
import { apiGet } from './api';
import { useDataMode } from './dataMode';

export interface HistoryPoint {
  date: string;
  value_minor: number;
  marketplaces: string[];
}

export interface ProductHistory {
  cutoff: string;
  window: { days: number; start: string; end: string };
  basis: 'base' | 'delivered';
  currency: string | null;
  status: 'available' | 'insufficient' | 'unavailable';
  reason: string | null;
  series: HistoryPoint[];
  coverage: { days_in_window: number; days_with_data: number; first_date: string | null; last_date: string | null; missing_dates: string[] };
  excluded: { timezone_unknown: number; unknown_shipping_observations: number };
  source: { synthetic: boolean; source_labels: string[] };
}

export interface ObservedState {
  observed_at: string;
  currency: string | null;
  price_minor: number | null;
  shipping_minor: number | null;
  shipping_known: boolean;
  availability: string | null;
  stock_quantity: number | null;
  synthetic: boolean | null;
}

export interface AsOf {
  requested_at: string;
  listings: { listing_id: string; marketplace: string; seller_id: string; observation: ObservedState | null; age_seconds: number | null; changed_fields: string[]; reason: string | null }[];
  excluded: { timezone_unknown: number };
}

export const WINDOWS = [7, 30, 90, 180] as const;

/** End of a UTC calendar day: the explicit cutoff used for "as it was on this date". */
export function endOfDayUtc(day: string): string {
  return `${day}T23:59:59Z`;
}

export function addDays(day: string, n: number): string {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

export function formatAge(seconds: number | null): string {
  if (seconds === null) return '';
  if (seconds < 3600) return `${Math.max(0, Math.floor(seconds / 60))} min old`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h old`;
  return `${Math.floor(seconds / 86400)} d ${Math.floor((seconds % 86400) / 3600)} h old`;
}

export function useHistory(productId: string, cutoff: string | null, window: number, basis: 'base' | 'delivered') {
  const { mode, unavailableReason } = useDataMode();
  return useQuery({
    queryKey: ['history', mode, productId, cutoff, window, basis],
    queryFn: () => apiGet<ProductHistory>(`/api/v1/products/${encodeURIComponent(productId)}/history`, { mode, cutoff: cutoff!, window: String(window), basis }),
    enabled: cutoff !== null && unavailableReason(mode) === null,
    placeholderData: (prev, q) => (q?.queryKey[1] === mode && q?.queryKey[2] === productId ? prev : undefined),
  });
}

export function useAsOf(productId: string, at: string | null) {
  const { mode, unavailableReason } = useDataMode();
  return useQuery({
    queryKey: ['as-of', mode, productId, at],
    queryFn: () => apiGet<AsOf>(`/api/v1/products/${encodeURIComponent(productId)}/as-of`, { mode, at: at! }),
    enabled: at !== null && unavailableReason(mode) === null,
  });
}

export interface EvidenceDaily { date: string; value_minor: number; reference_minor: number | null; observations: number }
export interface ScoreComponent { key: 'savings' | 'percentile' | 'agreement'; weight: number; available: boolean; value: number | null; points: number | null; explanation: string }
export interface ListingEvidence {
  listing_id: string; marketplace: string; seller_id: string; seller_name?: string | null; status: 'available' | 'insufficient' | 'unavailable';
  reason: string | null; currency: string | null; observed_days: number; current_minor: number | null; baseline_minor: number | null;
  savings_percent: number | null; current_observed_at: string | null;
}
export interface PriceEvidence {
  cutoff: string;
  basis: 'base' | 'delivered';
  window: { days: number; start: string; end: string };
  method: { version: string; min_days: number; savings_threshold: number; full_savings: number; reference_increase: number; weights: Record<string, number>; agreement_points: number[] };
  status: 'available' | 'insufficient' | 'unavailable';
  reason: string | null;
  headline: { listing_id: string; marketplace: string; seller_id: string; seller_name?: string | null } | null;
  detector: {
    verdict: 'below_usual' | 'around_usual' | 'above_usual'; label: string; explanation: string; currency: string;
    current_minor: number; baseline_minor: number; savings_percent: number; price_percentile: number;
    advertised_discount_percent: number | null; advertised_support: 'supported' | 'partly_supported' | 'not_supported' | 'no_advertised_discount'; advertised_note: string;
    reference: { current_minor: number | null; baseline_minor: number | null; change_percent: number | null; increased: boolean | null; since: string | null; note: string };
  } | null;
  score: { status: 'available' | 'unavailable'; value: number | null; band: 'strong' | 'moderate' | 'weak' | null; label: string | null; weight_used: number; components: ScoreComponent[]; reason: string | null };
  evidence: {
    listing_id: string; marketplace: string; daily: EvidenceDaily[]; baseline_days: number; first_date: string; last_date: string; missing_dates: string[];
    lowest_minor: number; highest_minor: number;
    current_observation: { observed_at: string; marketplace: string; seller_id: string; currency: string; price_minor: number; shipping_minor: number | null; shipping_known: boolean; value_minor: number; reference_price_minor: number | null; advertised_discount_percent: number | null; coupon_discount_minor: number | null; payment_offer: string | null; availability: string | null; synthetic: boolean | null; source_label: string | null };
  } | null;
  listings: ListingEvidence[];
  excluded: { timezone_unknown: number; unknown_shipping: number; not_purchasable: number; stock_contradiction: number; no_price: number };
  source: { synthetic: boolean; source_labels: string[]; ingestion_runs: string[]; source_files: string[] };
  limitations: string[];
}

export const EVIDENCE_WINDOWS = [30, 90, 180] as const;

export function useEvidence(productId: string, cutoff: string | null, window: number, basis: 'base' | 'delivered') {
  const { mode, unavailableReason } = useDataMode();
  return useQuery({
    queryKey: ['evidence', mode, productId, cutoff, window, basis],
    queryFn: () => apiGet<PriceEvidence>(`/api/v1/products/${encodeURIComponent(productId)}/evidence`, { mode, cutoff: cutoff!, window: String(window), basis }),
    enabled: cutoff !== null && unavailableReason(mode) === null,
    placeholderData: (prev, q) => (q?.queryKey[1] === mode && q?.queryKey[2] === productId ? prev : undefined),
  });
}

export interface BuyingAdvice {
  cutoff: string;
  basis: 'base' | 'delivered';
  window: { days: number; start: string; end: string };
  method: { version: string };
  forecast: {
    used: boolean; note: string; expectation_note?: string | null;
    expectation?: { horizon_days: number; date: string; currency: string; value_minor: number; low_minor: number | null; high_minor: number | null; interval: { level_percent: number; measured_coverage_percent: number | null }; model_label: string; mae_minor: number; baseline_mae_minor: number; backtest_points: number; note: string } | null;
  };
  recommendation: { code: 'buy_now' | 'consider_waiting' | 'insufficient_evidence'; label: string; reason: string };
  confidence: { level: 'low' | 'medium' | 'high' | null; reasons: string[] };
  reasons: string[];
  disagreeing: { key: string; label: string; detail: string }[];
  signals: { key: string; label: string; value: string; supports: 'buy' | 'wait' | 'neutral' }[];
  price: { currency: string; current_minor: number; usual_minor: number; savings_percent: number; price_percentile: number; verdict: string; verdict_label: string; advertised_discount_percent: number | null; advertised_support: string } | null;
  score: PriceEvidence['score'];
  coverage: { observed_days: number; window_days: number; first_date: string; last_date: string; missing_days: number; range_days: number } | null;
  freshness: { observed_at: string; age_hours: number; marketplace: string } | null;
  limitations: string[];
  source: PriceEvidence['source'];
}

export function useAdvice(productId: string, cutoff: string | null, window: number, basis: 'base' | 'delivered') {
  const { mode, unavailableReason } = useDataMode();
  return useQuery({
    queryKey: ['advice', mode, productId, cutoff, window, basis],
    queryFn: () => apiGet<BuyingAdvice>(`/api/v1/products/${encodeURIComponent(productId)}/advice`, { mode, cutoff: cutoff!, window: String(window), basis }),
    enabled: cutoff !== null && unavailableReason(mode) === null,
    placeholderData: (prev, q) => (q?.queryKey[1] === mode && q?.queryKey[2] === productId ? prev : undefined),
  });
}

/** The analysis date shared by Buying advice, Evidence and the Time Machine (`at`), within verified history. */
export function analysisDay(params: URLSearchParams, first: string | null, last: string | null): string | null {
  if (!first || !last) return null;
  const raw = params.get('at');
  return raw && raw >= first && raw <= last ? raw : last;
}

export interface ForecastHorizon {
  days: number;
  status: 'available' | 'insufficient';
  reason: string | null;
  chosen: 'naive' | 'recent_median' | null;
  chosen_label: string | null;
  improvement_percent: number | null;
  note: string | null;
  models: { key: string; label: string; n: number; mae_minor: number | null; mape_percent: number | null }[];
  backtest_first: string | null;
  backtest_last: string | null;
  forecast: { date: string; from_date: string; value_minor: number; low_minor: number | null; high_minor: number | null; interval: { level_percent: number; method?: string; measured_coverage_percent: number | null; measured_on: number; mean_width_percent?: number | null; half_width_percent?: number | null; previous_method?: { name: string; measured_coverage_percent: number | null; mean_width_percent: number | null; measured_on: number } } } | null;
}
type Outcome = { date: string; outcome: 'returned' | 'stayed_low' | 'fell_further' | 'not_completed' | 'no_observation'; value_minor: number | null };
export interface PriceMemory {
  events: { date: string; value_minor: number; before_median_minor: number; drop_percent: number; outcomes: Record<string, Outcome> }[];
  summary: Record<string, { completed: number; returned: number; stayed_low: number; fell_further: number; pending: number }>;
  current_event: PriceMemory['events'][number] | null;
  definition: string;
  note: string;
}
export interface ProductForecast {
  cutoff: string;
  basis: 'base' | 'delivered';
  status: 'available' | 'insufficient' | 'unavailable';
  reason: string | null;
  currency: string | null;
  method: { version: string; min_origins: number; min_improvement_percent: number; interval_level_percent: number; stale_days: number };
  headline: { listing_id: string; marketplace: string; seller_id: string; seller_name?: string | null } | null;
  history: { date: string; value_minor: number }[];
  horizons: ForecastHorizon[];
  memory: PriceMemory | null;
  coverage: { observed_days: number; first_date: string; last_date: string; missing_days: number } | null;
  freshness: { last_observed_date: string; age_days: number; marketplace: string } | null;
  limitations: string[];
  source: PriceEvidence['source'];
}

export function useForecast(productId: string, cutoff: string | null, basis: 'base' | 'delivered') {
  const { mode, unavailableReason } = useDataMode();
  return useQuery({
    queryKey: ['forecast', mode, productId, cutoff, basis],
    queryFn: () => apiGet<ProductForecast>(`/api/v1/products/${encodeURIComponent(productId)}/forecast`, { mode, cutoff: cutoff!, basis }),
    enabled: cutoff !== null && unavailableReason(mode) === null,
    placeholderData: (prev, q) => (q?.queryKey[1] === mode && q?.queryKey[2] === productId ? prev : undefined),
  });
}

export interface SyncListing { listing_id: string; seller_id: string; seller_name?: string | null; marketplace: string; currency: string | null; observed_days: number; last_date: string | null; stale: boolean; changes: { date: string; from_date: string; from_minor: number; to_minor: number; change_percent: number }[] }
export interface SyncPair {
  a: SyncListing; b: SyncListing; common_days: number; matched: number; same_day: number; a_first: number; b_first: number; match_share: number | null;
  matches: { date_a: string; date_b: string; change_a_percent: number; change_b_percent: number; days_apart: number }[];
  status: 'pattern' | 'occasional' | 'independent' | 'no_changes' | 'insufficient' | 'not_comparable'; label: string; summary: string; benign_explanations: string[];
}
export interface SellerSync {
  cutoff: string; window: { days: number; start: string; end: string };
  method: { version: string; change_percent: number; match_days: number; min_matches: number; min_share: number };
  note: string; status: 'available' | 'insufficient'; reason: string | null; pairs: SyncPair[]; source: { synthetic: boolean; source_labels: string[] };
}
export interface AuditObservation { listing_id: string; marketplace: string; observed_at: string | null; source_timestamp: string | null; timestamp_quality: string | null; currency: string | null; price_minor: number | null; reference_price_minor: number | null; advertised_discount_percent: number | null; availability: string | null; stock_quantity: number | null; urgency_message: string | null; date?: string; value_minor?: number; note?: string }
export interface AuditFinding {
  rule_id: string; rule_version: string; title: string; kind: 'observed' | 'calculated' | 'heuristic'; severity: 'low' | 'medium' | 'high';
  confidence: { level: 'low' | 'medium' | 'high'; reason: string }; explanation: string; supporting_observations: AuditObservation[]; benign_explanations: string[]; limitations: string[];
}
export interface ProductAudit {
  cutoff: string; window: { days: number }; version: string; note: string; findings: AuditFinding[];
  rules: { rule_id: string; title: string; version: string; kind: string; required: string; status: 'triggered' | 'not_triggered' | 'disabled'; reason: string }[];
  observations_read: { verified: number; snapshot: number }; source: { synthetic: boolean | null; source_labels: string[] };
}

function useAnalysis<T>(kind: string, productId: string, cutoff: string | null, window: number) {
  const { mode, unavailableReason } = useDataMode();
  return useQuery({
    queryKey: [kind, mode, productId, cutoff, window],
    queryFn: () => apiGet<T>(`/api/v1/products/${encodeURIComponent(productId)}/${kind}`, { mode, cutoff: cutoff!, window: String(window) }),
    enabled: cutoff !== null && unavailableReason(mode) === null,
  });
}
export const useSellerSync = (productId: string, cutoff: string | null, window: number) => useAnalysis<SellerSync>('sync', productId, cutoff, window);
export const useAudit = (productId: string, cutoff: string | null, window: number) => useAnalysis<ProductAudit>('audit', productId, cutoff, window);
