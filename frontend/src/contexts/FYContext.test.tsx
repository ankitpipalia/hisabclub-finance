import { act, renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, beforeEach } from 'vitest';
import { FYProvider, fyForDate, SUPPORTED_FYS, useFY } from './FYContext';

function wrapper({ children }: { children: ReactNode }) {
  return <FYProvider>{children}</FYProvider>;
}

describe('fyForDate', () => {
  it('returns the FY that contains the given date (April-March)', () => {
    expect(fyForDate(new Date('2024-04-01'))).toBe('FY24-25');
    expect(fyForDate(new Date('2024-12-31'))).toBe('FY24-25');
    expect(fyForDate(new Date('2025-03-31'))).toBe('FY24-25');
    expect(fyForDate(new Date('2025-04-01'))).toBe('FY25-26');
    expect(fyForDate(new Date('2024-01-31'))).toBe('FY23-24');
  });
});

describe('FYContext', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('exposes a default FY (one of the supported ones)', () => {
    const { result } = renderHook(() => useFY(), { wrapper });
    expect(SUPPORTED_FYS).toContain(result.current.currentFY);
  });

  it('updates currentFY and persists to localStorage', () => {
    const { result } = renderHook(() => useFY(), { wrapper });
    act(() => {
      result.current.setCurrentFY('FY23-24');
    });
    expect(result.current.currentFY).toBe('FY23-24');
    expect(window.localStorage.getItem('hc.currentFY')).toBe('FY23-24');
  });

  it('rejects unsupported FY codes silently', () => {
    const { result } = renderHook(() => useFY(), { wrapper });
    const before = result.current.currentFY;
    act(() => {
      result.current.setCurrentFY('FY99-00');
    });
    expect(result.current.currentFY).toBe(before);
  });

  it('reads stored FY on mount', () => {
    window.localStorage.setItem('hc.currentFY', 'FY24-25');
    const { result } = renderHook(() => useFY(), { wrapper });
    expect(result.current.currentFY).toBe('FY24-25');
  });
});
