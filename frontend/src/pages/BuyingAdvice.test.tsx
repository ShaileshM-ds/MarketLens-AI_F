import { describe, expect, it } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProductPage } from './ProductPage';
import { currentLocation, mockApi, renderAt } from '../test/render';
import { detail, reviewsResponse } from '../test/fixtures';

const routes = [{ path: '/products/:productId', element: <ProductPage /> }];
const withHistory = () =>
  detail([], {
    price_history: {
      status: 'available', reason: 'Verified UTC observations are available for this product.',
      verified_observation_count: 300, timezone_unknown_observation_count: 0,
      first_verified_at: '2026-05-01T10:00:00Z', last_verified_at: '2026-10-31T10:00:00Z',
    },
  });

function advice(over: Record<string, unknown> = {}) {
  return {
    mode: 'imported', product_id: 'MCL0001', cutoff: '2026-10-31T23:59:59Z', basis: 'base',
    window: { days: 90, start: '2026-08-03T00:00:00Z', end: '2026-10-31T23:59:59Z' },
    method: { version: 'advice-1' },
    forecast: { used: false, note: 'No forecast is used. There is no validated forecasting model yet, so this advice is based on prices observed up to the cutoff, not on predicted future prices.' },
    recommendation: { code: 'buy_now', label: 'Buy now', reason: 'The current price is 20.79% below its usual (median) level over the 90-day window.' },
    confidence: { level: 'high', reasons: ['Fresh, well-covered observations and no disagreeing signals.'] },
    reasons: ['The current price is 20.79% below its usual (median) level over the 90-day window.', 'It is lower than 100% of observed days in the window.'],
    disagreeing: [{ key: 'reference_increase', label: 'Seller reference price raised', detail: 'The reference went up 50%.' }],
    signals: [{ key: 'real_savings', label: 'Real savings vs usual price', value: '20.79%', supports: 'buy' }],
    price: { currency: 'INR', current_minor: 80000, usual_minor: 101000, savings_percent: 20.79, price_percentile: 100, verdict: 'below_usual', verdict_label: 'Genuine price reduction', advertised_discount_percent: 38.46, advertised_support: 'partly_supported' },
    score: { status: 'available', value: 80, band: 'strong', label: 'Strong evidence of a genuine discount', weight_used: 100, components: [], reason: null },
    coverage: { observed_days: 60, window_days: 90, first_date: '2026-09-01', last_date: '2026-10-31', missing_days: 0, range_days: 60 },
    freshness: { observed_at: '2026-10-31T10:00:00Z', age_hours: 13, marketplace: 'Amazon' },
    headline: { listing_id: 'L-A', marketplace: 'Amazon', seller_id: 'S1' },
    evidence_status: 'available',
    limitations: ['This is synthetic demo data.'],
    source: { synthetic: true, source_labels: ['demo'], ingestion_runs: [], source_files: [] },
    ...over,
  };
}

function api(body = withHistory(), adv: () => { status?: number; body: unknown } = () => ({ body: advice() })) {
  window.localStorage.setItem('ml-data-mode', 'imported');
  return mockApi((url) => {
    if (url.pathname.endsWith('/reviews')) return { body: reviewsResponse() };
    if (url.pathname.endsWith('/audit') || url.pathname.endsWith('/sync')) return { status: 503, body: { detail: 'not mocked here' } };
    if (url.pathname.endsWith('/forecast')) return { status: 503, body: { detail: 'not mocked here' } };
    if (url.pathname.endsWith('/advice')) return adv();
    if (url.pathname.endsWith('/history') || url.pathname.endsWith('/as-of') || url.pathname.endsWith('/evidence')) return { status: 503, body: { detail: 'not mocked here' } };
    if (url.pathname.startsWith('/api/v1/products/')) return { body };
  });
}

describe('Buying advice', () => {
  it('explains a recommendation with price, score, coverage, freshness, confidence and no forecast claim', async () => {
    const m = api();
    renderAt('/products/MCL0001', routes);
    const card = await screen.findByRole('region', { name: /buying advice/i });
    expect(await within(card).findByRole('heading', { name: 'Buy now' })).toBeInTheDocument();
    const call = m.calls.find((u) => u.pathname.endsWith('/advice'))!;
    expect(call.searchParams.get('cutoff')).toBe('2026-10-31T23:59:59Z');
    expect(within(card).getByText(/high confidence/i)).toBeInTheDocument();
    expect(within(card).getAllByText('₹800').length).toBeGreaterThan(0);
    expect(within(card).getAllByText('₹1,010').length).toBeGreaterThan(0);
    expect(within(card).getByText('80 / 100')).toBeInTheDocument();
    expect(within(card).getByText(/60 observed days/i)).toBeInTheDocument();
    expect(within(card).getByText(/13 h old/i)).toBeInTheDocument();
    expect(within(card).getByText(/seller reference price raised/i)).toBeInTheDocument();
    expect(within(card).getByText(/not on predicted future prices/i)).toBeInTheDocument();
    expect(within(card).queryByText(/synthetic data/i)).toBeNull();
  });

  it('links to the Evidence and Timeline views', async () => {
    api();
    renderAt('/products/MCL0001', routes);
    const card = await screen.findByRole('region', { name: /buying advice/i });
    await within(card).findByRole('heading', { name: 'Buy now' });
    await userEvent.click(within(card).getByRole('button', { name: /see the evidence/i }));
    expect(currentLocation).toContain('tab=evidence');
    await userEvent.click(within(card).getByRole('button', { name: /latest observation in the time machine/i }));
    expect(currentLocation).toContain('tab=timeline');
    expect(currentLocation).toContain('at=2026-10-31');
  });

  it('shows insufficient evidence without a confidence level', async () => {
    api(withHistory(), () => ({ body: advice({
      recommendation: { code: 'insufficient_evidence', label: 'Insufficient evidence', reason: 'Insufficient evidence: the latest verified observation is 12 days before the cutoff, so it is stale (more than 7 days).' },
      confidence: { level: null, reasons: [] }, price: null, coverage: null, freshness: null, disagreeing: [], signals: [],
      score: { status: 'unavailable', value: null, band: null, label: null, weight_used: 0, components: [], reason: 'x' },
    }) }));
    renderAt('/products/MCL0001', routes);
    const card = await screen.findByRole('region', { name: /buying advice/i });
    expect(await within(card).findByRole('heading', { name: 'Insufficient evidence' })).toBeInTheDocument();
    expect(within(card).getAllByText(/stale/i).length).toBeGreaterThan(0);
    expect(within(card).queryByText(/confidence/i)).toBeNull();
  });

  it('never requests advice for a snapshot-only product', async () => {
    const m = api(detail());
    renderAt('/products/MCL0001', routes);
    const card = await screen.findByRole('region', { name: /buying advice/i });
    expect(within(card).getByRole('heading', { name: 'Insufficient evidence' })).toBeInTheDocument();
    expect(m.calls.some((u) => u.pathname.endsWith('/advice'))).toBe(false);
  });

  it('shows an error state', async () => {
    api(withHistory(), () => ({ status: 500, body: { detail: 'boom' } }));
    renderAt('/products/MCL0001', routes);
    expect(await screen.findByText(/couldn't load buying advice/i)).toBeInTheDocument();
  });
  it('shows a validated forecast expectation separately, without changing the recommendation', async () => {
    api(withHistory(), () => ({ body: advice({
      recommendation: { code: 'consider_waiting', label: 'Consider waiting', reason: 'No genuine discount: an ordinary price, not a bargain.' },
      confidence: { level: 'low', reasons: ['Only a usual price.'] },
      forecast: { used: false, note: 'The recommendation is based on prices observed up to the cutoff, not on predicted future prices.', expectation_note: null,
        expectation: { horizon_days: 7, date: '2026-11-07', currency: 'INR', value_minor: 95000, low_minor: 90000, high_minor: 99000, interval: { level_percent: 80, measured_coverage_percent: 76.5 },
          model_label: 'Median of the last 14 observed days', mae_minor: 2000, baseline_mae_minor: 3000, backtest_points: 60, note: 'An estimate from past prices. It is not a guarantee and does not change the recommendation.' } },
    }) }));
    renderAt('/products/MCL0001', routes);
    const card = await screen.findByRole('region', { name: /buying advice/i });
    expect(await within(card).findByRole('heading', { name: 'Consider waiting' })).toBeInTheDocument();
    const fc = within(card).getByRole('region', { name: /forecast-based expectation/i });
    expect(within(fc).getByText('₹950')).toBeInTheDocument();
    expect(within(fc).getByText(/₹20 vs ₹30/)).toBeInTheDocument();
    expect(within(fc).getByText(/not a guarantee/i)).toBeInTheDocument();
  });
});
