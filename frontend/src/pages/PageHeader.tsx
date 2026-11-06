import type { ReactNode } from 'react';

export function PageHeader({ eyebrow, title, note }: { eyebrow?: string; title: ReactNode; note?: string }) {
  return (
    <header className="page-header">
      {eyebrow && <p className="eyebrow">{eyebrow}</p>}
      <h1 className="page-title">{title}</h1>
      {note && <p className="muted">{note}</p>}
    </header>
  );
}
