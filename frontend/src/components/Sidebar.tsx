import { NavLink } from 'react-router-dom';
import { NAV_ITEMS } from '../lib/nav';
import { CloseIcon } from './Icons';

export function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <aside className={`sidebar${open ? ' sidebar--open' : ''}`} aria-label="Main navigation">
      <div className="sidebar__head">
        <NavLink to="/" className="logo" end>
          <span className="logo__mark" aria-hidden="true" />
          <span className="logo__text">MarketLens AI</span>
        </NavLink>
        <button type="button" className="icon-button sidebar__close" onClick={onClose} aria-label="Close navigation">
          <CloseIcon />
        </button>
      </div>
      <nav>
        <ul className="nav-list">
          {NAV_ITEMS.map((item) => (
            <li key={item.to}>
              <NavLink to={item.to} end={item.end} className={({ isActive }) => `nav-link${isActive ? ' nav-link--active' : ''}`}>
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </aside>
  );
}
