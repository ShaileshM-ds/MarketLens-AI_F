import { describe, expect, it } from 'vitest';
import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProductExplorer } from './ProductExplorer';
import { ModeSwitcher } from '../components/ModeSwitcher';
import { currentLocation, mockApi, renderAt } from '../test/render';
import { filtersResponse, item, listResponse } from '../test/fixtures';

const routes = [
  { path: '/products', element: <ProductExplorer /> },
  { path: '/products/:productId', element: <p>detail page</p> },
];

function imported() {
  window.localStorage.setItem('ml-data-mode', 'imported');
}

function standardApi(items = [item(), item({ product_id: 'MCL0002', name: 'Adidas Olive Shirt' })], total = 500) {
  return mockApi((url) => {
    if (url.pathname === '/api/v1/products/filters') return { body: filtersResponse(url.searchParams.get('mode') ?? 'demo', url.searchParams.get('mode') === 'imported' ? 500 : 0) };
    if (url.pathname === '/api/v1/products') {
      const mode = url.searchParams.get('mode');
      if (mode !== 'imported') return { body: listResponse([], 0, 1, mode ?? 'demo') };
      return { body: listResponse(items, total, Number(url.searchParams.get('page') ?? 1)) };
    }
  });
}

describe('Product Explorer', () => {
  it('renders real API records with honest price labels and provenance', async () => {
    imported();
    standardApi();
    renderAt('/products', routes);
    expect(await screen.findByRole('heading', { name: 'Product Explorer' })).toBeInTheDocument();
    const card = (await screen.findByText("Nike Men's Black Crew-Neck T-Shirt - Size S (Style 001)")).closest('article')!;
    expect(within(card).getByText('From ₹1,370')).toBeInTheDocument();
    expect(within(card).getByText(/base listing price, excludes shipping/i)).toBeInTheDocument();
    expect(within(card).getByText('3 stores')).toBeInTheDocument();
    expect(within(card).getByText(/Product rating 3.5–4.2/)).toBeInTheDocument();
    expect(within(card).getByText('MCL0001')).toBeInTheDocument();
    expect(screen.getByText('500 products')).toBeInTheDocument();
    expect(screen.queryAllByText(/Synthetic demonstration data/)).toHaveLength(0);
    expect(screen.getByText(/single snapshot per listing/i)).toBeInTheDocument();
  });

  it('marks unknown shipping, out-of-stock lowest prices and unavailable prices', async () => {
    imported();
    standardApi([
      item({ product_id: 'A1', name: 'Unknown shipping', lowest_price: { ...item().lowest_price, offers_with_unknown_shipping: 1 } }),
      item({ product_id: 'A2', name: 'Out of stock one', lowest_price: { ...item().lowest_price, out_of_stock: true } }),
      item({ product_id: 'A3', name: 'No price', lowest_price: null, lowest_price_unavailable_reason: 'No current price is available for the matching listings.' }),
    ]);
    renderAt('/products', routes);
    expect(await screen.findByText(/shipping unknown for 1 listing/i)).toBeInTheDocument();
    expect(screen.getByText(/out of stock at this price/i)).toBeInTheDocument();
    expect(screen.getByText('Price unavailable')).toBeInTheDocument();
    expect(screen.getByText('No current price is available for the matching listings.')).toBeInTheDocument();
  });

  it('searches on Enter, debounces typing and can clear the search', async () => {
    imported();
    const api = standardApi();
    renderAt('/products', routes);
    await screen.findByText('500 products');
    const box = screen.getByRole('searchbox', { name: /search products/i });
    await userEvent.type(box, 'MCL0001{Enter}');
    await waitFor(() => expect(api.productCalls().at(-1)!.searchParams.get('q')).toBe('MCL0001'));
    expect(currentLocation).toContain('q=MCL0001');
    await userEvent.click(screen.getByRole('button', { name: /clear search/i }));
    await waitFor(() => expect(api.productCalls().at(-1)!.searchParams.get('q')).toBeNull());
    await userEvent.type(box, 'crew');
    await waitFor(() => expect(api.productCalls().at(-1)!.searchParams.get('q')).toBe('crew'), { timeout: 2000 });
  });

  it('applies marketplace, free-shipping and price filters, resets the page, and clears all', async () => {
    imported();
    const api = standardApi();
    renderAt('/products?page=3', routes);
    await screen.findByText('500 products');
    await userEvent.click(screen.getByRole('checkbox', { name: 'Amazon' }));
    await waitFor(() => expect(api.productCalls().at(-1)!.searchParams.getAll('marketplace')).toEqual(['Amazon']));
    expect(api.productCalls().at(-1)!.searchParams.get('page')).toBe('1');
    await userEvent.click(screen.getByRole('checkbox', { name: /known free shipping/i }));
    await waitFor(() => expect(api.productCalls().at(-1)!.searchParams.get('free_shipping')).toBe('true'));
    await userEvent.type(screen.getByLabelText(/minimum price/i), '1370');
    await userEvent.click(screen.getByRole('button', { name: /apply price/i }));
    await waitFor(() => expect(api.productCalls().at(-1)!.searchParams.get('price_min_minor')).toBe('137000'));
    expect(screen.getByRole('button', { name: /remove filter: store: amazon/i })).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole('button', { name: /clear all/i })[0]);
    await waitFor(() => {
      const last = api.productCalls().at(-1)!.searchParams;
      expect(last.getAll('marketplace')).toEqual([]);
      expect(last.get('free_shipping')).toBeNull();
      expect(last.get('price_min_minor')).toBeNull();
    });
  });

  it('shows a plain error for a reversed price range instead of querying', async () => {
    imported();
    standardApi();
    renderAt('/products?min=2000&max=1000', routes);
    expect(await screen.findByText(/minimum price is higher than the maximum/i)).toBeInTheDocument();
  });

  it('changes sort and paginates', async () => {
    imported();
    const api = standardApi();
    renderAt('/products', routes);
    await screen.findByText('500 products');
    await userEvent.selectOptions(screen.getByLabelText(/sort by/i), 'price_asc');
    await waitFor(() => expect(api.productCalls().at(-1)!.searchParams.get('sort')).toBe('price_asc'));
    await userEvent.click(screen.getByRole('button', { name: /next page/i }));
    await waitFor(() => expect(api.productCalls().at(-1)!.searchParams.get('page')).toBe('2'));
    expect(currentLocation).toContain('page=2');
    expect(screen.getByText(/page 2 of 21/i)).toBeInTheDocument();
  });

  it('cards link to product details', async () => {
    imported();
    standardApi();
    renderAt('/products', routes);
    await userEvent.click(await screen.findByRole('link', { name: /view details for nike/i }));
    expect(await screen.findByText('detail page')).toBeInTheDocument();
    expect(currentLocation).toBe('/products/MCL0001');
  });

  it('shows a Demo empty state and never falls back to Imported', async () => {
    const api = standardApi();
    renderAt('/products', routes);
    expect(await screen.findByText(/no products in demo data/i)).toBeInTheDocument();
    expect(api.productCalls().every((u) => u.searchParams.get('mode') === 'demo')).toBe(true);
  });

  it('shows an error with a working retry', async () => {
    imported();
    let fail = true;
    mockApi((url) => {
      if (url.pathname === '/api/v1/products/filters') return { body: filtersResponse() };
      if (url.pathname === '/api/v1/products') return fail ? { status: 503, body: { detail: 'The database is unavailable. Try again shortly.' } } : { body: listResponse([item()], 1) };
    });
    renderAt('/products', routes);
    expect(await screen.findByText(/couldn't load products/i)).toBeInTheDocument();
    expect(screen.getByText('The database is unavailable. Try again shortly.')).toBeInTheDocument();
    fail = false;
    await userEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(await screen.findByText('1 product')).toBeInTheDocument();
  });

  it('shows loading placeholders while fetching', async () => {
    imported();
    mockApi((url) => {
      if (url.pathname === '/api/v1/products/filters') return { body: filtersResponse() };
      if (url.pathname === '/api/v1/products') return { body: listResponse([item()], 1), delay: 300 };
    });
    renderAt('/products', routes);
    expect(await screen.findByText(/loading products/i)).toBeInTheDocument();
    expect(await screen.findByText('1 product')).toBeInTheDocument();
  });

  it('ignores a slow older search response when a newer one arrives first', async () => {
    imported();
    mockApi((url) => {
      if (url.pathname === '/api/v1/products/filters') return { body: filtersResponse() };
      if (url.pathname === '/api/v1/products') {
        const q = url.searchParams.get('q');
        if (q === 'old') return { body: listResponse([item({ product_id: 'OLD', name: 'Old result' })], 1), delay: 400 };
        if (q === 'new') return { body: listResponse([item({ product_id: 'NEW', name: 'New result' })], 1), delay: 10 };
        return { body: listResponse([item()], 1) };
      }
    });
    renderAt('/products', routes);
    await screen.findByText('1 product');
    const box = screen.getByRole('searchbox', { name: /search products/i });
    await userEvent.clear(box);
    await userEvent.type(box, 'old{Enter}');
    await userEvent.clear(box);
    await userEvent.type(box, 'new{Enter}');
    expect(await screen.findByText('New result')).toBeInTheDocument();
    await act(() => new Promise((r) => setTimeout(r, 500)));
    expect(screen.queryByText('Old result')).not.toBeInTheDocument();
    expect(screen.getByText('New result')).toBeInTheDocument();
  });

  it('switching workspace shows that workspace only, without stale records', async () => {
    imported();
    const api = standardApi();
    renderAt('/products?page=2', routes, <ModeSwitcher />);
    expect(await screen.findByText("Nike Men's Black Crew-Neck T-Shirt - Size S (Style 001)")).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Demo' }));
    expect(await screen.findByText(/no products in demo data/i)).toBeInTheDocument();
    expect(screen.queryByText("Nike Men's Black Crew-Neck T-Shirt - Size S (Style 001)")).not.toBeInTheDocument();
    const last = api.productCalls().at(-1)!.searchParams;
    expect(last.get('mode')).toBe('demo');
    expect(last.get('page')).toBe('1'); // page selection reset on workspace change
  });

  it('opens the filter drawer on small screens and closes it with Escape', async () => {
    imported();
    standardApi();
    renderAt('/products', routes);
    await screen.findByText('500 products');
    const toggle = screen.getByRole('button', { name: /^filters/i });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('dialog', { name: /filters/i })).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
  });

  it('hides brand, size and colour filters when the data has none', async () => {
    imported();
    standardApi();
    renderAt('/products', routes);
    await screen.findByText('500 products');
    expect(screen.queryByLabelText(/^brand/i)).not.toBeInTheDocument();
    expect(screen.getByText(/brand, size and colour aren't in this dataset/i)).toBeInTheDocument();
  });

  it('is keyboard operable: search, filter and sort controls are reachable by Tab', async () => {
    imported();
    standardApi();
    renderAt('/products', routes);
    await screen.findByText('500 products');
    const user = userEvent.setup();
    const reached = new Set<string>();
    for (let i = 0; i < 40; i++) {
      await user.tab();
      const el = document.activeElement as HTMLInputElement;
      // Record each focused control's accessible label.
      reached.add(el.getAttribute('aria-label') || el.labels?.[0]?.textContent?.trim() || el.textContent?.trim() || el.tagName);
    }
    const all = [...reached].join(' | ');
    expect(all).toMatch(/Search products/i);
    expect(all).toMatch(/Amazon/);
    expect(all).toMatch(/sort/i);
  });

  // ---------- Phase 4 ----------
  it('shows the lowest confirmed delivered price on cards, and flags uncertainty', async () => {
    imported();
    standardApi([
      item(),
      item({ product_id: 'U1', name: 'Uncertain one', lowest_delivered: { amount_minor: 99000, currency: 'INR', marketplaces: ['Amazon'], certain_overall: false } }),
      item({ product_id: 'N1', name: 'No delivered', lowest_delivered: null }),
    ]);
    renderAt('/products', routes);
    const card = (await screen.findByText("Nike Men's Black Crew-Neck T-Shirt - Size S (Style 001)")).closest('article')!;
    expect(within(card).getByText('Lowest confirmed delivered ₹1,430')).toBeInTheDocument();
    expect(screen.getByText(/may not be the cheapest overall/i)).toBeInTheDocument();
    expect(screen.getByText(/delivered price can't be confirmed/i)).toBeInTheDocument();
  });

  it('adds products to the comparison tray and links to the compare page', async () => {
    imported();
    standardApi();
    renderAt('/products', routes);
    await userEvent.click(await screen.findByRole('checkbox', { name: /add nike.* to comparison/i }));
    const tray = screen.getByRole('complementary', { name: /comparison tray/i });
    expect(within(tray).getByText(/nike/i)).toBeInTheDocument();
    expect(within(tray).getByRole('link', { name: /compare \(1\)/i })).toHaveAttribute('href', '/compare?ids=MCL0001');
    await userEvent.click(screen.getByRole('checkbox', { name: /add adidas.* to comparison/i }));
    expect(within(tray).getByRole('link', { name: /compare \(2\)/i })).toHaveAttribute('href', '/compare?ids=MCL0001&ids=MCL0002');
    await userEvent.click(within(tray).getByRole('button', { name: /remove adidas.* from comparison/i }));
    expect(within(tray).getByRole('link', { name: /compare \(1\)/i })).toBeInTheDocument();
    await userEvent.click(within(tray).getByRole('button', { name: /^clear$/i }));
    expect(screen.queryByRole('complementary', { name: /comparison tray/i })).not.toBeInTheDocument();
  });

  it('sorts by confirmed delivered price and filters by advertised discount and known delivery', async () => {
    imported();
    const api = standardApi();
    renderAt('/products', routes);
    await screen.findByText('500 products');
    await userEvent.selectOptions(screen.getByLabelText(/sort by/i), 'delivered_asc');
    await waitFor(() => expect(api.productCalls().at(-1)!.searchParams.get('sort')).toBe('delivered_asc'));
    await userEvent.type(screen.getByLabelText(/minimum discount/i), '30');
    await userEvent.type(screen.getByLabelText(/maximum discount/i), '40');
    await userEvent.click(screen.getByRole('button', { name: /apply discount/i }));
    await waitFor(() => {
      const q = api.productCalls().at(-1)!.searchParams;
      expect(q.get('discount_min')).toBe('30');
      expect(q.get('discount_max')).toBe('40');
    });
    expect(screen.getByRole('button', { name: /remove filter: advertised discount 30–40%/i })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('checkbox', { name: /confirmed delivered price only/i }));
    await waitFor(() => expect(api.productCalls().at(-1)!.searchParams.get('delivered_known')).toBe('true'));
  });
});
