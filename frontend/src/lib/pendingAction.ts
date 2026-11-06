/**
 * A signed-out "Watch" / "Track price" tap is remembered for this tab and resumed after sign-in (SCOPE §5).
 * Session storage only: it never outlives the tab and holds no personal data.
 */
const KEY = 'ml-pending-action';

export interface PendingWatch {
  type: 'watch';
  mode: string;
  productId: string;
}

export function savePending(action: PendingWatch): void {
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify(action));
  } catch {
    /* storage blocked: the user simply repeats the tap after signing in */
  }
}

export function takePending(): PendingWatch | null {
  try {
    const raw = window.sessionStorage.getItem(KEY);
    window.sessionStorage.removeItem(KEY);
    const v = raw ? JSON.parse(raw) : null;
    return v && v.type === 'watch' && typeof v.productId === 'string' && typeof v.mode === 'string' ? v : null;
  } catch {
    return null;
  }
}

/** Only same-site paths are allowed as a return address. */
export function safeNext(next: string | null): string {
  return next && next.startsWith('/') && !next.startsWith('//') ? next : '/';
}
