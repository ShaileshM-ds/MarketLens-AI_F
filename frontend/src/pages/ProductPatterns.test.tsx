import { describe, expect, it } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProductPage } from './ProductPage';
import { mockApi, renderAt } from '../test/render';
import { detail, reviewsResponse } from '../test/fixtures';

const routes = [{ path: '/products/:productId', element: <ProductPage /> }];
const withHistory = () =>
  detail([], {
    price_history: {
      status: 'available', reason: 'ok', verified_observation_count: 300, timezone_unknown_observation_count: 0,
      first_verified_at: '2026-05-01T10:00:00Z', last_verified_at: '2026-10-31T10:00:00Z',
    },
  });

const listing = (id: string, market: string, seller: string, changes: { date: string; change_percent: number }[]) => ({
  listing_id: id, seller_id: seller, seller_name: `${seller} name`, marketplace: market, currency: 'INR', mixed_currency: false,
  observed_days: 90, last_date: '2026-10-31', stale: false,
  changes: changes.map((c) => ({ ...c, from_date: c.date, from_minor: 100000, to_minor: 110000 })),
});

const sync = {
  mode: 'imported', product_id: 'MCL0001', cutoff: '2026-10-31T23:59:59Z', window: { days: 90, start: '2026-08-03T00:00:00Z', end: '2026-10-31T23:59:59Z' },
  method: { version: 'sync-1', change_percent: 3, match_days: 1, min_matches: 3, min_share: 0.6 },
  note: 'Similar or simultaneous price changes are patterns worth investigating, not proof of collusion.',
  status: 'available', reason: null, source: { synthetic: true, source_labels: ['demo'] },
  pairs: [
    {
      a: listing('L-A', 'Amazon', 'S1', [{ date: '2026-09-01', change_percent: -15 }, { date: '2026-09-08', change_percent: 17.6 }, { date: '2026-10-01', change_percent: -15 }]),
      b: listing('L-F', 'Flipkart', 'S2', [{ date: '2026-09-01', change_percent: -15 }, { date: '2026-09-08', change_percent: 17.6 }, { date: '2026-10-02', change_percent: -15 }]),
      common_days: 90, matched: 3, same_day: 2, a_first: 1, b_first: 0, match_share: 1,
      matches: [
        { date_a: '2026-09-01', date_b: '2026-09-01', change_a_percent: -15, change_b_percent: -15, days_apart: 0 },
        { date_a: '2026-09-08', date_b: '2026-09-08', change_a_percent: 17.6, change_b_percent: 17.6, days_apart: 0 },
        { date_a: '2026-10-01', date_b: '2026-10-02', change_a_percent: -15, change_b_percent: -15, days_apart: 1 },
      ],
      status: 'pattern', label: 'Synchronized changes worth investigating',
      summary: '3 of 3 price changes moved in the same direction within 1 day. This is a pattern worth investigating, not proof of coordination.',
      benign_explanations: ['A store-wide or festival sale that both listings joined.'],
    },
    {
      a: listing('L-A', 'Amazon', 'S1', []), b: listing('L-M', 'Myntra', 'S3', []), common_days: 5, matched: 0, same_day: 0, a_first: 0, b_first: 0,
      match_share: null, matches: [], status: 'insufficient', label: 'Insufficient evidence', summary: 'Insufficient evidence: only 5 days observed for both listings.', benign_explanations: [],
    },
  ],
};

const obs = { listing_id: 'L-A', marketplace: 'Amazon', seller_id: 'S1', observed_at: '2026-10-31T10:00:00Z', source_timestamp: '2026-10-31T10:00:00Z', timestamp_quality: 'utc', currency: 'INR', price_minor: 100000, reference_price_minor: 195000, advertised_discount_percent: 48.72, availability: 'In Stock', stock_quantity: 40, urgency_message: 'Only a few left!', flags: [], synthetic: true, source_label: 'demo' };
const audit = (findings: unknown[], rules?: unknown[]) => ({
  mode: 'imported', product_id: 'MCL0001', cutoff: '2026-10-31T23:59:59Z', window: { days: 90 }, version: 'audit-1',
  note: 'These are evidence-based flags for review, not a legal finding or an accusation against any seller.',
  findings, observations_read: { verified: 90, snapshot: 0 }, source: { synthetic: true, source_labels: ['demo'] },
  rules: rules ?? [
    { rule_id: 'reference_inflation', title: 'Reference price raised', version: 'audit-1/1.0', kind: 'calculated', required: 'x', status: 'triggered', reason: 'Reference 50% above.' },
    { rule_id: 'discount_arithmetic', title: 'Displayed discount doesn’t match displayed prices', version: 'audit-1/1.0', kind: 'observed', required: 'x', status: 'disabled', reason: 'Disabled: needs price, reference price and advertised discount on the same observation.' },
  ],
});
const refFinding = {
  rule_id: 'reference_inflation', rule_version: 'audit-1/1.0', title: 'Reference price raised', kind: 'calculated', severity: 'high',
  confidence: { level: 'high', reason: 'Baseline of 89 observed days on Amazon.' },
  explanation: 'The seller’s reference price is 50% above its usual level in this window, since 2026-10-02.',
  supporting_observations: [obs], benign_explanations: ['The manufacturer may have raised its list price (MRP).'], limitations: ['Based on the 90-day window.'],
};

function api(body = withHistory(), opts: { audit?: unknown; sync?: unknown } = {}) {
  window.localStorage.setItem('ml-data-mode', 'imported');
  return mockApi((url) => {
    if (url.pathname.endsWith('/reviews')) return { body: reviewsResponse() };
    if (url.pathname.endsWith('/audit')) return { body: opts.audit ?? audit([refFinding]) };
    if (url.pathname.endsWith('/sync')) return { body: opts.sync ?? sync };
    if (['/advice', '/history', '/as-of', '/evidence', '/forecast'].some((s) => url.pathname.endsWith(s))) return { status: 503, body: { detail: 'not mocked here' } };
    if (url.pathname.startsWith('/api/v1/products/')) return { body };
  });
}

describe('Seller synchronization and pricing audit', () => {
  it('shows audit findings with kind, severity, confidence, evidence, benign explanations and disabled rules', async () => {
    const m = api();
    renderAt('/products/MCL0001', routes);
    const sec = await screen.findByRole('region', { name: /pricing practices audit/i });
    expect(await within(sec).findByRole('heading', { name: 'Reference price raised' })).toBeInTheDocument();
    expect(m.calls.find((u) => u.pathname.endsWith('/audit'))!.searchParams.get('cutoff')).toBe('2026-10-31T23:59:59Z');
    expect(within(sec).getByText('Calculated finding')).toBeInTheDocument();
    expect(within(sec).getByText('High severity')).toBeInTheDocument();
    expect(within(sec).getByText(/high confidence/i)).toBeInTheDocument();
    expect(within(sec).getByText(/manufacturer may have raised/i)).toBeInTheDocument();
    expect(within(sec).getByText(/not a legal finding/i)).toBeInTheDocument();
    await userEvent.click(within(sec).getByText(/supporting observations \(1\)/i));
    expect(within(sec).getByText('₹1,950')).toBeInTheDocument();
    expect(within(sec).getByText(/disabled: needs price/i)).toBeInTheDocument();
  });

  it('shows a synchronization pattern as worth investigating, never proof, with an aligned timeline', async () => {
    api();
    const { container: c2 } = renderAt('/products/MCL0001', routes);
    const sec = await screen.findByRole('region', { name: /seller synchronization/i });
    expect(await within(sec).findByText('Synchronized changes worth investigating')).toBeInTheDocument();
    expect(within(sec).getAllByText(/not proof/i).length).toBeGreaterThan(0);
    expect(within(sec).getByText(/store-wide or festival sale/i)).toBeInTheDocument();
    expect(c2.querySelectorAll('.sync-timeline .sync-mark--matched').length).toBe(6);
    expect(within(sec).getByRole('table', { name: /matched changes/i })).toBeInTheDocument();
    expect(within(sec).getByText(/only 5 days observed/i)).toBeInTheDocument();
  });

  it('audits a snapshot-only product with an explicit cutoff but never requests synchronization', async () => {
    const stock = { ...refFinding, rule_id: 'stock_contradiction', title: 'Availability and stock quantity disagree', kind: 'observed', severity: 'low',
      confidence: { level: 'high', reason: 'Recorded directly.' }, explanation: '1 observation reports Out of Stock with stock 5.',
      supporting_observations: [{ ...obs, observed_at: null, timestamp_quality: 'timezone_unknown', source_timestamp: '2026-11-05T09:00:00' }] };
    const m = api(detail(), { audit: audit([stock]) });
    renderAt('/products/MCL0001', routes);
    const sec = await screen.findByRole('region', { name: /pricing practices audit/i });
    expect(await within(sec).findByText('Observed fact')).toBeInTheDocument();
    expect(m.calls.find((u) => u.pathname.endsWith('/audit'))!.searchParams.get('cutoff')).toMatch(/T23:59:59Z$/);
    expect(m.calls.some((u) => u.pathname.endsWith('/sync'))).toBe(false);
    const syncSec = screen.getByRole('region', { name: /seller synchronization/i });
    expect(within(syncSec).getByText(/insufficient evidence/i)).toBeInTheDocument();
  });

  it('shows no-findings and error states', async () => {
    window.localStorage.setItem('ml-data-mode', 'imported');
    mockApi((url) => {
      if (url.pathname.endsWith('/reviews')) return { body: reviewsResponse() };
      if (url.pathname.endsWith('/audit')) return { body: audit([]) };
      if (url.pathname.endsWith('/sync')) return { status: 500, body: { detail: 'boom' } };
      if (['/advice', '/history', '/as-of', '/evidence', '/forecast'].some((s) => url.pathname.endsWith(s))) return { status: 503, body: { detail: 'x' } };
      if (url.pathname.startsWith('/api/v1/products/')) return { body: withHistory() };
    });
    renderAt('/products/MCL0001', routes);
    expect(await screen.findByText(/no audit rule was triggered/i)).toBeInTheDocument();
    expect(await screen.findByText(/couldn't load seller synchronization/i)).toBeInTheDocument();
  });
});
