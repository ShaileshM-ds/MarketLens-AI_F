import { useQuery } from '@tanstack/react-query';
import { PageHeader } from './PageHeader';

interface Credit { file: string; category: string; title: string; author: string; license: string; license_url: string | null; source: string }

/** Authors and licences of the openly licensed product photos (CC BY and CC BY-SA require this attribution). */
export function ImageCreditsPage() {
  const q = useQuery({ queryKey: ['image-credits'], queryFn: async () => (await fetch('/demo-photos/credits.json')).json() as Promise<Credit[]> });
  return (
    <div className="stack-lg">
      <PageHeader eyebrow="Credits" title="Image credits" note="Product photos are openly licensed images from Wikimedia Commons, stored with the app and shown unchanged (scaled to 600 px)." />
      {q.isPending && <p className="muted" role="status">Loading credits…</p>}
      {q.isError && <p className="inline-error" role="alert">Couldn't load the image credits.</p>}
      {q.data && (
        <section className="card section-card">
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Image credits region">
            <table className="table table--compact" aria-label="Image credits">
              <thead><tr><th scope="col">Image</th><th scope="col">Title</th><th scope="col">Author</th><th scope="col">Licence</th><th scope="col">Source</th></tr></thead>
              <tbody>
                {q.data.map((c) => (
                  <tr key={c.file}>
                    <td><img src={`/demo-photos/${c.file}`} alt="" width={56} height={56} loading="lazy" style={{ objectFit: 'cover', borderRadius: 8 }} /></td>
                    <td>{c.title}</td>
                    <td>{c.author}</td>
                    <td>{c.license_url ? <a href={c.license_url.replace('http://', 'https://')} target="_blank" rel="noopener noreferrer">{c.license}</a> : c.license}</td>
                    <td><a href={c.source} target="_blank" rel="noopener noreferrer">Wikimedia Commons</a></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
