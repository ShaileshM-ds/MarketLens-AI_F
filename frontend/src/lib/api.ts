import type { DataMode } from './dataMode';

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public problems: string[] = [],
  ) {
    super(message);
  }
}

async function toError(res: Response): Promise<ApiError> {
  try {
    const body = await res.json();
    const d = body?.detail;
    if (typeof d === 'string') return new ApiError(res.status, d);
    if (d && typeof d.message === 'string') return new ApiError(res.status, d.message, Array.isArray(d.problems) ? d.problems : []);
    if (Array.isArray(d)) return new ApiError(res.status, 'Some values were not accepted.', d.map((x) => String(x?.msg ?? x)));
  } catch {
    /* not JSON */
  }
  return new ApiError(res.status, res.statusText || `Request failed (${res.status})`);
}

export async function apiGet<T>(path: string, params?: Record<string, string> | URLSearchParams): Promise<T> {
  const url = new URL(path, window.location.origin);
  if (params instanceof URLSearchParams) params.forEach((v, k) => url.searchParams.append(k, v));
  else if (params) for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
  const res = await fetch(url, { headers: { Accept: 'application/json' }, credentials: 'same-origin' });
  if (!res.ok) throw await toError(res);
  return res.json() as Promise<T>;
}

/** POST/PUT/DELETE with a JSON body, or FormData for uploads. */
export async function apiSend<T>(method: 'POST' | 'PUT' | 'PATCH' | 'DELETE', path: string, body?: unknown): Promise<T> {
  const isForm = body instanceof FormData;
  const res = await fetch(path, {
    method,
    credentials: 'same-origin',
    headers: isForm ? { Accept: 'application/json' } : { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
  });
  if (!res.ok) throw await toError(res);
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export interface ModeStatus {
  database: string;
  available: boolean;
  reason: string | null;
}

export interface Health {
  status: 'ok' | 'degraded';
  service: string;
  version: string;
  checked_at: string;
  mongo: 'ok' | 'unavailable';
  modes: Record<DataMode, ModeStatus>;
}

/** Health returns 503 with a body when MongoDB is down; keep that body. */
export async function fetchHealth(): Promise<Health> {
  const res = await fetch('/api/v1/health', { headers: { Accept: 'application/json' } });
  if (res.ok || res.status === 503) return res.json() as Promise<Health>;
  throw await toError(res);
}

export interface CategoryCount {
  slug: string;
  label: string;
  product_count: number;
}

export function fetchCategories(mode: DataMode) {
  return apiGet<{ mode: DataMode; categories: CategoryCount[] }>('/api/v1/categories', { mode });
}
