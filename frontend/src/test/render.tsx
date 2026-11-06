import type { ReactElement } from 'react';
import { render } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { vi } from 'vitest';
import { ThemeProvider } from '../lib/theme';
import { DataModeProvider } from '../lib/dataMode';
import { CompareProvider } from '../lib/compareSelection';
import { health } from './fixtures';

export interface MockRequest {
  url: URL;
  method: string;
  body: unknown;
}
export type Handler = (url: URL, req: MockRequest) => { status?: number; body: unknown; delay?: number } | undefined;

/** Routes fetch() calls to handlers; records every request (URL, method, JSON body). */
export function mockApi(handler: Handler) {
  const calls: URL[] = [];
  const requests: MockRequest[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://localhost');
    let body: unknown = undefined;
    if (typeof init?.body === 'string') {
      try {
        body = JSON.parse(init.body);
      } catch {
        body = init.body;
      }
    }
    const req = { url, method: (init?.method ?? 'GET').toUpperCase(), body };
    calls.push(url);
    requests.push(req);
    const res = url.pathname === '/api/v1/health' ? { body: health } : handler(url, req);
    if (!res) return new Response(JSON.stringify({ detail: 'not mocked' }), { status: 500 });
    if (res.delay) await new Promise((r) => setTimeout(r, res.delay));
    if (res.status === 204) return new Response(null, { status: 204 });
    return new Response(JSON.stringify(res.body), { status: res.status ?? 200, headers: { 'Content-Type': 'application/json' } });
  });
  vi.stubGlobal('fetch', fetchMock);
  return {
    calls,
    requests,
    fetchMock,
    productCalls: () => calls.filter((u) => u.pathname === '/api/v1/products'),
    sent: (method: string, path: string) => requests.filter((r) => r.method === method && r.url.pathname === path),
  };
}

export let currentLocation = '';
function LocationProbe() {
  const loc = useLocation();
  currentLocation = loc.pathname + loc.search;
  return null;
}

export function renderAt(path: string, routes: { path: string; element: ReactElement }[], extra?: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeProvider>
        <DataModeProvider>
          <CompareProvider>
          <MemoryRouter initialEntries={[path]}>
            {extra}
            <LocationProbe />
            <Routes>
              {routes.map((r) => (
                <Route key={r.path} path={r.path} element={r.element} />
              ))}
              <Route path="*" element={<p>other page</p>} />
            </Routes>
          </MemoryRouter>
          </CompareProvider>
        </DataModeProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}
