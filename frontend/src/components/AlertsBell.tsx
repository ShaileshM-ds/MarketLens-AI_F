import { Link } from 'react-router-dom';
import { BellIcon } from './Icons';
import { useUnreadCount } from '../lib/watch';

/** Unread in-app notifications for the signed-in user in the current workspace. */
export function AlertsBell() {
  const q = useUnreadCount();
  const unread = q.data?.unread ?? 0;
  return (
    <Link to="/watchlist#notifications" className="pill alerts" aria-label={`Alerts, ${unread} unread`}>
      <BellIcon />
      <span className="alerts__label">Alerts</span>
      {unread > 0 && (
        <span className="alerts__count" aria-hidden="true">
          {unread > 99 ? '99+' : unread}
        </span>
      )}
    </Link>
  );
}
