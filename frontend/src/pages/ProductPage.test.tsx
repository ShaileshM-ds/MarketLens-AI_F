import { describe, expect, it } from 'vitest';
import { screen, within } from '@testing-library/react';
import { ProductPage } from './ProductPage';
import { mockApi, renderAt } from '../test/render';
import { detail, pricing, reviewsResponse } from '../test/fixtures';
import userEvent from '@testing-library/user-event';

const routes = [{ path: '/products/:productId', element: <ProductPage /> }];

function api(body = detail(), reviews = reviewsResponse(), status = 200) {
  window.localStorage.setItem('ml-data-mode', 'imported');
  return mockApi((url) => {
    if (url.pathname.endsWith('/reviews')) return { body: reviews };
    if (url.pathname.startsWith('/api/v1/products/')) return { status, body };
  });
}

function offerCard(store: string) {
  return screen.getByRole('heading', { name: store, level: 3 }).closest('article')!;
}

describe('Product details', () => {
  it('shows each store with exact base price, shipping and known total', async () => {
    api();
    renderAt('/products/MCL0001', routes);
    expect(await screen.findByRole('heading', { level: 1, name: /Nike Men's Black Crew-Neck/ })).toBeInTheDocument();
    const amazon = offerCard('Amazon');
    expect(within(amazon).getByText('₹1,380')).toBeInTheDocument();
    expect(within(amazon).getByText('₹60')).toBeInTheDocument();
    expect(within(amazon).getByText('₹1,440')).toBeInTheDocument();
    expect(within(amazon).getByText('CLSEL00001')).toBeInTheDocument();
    expect(within(amazon).getByText('AMA-CLO-LIST-000001')).toBeInTheDocument();
    const flipkart = offerCard('Flipkart');
    // Phase 4 replaced the Phase 3 badges with the three explicit designations.
    expect(within(flipkart).getByText('Lowest listed price')).toBeInTheDocument();
    expect(within(flipkart).getByText('Lowest confirmed delivered price')).toBeInTheDocument();
    expect(within(flipkart).getByText('Lowest confirmed delivered (available)')).toBeInTheDocument();
    const myntra = offerCard('Myntra');
    expect(within(myntra).getByText('Free')).toBeInTheDocument();
    expect(within(myntra).getByText('₹1,480', { selector: '.offer__total' })).toBeInTheDocument();
    expect(screen.getByText('₹1,370', { selector: '.summary__value' })).toBeInTheDocument();
    expect(screen.getAllByText('₹1,430', { selector: '.summary__value' })).toHaveLength(2);
  });

  it('keeps unknown shipping visibly unknown and labels out-of-stock and contradictions', async () => {
    api(
      detail([
        {
          listing_id: 'X-1', marketplace: 'Ajio', seller_id: 'S9', price_minor: 120000, shipping_minor: null, shipping_known: false, total_minor: null,
          warnings: [{ code: 'shipping_unknown', message: "Shipping cost isn't stated, so the delivered total is unknown." }],
        },
        {
          listing_id: 'X-2', marketplace: 'Tata', seller_id: 'S10', price_minor: 110000, shipping_minor: 0, total_minor: 110000, free_shipping: true,
          availability: 'Out of Stock', availability_class: 'out_of_stock', stock_quantity: 25, purchasable: false,
          warnings: [{ code: 'stock_availability_contradiction', message: 'Availability and reported stock quantity disagree.' }],
        },
      ]),
    );
    renderAt('/products/MCL0001', routes);
    const ajio = (await screen.findByRole('heading', { name: 'Ajio', level: 3 })).closest('article')!;
    // Phase 4 wording: unknown values read "Unknown"; "Total incomplete" stays (CLAUDE.md rule).
    expect(within(ajio).getByText('Unknown')).toBeInTheDocument();
    expect(within(ajio).getByText('Total incomplete')).toBeInTheDocument();
    expect(within(ajio).getByText(/delivered total can't be confirmed/i)).toBeInTheDocument();
    expect(within(ajio).queryByText('Free')).not.toBeInTheDocument();
    const tata = offerCard('Tata');
    expect(within(tata).getByText('Out of stock')).toBeInTheDocument();
    expect(within(tata).getByText('Availability and reported stock quantity disagree.')).toBeInTheDocument();
    expect(within(tata).getByText('25')).toBeInTheDocument(); // stock shown as supplied, not corrected
  });

  it('shows the observation time with its timezone status and no store link when none is stored', async () => {
    api();
    renderAt('/products/MCL0001', routes);
    const amazon = (await screen.findByRole('heading', { name: 'Amazon', level: 3 })).closest('article')!;
    expect(within(amazon).getByText(/4 Nov 2026, 10:30 \(timezone not stated\)/)).toBeInTheDocument();
    expect(within(amazon).getByText(/no store link in this dataset/i)).toBeInTheDocument();
    expect(within(amazon).queryByRole('link', { name: /visit/i })).not.toBeInTheDocument();
  });

  it('shows the price-history empty state and never draws a chart', async () => {
    api();
    const { container } = renderAt('/products/MCL0001', routes);
    expect(await screen.findByRole('heading', { name: 'Price History' })).toBeInTheDocument();
    // Phase 4 brief §9 sets the exact message.
    expect(screen.getByText(/verified historical price data is not available for this product yet/i)).toBeInTheDocument();
    expect(container.querySelector('svg.chart, canvas')).toBeNull();
  });

  it('shows synthetic disclosure and reviews as plain text with separate rating kinds', async () => {
    api();
    renderAt('/products/MCL0001', routes);
    expect((await screen.findAllByText(/synthetic demonstration data/i)).length).toBeGreaterThan(0);
    expect(await screen.findByText('<b>Not bold</b> plain text only')).toBeInTheDocument();
    expect(document.querySelector('.review b')).toBeNull();
    expect(screen.getByText('Review rating 3 / 5')).toBeInTheDocument();
    expect(screen.getByText('Synthetic sample review')).toBeInTheDocument();
    expect(screen.getByText(/average review rating 4.00 \/ 5 from 3 reviews/i)).toBeInTheDocument();
    const amazon = offerCard('Amazon');
    expect(within(amazon).getByText('Seller rating')).toBeInTheDocument();
    expect(within(amazon).getByText('Product rating (this store)')).toBeInTheDocument();
  });

  it('says when a product is not in the active workspace', async () => {
    api({ detail: "No product 'MCL0001' in Imported data." } as never, reviewsResponse([]), 404);
    renderAt('/products/MCL0001', routes);
    expect(await screen.findByText(/product not found/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /back to product explorer/i })).toBeInTheDocument();
  });

  it('shows the reviews empty state', async () => {
    api(detail(), reviewsResponse([]));
    renderAt('/products/MCL0001', routes);
    expect(await screen.findByText(/no reviews for this product/i)).toBeInTheDocument();
  });

  // ---------- Phase 4: price intelligence ----------
  it('shows the three lowest-price measures with their meaning', async () => {
    api();
    renderAt('/products/MCL0001', routes);
    const section = (await screen.findByRole('heading', { name: 'Delivered price comparison' })).closest('section')!;
    expect(within(section).getByText('Lowest listed price')).toBeInTheDocument();
    expect(within(section).getByText('Lowest confirmed delivered price')).toBeInTheDocument();
    expect(within(section).getByText('Lowest confirmed delivered price among offers marked available')).toBeInTheDocument();
    expect(within(section).getAllByText('Designation note.').length).toBe(3);
    expect(within(section).getByText(/coupons and payment offers are conditional and never subtracted/i)).toBeInTheDocument();
  });

  it('warns when the cheapest delivered price overall cannot be determined', async () => {
    api(detail([], { pricing: pricing({ lowest_confirmed_delivered: { amount_minor: 143000, currency: 'INR', listing_ids: ['F'], marketplaces: ['Flipkart'], considered_count: 2, certain_overall: false, note: '1 listing(s) with unknown shipping have a lower base price.' } }) }));
    renderAt('/products/MCL0001', routes);
    expect(await screen.findByText(/cheapest delivered price overall can't be determined/i)).toBeInTheDocument();
  });

  it('charts confirmed delivered prices and price composition from stored values, with a table view', async () => {
    api(detail([{ listing_id: 'X-1', marketplace: 'Ajio', seller_id: 'S9', price_minor: 120000, shipping_minor: null, shipping_known: false, total_minor: null }]));
    renderAt('/products/MCL0001', routes);
    const chart = (await screen.findByRole('figure', { name: /confirmed delivered price by store/i }));
    expect(within(chart).getByText('Ajio')).toBeInTheDocument();
    expect(within(chart).getByText(/shipping unknown, not charted/i)).toBeInTheDocument();
    await userEvent.click(within(chart).getByRole('button', { name: 'Table' }));
    const table = within(chart).getByRole('table');
    expect(within(table).getByText('₹1,440')).toBeInTheDocument();
    expect(within(table).getByText('₹1,430')).toBeInTheDocument();
    const comp = screen.getByRole('figure', { name: /price composition/i });
    expect(within(comp).getAllByText(/base price/i).length).toBeGreaterThan(0);
    expect(within(comp).getAllByText(/shipping/i).length).toBeGreaterThan(0);
  });

  it('separates advertised discount, calculated reduction and conditional offers', async () => {
    api(detail([{ listing_id: 'X-1', marketplace: 'Ajio', seller_id: 'S9', price_minor: 128000, advertised_discount_percent: 26.25, coupon_discount_minor: 15000, payment_offer: 'Eligible UPI offer: 5% up to ₹300' }]));
    renderAt('/products/MCL0001', routes);
    const section = (await screen.findByRole('heading', { name: 'Discount transparency' })).closest('section')!;
    const row = within(section).getByRole('row', { name: /^Ajio/ });
    expect(within(row).getByText('₹1,600')).toBeInTheDocument();
    expect(within(row).getByText('₹1,280')).toBeInTheDocument();
    expect(within(row).getByText('26.25%')).toBeInTheDocument();
    expect(within(row).getByText('20.00%')).toBeInTheDocument();
    expect(within(row).getByText(/differs by 6.25 points/i)).toBeInTheDocument();
    expect(within(section).getAllByText(/seller-provided reference price/i).length).toBeGreaterThan(0);
    expect(within(section).getByText(/₹150 coupon/)).toBeInTheDocument();
    expect(within(section).getAllByText(/not included in any total/i).length).toBeGreaterThan(0);
  });

  it('reports availability as a snapshot fact and keeps contradictions visible', async () => {
    api(detail([{ listing_id: 'X-2', marketplace: 'Tata', seller_id: 'S10', price_minor: 110000, availability: 'Out of Stock', availability_class: 'out_of_stock', stock_quantity: 25, purchasable: false, flags: ['stock_availability_contradiction'], warnings: [{ code: 'stock_availability_contradiction', message: 'Availability and reported stock quantity disagree.' }] }], { availability_summary: { in_stock: 3, limited_stock: 0, out_of_stock: 1, unknown: 0, contradictions: 1 } }));
    renderAt('/products/MCL0001', routes);
    const section = (await screen.findByRole('heading', { name: 'Stock and availability' })).closest('section')!;
    expect(within(section).getAllByText(/availability reported in imported snapshot/i).length).toBeGreaterThan(0);
    expect(within(section).getByText(/1 listing's availability disagrees with its stock quantity/i)).toBeInTheDocument();
    expect(within(screen.getByRole('figure', { name: /listings by reported availability/i })).getByText('Out of stock')).toBeInTheDocument();
  });

  it('shows data-quality labels, the new history message and section navigation', async () => {
    api();
    renderAt('/products/MCL0001', routes);
    const prov = (await screen.findByRole('heading', { name: 'Data provenance' })).closest('section')!;
    for (const l of ['Synthetic dataset', 'Timezone unknown', 'Missing product metadata']) expect(within(prov).getByText(l)).toBeInTheDocument();
    expect(screen.getByText('Verified historical price data is not available for this product yet. Current comparisons use imported snapshot observations.')).toBeInTheDocument();
    const nav = screen.getByRole('navigation', { name: 'Product sections' });
    expect(within(nav).getByRole('link', { name: 'Delivered prices' })).toHaveAttribute('href', '#delivered');
    expect(screen.getByRole('figure', { name: /ratings by store/i })).toBeInTheDocument();
  });

  it('expands offer details and adds the product to the comparison', async () => {
    api();
    renderAt('/products/MCL0001', routes);
    const amazon = (await screen.findByRole('heading', { name: 'Amazon', level: 3 })).closest('article')!;
    const more = amazon.querySelector('details')!;
    expect(more.open).toBe(false);
    await userEvent.click(within(amazon).getByText('More details'));
    expect(more.open).toBe(true);
    await userEvent.click(screen.getByRole('button', { name: /add to comparison/i }));
    expect(await screen.findByRole('link', { name: /compare \(1\)/i })).toHaveAttribute('href', '/compare?ids=MCL0001');
    expect(screen.getByRole('button', { name: /in comparison/i })).toBeInTheDocument();
  });
});
