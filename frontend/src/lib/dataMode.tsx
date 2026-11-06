import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchHealth } from './api';
import { storageGet, storageSet } from './storage';

export type DataMode = 'demo' | 'imported' | 'live';
export const DATA_MODES: DataMode[] = ['demo', 'imported', 'live'];

/** Labels reused by the badge, exports and notifications (CLAUDE.md: Provenance). */
export const MODE_LABELS: Record<DataMode, { name: string; badge: string }> = {
  demo: { name: 'Demo', badge: 'Demo · synthetic data' },
  imported: { name: 'Imported', badge: 'Imported data' },
  live: { name: 'Live', badge: 'Live data' },
};

const STORAGE_KEY = 'ml-data-mode';

interface DataModeContextValue {
  mode: DataMode;
  setMode: (m: DataMode) => void;
  /** null when available; otherwise why the mode cannot be used. */
  unavailableReason: (m: DataMode) => string | null;
}

const DataModeContext = createContext<DataModeContextValue | null>(null);

function initialMode(): DataMode {
  const saved = storageGet(STORAGE_KEY);
  return saved === 'demo' || saved === 'imported' || saved === 'live' ? saved : 'demo';
}

export function DataModeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<DataMode>(initialMode);
  const health = useQuery({ queryKey: ['health'], queryFn: fetchHealth, refetchInterval: 60_000 });

  const unavailableReason = (m: DataMode): string | null => {
    const status = health.data?.modes[m];
    if (status) return status.available ? null : (status.reason ?? `${MODE_LABELS[m].name} data is unavailable.`);
    // Before health loads, only Live is assumed off (it needs a configured provider).
    return m === 'live' ? 'Live data is off: no live provider is configured.' : null;
  };

  // Never stay in a mode the server says is unavailable.
  useEffect(() => {
    if (health.data && !health.data.modes[mode]?.available) setModeState('demo');
  }, [health.data, mode]);

  useEffect(() => storageSet(STORAGE_KEY, mode), [mode]);

  const value = useMemo(
    () => ({ mode, setMode: setModeState, unavailableReason }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [mode, health.data],
  );
  return <DataModeContext.Provider value={value}>{children}</DataModeContext.Provider>;
}

export function useDataMode(): DataModeContextValue {
  const ctx = useContext(DataModeContext);
  if (!ctx) throw new Error('useDataMode must be used inside DataModeProvider');
  return ctx;
}
