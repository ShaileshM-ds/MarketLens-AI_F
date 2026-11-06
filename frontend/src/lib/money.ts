/**
 * THE shared money formatter (CLAUDE.md: Money).
 *
 * Prices are stored as integer minor units (₹1,380 = 138000). Chart axes,
 * tooltips, tables, filters and inputs must all display money through
 * formatMoney, and convert user input (entered in rupees) through
 * parseMajorToMinor. Do not format money anywhere else.
 */

const formatters = new Map<string, Intl.NumberFormat>();

function getFormatter(currency: string, fractionDigits?: number): Intl.NumberFormat {
  const key = `${currency}:${fractionDigits ?? 'default'}`;
  let f = formatters.get(key);
  if (!f) {
    f = new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency,
      currencyDisplay: 'narrowSymbol',
      ...(fractionDigits === undefined
        ? {}
        : { minimumFractionDigits: fractionDigits, maximumFractionDigits: fractionDigits }),
    });
    formatters.set(key, f);
  }
  return f;
}

/** Number of minor-unit digits for a currency: INR 2, JPY 0. */
export function minorUnitDigits(currency = 'INR'): number {
  return getFormatter(currency).resolvedOptions().maximumFractionDigits ?? 2;
}

/**
 * Format an amount in minor units. Unknown amounts return '' (blank), never 0.
 * Whole amounts drop the fraction (₹1,380); others keep it (₹1,380.50).
 */
export function formatMoney(minor: number | null | undefined, currency = 'INR'): string {
  if (minor === null || minor === undefined || !Number.isFinite(minor)) return '';
  const digits = minorUnitDigits(currency);
  const scale = 10 ** digits;
  const whole = minor % scale === 0;
  return getFormatter(currency, whole ? 0 : digits).format(minor / scale);
}

/**
 * Convert a user-typed major-unit amount (rupees for INR) to minor units.
 * Returns null when the input is not a valid non-negative amount.
 */
export function parseMajorToMinor(input: string, currency = 'INR'): number | null {
  const cleaned = input.replace(/[₹,\s]/g, '');
  if (!/^\d+(\.\d+)?$/.test(cleaned)) return null;
  const digits = minorUnitDigits(currency);
  const [intPart, fracPart = ''] = cleaned.split('.');
  if (fracPart.length > digits) return null;
  const frac = digits === 0 ? 0 : Number(fracPart.padEnd(digits, '0'));
  return Number(intPart) * 10 ** digits + frac;
}
