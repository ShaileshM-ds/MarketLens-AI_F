import { describe, expect, it } from 'vitest';
import { ApiError } from './api';
import { shouldRetry } from './queryClient';

describe('query retry policy', () => {
  it('never retries client errors such as 404 or 422', () => {
    expect(shouldRetry(0, new ApiError(404, 'No product'))).toBe(false);
    expect(shouldRetry(0, new ApiError(422, 'Bad input'))).toBe(false);
    expect(shouldRetry(0, new ApiError(409, 'Live data is off'))).toBe(false);
  });
  it('retries server and network errors once', () => {
    expect(shouldRetry(0, new ApiError(503, 'Database unavailable'))).toBe(true);
    expect(shouldRetry(0, new TypeError('Failed to fetch'))).toBe(true);
    expect(shouldRetry(1, new ApiError(503, 'Database unavailable'))).toBe(false);
  });
});
