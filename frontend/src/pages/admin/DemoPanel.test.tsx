import { describe, expect, it } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DemoPanel } from './DemoPanel';
import { mockApi, renderAt } from '../../test/render';

function api(products = 0) {
  return mockApi((url, req) => {
    if (url.pathname === '/api/v1/admin/demo/status') {
      return { body: { database: 'marketlens_demo', products, observations: products ? 20000 : 0, reviews: products ? 300 : 0, last_run: null, jobs: [], export_location: 'data/demo-export/' } };
    }
    if (url.pathname === '/api/v1/admin/demo/generate' && req.method === 'POST') return { body: { id: 'j1', type: 'demo_generate', status: 'queued' } };
    if (url.pathname === '/api/v1/admin/demo/reset' && req.method === 'POST') return { body: { id: 'j2', type: 'demo_reset', status: 'queued' } };
  });
}

describe('Demo data panel', () => {
  it('queues generation when Demo is empty and explains the answer key', async () => {
    const m = api(0);
    renderAt('/', [{ path: '/', element: <DemoPanel /> }]);
    await userEvent.click(await screen.findByRole('button', { name: /generate demo data/i }));
    await waitFor(() => expect(m.sent('POST', '/api/v1/admin/demo/generate')).toHaveLength(1));
    expect(screen.getByText(/answer_key\.json/)).toBeInTheDocument();
    expect(screen.getAllByText(/only the demo database/i).length).toBeGreaterThan(0);
  });

  it('requires the typed phrase before resetting', async () => {
    const m = api(40);
    renderAt('/', [{ path: '/', element: <DemoPanel /> }]);
    const reset = await screen.findByRole('button', { name: /reset demo data/i });
    expect(reset).toBeDisabled();
    expect(screen.getByRole('button', { name: /generate demo data/i })).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/type reset demo/i), 'RESET DEMO');
    await userEvent.click(reset);
    await waitFor(() => expect(m.sent('POST', '/api/v1/admin/demo/reset')[0].body).toEqual({ confirm: 'RESET DEMO' }));
  });
});
