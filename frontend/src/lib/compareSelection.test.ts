import { describe, expect, it } from 'vitest';
import { MAX_COMPARE, addItem, removeItem, replaceItem, storageKey } from './compareSelection';

const a = { id: 'MCL0001', name: 'A' };
const b = { id: 'MCL0002', name: 'B' };
const c = { id: 'MCL0003', name: 'C' };
const d = { id: 'MCL0004', name: 'D' };
const e = { id: 'MCL0005', name: 'E' };

describe('comparison selection', () => {
  it('adds up to the maximum and explains when full', () => {
    let list = [a, b, c, d];
    expect(MAX_COMPARE).toBe(4);
    const r = addItem(list, e);
    expect(r.list).toEqual(list);
    expect(r.error).toMatch(/up to 4 products/i);
    list = addItem([a], b).list;
    expect(list.map((x) => x.id)).toEqual(['MCL0001', 'MCL0002']);
  });

  it('ignores duplicates by stable product ID, never by name', () => {
    expect(addItem([a], { id: 'MCL0001', name: 'Renamed' }).list).toEqual([a]);
    expect(addItem([a], { id: 'MCL0009', name: 'A' }).list).toHaveLength(2);
  });

  it('removes and replaces in place', () => {
    expect(removeItem([a, b, c], 'MCL0002')).toEqual([a, c]);
    const r = replaceItem([a, b, c], 'MCL0002', d);
    expect(r.list).toEqual([a, d, c]);
    expect(replaceItem([a, b], 'MCL0002', a).error).toMatch(/already/i);
  });

  it('keeps a separate selection per workspace', () => {
    expect(storageKey('imported')).not.toBe(storageKey('demo'));
  });
});
