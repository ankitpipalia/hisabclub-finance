/**
 * Global Financial Year selector — feature #104 in master_plan_2026.md.
 *
 * - `currentFY` is persisted in localStorage so it survives reloads.
 * - Default is computed from today's date using the Indian FY (Apr-Mar).
 * - Components anywhere in the tree consume via `useFY()`.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

const STORAGE_KEY = 'hc.currentFY';

/** Returns the FY code (e.g. "FY24-25") that the given JS Date falls into. */
export function fyForDate(date: Date): string {
  const month = date.getMonth(); // 0-indexed; Jan=0, Apr=3, Mar=2
  const year = date.getFullYear();
  // Indian FY runs Apr (month=3) of year N to Mar (month=2) of year N+1.
  const startYear = month >= 3 ? year : year - 1;
  const startShort = String(startYear).slice(-2);
  const endShort = String(startYear + 1).slice(-2);
  return `FY${startShort}-${endShort}`;
}

/** Supported FY codes shown in the dropdown. Keep in sync with backend
 *  `/api/v1/tax/rules/supported`. */
export const SUPPORTED_FYS: readonly string[] = ['FY23-24', 'FY24-25', 'FY25-26'];

type FYContextValue = {
  currentFY: string;
  setCurrentFY: (fy: string) => void;
  supportedFYs: readonly string[];
};

const FYContext = createContext<FYContextValue | undefined>(undefined);

function readInitialFY(): string {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored && SUPPORTED_FYS.includes(stored)) return stored;
  } catch {
    // localStorage may be disabled (private mode, SSR); fall through.
  }
  const computed = fyForDate(new Date());
  return SUPPORTED_FYS.includes(computed) ? computed : SUPPORTED_FYS[SUPPORTED_FYS.length - 1];
}

export function FYProvider({ children }: { children: ReactNode }) {
  const [currentFY, _setCurrentFY] = useState<string>(readInitialFY);

  const setCurrentFY = useCallback((fy: string) => {
    if (!SUPPORTED_FYS.includes(fy)) {
      // Reject unsupported FY silently to avoid breaking children.
      return;
    }
    _setCurrentFY(fy);
    try {
      window.localStorage.setItem(STORAGE_KEY, fy);
    } catch {
      // ignore storage failure
    }
  }, []);

  useEffect(() => {
    // If localStorage was cleared elsewhere, persist the current default.
    try {
      window.localStorage.setItem(STORAGE_KEY, currentFY);
    } catch {
      // ignore
    }
    // Only run on mount; persistence on change is handled by setCurrentFY.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const value = useMemo(
    () => ({
      currentFY,
      setCurrentFY,
      supportedFYs: SUPPORTED_FYS,
    }),
    [currentFY, setCurrentFY],
  );

  return <FYContext.Provider value={value}>{children}</FYContext.Provider>;
}

export function useFY(): FYContextValue {
  const ctx = useContext(FYContext);
  if (!ctx) {
    throw new Error('useFY must be used within FYProvider');
  }
  return ctx;
}
