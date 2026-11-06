import { describe, expect, it } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WatchToggle } from './WatchToggle';
import { AlertsBell } from './AlertsBell';
import { SignInPage } from '../pages/SignInPage';
import { currentLocation, mockApi, renderAt } from '../test/render';
import { me, watchItem } from '../test/p5fixtures';

function api(signedIn: boolean, watched: string[] = [], unread = 0) {
  window.localStorage.setItem('ml-data-mode', 'imported');
  let loggedIn = signedIn;
  return mockApi((url, req) => {
    if (url.pathname === '/api/v1/auth/me') return loggedIn ? { body: me } : { status: 401, body: { detail: 'Sign in to continue.' } };
    if (url.pathname === '/api/v1/auth/login') {
      loggedIn = true;
      return { body: me };
    }
    if (url.pathname === '/api/v1/watchlist') return { body: { mode: 'imported', items: watched.map((id) => watchItem(id)) } };
    if (url.pathname.startsWith('/api/v1/watchlist/') && req.method === 'PUT') return { body: { product_id: url.pathname.split('/').pop() } };
    if (url.pathname.startsWith('/api/v1/watchlist/') && req.method === 'DELETE') return { status: 204, body: null };
    if (url.pathname === '/api/v1/notifications/unread-count') return { body: { unread } };
  });
}

const routes = [
  { path: '/products/:id', element: <WatchToggle productId="MCL0001" name="Nike Tee" /> },
  { path: '/signin', element: <SignInPage /> },
];

describe('Watch toggle', () => {
  it('adds a product for a signed-in user, showing the pressed state', async () => {
    const m = api(true);
    renderAt('/products/MCL0001', routes);
    const btn = await screen.findByRole('button', { name: 'Watch Nike Tee' });
    expect(btn).toHaveAttribute('aria-pressed', 'false');
    await userEvent.click(btn);
    await waitFor(() => expect(m.sent('PUT', '/api/v1/watchlist/MCL0001')).toHaveLength(1));
    expect(m.sent('PUT', '/api/v1/watchlist/MCL0001')[0].url.searchParams.get('mode')).toBe('imported');
  });

  it('shows Watching for a watched product and removes it', async () => {
    const m = api(true, ['MCL0001']);
    renderAt('/products/MCL0001', routes);
    const btn = await screen.findByRole('button', { name: 'Stop watching Nike Tee' });
    expect(btn).toHaveAttribute('aria-pressed', 'true');
    expect(btn).toHaveTextContent('Watching');
    await userEvent.click(btn);
    await waitFor(() => expect(m.sent('DELETE', '/api/v1/watchlist/MCL0001')).toHaveLength(1));
  });

  it('a signed-out tap resumes after sign-in (SCOPE §5)', async () => {
    const m = api(false);
    renderAt('/products/MCL0001', routes);
    await userEvent.click(await screen.findByRole('button', { name: 'Watch Nike Tee' }));
    await waitFor(() => expect(currentLocation).toBe('/signin?next=%2Fproducts%2FMCL0001'));
    expect(m.sent('PUT', '/api/v1/watchlist/MCL0001')).toHaveLength(0);
    await userEvent.type(screen.getByLabelText('Username'), 'alice');
    await userEvent.type(screen.getByLabelText('Password'), 'alice-test-password-1');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    await waitFor(() => expect(m.sent('PUT', '/api/v1/watchlist/MCL0001')).toHaveLength(1));
    await waitFor(() => expect(currentLocation).toBe('/products/MCL0001'));
    expect(window.sessionStorage.getItem('ml-pending-action')).toBeNull();
  });
});

describe('Alerts bell', () => {
  it('shows the unread count for signed-in users', async () => {
    api(true, [], 2);
    renderAt('/', [{ path: '/', element: <AlertsBell /> }]);
    expect(await screen.findByRole('link', { name: 'Alerts, 2 unread' })).toHaveAttribute('href', '/watchlist#notifications');
  });

  it('shows no count when signed out', async () => {
    api(false);
    renderAt('/', [{ path: '/', element: <AlertsBell /> }]);
    expect(await screen.findByRole('link', { name: 'Alerts, 0 unread' })).toBeInTheDocument();
  });
});
