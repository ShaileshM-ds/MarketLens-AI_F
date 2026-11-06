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
      status: 'available', reason: 'Verified UTC observations are available for this product.',
      verified_observation_count: 300, timezone_unknown_observation_count: 0,
      first_verified_at: '2026-05-01T10:00:00Z', last_verified_at: '2026-10-31T10:00:00Z',
    },
  });

function history(window: number) {
  const series = [
    { date: '2026-10-28', value_minor: 140000, marketplaces: ['Amazon'] },
    { date: '2026-10-29', value_minor: 139000, marketplaces: ['Flipkart'] },
    // 30 Oct missing: a gap
    { date: '2026-10-31', value_minor: 141000, marketplaces: ['Amazon'] },
  ];
  return {
    mode: 'imported', product_id: 'MCL0001', cutoff: '2026-10-31T23:59:59Z', window: { days: window, start: '', end: '' }, basis: 'base',
    marketplace: null, currency: 'INR', status: 'available', reason: null, series, listings: [],
    coverage: { days_in_window: window, days_with_data: 3, first_date: '2026-10-28', last_date: '2026-10-31', missing_dates: ['2026-10-30'] },
    excluded: { timezone_unknown: 3, unknown_shipping_observations: 0 }, source: { synthetic: true, source_labels: ['MarketLens demo generator (seed 1)'] },
  };
}

function asOf(at: string) {
  const day = at.slice(0, 10);
  const price = day === '2026-10-31' ? 141000 : 139000;
  return {
    mode: 'imported', product_id: 'MCL0001', requested_at: at, excluded: { timezone_unknown: 0 },
    listings: [{
      listing_id: 'L-A', marketplace: 'Amazon', seller_id: 'S1', seller_name: 'Seller',
      observation: { observed_at: `${day}T10:00:00Z`, source_timestamp: `${day}T10:00:00Z`, currency: 'INR', price_minor: price, reference_price_minor: 160000, shipping_minor: 0, shipping_known: true, delivered_price_minor: price, advertised_discount_percent: 10, coupon_discount_minor: 0, payment_offer: null, availability: 'In Stock', stock_quantity: 10, urgency_message: null, seller_rating: 4.2, product_rating: 4.1, flags: [], synthetic: true, source_label: 'x' },
      previous: null, age_seconds: 50399, changed_fields: [], reason: null,
    }, {
      listing_id: 'L-M', marketplace: 'Myntra', seller_id: 'S3', seller_name: 'Seller 3', observation: null, previous: null, age_seconds: null, changed_fields: [],
      reason: 'No verified observation at or before this time.',
    }],
  };
}

function api(body = withHistory()) {
  window.localStorage.setItem('ml-data-mode', 'imported');
  return mockApi((url) => {
    if (url.pathname.endsWith('/reviews')) return { body: reviewsResponse() };
    if (url.pathname.endsWith('/audit') || url.pathname.endsWith('/sync')) return { status: 503, body: { detail: 'not mocked here' } };
    if (url.pathname.endsWith('/forecast')) return { status: 503, body: { detail: 'not mocked here' } };
    if (url.pathname.endsWith('/advice')) return { status: 503, body: { detail: 'not mocked here' } };
    if (url.pathname.endsWith('/history')) return { body: history(Number(url.searchParams.get('window'))) };
    if (url.pathname.endsWith('/as-of')) return { body: asOf(url.searchParams.get('at')!) };
    if (url.pathname.endsWith('/evidence')) return { status: 503, body: { detail: 'not mocked here' } };
    if (url.pathname.startsWith('/api/v1/products/')) return { body };
  });
}

describe('Product history', () => {
  it('restores the Timeline, Evidence and Forecast tabs with the tab kept in the URL', async () => {
    api();
    renderAt('/products/MCL0001', routes);
    const tabs = await screen.findByRole('tablist', { name: /product analysis/i });
    expect(within(tabs).getAllByRole('tab').map((t) => t.textContent)).toEqual(['Timeline', 'Evidence', 'Forecast']);
    expect(within(tabs).getByRole('tab', { name: 'Timeline' })).toHaveAttribute('aria-selected', 'true');
    await userEvent.click(within(tabs).getByRole('tab', { name: 'Evidence' }));
    expect(currentLocation).toContain('tab=evidence');
    expect(screen.getByRole('tabpanel')).toHaveTextContent(/evidence as of/i);
    await userEvent.click(within(tabs).getByRole('tab', { name: 'Forecast' }));
    expect(screen.getByRole('tabpanel')).toHaveTextContent(/forecast/i);
  });

  it('shows unavailable states and never draws a chart without verified history', async () => {
    const m = api(detail());
    const { container } = renderAt('/products/MCL0001', routes);
    expect(await screen.findByText(/verified historical price data is not available/i)).toBeInTheDocument();
    expect(container.querySelector('svg.history-chart')).toBeNull();
    expect(screen.getByRole('tabpanel')).toHaveTextContent(/needs verified utc observations/i);
    expect(m.calls.some((u) => u.pathname.endsWith('/history') || u.pathname.endsWith('/as-of'))).toBe(false);
  });

  it('charts verified observations up to an explicit cutoff, with presets, gaps and a table', async () => {
    const m = api();
    const { container } = renderAt('/products/MCL0001', routes);
    const chart = await screen.findByRole('img', { name: /price history/i });
    const first = m.calls.find((u) => u.pathname.endsWith('/history'))!;
    expect(first.searchParams.get('cutoff')).toBe('2026-10-31T23:59:59Z');
    expect(first.searchParams.get('window')).toBe('30');
    expect(container.querySelectorAll('svg.history-chart path.history-line')).toHaveLength(2); // gap on 30 Oct splits the line
    expect(screen.getByText(/1 missing day/i)).toBeInTheDocument();
    expect(chart).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '90D' }));
    await waitFor(() => expect(m.calls.filter((u) => u.pathname.endsWith('/history')).at(-1)!.searchParams.get('window')).toBe('90'));
    expect(currentLocation).toContain('range=90');
    await userEvent.click(screen.getByRole('button', { name: /price history table view/i }));
    const table = screen.getByRole('table', { name: /price history data/i });
    expect(within(table).getByText('₹1,390')).toBeInTheDocument();
    expect(screen.getByText(/3 snapshot observations without a timezone are excluded/i)).toBeInTheDocument();
  });

  it('Time Machine uses an explicit cutoff, never shows later data, and highlights changes', async () => {
    const m = api();
    renderAt('/products/MCL0001?tab=timeline', routes);
    const panel = await screen.findByRole('tabpanel');
    await within(panel).findByText('₹1,410');
    const asOfCalls = () => m.calls.filter((u) => u.pathname.endsWith('/as-of')).map((u) => u.searchParams.get('at'));
    expect(asOfCalls()).toContain('2026-10-31T23:59:59Z');
    expect(within(panel).getByText(/31 Oct 2026, 10:00 UTC/)).toBeInTheDocument();
    expect(within(panel).getAllByText(/13 h old/).length).toBeGreaterThan(0);
    expect(within(panel).getAllByText(/no verified observation at or before this time/i).length).toBeGreaterThan(0);
    expect(within(panel).getByRole('button', { name: /next day/i })).toBeDisabled(); // can't step past the latest observation
    // 31 Oct compared with the day before: the price changed, marked in words, not only colour.
    expect(await within(panel).findAllByText('Changed')).not.toHaveLength(0);
    await userEvent.click(within(panel).getByRole('button', { name: /previous day/i }));
    await waitFor(() => expect(asOfCalls()).toContain('2026-10-30T23:59:59Z'));
    expect(currentLocation).toContain('at=2026-10-30');
  });
});
