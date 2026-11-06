import { QueryClient } from '@tanstack/react-query';
import { ApiError } from './api';

/** Client errors (404 not found, 409 unavailable mode, 422 bad input) are answers, not glitches: never retry them. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status < 500) return false;
  return failureCount < 1;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { staleTime: 60_000, retry: shouldRetry, refetchOnWindowFocus: false } },
  });
}
