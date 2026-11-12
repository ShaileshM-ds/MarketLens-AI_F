import { describe, expect, it } from 'vitest';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WatchlistPage } from './WatchlistPage';
import { ModeSwitcher } from '../components/ModeSwitcher';
import { mockApi, renderAt } from '../test/render';
import { me, notification, notificationsResponse, rule, watchItem } from '../test/p5fixtures';

const routes = [{ path: '/watchlist', element: <WatchlistPage /> }];

interface Opts {
  signedIn?: boolean;
  items?: unknown[];
  rules?: unknown[];
  notes?: ReturnType<typeof notificationsResponse>;
}

function api({ signedIn = true, items = [watchItem()], rules = [rule()], notes = notificationsResponse() }: Opts = {}) {
  window.localStorage.setItem('ml-data-mode', 'imported');
  return mockApi((url, req) => {
    const mode = url.searchParams.get('mode');
    const empty = mode === 'demo';
    if (url.pathname === '/api/v1/auth/me') return signedIn ? { body: me } : { status: 401, body: { detail: 'Sign in to continue.' } };
    if (url.pathname === '/api/v1/watchlist') return { body: { mode, items: empty ? [] : items } };
    if (url.pathname.startsWith('/api/v1/watchlist/') && req.method === 'DELETE') return { status: 204, body: null };
    if (url.pathname === '/api/v1/alerts' && req.method === 'GET') return { body: { mode, rules: empty ? [] : rules } };
    if (url.pathname === '/api/v1/alerts' && req.method === 'POST') {
      const b = req.body as Record<string, unknown>;
      return { status: 201, body: { ...rule(b), current_context: { qualifying_now: [{ marketplace: 'Flipkart', listing_id: 'L-F', value_minor: 137000 }], note: 'Context only: these are existing imported snapshot observations. They never trigger a notification.' } } };
    }
    if (url.pathname.startsWith('/api/v1/alerts/') && req.method === 'PATCH') return { body: { ...rule(req.body as Record<string, unknown>), current_context: { qualifying_now: [], note: 'Context only.' } } };
    if (url.pathname.startsWith('/api/v1/alerts/') && req.method === 'DELETE') return { status: 204, body: null };
    if (url.pathname === '/api/v1/notifications') return { body: empty ? notificationsResponse([], 0) : notes };
    if (url.pathname === '/api/v1/notifications/unread-count') return { body: { unread: empty ? 0 : notes.unread } };
    if (url.pathname.endsWith('/read')) return { body: { ...notification(), read: true } };
    if (url.pathname.endsWith('/dismiss')) return { body: { ...notification(), dismissed: true } };
    if (url.pathname === '/api/v1/notifications/read-all') return { body: { marked_read: 1 } };
  });
}

describe('Watchlist & alerts page', () => {
  it('asks signed-out visitors to sign in and comes back here afterwards', async () => {
    api({ signedIn: false });
    renderAt('/watchlist', routes);
    const link = await screen.findByRole('link', { name: /sign in/i });
    expect(link).toHaveAttribute('href', '/signin?next=%2Fwatchlist');
  });

  it('says honestly how alerts are checked', async () => {
    api();
    renderAt('/watchlist', routes);
    expect(await screen.findByText(/checked when new observations are imported/i)).toBeInTheDocument();
    expect(screen.getByText(/no continuous live monitoring/i)).toBeInTheDocument();
  });

  it('shows clear empty states', async () => {
    api({ items: [], rules: [], notes: notificationsResponse([], 0) });
    renderAt('/watchlist', routes);
    expect(await screen.findByText(/your watchlist is empty/i)).toBeInTheDocument();
    expect(screen.getByText('No price alerts yet. Add a product to your watchlist and create a target-price alert.')).toBeInTheDocument();
    expect(screen.getByText(/no notifications/i)).toBeInTheDocument();
  });

  it('lists watched products with stored prices and alert status, and removes them', async () => {
    const m = api();
    renderAt('/watchlist', routes);
    const card = (await screen.findByRole('heading', { name: "Nike Men's Black Crew-Neck T-Shirt", level: 3 })).closest('article')!;
    expect(within(card).getByText('₹1,370')).toBeInTheDocument();
    expect(within(card).getByText('₹1,430')).toBeInTheDocument();
    expect(within(card).getByText('MCL0001')).toBeInTheDocument();
    expect(within(card).getByText(/1 active alert/i)).toBeInTheDocument();
    expect(within(card).queryByText('Synthetic dataset')).toBeNull();
    expect(within(card).getByRole('link', { name: /view details/i })).toHaveAttribute('href', '/products/MCL0001');
    await userEvent.click(within(card).getByRole('button', { name: /remove .* from watchlist/i }));
    await userEvent.click(within(card).getByRole('button', { name: /confirm remove/i }));
    await waitFor(() => expect(m.sent('DELETE', '/api/v1/watchlist/MCL0001')).toHaveLength(1));
  });

  it('creates an alert with exact minor units and shows the snapshot only as context', async () => {
    const m = api({ rules: [] });
    renderAt('/watchlist', routes);
    await userEvent.click(await screen.findByRole('button', { name: /create alert for nike/i }));
    const dialog = screen.getByRole('dialog', { name: /price alert/i });
    await userEvent.type(within(dialog).getByLabelText(/target price/i), 'abc');
    await userEvent.click(within(dialog).getByRole('button', { name: /save alert/i }));
    expect(within(dialog).getByText(/enter a target price in rupees/i)).toBeInTheDocument();
    expect(m.sent('POST', '/api/v1/alerts')).toHaveLength(0);
    await userEvent.clear(within(dialog).getByLabelText(/target price/i));
    await userEvent.type(within(dialog).getByLabelText(/target price/i), '1,400.50');
    await userEvent.click(within(dialog).getByLabelText(/confirmed delivered price/i));
    await userEvent.selectOptions(within(dialog).getByLabelText(/^store/i), 'Flipkart');
    await userEvent.click(within(dialog).getByRole('button', { name: /save alert/i }));
    await waitFor(() => expect(m.sent('POST', '/api/v1/alerts')).toHaveLength(1));
    expect(m.sent('POST', '/api/v1/alerts')[0].body).toEqual({
      product_id: 'MCL0001', marketplace: 'Flipkart', basis: 'delivered', target_price_minor: 140050, currency: 'INR', cooldown_hours: 24, enabled: true,
    });
    const status = await screen.findByRole('status', { name: /alert saved/i });
    expect(within(status).getByText(/context only/i)).toBeInTheDocument();
    expect(within(status).getByText(/Flipkart ₹1,370/)).toBeInTheDocument();
  });

  it('edits, pauses and deletes alerts', async () => {
    const m = api();
    renderAt('/watchlist', routes);
    const row = await screen.findByRole('row', { name: /nike/i });
    expect(within(row).getByText('₹1,400')).toBeInTheDocument();
    expect(within(row).getByText('Any store')).toBeInTheDocument();
    expect(within(row).getByText('Base price')).toBeInTheDocument();
    await userEvent.click(within(row).getByRole('button', { name: /pause/i }));
    await waitFor(() => expect(m.sent('PATCH', `/api/v1/alerts/${'a'.repeat(32)}`)[0].body).toEqual({ enabled: false }));
    await userEvent.click(within(row).getByRole('button', { name: /edit/i }));
    const dialog = screen.getByRole('dialog', { name: /price alert/i });
    const input = within(dialog).getByLabelText(/target price/i);
    expect(input).toHaveValue('₹1,400'); // inputs use the one shared money formatter (CLAUDE.md)
    await userEvent.clear(input);
    await userEvent.type(input, '1350');
    await userEvent.click(within(dialog).getByRole('button', { name: /save alert/i }));
    await waitFor(() => expect(m.sent('PATCH', `/api/v1/alerts/${'a'.repeat(32)}`).some((r) => (r.body as { target_price_minor?: number }).target_price_minor === 135000)).toBe(true));
    await userEvent.click(within(row).getByRole('button', { name: /^delete/i }));
    expect(m.sent('DELETE', `/api/v1/alerts/${'a'.repeat(32)}`)).toHaveLength(0);
    await userEvent.click(within(row).getByRole('button', { name: /confirm delete/i }));
    await waitFor(() => expect(m.sent('DELETE', `/api/v1/alerts/${'a'.repeat(32)}`)).toHaveLength(1));
  });

  it('closes the alert dialog with Escape and returns focus', async () => {
    api();
    renderAt('/watchlist', routes);
    const opener = await screen.findByRole('button', { name: /create alert for nike/i });
    await userEvent.click(opener);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it('shows notifications with evidence and marks them read', async () => {
    const m = api();
    renderAt('/watchlist', routes);
    const item = (await screen.findByText('New qualifying observation detected')).closest('li')!;
    expect(within(item).getByText('Unread')).toBeInTheDocument();
    expect(within(item).getByText(/Flipkart · base price ₹1,300 is at or below your target ₹1,350/)).toBeInTheDocument();
    expect(within(item).getByText(/5 Nov 2026, 09:00 UTC/)).toBeInTheDocument();
    expect(within(item).getByText(/email not sent \(local outbox only\)/i)).toBeInTheDocument();
    expect(within(item).queryByText('Synthetic')).toBeNull();
    expect(within(item).queryByText(/dropped/i)).not.toBeInTheDocument();
    await userEvent.click(within(item).getByRole('button', { name: /mark as read/i }));
    await waitFor(() => expect(m.sent('POST', `/api/v1/notifications/${'b'.repeat(24)}/read`)).toHaveLength(1));
    await userEvent.click(screen.getByRole('button', { name: /mark all as read/i }));
    await waitFor(() => expect(m.sent('POST', '/api/v1/notifications/read-all')).toHaveLength(1));
  });

  it('follows the selected workspace', async () => {
    const m = api();
    renderAt('/watchlist', routes, <ModeSwitcher />);
    await screen.findByRole('heading', { name: "Nike Men's Black Crew-Neck T-Shirt", level: 3 });
    await userEvent.click(screen.getByRole('button', { name: 'Demo' }));
    expect(await screen.findByText(/your watchlist is empty/i)).toBeInTheDocument();
    expect(m.requests.filter((r) => r.url.pathname === '/api/v1/watchlist').at(-1)!.url.searchParams.get('mode')).toBe('demo');
  });
});
