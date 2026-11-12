import { describe, expect, it } from 'vitest';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AnalystDashboard } from './AnalystDashboard';
import { currentLocation, mockApi, renderAt } from '../test/render';

const routes = [{ path: '/analyst', element: <AnalystDashboard /> }];
const meta: { mode: string; latest_verified_at: string | null; categories: string[]; marketplaces: string[]; windows: number[] } = { mode: 'demo', latest_verified_at: '2026-10-31T20:00:00Z', categories: ['mens-clothing', 'mobile-phones'], marketplaces: ['Amazon', 'Flipkart'], windows: [30, 90, 180] };
const product = (id: string, over: Record<string, unknown> = {}) => ({
  product_id: id, name: `Product ${id}`, category: 'mobile-phones', status: 'available', verdict: 'around_usual', savings_percent: 0.5, score: 12, band: 'weak',
  advice: 'consider_waiting', advice_confidence: 'low', lowest_marketplace: 'Amazon', audit: ['unsupported_discount'], sync_patterns: 0, forecast_7: { chosen: 'naive', improvement_percent: -10 }, ...over,
});

function dash(over: Record<string, unknown> = {}) {
  return {
    mode: 'demo', version: 'dashboard-1', cutoff: '2026-10-31T23:59:59Z', window: { days: 90 }, cache: { hit: false, computed_at: '2026-11-06T00:00:00Z' },
    totals: { products: 40, listings: 92, verified_observations: 17100, snapshot_observations: 0, rejected_records: 0, ingestion_runs: 1 },
    quality: { stock_contradiction_observations: 0, discount_mismatch_observations: 0, unknown_shipping_observations: 0, timezone_unknown_observations: 0, note: 'Snapshot observations are never used in historical analysis.' },
    provenance: { synthetic: true, synthetic_observations: 17100, source_labels: ['MarketLens demo generator'] },
    marketplaces: [
      { marketplace: 'Amazon', listings: 44, verified_observations: 8000, snapshot_observations: 0, lowest_current_price_products: 20 },
      { marketplace: 'Flipkart', listings: 40, verified_observations: 7300, snapshot_observations: 0, lowest_current_price_products: 19 },
    ],
    historical: {
      status: 'available', truncated: false, max_products: 200, products_analyzed: 39, products_insufficient: 1,
      detector: { below_usual: 2, around_usual: 37 }, score_bands: { weak: 37, moderate: 1, strong: 1 }, advice: { buy_now: 2, consider_waiting: 37, insufficient_evidence: 1 },
      savings_distribution: [{ label: '≤ −10%', count: 0 }, { label: '−5 to +5%', count: 37 }, { label: '≥ 20%', count: 0 }],
      audit: { by_rule: { reference_inflation: { title: 'Reference price raised', kind: 'calculated', count: 1, products: [{ product_id: 'DEMO-P-002', name: 'Inflated thing', severity: 'high' }] } }, disabled: {}, note: 'Evidence-based flags for review, not legal findings or accusations.' },
      sync: { pairs: { pattern: 3, no_changes: 60 }, pattern_products: [{ product_id: 'DEMO-P-007', name: 'Kurta', pairs: 3 }], note: 'Patterns worth investigating, not proof of collusion.' },
      forecast: { note: 'Forecasts are estimates.', horizons: [
        { days: 7, available: 39, model_chosen: 0, baseline_chosen: 39, mean_mae_baseline_minor: 6010, mean_mae_model_minor: 7413, mean_mape_baseline_percent: 1.15, mean_mape_model_percent: 1.51, mean_measured_coverage_percent: 75.6, coverage_note: 'Nominal 80% range; measured coverage 75.6%.' },
        { days: 30, available: 39, model_chosen: 9, baseline_chosen: 30, mean_mae_baseline_minor: 11254, mean_mae_model_minor: 11733, mean_mape_baseline_percent: 2.33, mean_mape_model_percent: 2.36, mean_measured_coverage_percent: 52.1, coverage_note: 'Nominal 80% range; measured coverage 52.1% — not calibrated.' },
      ] },
      trend: Array.from({ length: 30 }, (_, i) => ({ date: `2026-10-${String(i + 2).padStart(2, '0')}`, index: 100 + (i % 3), products: 39 })),
      trend_note: 'Daily median price index.',
      products: [product('DEMO-P-001', { verdict: 'below_usual', savings_percent: 19.07, advice: 'buy_now', band: 'moderate', score: 68 }), product('DEMO-P-002')],
    },
    ...over,
  };
}

function api(d: () => { status?: number; body: unknown } = () => ({ body: dash() }), m = meta) {
  window.localStorage.setItem('ml-data-mode', 'demo');
  return mockApi((url) => {
    if (url.pathname === '/api/v1/dashboard/meta') return { body: m };
    if (url.pathname === '/api/v1/dashboard') return d();
  });
}

describe('Analyst dashboard', () => {
  it('shows database-backed metrics with an explicit cutoff, provenance and links to product evidence', async () => {
    const m = api();
    renderAt('/analyst', routes);
    expect(await screen.findByText('17,100')).toBeInTheDocument();
    const call = m.calls.find((u) => u.pathname === '/api/v1/dashboard')!;
    expect(call.searchParams.get('cutoff')).toBe('2026-10-31T23:59:59Z');
    expect(call.searchParams.get('window')).toBe('90');
    expect(screen.queryByText('Synthetic data')).toBeNull(); // only the top-bar badge marks the mode
    expect(screen.getByText(/not proof of collusion/i)).toBeInTheDocument();
    expect(screen.getByText(/not legal findings/i)).toBeInTheDocument();
    expect(screen.getByText(/not calibrated/i)).toBeInTheDocument();
    const link = screen.getByRole('link', { name: 'Inflated thing' });
    expect(link.getAttribute('href')).toContain('/products/DEMO-P-002');
    const table = screen.getByRole('table', { name: /products analysed/i });
    expect(within(table).getByRole('link', { name: 'Product DEMO-P-001' }).getAttribute('href')).toContain('tab=evidence');
    expect(screen.getByRole('img', { name: /price index/i })).toBeInTheDocument();
  });

  it('applies category, marketplace, window and cutoff filters through the URL', async () => {
    const m = api();
    renderAt('/analyst', routes);
    await screen.findByText('17,100');
    await userEvent.selectOptions(screen.getByLabelText(/category/i), 'mobile-phones');
    await userEvent.selectOptions(screen.getByLabelText(/^store$/i), 'Flipkart');
    await userEvent.click(screen.getByRole('button', { name: '30D' }));
    await waitFor(() => {
      const last = m.calls.filter((u) => u.pathname === '/api/v1/dashboard').at(-1)!;
      expect(last.searchParams.get('category')).toBe('mobile-phones');
      expect(last.searchParams.get('marketplace')).toBe('Flipkart');
      expect(last.searchParams.get('window')).toBe('30');
    });
    expect(currentLocation).toContain('category=mobile-phones');
    const date = screen.getByLabelText(/cutoff/i);
    fireEvent.change(date, { target: { value: '2026-09-30' } });
    await waitFor(() => expect(m.calls.filter((u) => u.pathname === '/api/v1/dashboard').at(-1)!.searchParams.get('cutoff')).toBe('2026-09-30T23:59:59Z'));
  });

  it('separates snapshot data and shows the no-history state', async () => {
    api(() => ({ body: dash({ totals: { products: 500, listings: 1500, verified_observations: 0, snapshot_observations: 1500, rejected_records: 12715, ingestion_runs: 5 },
      quality: { stock_contradiction_observations: 44, discount_mismatch_observations: 3, unknown_shipping_observations: 0, timezone_unknown_observations: 1500, note: 'x' },
      provenance: { synthetic: false, synthetic_observations: 0, source_labels: [] }, marketplaces: [],
      historical: { status: 'no_verified_history', products: [], products_analyzed: 0, products_insufficient: 0, reason: 'No verified UTC observations up to this cutoff, so no historical analytics are shown.' } }) }),
      { ...meta, latest_verified_at: null });
    renderAt('/analyst', routes);
    expect(await screen.findByText(/no verified utc observations up to this cutoff/i)).toBeInTheDocument();
    expect(screen.getByText('44')).toBeInTheDocument();
    expect(screen.getAllByText('1,500').length).toBeGreaterThan(0);
  });

  it('shows an error state', async () => {
    api(() => ({ status: 500, body: { detail: 'boom' } }));
    renderAt('/analyst', routes);
    expect(await screen.findByText(/couldn't load the dashboard/i)).toBeInTheDocument();
  });
});
