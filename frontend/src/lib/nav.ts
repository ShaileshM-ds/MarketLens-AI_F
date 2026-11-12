export interface NavItem {
  to: string;
  label: string;
  end?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Overview', end: true },
  { to: '/products', label: 'Product explorer' },
  { to: '/watchlist', label: 'Watchlist & alerts' },
  { to: '/analyst', label: 'Analyst dashboard' },
  { to: '/admin', label: 'Data administration' },
  { to: '/methodology', label: 'Methodology' },
  { to: '/credits', label: 'Image credits' },
];

/** Pages reached from within a section rather than from the sidebar. */
const EXTRA_PAGES: NavItem[] = [
  { to: '/compare', label: 'Compare products' },
  { to: '/signin', label: 'Sign in' },
];

export function navItemFor(pathname: string): NavItem | undefined {
  if (pathname === '/') return NAV_ITEMS[0];
  const extra = EXTRA_PAGES.find((n) => pathname === n.to || pathname.startsWith(`${n.to}/`));
  if (extra) return extra;
  return NAV_ITEMS.find((n) => n.to !== '/' && (pathname === n.to || pathname.startsWith(`${n.to}/`)));
}
