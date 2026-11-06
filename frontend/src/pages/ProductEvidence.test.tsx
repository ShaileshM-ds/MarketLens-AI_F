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

const daily = Array.from({ length: 20 }, (_, i) => ({
  date: `2026-10-${String(i + 11).padStart(2, '0')}`, value_minor: 101000, reference_minor: 130000, observations: 1,
}));

function evidence(over: Record<string, unknown> = {}) {
  return {
    mode: 'imported', product_id: 'MCL0001', cutoff: '2026-10-31T23:59:59Z', basis: 'base',
    window: { days: 90, start: '2026-08-03T00:00:00Z', end: '2026-10-31T23:59:59Z' },
    method: { version: 'evidence-1', min_days: 14, savings_threshold: 5, full_savings: 25, reference_increase: 20, weights: { savings: 60, percentile: 25, agreement: 15 }, agreement_points: [5, 25] },
    status: 'available', reason: null,
    headline: { listing_id: 'L-A', marketplace: 'Amazon', seller_id: 'S1', seller_name: 'Seller One' },
    detector: {
      verdict: 'below_usual', label: 'Genuine price reduction', explanation: 'The current price is 20.79% below its usual (median) level over the window.',
      currency: 'INR', current_minor: 80000, baseline_minor: 101000, savings_percent: 20.79, price_percentile: 100,
      advertised_discount_percent: 38.46, advertised_support: 'partly_supported', advertised_note: 'The price did fall (20.79%), but by less than the advertised 38.46%.',
      reference: { current_minor: 130000, baseline_minor: 130000, change_percent: 0, increased: false, since: null, note: 'The seller’s reference price is close to its usual level in this window.' },
    },
    score: {
      status: 'available', value: 68, band: 'moderate', label: 'Some evidence of a genuine discount', weight_used: 100, reason: null,
      components: [
        { key: 'savings', weight: 60, available: true, value: 83.16, points: 49.9, explanation: 'Real savings of 20.79%.' },
        { key: 'percentile', weight: 25, available: true, value: 100, points: 25, explanation: 'Lower than 100% of observed days.' },
        { key: 'agreement', weight: 15, available: true, value: 0, points: 0, explanation: 'Advertised 38.46% vs real 20.79%.' },
      ],
    },
    evidence: {
      listing_id: 'L-A', marketplace: 'Amazon', daily, baseline_days: 20, first_date: '2026-10-11', last_date: '2026-10-30', missing_dates: ['2026-10-20'],
      lowest_minor: 101000, highest_minor: 101000,
      current_observation: { observed_at: '2026-10-31T10:00:00Z', marketplace: 'Amazon', seller_id: 'S1', currency: 'INR', price_minor: 80000, shipping_minor: 4000, shipping_known: true, value_minor: 80000, reference_price_minor: 130000, advertised_discount_percent: 38.46, coupon_discount_minor: 10000, payment_offer: null, availability: 'In Stock', synthetic: true, source_label: 'demo' },
    },
    listings: [
      { listing_id: 'L-A', marketplace: 'Amazon', seller_id: 'S1', seller_name: 'Seller One', status: 'available', reason: null, currency: 'INR', observed_days: 21, current_minor: 80000, baseline_minor: 101000, savings_percent: 20.79, current_observed_at: '2026-10-31T10:00:00Z' },
      { listing_id: 'L-F', marketplace: 'Flipkart', seller_id: 'S2', seller_name: 'Seller Two', status: 'unavailable', reason: 'Its latest observation is reported out of stock or without availability, so it isn’t a current purchasable price.', currency: null, observed_days: 0, current_minor: null, baseline_minor: null, savings_percent: null, current_observed_at: '2026-10-31T10:00:00Z' },
    ],
    excluded: { timezone_unknown: 3, unknown_shipping: 0, not_purchasable: 1, stock_contradiction: 0, no_price: 0 },
    source: { synthetic: true, source_labels: ['MarketLens demo generator (seed 1)'], ingestion_runs: ['run1'], source_files: ['demo_dataset.csv'] },
    limitations: ['1 day in this listing’s range are missing; they are gaps, not filled in.', 'Coupons and payment offers are conditional and are not subtracted.'],
    ...over,
  };
}

function api(body = withHistory(), ev: () => unknown = () => evidence()) {
  window.localStorage.setItem('ml-data-mode', 'imported');
  return mockApi((url) => {
    if (url.pathname.endsWith('/reviews')) return { body: reviewsResponse() };
    if (url.pathname.endsWith('/audit') || url.pathname.endsWith('/sync')) return { status: 503, body: { detail: 'not mocked here' } };
    if (url.pathname.endsWith('/forecast')) return { status: 503, body: { detail: 'not mocked here' } };
    if (url.pathname.endsWith('/advice')) return { status: 503, body: { detail: 'not mocked here' } };
    if (url.pathname.endsWith('/evidence')) return { body: ev() };
    if (url.pathname.endsWith('/history')) return { body: { status: 'unavailable', reason: 'x', series: [], listings: [], coverage: { days_in_window: 30, days_with_data: 0, first_date: null, last_date: null, missing_dates: [] }, excluded: { timezone_unknown: 0, unknown_shipping_observations: 0 }, source: { synthetic: true, source_labels: [] }, window: { days: 30, start: '', end: '' }, cutoff: '', basis: 'base', currency: 'INR' } };
    if (url.pathname.endsWith('/as-of')) return { body: { requested_at: url.searchParams.get('at'), listings: [], excluded: { timezone_unknown: 0 } } };
    if (url.pathname.startsWith('/api/v1/products/')) return { body };
  });
}

describe('Evidence tab', () => {
  it('shows the detector verdict, score, advertised vs observed and evidence with an explicit cutoff', async () => {
    const m = api();
    renderAt('/products/MCL0001?tab=evidence', routes);
    const panel = await screen.findByRole('tabpanel');
    expect(await within(panel).findByText('Genuine price reduction')).toBeInTheDocument();
    const call = m.calls.find((u) => u.pathname.endsWith('/evidence'))!;
    expect(call.searchParams.get('cutoff')).toBe('2026-10-31T23:59:59Z');
    expect(call.searchParams.get('window')).toBe('90');
    const meter = within(panel).getByRole('meter', { name: /genuine discount score/i });
    expect(meter).toHaveAttribute('aria-valuenow', '68');
    expect(within(panel).getByText('Some evidence of a genuine discount')).toBeInTheDocument();
    // Advertised and measured reductions are shown separately; money through the shared formatter.
    expect(within(panel).getByText('38.46%')).toBeInTheDocument();
    expect(within(panel).getAllByText('20.79%').length).toBeGreaterThan(0);
    expect(within(panel).getAllByText('₹800').length).toBeGreaterThan(0);
    expect(within(panel).getAllByText('₹1,010').length).toBeGreaterThan(0);
    expect(within(panel).getByText(/coupons and payment offers are conditional/i)).toBeInTheDocument();
    expect(within(panel).getByText(/1 missing day/i)).toBeInTheDocument();
    expect(within(panel).getByText(/out of stock or without availability/i)).toBeInTheDocument();
  });

  it('explains terms in tooltips and changes window and basis', async () => {
    const m = api();
    renderAt('/products/MCL0001?tab=evidence', routes);
    const panel = await screen.findByRole('tabpanel');
    await within(panel).findByText('Genuine price reduction');
    await userEvent.click(within(panel).getByRole('button', { name: /what is usual price/i }));
    expect(within(panel).getByRole('tooltip')).toHaveTextContent(/median/i);
    await userEvent.click(within(panel).getByRole('button', { name: '180D' }));
    await waitFor(() => expect(m.calls.filter((u) => u.pathname.endsWith('/evidence')).at(-1)!.searchParams.get('window')).toBe('180'));
    expect(currentLocation).toContain('ewin=180');
    await userEvent.click(within(panel).getByRole('button', { name: /confirmed delivered/i }));
    await waitFor(() => expect(m.calls.filter((u) => u.pathname.endsWith('/evidence')).at(-1)!.searchParams.get('basis')).toBe('delivered'));
  });

  it('links evidence dates to the Time Machine', async () => {
    api();
    renderAt('/products/MCL0001?tab=evidence', routes);
    const panel = await screen.findByRole('tabpanel');
    await within(panel).findByText('Genuine price reduction');
    await userEvent.click(within(panel).getByRole('button', { name: /open the current observation in the time machine/i }));
    expect(currentLocation).toContain('tab=timeline');
    expect(currentLocation).toContain('at=2026-10-31');
  });

  it('shows insufficient evidence instead of a verdict or score', async () => {
    api(withHistory(), () => evidence({
      status: 'insufficient', reason: 'Insufficient historical evidence: 10 distinct observed days in the window; at least 14 are needed.',
      headline: null, detector: null, evidence: null,
      score: { status: 'unavailable', value: null, band: null, label: null, weight_used: 0, components: [], reason: 'Scoring isn’t justified.' },
    }));
    renderAt('/products/MCL0001?tab=evidence', routes);
    const panel = await screen.findByRole('tabpanel');
    expect(await within(panel).findByText(/insufficient historical evidence: 10 distinct/i)).toBeInTheDocument();
    expect(within(panel).queryByRole('meter')).toBeNull();
    expect(within(panel).getByText(/score unavailable/i)).toBeInTheDocument();
  });

  it('never requests evidence for a snapshot-only product', async () => {
    const m = api(detail());
    renderAt('/products/MCL0001?tab=evidence', routes);
    const panel = await screen.findByRole('tabpanel');
    expect(await within(panel).findByText(/insufficient historical evidence/i)).toBeInTheDocument();
    expect(m.calls.some((u) => u.pathname.endsWith('/evidence'))).toBe(false);
  });

  it('shows an error state when evidence cannot be loaded', async () => {
    window.localStorage.setItem('ml-data-mode', 'imported');
    mockApi((url) => {
      if (url.pathname.endsWith('/evidence')) return { status: 500, body: { detail: 'boom' } };
      if (url.pathname.endsWith('/reviews')) return { body: reviewsResponse() };
      if (url.pathname.endsWith('/history') || url.pathname.endsWith('/as-of')) return { status: 500, body: { detail: 'x' } };
      if (url.pathname.startsWith('/api/v1/products/')) return { body: withHistory() };
    });
    renderAt('/products/MCL0001?tab=evidence', routes);
    expect(await screen.findByText(/couldn't load the price evidence/i)).toBeInTheDocument();
  });
});
