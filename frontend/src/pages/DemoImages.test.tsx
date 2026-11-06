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
    const sec = (await screen.findByRole('heading', { name: /featured demo products/i })).closest('section')!;
    const imgs = await within(sec).findAllByRole('img');
    // DEMO-P-001 (a t-shirt) uses a licensed stock photo; DEMO-P-012 (a phone) keeps its artwork: no suitable photo.
    expect(imgs.map((i) => i.getAttribute('src'))).toEqual(['/demo-photos/mens-clothing-1.jpg', '/demo-images/DEMO-P-012.svg']);
    for (const i of imgs) expect(i.getAttribute('src')!.startsWith('/')).toBe(true); // never an external host
    expect(imgs[0].getAttribute('alt')).toMatch(/stock photo of a similar product/i);
    expect(imgs[1].getAttribute('alt')).toMatch(/synthetic demo artwork/i);
    expect(within(sec).getByText(/synthetic data and artwork/i)).toBeInTheDocument();
  });

  it('never shows demo artwork outside Demo mode', async () => {
    const m = api('imported');
    renderAt('/', routes);
    await screen.findByRole('heading', { name: /shop by category/i });
    expect(screen.queryByRole('heading', { name: /featured demo products/i })).toBeNull();
    expect(document.querySelector('img[src^="/demo-images/"]')).toBeNull();
    expect(m.calls.some((u) => u.pathname === '/api/v1/products')).toBe(false);
  });
});
