import { describe, expect, it } from 'vitest';
import { screen, within } from '@testing-library/react';
import { MethodologyPage } from './MethodologyPage';
import { mockApi, renderAt } from '../test/render';

const routes = [{ path: '/methodology', element: <MethodologyPage /> }];

// Deliberately unusual values: the page must show what the API (the code) says, not hardcoded numbers.
const m = {
  sections: ['ingestion', 'history', 'prices', 'detector', 'score', 'advice', 'forecast', 'memory', 'sync', 'audit', 'dashboard', 'alerts'],
  history: { windows: [7, 30, 90, 180], bases: ['base', 'delivered'] },
  pricing: { discount_tolerance_points: 0.5 },
  evidence: { version: 'evidence-1', min_days: 17, savings_threshold: 5, full_savings: 25, agreement_points: [5, 25], reference_increase: 20, stale_days: 3, weights: { savings: 61, percentile: 24, agreement: 15 } },
  advice: { version: 'advice-1', low_percentile: 25, strong_savings: 10, strong_percentile: 80, fresh_hours: 48, stale_days: 7, missing_share: 0.1, short_history_days: 30, expectation_horizon: 7 },
  forecast: { version: 'forecast-2', horizons: [7, 14, 30], models: { naive: 'Last observed price (baseline)', recent_median: 'Median of the last 14 observed days' }, median_days: 14, min_train_days: 14, min_origins: 20, max_origins: 120, min_improvement_percent: 5, interval_level_percent: 80, interval_method: 'conformal-relative-abs', min_residuals: 10, lookback_days: 365, stale_days: 7 },
  memory: { drop_percent: 10, return_within_percent: 5, further_percent: 5, days: [1, 3, 7, 14], baseline_days: 14 },
  sync: { version: 'sync-1', change_percent: 3, max_gap_days: 2, match_days: 1, min_days: 14, min_matches: 3, min_share: 0.6, stale_days: 7, benign: ['A store-wide or festival sale that both listings joined.'] },
  audit: { version: 'audit-1', urgency_min_days: 14, low_stock: 5, rules: [{ rule_id: 'reference_inflation', title: 'Reference price raised', version: '1.0', kind: 'calculated', required: 'verified history of the seller’s reference price' }, { rule_id: 'repeated_urgency', title: 'Repeated urgency message while stock stayed normal', version: '1.0', kind: 'heuristic', required: 'urgency messages' }] },
  dashboard: { version: 'dashboard-1', max_products: 200 },
  alerts: {
    below_target: { label: 'Below target price', description: 'A newly imported observation at or below your target price.', family: 'observation' },
    new_low: { label: 'New lowest verified price', description: 'x', family: 'event' }, restock: { label: 'Back in stock (reported)', description: 'x', family: 'event' },
    meaningful_discount: { label: 'Meaningful discount', description: 'x', family: 'state' }, advice_change: { label: 'Buying advice change', description: 'x', family: 'state' },
    seller_switch: { label: 'Lowest-price seller change', description: 'x', family: 'state' }, audit_finding: { label: 'New pricing audit finding', description: 'x', family: 'state' },
    synchronization_anomaly: { label: 'New synchronized price pattern', description: 'x', family: 'state' },
  },
  alert_rules: { new_low_lookback_days: 90, new_low_min_days: 14, switch_fresh_days: 7, default_min_score: 70, min_score_range: [40, 100], window_days: 90 },
};
const evalReport = {
  mode: 'demo', version: 'forecast-2', cutoff: '2026-10-31T23:59:59Z', basis: 'base', level_percent: 80, products_evaluated: 39, listings_evaluated: 39, synthetic: true,
  insufficient: [{ product_id: 'DEMO-P-011', reason: 'Insufficient historical evidence: 10 distinct observed days.' }],
  note: 'Results on synthetic Demo data are not evidence of real-market performance.',
  horizons: [{ days: 30, points: 4601, first_origin: '2026-05-22', last_origin: '2026-10-01', mae_baseline_minor: 11399, mae_candidate_minor: 11884, mape_baseline_percent: 2.34, mape_candidate_percent: 2.37, candidate_chosen: 9, baseline_chosen: 30,
    calibrated: { method: 'conformal-relative-abs', points: 3099, coverage_percent: 70.8, mean_width_percent: 6.21 }, previous: { method: 'x', points: 3099, coverage_percent: 51.4, mean_width_percent: 4.54 } }],
};

function api(meta: { latest_verified_at: string | null } = { latest_verified_at: '2026-10-31T10:00:00Z' }) {
  window.localStorage.setItem('ml-data-mode', 'demo');
  return mockApi((url) => {
    if (url.pathname === '/api/v1/methodology') return { body: m };
    if (url.pathname === '/api/v1/dashboard/meta') return { body: { mode: 'demo', categories: [], marketplaces: [], windows: [30, 90, 180], ...meta } };
    if (url.pathname === '/api/v1/forecast-evaluation') return { body: evalReport };
  });
}

describe('Methodology page', () => {
  it('has the twelve sections with navigation and a misconduct disclaimer', async () => {
    api();
    renderAt('/methodology', routes);
    const toc = await screen.findByRole('navigation', { name: /methodology sections/i });
    const links = within(toc).getAllByRole('link');
    expect(links.map((a) => a.getAttribute('href'))).toEqual(m.sections.map((s) => `#${s}`));
    for (const s of m.sections) expect(document.getElementById(s)).not.toBeNull();
    expect(screen.getByText(/not proof of misconduct/i)).toBeInTheDocument();
    expect(screen.getAllByText(/synthetic/i).length).toBeGreaterThan(0);
  });

  it('shows the formulas and thresholds the code reports', async () => {
    api();
    renderAt('/methodology', routes);
    const score = (await screen.findByRole('heading', { name: /genuine discount score/i })).closest('section')!;
    expect(within(score).getByText(/61% real savings/i)).toBeInTheDocument();
    expect(within(score).getAllByText(/17 distinct observed days/i).length).toBeGreaterThan(0);
    const fc = screen.getByRole('heading', { name: /^forecasting/i }).closest('section')!;
    expect(within(fc).getByText(/ceil\(\(n \+ 1\) × 0\.8\)/)).toBeInTheDocument();
    expect(within(fc).getByText(/separately for each forecast series/i)).toBeInTheDocument();
    expect(within(fc).queryByText(/across the whole workspace/i)).toBeNull();
    const alerts = screen.getByRole('heading', { name: /alert types/i }).closest('section')!;
    expect(within(alerts).getAllByRole('row')).toHaveLength(9); // header + the eight types the API lists
  });

  it('shows the forecast evaluation before and after calibration, labelled synthetic', async () => {
    const calls = api();
    renderAt('/methodology', routes);
    const table = await screen.findByRole('table', { name: /forecast evaluation/i });
    expect(within(table).getByText('51.4% → 70.8%')).toBeInTheDocument();
    expect(within(table).getByText('4.54% → 6.21%')).toBeInTheDocument();
    expect(screen.getByText(/not evidence of real-market performance/i)).toBeInTheDocument();
    // Plain statements: wider ranges bought the coverage, 30 days is still below target, and the baseline is used.
    expect(screen.getByText(/came with wider ranges/i)).toBeInTheDocument();
    expect(screen.getByText(/30-day ranges remain below the nominal 80% target and are not calibrated/i)).toBeInTheDocument();
    expect(within(table).getByText('9 of 39')).toBeInTheDocument(); // per-series choices are reported, not overridden
    expect(calls.calls.find((u) => u.pathname === '/api/v1/forecast-evaluation')!.searchParams.get('cutoff')).toBe('2026-10-31T23:59:59Z');
  });

  it('says when the workspace has no verified history to evaluate', async () => {
    const calls = api({ latest_verified_at: null });
    renderAt('/methodology', routes);
    expect(await screen.findByText(/no verified history in this workspace/i)).toBeInTheDocument();
    expect(calls.calls.some((u) => u.pathname === '/api/v1/forecast-evaluation')).toBe(false);
  });
});
