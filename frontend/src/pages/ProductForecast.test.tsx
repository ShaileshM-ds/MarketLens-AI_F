import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProductPage } from './ProductPage';
import { currentLocation, mockApi, renderAt } from '../test/render';
import { detail, reviewsResponse } from '../test/fixtures';

const routes = [{ path: '/products/:productId', element: <ProductPage /> }];
const withHistory = () =>
  detail([], {
    price_history: {
      status: 'available', reason: 'ok', verified_observation_count: 300, timezone_unknown_observation_count: 0,
      first_verified_at: '2026-05-01T10:00:00Z', last_verified_at: '2026-10-31T10:00:00Z',
    },
  });

const horizon = (days: number, chosen: 'naive' | 'recent_median', value: number) => ({
  days, status: 'available', reason: null, chosen, chosen_label: chosen === 'naive' ? 'Last observed price (baseline)' : 'Median of the last 14 observed days',
  improvement_percent: chosen === 'naive' ? -12.5 : 14.43,
  note: chosen === 'naive' ? 'The 14-day median did not beat the last-price baseline by at least 5% (-12.5%), so the baseline is used.' : 'The 14-day median beat the last-price baseline by 14.43%.',
  models: [
    { key: 'naive', label: 'Last observed price (baseline)', n: 60, mae_minor: 6000, mape_percent: 6.1 },
    { key: 'recent_median', label: 'Median of the last 14 observed days', n: 60, mae_minor: chosen === 'naive' ? 6750 : 5134, mape_percent: 5.2 },
  ],
  backtest_first: '2026-07-01', backtest_last: '2026-10-01',
  forecast: { date: `2026-11-${String(days).padStart(2, '0')}`, from_date: '2026-10-31', value_minor: value, low_minor: value - 5000, high_minor: value + 4000, interval: { level_percent: 80, measured_coverage_percent: 72.5, measured_on: 40 } },
});

function forecast(over: Record<string, unknown> = {}) {
  return {
    mode: 'imported', product_id: 'MCL0001', cutoff: '2026-10-31T23:59:59Z', basis: 'base', status: 'available', reason: null,
    predicted_values_are_observations: false, currency: 'INR',
    method: { version: 'forecast-1', models: {}, horizons: [7, 14, 30], min_origins: 20, max_origins: 120, min_improvement_percent: 5, interval_level_percent: 80, lookback_days: 365, stale_days: 7 },
    headline: { listing_id: 'L-A', marketplace: 'Amazon', seller_id: 'S1', seller_name: 'Seller One' },
    history: Array.from({ length: 30 }, (_, i) => ({ date: `2026-10-${String(i + 2).padStart(2, '0')}`, value_minor: 100000 + (i % 3) * 1000 })),
    horizons: [horizon(7, 'naive', 101000), horizon(14, 'naive', 101000), horizon(30, 'recent_median', 99000)],
    memory: {
      events: [{ date: '2026-08-10', value_minor: 85000, before_median_minor: 100000, drop_percent: 15, outcomes: {
        1: { date: '2026-08-11', outcome: 'stayed_low', value_minor: 85000 }, 3: { date: '2026-08-13', outcome: 'stayed_low', value_minor: 85000 },
        7: { date: '2026-08-17', outcome: 'returned', value_minor: 100000 }, 14: { date: '2026-08-24', outcome: 'returned', value_minor: 100000 } } }],
      summary: { 1: { completed: 1, returned: 0, stayed_low: 1, fell_further: 0, pending: 0 }, 3: { completed: 1, returned: 0, stayed_low: 1, fell_further: 0, pending: 0 },
        7: { completed: 1, returned: 1, stayed_low: 0, fell_further: 0, pending: 0 }, 14: { completed: 1, returned: 1, stayed_low: 0, fell_further: 0, pending: 0 } },
      current_event: null, definition: 'A similar event is a daily price at least 10% below the median of the previous 14 observed days.',
      note: 'Counts of what happened after past drops. These are past frequencies, not a probability or a prediction.',
    },
    coverage: { observed_days: 184, first_date: '2026-05-01', last_date: '2026-10-31', missing_days: 0, excluded: {} },
    freshness: { last_observed_date: '2026-10-31', age_days: 0, marketplace: 'Amazon' },
    limitations: ['Forecasts are estimates from past prices of this store listing, not observed prices and not a guarantee.'],
    source: { synthetic: true, source_labels: ['demo'], ingestion_runs: [], source_files: [] },
    ...over,
  };
}

function api(body = withHistory(), fc: () => { status?: number; body: unknown } = () => ({ body: forecast() })) {
  window.localStorage.setItem('ml-data-mode', 'imported');
  return mockApi((url) => {
    if (url.pathname.endsWith('/reviews')) return { body: reviewsResponse() };
    if (url.pathname.endsWith('/audit') || url.pathname.endsWith('/sync')) return { status: 503, body: { detail: 'not mocked here' } };
    if (url.pathname.endsWith('/forecast')) return fc();
    if (['/advice', '/history', '/as-of', '/evidence'].some((s) => url.pathname.endsWith(s))) return { status: 503, body: { detail: 'not mocked here' } };
    if (url.pathname.startsWith('/api/v1/products/')) return { body };
  });
}

describe('Forecast tab', () => {
  it('shows a labelled estimate separate from observed prices, with backtest vs baseline and measured coverage', async () => {
    const m = api();
    const { container } = renderAt('/products/MCL0001?tab=forecast', routes);
    const panel = await screen.findByRole('tabpanel');
    expect(await within(panel).findByText(/estimated 7-day price/i)).toBeInTheDocument();
    expect(m.calls.find((u) => u.pathname.endsWith('/forecast'))!.searchParams.get('cutoff')).toBe('2026-10-31T23:59:59Z');
    expect(within(panel).getAllByText('₹1,010').length).toBeGreaterThan(0);
    expect(within(panel).getByText(/₹960 – ₹1,050/)).toBeInTheDocument();
    expect(within(panel).getByText(/72.5% measured/i)).toBeInTheDocument();
    expect(within(panel).getByText(/nominal 80% range:/i)).toBeInTheDocument();
    expect(within(panel).getByText(/not calibrated/i)).toBeInTheDocument(); // 72.5% measured < 80% nominal
    expect(within(panel).getByText(/baseline is used/i)).toBeInTheDocument();
    const table = within(panel).getByRole('table', { name: /backtest/i });
    expect(within(table).getByText('₹60')).toBeInTheDocument();
    expect(container.querySelector('.fc-chart .fc-observed')).not.toBeNull();
    expect(container.querySelector('.fc-chart .fc-predicted')).not.toBeNull();
    expect(within(panel).getByText(/not observed prices and not a guarantee/i)).toBeInTheDocument();
  });

  it('switches horizons in the URL and shows Future Price Memory as counts, not probabilities', async () => {
    api();
    renderAt('/products/MCL0001?tab=forecast', routes);
    const panel = await screen.findByRole('tabpanel');
    await within(panel).findByText(/estimated 7-day price/i);
    await userEvent.click(within(panel).getByRole('button', { name: '30 days' }));
    expect(currentLocation).toContain('h=30');
    expect(within(panel).getByText(/estimated 30-day price/i)).toBeInTheDocument();
    expect(within(panel).getAllByText('₹990').length).toBeGreaterThan(0);
    expect(within(panel).getAllByText(/1 of 1 completed/i).length).toBeGreaterThan(0);
    expect(within(panel).getByText(/not a probability/i)).toBeInTheDocument();
  });

  it('shows an unavailable state, never a forecast, for insufficient or snapshot-only products', async () => {
    api(withHistory(), () => ({ body: forecast({ status: 'unavailable', reason: 'No forecast: Insufficient historical evidence: 10 distinct observed days.', horizons: [], history: [], memory: null }) }));
    renderAt('/products/MCL0001?tab=forecast', routes);
    const panel = await screen.findByRole('tabpanel');
    expect(await within(panel).findByText(/no forecast: insufficient historical evidence/i)).toBeInTheDocument();
    expect(within(panel).queryByText(/estimated/i)).toBeNull();
  });

  it('does not request a forecast for a snapshot-only product and shows API errors', async () => {
    const m = api(detail());
    renderAt('/products/MCL0001?tab=forecast', routes);
    const panel = await screen.findByRole('tabpanel');
    expect(within(panel).getByText(/no forecast/i)).toBeInTheDocument();
    expect(m.calls.some((u) => u.pathname.endsWith('/forecast'))).toBe(false);
  });

  it('shows an error state', async () => {
    api(withHistory(), () => ({ status: 500, body: { detail: 'boom' } }));
    renderAt('/products/MCL0001?tab=forecast', routes);
    await waitFor(() => expect(screen.getByText(/couldn't load the forecast/i)).toBeInTheDocument());
  });

  it('says the range is unavailable when too few past errors exist, without drawing a band', async () => {
    const f = forecast();
    const hs = (f.horizons as ReturnType<typeof horizon>[]).map((h) => (h.days === 7 && h.forecast ? { ...h, forecast: { ...h.forecast, low_minor: null, high_minor: null } } : h));
    api(withHistory(), () => ({ body: { ...f, horizons: hs } }));
    const { container } = renderAt('/products/MCL0001?tab=forecast', routes);
    const panel = await screen.findByRole('tabpanel');
    expect(await within(panel).findByText(/unavailable \(too few past errors/i)).toBeInTheDocument();
    expect(container.querySelector('.fc-band')).toBeNull();
  });
});
