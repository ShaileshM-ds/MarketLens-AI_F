import { describe, expect, it } from 'vitest';
import { screen, within } from '@testing-library/react';
import { Home } from './Home';
import { mockApi, renderAt } from '../test/render';

const routes = [{ path: '/', element: <Home /> }];
const item = (id: string, name: string) => ({ product_id: id, name, category_label: 'Mobile phones', lowest_price: { amount_minor: 1899900, currency: 'INR' } });

function api(mode: 'demo' | 'imported') {
  window.localStorage.setItem('ml-data-mode', mode);
  return mockApi((url) => {
    if (url.pathname === '/api/v1/categories') return { body: { mode, categories: [] } };
    if (url.pathname === '/api/v1/products') return { body: { items: [item('DEMO-P-012', 'Nimbra 5G Phone'), item('DEMO-P-001', 'Zephyra Cotton Tee'), item('DEMO-P-002', 'Not featured')], total: 3 } };
  });
}

describe('Demo product artwork', () => {
  it('shows featured Demo products with local synthetic artwork on the Overview', async () => {
    api('demo');
    renderAt('/', routes);
    const sec = (await screen.findByRole('heading', { name: /featured products/i })).closest('section')!;
    const imgs = await within(sec).findAllByRole('img');
    // Each Demo product shows its own locally stored, openly licensed photo.
    expect(imgs.map((i) => i.getAttribute('src'))).toEqual(['/demo-photos/mens-clothing-1.jpg', '/demo-photos/mobile-phones-2.jpg']);
    for (const i of imgs) expect(i.getAttribute('src')!.startsWith('/')).toBe(true); // never an external host
    expect(imgs.map((i) => i.getAttribute('alt'))).toEqual(['Zephyra Cotton Tee', 'Nimbra 5G Phone']);
    expect(within(sec).queryByText(/synthetic/i)).toBeNull(); // only the top-bar data-mode badge says Demo
  });

  it('never shows demo artwork outside Demo mode', async () => {
    const m = api('imported');
    renderAt('/', routes);
    await screen.findByRole('heading', { name: /shop by category/i });
    expect(screen.queryByRole('heading', { name: /featured products/i })).toBeNull();
    expect(document.querySelector('img[src^="/demo-images/"]')).toBeNull();
    expect(m.calls.some((u) => u.pathname === '/api/v1/products')).toBe(false);
  });
});
