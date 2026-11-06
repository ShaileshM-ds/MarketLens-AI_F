import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiSend } from './api';
import { useMe } from './auth';
import { useDataMode } from './dataMode';
import type { CompareProduct } from './products';

export interface WatchItem {
  product_id: string;
  notes: string | null;
  horizon_date: string | null;
  added_at: string;
  updated_at: string;
  product: CompareProduct | null;
  alerts: { active: number; paused: number };
}

export interface AlertRule {
  id: string;
  product_id: string;
  product_name: string | null;
  type: string;
  marketplace: string | null;
  basis: 'base' | 'delivered' | null;
  target_price_minor: number | null;
  currency: string | null;
  min_score?: number | null;
  cooldown_hours: number;
  enabled: boolean;
  armed: boolean;
  status: 'active' | 'archived';
  created_at: string;
  updated_at: string;
  active_since: string;
  last_evaluated: { observation_id?: string; run_id?: string; outcome: string; reason: string | null; at: string; cutoff?: string } | null;
  last_triggered_at: string | null;
  last_notification_id: string | null;
  current_context?: { qualifying_now: { marketplace: string; listing_id: string; value_minor: number }[]; note: string };
}

export interface AppNotification {
  id: string;
  title: string;
  message: string;
  rule_id: string;
  product_id: string;
  product_name: string | null;
  marketplace: string | null;
  listing_id: string | null;
  type?: string;
  evidence?: Record<string, unknown> | null;
  basis: 'base' | 'delivered' | null;
  observed_minor: number | null;
  target_minor: number | null;
  currency: string | null;
  observation_id: string | null;
  ingestion_run_id: string | null;
  source_timestamp: string | null;
  timestamp_quality: string | null;
  observed_at: string | null;
  synthetic: boolean | null;
  source_label: string | null;
  created_at: string;
  read: boolean;
  dismissed: boolean;
  email: { status: string; note: string } | null;
}

export interface NotificationPage {
  total: number;
  unread: number;
  page: number;
  page_size: number;
  items: AppNotification[];
}

/** Signed-in and the workspace is usable: the precondition for every personal query. */
function useEnabled() {
  const me = useMe();
  const { mode, unavailableReason } = useDataMode();
  return { mode, enabled: !!me.data && unavailableReason(mode) === null };
}

export function useWatchlist() {
  const { mode, enabled } = useEnabled();
  return useQuery({
    queryKey: ['watchlist', mode],
    queryFn: () => apiGet<{ items: WatchItem[] }>('/api/v1/watchlist', { mode }),
    enabled,
  });
}

export function useRules() {
  const { mode, enabled } = useEnabled();
  return useQuery({
    queryKey: ['alerts', mode],
    queryFn: () => apiGet<{ rules: AlertRule[] }>('/api/v1/alerts', { mode }),
    enabled,
  });
}

export function useNotifications(status: 'active' | 'unread' | 'all', page: number) {
  const { mode, enabled } = useEnabled();
  return useQuery({
    queryKey: ['notifications', mode, status, page],
    queryFn: () => apiGet<NotificationPage>('/api/v1/notifications', { mode, status, page: String(page), page_size: '20' }),
    enabled,
  });
}

export function useUnreadCount() {
  const { mode, enabled } = useEnabled();
  return useQuery({
    queryKey: ['notifications', mode, 'unread-count'],
    queryFn: () => apiGet<{ unread: number }>('/api/v1/notifications/unread-count', { mode }),
    enabled,
    refetchInterval: 60_000,
  });
}

/** One mutation helper: every change refreshes watchlist, alerts and notifications for this workspace. */
export function usePersonalMutation<TVars, TResult = unknown>(fn: (vars: TVars, mode: string) => Promise<TResult>) {
  const qc = useQueryClient();
  const { mode } = useDataMode();
  return useMutation({
    mutationFn: (vars: TVars) => fn(vars, mode),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['watchlist', mode] });
      qc.invalidateQueries({ queryKey: ['alerts', mode] });
      qc.invalidateQueries({ queryKey: ['notifications', mode] });
    },
  });
}

const q = (mode: string) => `?mode=${encodeURIComponent(mode)}`;

export const watchApi = {
  add: (productId: string, mode: string) => apiSend<WatchItem>('PUT', `/api/v1/watchlist/${encodeURIComponent(productId)}${q(mode)}`, {}),
  remove: (productId: string, mode: string) => apiSend<void>('DELETE', `/api/v1/watchlist/${encodeURIComponent(productId)}${q(mode)}`),
  createRule: (body: Record<string, unknown>, mode: string) => apiSend<AlertRule>('POST', `/api/v1/alerts${q(mode)}`, body),
  patchRule: (id: string, body: Record<string, unknown>, mode: string) => apiSend<AlertRule>('PATCH', `/api/v1/alerts/${id}${q(mode)}`, body),
  deleteRule: (id: string, mode: string) => apiSend<void>('DELETE', `/api/v1/alerts/${id}${q(mode)}`),
  read: (id: string, mode: string) => apiSend<AppNotification>('POST', `/api/v1/notifications/${id}/read${q(mode)}`),
  dismiss: (id: string, mode: string) => apiSend<AppNotification>('POST', `/api/v1/notifications/${id}/dismiss${q(mode)}`),
  readAll: (mode: string) => apiSend<{ marked_read: number }>('POST', `/api/v1/notifications/read-all${q(mode)}`),
};

/** The SCOPE alert types (mirrors the API's /alerts/types). Only below_target takes a target price. */
export const ALERT_TYPES = [
  { type: 'below_target', label: 'Below target price', store: true, basis: true, description: 'A newly imported observation at or below your target price.' },
  { type: 'new_low', label: 'New lowest verified price', store: true, basis: true, description: 'A new verified observation lower than every verified price of this product in the previous 90 days (needs 14+ earlier observed days).' },
  { type: 'restock', label: 'Back in stock (reported)', store: true, basis: false, description: 'A listing reported out of stock in its previous verified observation is reported in stock again.' },
  { type: 'meaningful_discount', label: 'Meaningful discount', store: false, basis: true, description: 'The Real Price Detector finds a genuine reduction and the Genuine Discount Score reaches your minimum (needs 14+ observed days).' },
  { type: 'advice_change', label: 'Buying advice change', store: false, basis: false, description: 'Buying advice changes between two valid evaluations under the same rules version.' },
  { type: 'seller_switch', label: 'Lowest-price seller change', store: false, basis: false, description: 'A different seller ID has the lowest current verified price among in-stock listings.' },
  { type: 'audit_finding', label: 'New pricing audit finding', store: false, basis: false, description: "A pricing-audit rule triggers that wasn't triggered at the previous evaluation. Flags for review, not accusations." },
  { type: 'synchronization_anomaly', label: 'New synchronized price pattern', store: false, basis: false, description: 'A pair of store listings newly shows synchronized price changes. A pattern worth investigating, not proof.' },
] as const;
export const alertTypeLabel = (t: string) => ALERT_TYPES.find((x) => x.type === t)?.label ?? t;
