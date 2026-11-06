import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ComparePage } from './ComparePage';
import { currentLocation, mockApi, renderAt } from '../test/render';
import { compareProduct, compareResponse, item, listResponse } from '../test/fixtures';

const routes = [{ path: '/compare', element: <ComparePage /> }];

function api(products = [compareProduct('MCL0001', 'Nike Tee'), compareProduct('MCL0002', 'Adidas Shirt')], extra: Partial<ReturnType<typeof compareResponse>> = {}) {
  window.localStorage.setItem('ml-data-mode', 'imported');
  return mockApi((url) => {
    if (url.pathname === '/api/v1/compare') {
      const ids = url.searchParams.getAll('ids');
      return { body: { ...compareResponse(products.filter((p) => ids.includes(p.product_id))), ...extra } };
    }
    if (url.pathname === '/api/v1/products') return { body: listResponse([item({ product_id: 'MCL0003', name: 'Puma Jacket' })], 1) };
  });
}

describe('Compare products', () => {
  it('shows selected products side by side with the three price measures', async () => {
    api();
    renderAt('/compare?ids=MCL0001&ids=MCL0002', routes);
    expect(await screen.findByRole('heading', { level: 1, name: 'Compare products' })).toBeInTheDocument();
    const table = await screen.findByRole('table');
    expect(within(table).getByText('Nike Tee')).toBeInTheDocument();
    expect(within(table).getByText('Adidas Shirt')).toBeInTheDocument();
    for (const label of ['Lowest listed price', 'Lowest confirmed delivered price', 'Lowest confirmed delivered price (available offers)', 'Reference price (seller-provided)', 'Advertised discount', 'Calculated reduction from reference']) {
      expect(within(table).getByRole('rowheader', { name: label })).toBeInTheDocument();
    }
    expect(within(table).getAllByText('₹1,370').length).toBeGreaterThan(0);
    expect(within(table).getAllByText('₹1,430').length).toBeGreaterThan(0);
    expect(screen.getByRole('region', { name: /product comparison table/i })).toHaveAttribute('tabindex', '0');
    expect(screen.getAllByText(/synthetic dataset/i).length).toBeGreaterThan(0);
  });

  it('removes a product and updates the address', async () => {
    api();
    renderAt('/compare?ids=MCL0001&ids=MCL0002', routes);
    await userEvent.click(await screen.findByRole('button', { name: 'Remove Nike Tee from comparison' }));
    await waitFor(() => expect(currentLocation).toBe('/compare?ids=MCL0002'));
    expect(await screen.findByText('Adidas Shirt')).toBeInTheDocument();
    expect(screen.queryByText('Nike Tee')).not.toBeInTheDocument();
  });

  it('adds a product from search and can replace one in place', async () => {
    api([compareProduct('MCL0001', 'Nike Tee'), compareProduct('MCL0002', 'Adidas Shirt'), compareProduct('MCL0003', 'Puma Jacket')]);
    renderAt('/compare?ids=MCL0001&ids=MCL0002', routes);
    await screen.findByText('Nike Tee');
    await userEvent.type(screen.getByLabelText(/find a product to add/i), 'puma');
    await userEvent.click(await screen.findByRole('button', { name: 'Add Puma Jacket to comparison' }));
    await waitFor(() => expect(currentLocation).toBe('/compare?ids=MCL0001&ids=MCL0002&ids=MCL0003'));
    await userEvent.click(screen.getByRole('button', { name: 'Replace Nike Tee' }));
    await userEvent.clear(screen.getByLabelText(/find a product to add/i));
    await userEvent.type(screen.getByLabelText(/find a product to add/i), 'puma');
    // Puma is already compared, so trying to use it as Nike's replacement is refused with a reason.
    await userEvent.click(await screen.findByRole('button', { name: 'Replace Nike Tee with Puma Jacket' }));
    expect(await screen.findByText(/already in the comparison/i)).toBeInTheDocument();
    expect(currentLocation).toBe('/compare?ids=MCL0001&ids=MCL0002&ids=MCL0003');
  });

  it('explains the four-product limit', async () => {
    const four = ['MCL0001', 'MCL0002', 'MCL0004', 'MCL0005'].map((id) => compareProduct(id, `P ${id}`));
    api(four);
    renderAt('/compare?ids=MCL0001&ids=MCL0002&ids=MCL0004&ids=MCL0005', routes);
    await screen.findByText('P MCL0001');
    expect(screen.getByText(/comparing 4 products, the maximum/i)).toBeInTheDocument();
  });

  it('clears the comparison', async () => {
    api();
    renderAt('/compare?ids=MCL0001&ids=MCL0002', routes);
    await screen.findByText('Nike Tee');
    await userEvent.click(screen.getByRole('button', { name: /clear comparison/i }));
    expect(await screen.findByText(/no products selected/i)).toBeInTheDocument();
    expect(currentLocation).toBe('/compare');
  });

  it('shows comparability warnings and products missing from the workspace', async () => {
    api(undefined, { missing: ['NOPE'], comparability_warnings: ['These products are in different sub-categories (Jeans, T-Shirts), so they may not be like-for-like.'] });
    renderAt('/compare?ids=MCL0001&ids=NOPE', routes);
    expect(await screen.findByText(/different sub-categories/i)).toBeInTheDocument();
    expect(screen.getByText(/NOPE isn't in Imported data/i)).toBeInTheDocument();
  });

  it('says when nothing is selected', async () => {
    api();
    renderAt('/compare', routes);
    expect(await screen.findByText(/no products selected/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /product explorer/i })).toBeInTheDocument();
  });
});
