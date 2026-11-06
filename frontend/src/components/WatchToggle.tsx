import { useLocation, useNavigate } from 'react-router-dom';
import { useMe } from '../lib/auth';
import { useDataMode } from '../lib/dataMode';
import { savePending } from '../lib/pendingAction';
import { usePersonalMutation, useWatchlist, watchApi } from '../lib/watch';

/** Watch / Watching toggle. Signed out: remembers the tap, signs in, then completes it. */
export function WatchToggle({ productId, name, compact = false }: { productId: string; name: string; compact?: boolean }) {
  const me = useMe();
  const { mode } = useDataMode();
  const navigate = useNavigate();
  const location = useLocation();
  const list = useWatchlist();
  const watched = !!list.data?.items.some((i) => i.product_id === productId);
  const add = usePersonalMutation((id: string, m) => watchApi.add(id, m));
  const remove = usePersonalMutation((id: string, m) => watchApi.remove(id, m));
  const busy = add.isPending || remove.isPending;

  const onClick = () => {
    if (me.isPending || busy) return;
    if (!me.data) {
      savePending({ type: 'watch', mode, productId });
      navigate(`/signin?next=${encodeURIComponent(location.pathname + location.search)}`);
      return;
    }
    if (watched) remove.mutate(productId);
    else add.mutate(productId);
  };

  return (
    <button
      type="button"
      className={`watch-toggle${watched ? ' watch-toggle--on' : ''}${compact ? ' watch-toggle--compact' : ''}`}
      aria-pressed={watched}
      aria-label={watched ? `Stop watching ${name}` : `Watch ${name}`}
      onClick={onClick}
      disabled={busy}
    >
      <span aria-hidden="true">{watched ? '★' : '☆'}</span> {watched ? 'Watching' : 'Watch'}
      {(add.isError || remove.isError) && <span className="visually-hidden" role="alert">Couldn't update your watchlist.</span>}
    </button>
  );
}
