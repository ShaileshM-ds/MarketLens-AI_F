/**
 * Products chosen for side-by-side comparison. Matched only by stable product ID,
 * kept per workspace (IDs in Imported mean nothing in Demo), at most 4.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useDataMode } from './dataMode';
import { storageGet, storageSet } from './storage';

export const MAX_COMPARE = 4;
export interface CompareItem {
  id: string;
  name: string;
}
type Result = { list: CompareItem[]; error: string | null };

export const FULL_MESSAGE = `You can compare up to ${MAX_COMPARE} products. Remove or replace one first.`;

export function storageKey(mode: string): string {
  return `ml-compare-${mode}`;
}

export function addItem(list: CompareItem[], item: CompareItem): Result {
  if (list.some((x) => x.id === item.id)) return { list, error: null };
  if (list.length >= MAX_COMPARE) return { list, error: FULL_MESSAGE };
  return { list: [...list, item], error: null };
}

export function removeItem(list: CompareItem[], id: string): CompareItem[] {
  return list.filter((x) => x.id !== id);
}

export function replaceItem(list: CompareItem[], oldId: string, item: CompareItem): Result {
  if (list.some((x) => x.id === item.id && x.id !== oldId)) return { list, error: `${item.name} is already in the comparison.` };
  return { list: list.map((x) => (x.id === oldId ? item : x)), error: null };
}

function load(mode: string): CompareItem[] {
  try {
    const raw = JSON.parse(storageGet(storageKey(mode)) ?? '[]');
    return Array.isArray(raw)
      ? raw.filter((x) => x && typeof x.id === 'string' && typeof x.name === 'string').slice(0, MAX_COMPARE)
      : [];
  } catch {
    return [];
  }
}

interface Ctx {
  items: CompareItem[];
  error: string | null;
  has: (id: string) => boolean;
  add: (item: CompareItem) => boolean;
  remove: (id: string) => void;
  replace: (oldId: string, item: CompareItem) => boolean;
  setAll: (items: CompareItem[]) => void;
  reset: () => void;
  clearError: () => void;
}

const CompareContext = createContext<Ctx | null>(null);

export function CompareProvider({ children }: { children: ReactNode }) {
  const { mode } = useDataMode();
  const [state, setState] = useState(() => ({ mode, items: load(mode) }));
  const [error, setError] = useState<string | null>(null);
  const items = state.mode === mode ? state.items : load(mode);

  useEffect(() => {
    if (state.mode !== mode) setState({ mode, items: load(mode) });
    setError(null);
  }, [mode, state.mode]);

  const commit = useCallback(
    (next: CompareItem[]) => {
      setState({ mode, items: next });
      storageSet(storageKey(mode), JSON.stringify(next));
    },
    [mode],
  );

  const value = useMemo<Ctx>(
    () => ({
      items,
      error,
      has: (id) => items.some((x) => x.id === id),
      add: (item) => {
        const r = addItem(items, item);
        setError(r.error);
        if (!r.error) commit(r.list);
        return !r.error;
      },
      remove: (id) => {
        setError(null);
        commit(removeItem(items, id));
      },
      replace: (oldId, item) => {
        const r = replaceItem(items, oldId, item);
        setError(r.error);
        if (!r.error) commit(r.list);
        return !r.error;
      },
      setAll: (next) => commit(next.slice(0, MAX_COMPARE)),
      reset: () => {
        setError(null);
        commit([]);
      },
      clearError: () => setError(null),
    }),
    [items, error, commit],
  );
  return <CompareContext.Provider value={value}>{children}</CompareContext.Provider>;
}

export function useCompare(): Ctx {
  const ctx = useContext(CompareContext);
  if (!ctx) throw new Error('useCompare must be used inside CompareProvider');
  return ctx;
}

export function compareHref(ids: string[]): string {
  const q = new URLSearchParams();
  ids.forEach((id) => q.append('ids', id));
  const s = q.toString();
  return s ? `/compare?${s}` : '/compare';
}
