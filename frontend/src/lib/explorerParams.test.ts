import { describe, expect, it } from 'vitest';
import { activeChips, clearAll, readState, toApiParams, withParam } from './explorerParams';

const p = (s: string) => new URLSearchParams(s);

describe('explorer URL state', () => {
  it('reads defaults', () => {
    const s = readState(p(''));
    expect(s).toMatchObject({ q: '', category: '', marketplaces: [], sort: 'name_asc', page: 1, view: 'grid', freeShipping: false });
  });

  it('reads repeated and bounded values', () => {
    const s = readState(p('marketplace=Amazon&marketplace=Myntra&availability=in_stock&page=3&sort=price_desc&free=1&prating=4'));
    expect(s.marketplaces).toEqual(['Amazon', 'Myntra']);
    expect(s.availability).toEqual(['in_stock']);
    expect(s.page).toBe(3);
    expect(s.sort).toBe('price_desc');
    expect(s.freeShipping).toBe(true);
    expect(s.productRatingMin).toBe('4');
    expect(readState(p('page=-2&sort=popular')).page).toBe(1);
    expect(readState(p('sort=popular')).sort).toBe('name_asc');
  });

  it('any filter change resets pagination', () => {
    const next = withParam(p('q=shirt&page=4'), 'marketplace', ['Amazon']);
    expect(next.get('page')).toBeNull();
    expect(next.getAll('marketplace')).toEqual(['Amazon']);
    expect(next.get('q')).toBe('shirt');
    expect(withParam(p('page=4'), 'sort', 'price_asc').get('page')).toBeNull();
  });

  it('page changes keep filters', () => {
    const next = withParam(p('q=shirt'), 'page', '2');
    expect(next.get('page')).toBe('2');
    expect(next.get('q')).toBe('shirt');
  });

  it('clear all removes search and filters but keeps sort and view', () => {
    const next = clearAll(p('q=a&category=mens-clothing&marketplace=Amazon&min=10&free=1&sort=price_asc&view=table&page=2'));
    expect(next.toString()).toBe('sort=price_asc&view=table');
  });

  it('converts rupee inputs to minor units at the boundary', () => {
    const r = toApiParams(readState(p('min=1370&max=1,380.50')), 'imported', 'INR');
    expect(r.error).toBeNull();
    expect(r.params.get('price_min_minor')).toBe('137000');
    expect(r.params.get('price_max_minor')).toBe('138050');
    expect(r.params.get('currency')).toBe('INR');
    expect(toApiParams(readState(p('min=0.29')), 'imported', 'INR').params.get('price_min_minor')).toBe('29');
  });

  it('rejects invalid or reversed price ranges without calling the API', () => {
    expect(toApiParams(readState(p('min=abc')), 'imported', 'INR').error).toMatch(/minimum price/i);
    expect(toApiParams(readState(p('min=2000&max=1000')), 'imported', 'INR').error).toMatch(/higher than/i);
  });

  it('maps every filter to API parameters', () => {
    const r = toApiParams(
      readState(p('q=crew&category=mens-clothing&marketplace=Amazon&availability=out_of_stock&prating=4&srating=4.5&free=1&sort=rating_desc&page=2')),
      'imported',
      'INR',
    );
    const q = r.params;
    expect(q.get('mode')).toBe('imported');
    expect(q.get('q')).toBe('crew');
    expect(q.get('category')).toBe('mens-clothing');
    expect(q.getAll('marketplace')).toEqual(['Amazon']);
    expect(q.getAll('availability')).toEqual(['out_of_stock']);
    expect(q.get('product_rating_min')).toBe('4');
    expect(q.get('seller_rating_min')).toBe('4.5');
    expect(q.get('free_shipping')).toBe('true');
    expect(q.get('sort')).toBe('rating_desc');
    expect(q.get('page')).toBe('2');
    expect(q.get('page_size')).toBe('24');
  });

  it('lists active filter chips with money shown through the shared formatter', () => {
    const chips = activeChips(readState(p('q=crew&marketplace=Amazon&min=1370&free=1')), { categoryLabel: () => '' });
    expect(chips.map((c) => c.label)).toEqual(['Search: crew', 'Store: Amazon', 'Base price from ₹1,370', 'Known free shipping']);
  });
});
