import { PageHeader } from './PageHeader';

export function Placeholder({ title, note }: { title: string; note?: string }) {
  return (
    <div className="stack-lg">
      <PageHeader title={title} note={note} />
      <section className="card empty-state">
        <h2>Not built yet</h2>
        <p className="muted">This screen is planned and arrives in a later step.</p>
      </section>
    </div>
  );
}
