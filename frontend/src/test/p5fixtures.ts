import { compareProduct } from './fixtures';

export const me = { username: 'alice', role: 'consumer' };

export function watchItem(id = 'MCL0001', name = "Nike Men's Black Crew-Neck T-Shirt", alerts = { active: 1, paused: 0 }) {
  return {
    product_id: id,
    notes: 'Gift idea',
    horizon_date: null,
    added_at: '2026-11-06T08:00:00+00:00',
    updated_at: '2026-11-06T08:00:00+00:00',
    product: compareProduct(id, name),
    alerts,
  };
}

export function rule(overrides: Record<string, unknown> = {}) {
  return {
    id: 'a'.repeat(32),
    product_id: 'MCL0001',
    product_name: "Nike Men's Black Crew-Neck T-Shirt",
    type: 'below_target',
    marketplace: null,
    basis: 'base',
    target_price_minor: 140000,
    currency: 'INR',
    cooldown_hours: 24,
    enabled: true,
    armed: true,
    status: 'active',
    created_at: '2026-11-06T08:00:00+00:00',
    updated_at: '2026-11-06T08:00:00+00:00',
    active_since: '2026-11-06T08:00:00+00:00',
    last_evaluated: null,
    last_triggered_at: null,
    last_notification_id: null,
    ...overrides,
  };
}

export function notification(overrides: Record<string, unknown> = {}) {
  return {
    id: 'b'.repeat(24),
    title: 'New qualifying observation detected',
    message: 'A newly imported observation from Flipkart has a base price at or below your target.',
    rule_id: 'a'.repeat(32),
    product_id: 'MCL0001',
    product_name: "Nike Men's Black Crew-Neck T-Shirt",
    marketplace: 'Flipkart',
    listing_id: 'L-F',
    basis: 'base',
    observed_minor: 130000,
    target_minor: 135000,
    currency: 'INR',
    observation_id: 'obs1|L-F|utc:2026-11-05T09:00:00.000000Z',
    ingestion_run_id: 'c'.repeat(32),
    source_timestamp: '2026-11-05T09:00:00Z',
    timestamp_quality: 'utc',
    observed_at: '2026-11-05T09:00:00+00:00',
    synthetic: true,
    source_label: 'Generated for project demonstration',
    mode: 'imported',
    created_at: '2026-11-06T09:00:00+00:00',
    read: false,
    read_at: null,
    dismissed: false,
    email: { status: 'not_sent', note: 'Email delivery is not configured. This is a local outbox record; nothing was sent.' },
    ...overrides,
  };
}

export function notificationsResponse(items: unknown[] = [notification()], unread = 1) {
  return { mode: 'imported', total: items.length, unread, page: 1, page_size: 20, items };
}
