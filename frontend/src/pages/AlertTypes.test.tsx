import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WatchlistPage } from './WatchlistPage';
import { mockApi, renderAt } from '../test/render';
import { me, notification, notificationsResponse, rule, watchItem } from '../test/p5fixtures';

const routes = [{ path: '/watchlist', element: <WatchlistPage /> }];

const signal = notification({
  id: 'd'.repeat(24), type: 'advice_change', title: 'Buying advice changed', basis: null, observed_minor: null, target_minor: null, observation_id: null,
  message: 'Buying advice changed from Consider waiting to Buy now (medium confidence): The current price is 30% below its usual level.',
  evidence: { analysis_version: 'advice-1', cutoff: '2026-10-31T20:00:00Z', previous: 'consider_waiting', current: 'buy_now' },
});

function api(rules = [rule(), rule({ id: 'e'.repeat(32), type: 'meaningful_discount', basis: 'base', target_price_minor: null, currency: null, min_score: 70 })]) {
  window.localStorage.setItem('ml-data-mode', 'imported');
  return mockApi((url, req) => {
    if (url.pathname === '/api/v1/auth/me') return { body: me };
    if (url.pathname === '/api/v1/watchlist') return { body: { mode: 'imported', items: [watchItem()] } };
    if (url.pathname === '/api/v1/alerts' && req.method === 'GET') return { body: { mode: 'imported', rules } };
    if (url.pathname === '/api/v1/alerts' && req.method === 'POST') return { status: 201, body: { ...rule(req.body as Record<string, unknown>), current_context: { qualifying_now: [], note: 'Evaluated only when new verified observations are imported.' } } };
    if (url.pathname === '/api/v1/notifications') return { body: notificationsResponse([signal, notification()], 2) };
    if (url.pathname === '/api/v1/notifications/unread-count') return { body: { unread: 2 } };
  });
}

describe('SCOPE alert types', () => {
  it('creates an advice-change alert without a target price', async () => {
    const m = api();
    renderAt('/watchlist', routes);
    await userEvent.click(await screen.findByRole('button', { name: /create alert for/i }));
    const dialog = screen.getByRole('dialog');
    await userEvent.selectOptions(within(dialog).getByLabelText(/alert type/i), 'advice_change');
    expect(within(dialog).queryByLabelText(/target price/i)).toBeNull();
    expect(within(dialog).getByText(/two valid evaluations/i)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: /save alert/i }));
    await waitFor(() => expect(m.calls.some((u) => u.pathname === '/api/v1/alerts')).toBe(true));
    const post = m.requests.find((r) => r.method === 'POST' && r.url.pathname === '/api/v1/alerts')!;
    expect(post.body).toMatchObject({ product_id: 'MCL0001', type: 'advice_change', cooldown_hours: 24 });
    expect((post.body as Record<string, unknown>).target_price_minor).toBeUndefined();
  });

  it('validates the minimum score for a meaningful-discount alert', async () => {
    const m = api();
    renderAt('/watchlist', routes);
    await userEvent.click(await screen.findByRole('button', { name: /create alert for/i }));
    const dialog = screen.getByRole('dialog');
    await userEvent.selectOptions(within(dialog).getByLabelText(/alert type/i), 'meaningful_discount');
    const score = within(dialog).getByLabelText(/minimum genuine discount score/i);
    await userEvent.clear(score);
    await userEvent.type(score, '20');
    await userEvent.click(within(dialog).getByRole('button', { name: /save alert/i }));
    expect(within(dialog).getByRole('alert')).toHaveTextContent(/40 to 100/);
    expect(m.requests.some((r) => r.method === 'POST')).toBe(false);
  });

  it('lists rule types and shows signal notifications with their evidence link', async () => {
    api();
    renderAt('/watchlist', routes);
    expect(await screen.findByText('Score ≥ 70')).toBeInTheDocument();
    expect(screen.getAllByText('Meaningful discount').length).toBeGreaterThan(0);
    const item = (await screen.findByText('Buying advice changed')).closest('li')!;
    expect(within(item).getByText(/from consider waiting to buy now/i)).toBeInTheDocument();
    expect(within(item).getByText(/advice-1/)).toBeInTheDocument();
    expect(within(item).getByRole('link', { name: /view the evidence/i }).getAttribute('href')).toContain('tab=evidence');
  });
});
