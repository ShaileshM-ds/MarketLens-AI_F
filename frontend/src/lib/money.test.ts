import { describe, expect, it } from 'vitest';
import { formatMoney, parseMajorToMinor } from './money';

describe('shared money formatter', () => {
  it('formats integer minor units', () => {
    expect(formatMoney(138000)).toBe('₹1,380');
    expect(formatMoney(29)).toBe('₹0.29');
    expect(formatMoney(138050)).toBe('₹1,380.50');
    expect(formatMoney(0)).toBe('₹0');
  });
  it('keeps unknown blank', () => {
    expect(formatMoney(null)).toBe('');
    expect(formatMoney(undefined)).toBe('');
  });
  it('handles zero-decimal currencies', () => {
    expect(formatMoney(1380, 'JPY')).toMatch(/1,380/);
  });
  it('parses rupee input exactly', () => {
    expect(parseMajorToMinor('0.29')).toBe(29);
    expect(parseMajorToMinor('1,380')).toBe(138000);
    expect(parseMajorToMinor('1380.555')).toBeNull();
    expect(parseMajorToMinor('-1')).toBeNull();
  });
});
