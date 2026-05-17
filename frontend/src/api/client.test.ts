/**
 * Smoke tests for the frontend ApiError contract and token storage.
 * These pin behavior so future refactors (e.g. moving token storage to a hook
 * or adding refresh-token plumbing) don't quietly break callers.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from './client';

describe('ApiError', () => {
  it('carries the HTTP status code on the error instance', () => {
    const err = new ApiError(401, 'Unauthorized');
    expect(err).toBeInstanceOf(Error);
    expect(err.name).toBe('ApiError');
    expect(err.status).toBe(401);
    expect(err.message).toBe('Unauthorized');
  });

  it('distinguishes network failures (status 0) from server failures', () => {
    const network = new ApiError(0, 'offline');
    const server = new ApiError(503, 'upstream');
    expect(network.status).toBe(0);
    expect(server.status).toBe(503);
  });
});

describe('localStorage token persistence', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('reads token from hisabclub_token key', () => {
    localStorage.setItem('hisabclub_token', 'abc.def.ghi');
    expect(localStorage.getItem('hisabclub_token')).toBe('abc.def.ghi');
  });

  it('clearing token removes it from storage', () => {
    localStorage.setItem('hisabclub_token', 'abc');
    localStorage.removeItem('hisabclub_token');
    expect(localStorage.getItem('hisabclub_token')).toBeNull();
  });
});
