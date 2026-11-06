import { useQuery } from '@tanstack/react-query';
import { fetchCategories } from './api';
import { useDataMode } from './dataMode';

/** Category counts for the active data mode only (modes are never mixed). */
export function useCategories() {
  const { mode, unavailableReason } = useDataMode();
  return useQuery({
    queryKey: ['categories', mode],
    queryFn: () => fetchCategories(mode),
    enabled: unavailableReason(mode) === null,
  });
}
