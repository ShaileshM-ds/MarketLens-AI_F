import { useQuery } from '@tanstack/react-query';
import { apiGet } from './api';

export type RunStatus = 'profiled' | 'mapped' | 'queued' | 'running' | 'completed' | 'failed';

export interface ImportConfig {
  field_map: Record<string, string | null>;
  category_map: Record<string, string>;
  timestamp_policy: 'allow_timezone_unknown' | 'require_utc';
  declare_synthetic: boolean;
}

export interface Counts {
  rows_total: number;
  accepted: number;
  duplicate: number;
  rejected: number;
  warning_rows: number;
  warning_count: number;
  warnings_by_type: Record<string, number>;
  rejected_by_reason: Record<string, number>;
  reviews_new: number;
  reviews_duplicate: number;
  products_new: number;
  listings_new: number;
}

export interface Summary extends Counts {
  created: { products: number; offers: number; observations: number; reviews: number };
}

export interface PreviewRow {
  row_number: number;
  status: 'accepted' | 'duplicate' | 'rejected';
  product_id: string | null;
  listing_id: string | null;
  marketplace: string | null;
  category: string | null;
  source_category: string | null;
  source_timestamp: string | null;
  timestamp_quality: string | null;
  currency: string | null;
  price_minor: number | null;
  reference_price_minor: number | null;
  shipping_minor: number | null;
  shipping_known: boolean | null;
  availability: string | null;
  stock_quantity: number | null;
  synthetic: boolean | null;
  review_rating: number | null;
  reasons: string[];
  warnings: string[];
}

export interface ColumnProfile {
  name: string;
  blank: number;
  distinct: number;
  examples: string[];
}

export interface ImportRun {
  id: string;
  mode: 'imported';
  status: RunStatus;
  file: { filename: string; format: string; size_bytes: number; sha256: string };
  profile?: { format: string; row_count: number; rows_with_problems: number; columns: ColumnProfile[] };
  source_categories?: string[];
  preset?: string | null;
  suggested_config?: ImportConfig;
  config?: ImportConfig | null;
  evaluation?: {
    counts: Counts;
    preview_rows: PreviewRow[];
    rejected_examples: PreviewRow[];
    warning_examples: PreviewRow[];
    evaluated_at: string;
  } | null;
  summary?: Summary | null;
  error?: string | null;
  previous_completed_run_id?: string | null;
  created_by: string;
  created_at: string;
  finished_at?: string;
}

export interface Reference {
  target_fields: { name: string; label: string; required: boolean; help: string }[];
  launch_categories: { slug: string; label: string }[];
  reason_labels: Record<string, string>;
  warning_labels: Record<string, string>;
  timestamp_policies: Record<string, string>;
}

export interface RejectedPage {
  total: number;
  page: number;
  page_size: number;
  items: { row_number: number; reasons: { code: string; message: string }[]; raw: Record<string, string>; raw_source_ref: string }[];
}

export const STATUS_LABELS: Record<RunStatus, string> = {
  profiled: 'Profiled',
  mapped: 'Mapped, not imported',
  queued: 'Waiting for the worker',
  running: 'Importing',
  completed: 'Completed',
  failed: 'Failed',
};

export function useReference() {
  return useQuery({
    queryKey: ['imports', 'reference'],
    queryFn: () => apiGet<Reference>('/api/v1/admin/imports/reference'),
    staleTime: Infinity,
  });
}

export function useRun(runId: string | undefined) {
  return useQuery({
    queryKey: ['imports', 'run', runId],
    queryFn: () => apiGet<ImportRun>(`/api/v1/admin/imports/${runId}`),
    enabled: !!runId,
    refetchInterval: (q) => (q.state.data && ['queued', 'running'].includes(q.state.data.status) ? 1500 : false),
  });
}

export function useRuns() {
  return useQuery({ queryKey: ['imports', 'list'], queryFn: () => apiGet<{ runs: ImportRun[] }>('/api/v1/admin/imports') });
}
