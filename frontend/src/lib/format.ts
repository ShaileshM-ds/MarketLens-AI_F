// Readable dates and counts (never raw ISO strings in the UI). Money: see money.ts.

const dateTime = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
  timeZone: 'UTC',
});
const count = new Intl.NumberFormat('en-IN');

/** "5 Nov 2026, 13:37 UTC". Blank when unknown. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : `${dateTime.format(d)} UTC`;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/**
 * Observation time as readable text. A timestamp without a timezone is shown as
 * the stated clock time, never converted or assumed to be UTC.
 */
export function formatObservedAt(sourceTimestamp: string | null | undefined, quality: string | null | undefined, observedAtIso?: string | null): string {
  if (quality && quality !== 'timezone_unknown' && observedAtIso) return formatDateTime(observedAtIso);
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(sourceTimestamp ?? '');
  if (!m) return sourceTimestamp ?? '';
  return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}, ${m[4]}:${m[5]} (timezone not stated)`;
}

export function formatRating(n: number | null | undefined): string {
  return n === null || n === undefined ? '' : n.toFixed(1);
}

export function formatCount(n: number | null | undefined): string {
  return n === null || n === undefined ? '' : count.format(n);
}

export function formatBytes(n: number): string {
  if (n < 1000) return `${n} bytes`;
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)} KB`;
  return `${(n / 1_000_000).toFixed(1)} MB`;
}
