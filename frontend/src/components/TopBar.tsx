import { Link, useLocation } from 'react-router-dom';
import { navItemFor } from '../lib/nav';
import { ModeSwitcher } from './ModeSwitcher';
import { ThemeToggle } from './ThemeToggle';
import { AlertsBell } from './AlertsBell';
import { MenuIcon } from './Icons';

export function TopBar({ onOpenNav }: { onOpenNav: () => void }) {
  const { pathname } = useLocation();
  const current = navItemFor(pathname);

  return (
    <header className="topbar">
      <div className="topbar__left">
        <button type="button" className="icon-button topbar__menu" onClick={onOpenNav} aria-label="Open navigation">
          <MenuIcon />
        </button>
        <nav aria-label="Breadcrumb" className="breadcrumb">
          <ol>
            <li>
              <Link to="/">Workspace</Link>
            </li>
            <li aria-current="page">{current?.label ?? 'Page not found'}</li>
          </ol>
        </nav>
      </div>
      <div className="topbar__right">
        <ModeSwitcher />
        <ThemeToggle />
        <AlertsBell />
      </div>
    </header>
  );
}
