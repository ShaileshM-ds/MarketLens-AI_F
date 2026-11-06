import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiSend } from '../../lib/api';
import { formatCount, formatDateTime } from '../../lib/format';

interface DemoStatus {
  database: string;
  products: number;
  observations: number;
  reviews: number;
  last_run: { id: string; created_at: string; seed: number; end_date: string; answer_key_sha256: string } | null;
  jobs: { id: string; type: string; status: string; error: string | null; created_at: string }[];
  export_location: string;
}

const PHRASE = 'RESET DEMO';

/** Generate or reset the synthetic Demo dataset. Only the Demo database is ever touched. */
export function DemoPanel() {
  const qc = useQueryClient();
  const [phrase, setPhrase] = useState('');
  const status = useQuery({
    queryKey: ['demo-status'],
    queryFn: () => apiGet<DemoStatus>('/api/v1/admin/demo/status'),
    refetchInterval: (q) => (q.state.data?.jobs.some((j) => j.status === 'queued' || j.status === 'running') ? 2000 : false),
  });
  const after = () => qc.invalidateQueries({ queryKey: ['demo-status'] });
  const generate = useMutation({ mutationFn: () => apiSend('POST', '/api/v1/admin/demo/generate'), onSettled: after });
  const reset = useMutation({ mutationFn: () => apiSend('POST', '/api/v1/admin/demo/reset', { confirm: PHRASE }), onSuccess: () => setPhrase(''), onSettled: after });
  const s = status.data;
  const busy = !!s?.jobs.some((j) => j.status === 'queued' || j.status === 'running');

  return (
    <section className="card section-card stack-md" aria-labelledby="demo-title">
      <h2 id="demo-title">Demo data</h2>
      <p className="muted small">
        A deterministic synthetic dataset: fictional products, 180+ days of UTC observations and planted scenarios. It affects only the Demo database.
        The CSV export and a separate answer key (answer_key.json) are written to {s?.export_location ?? 'data/demo-export/'}; the answer key is never imported or read by analytics.
      </p>
      {status.isError && <p className="inline-error" role="alert">Couldn't load Demo status: {status.error.message}</p>}
      {s && (
        <dl className="facts">
          <div className="facts__item"><dt>Products</dt><dd>{formatCount(s.products)}</dd></div>
          <div className="facts__item"><dt>Observations</dt><dd>{formatCount(s.observations)}</dd></div>
          <div className="facts__item"><dt>Reviews</dt><dd>{formatCount(s.reviews)}</dd></div>
          <div className="facts__item"><dt>Last generated</dt><dd>{s.last_run ? `${formatDateTime(s.last_run.created_at)} · seed ${s.last_run.seed}` : 'Never'}</dd></div>
        </dl>
      )}
      {s?.jobs.length ? (
        <ul className="bullets small" aria-label="Recent Demo jobs">
          {s.jobs.map((j) => (
            <li key={j.id}>{j.type === 'demo_generate' ? 'Generate' : 'Reset'}: {j.status}{j.error ? ` (${j.error})` : ''} · {formatDateTime(j.created_at)}</li>
          ))}
        </ul>
      ) : null}
      <div className="row-gap">
        <button type="button" className="btn btn--primary" disabled={!s || s.products > 0 || busy || generate.isPending} onClick={() => generate.mutate()}>
          Generate demo data
        </button>
        {s && s.products > 0 && <span className="muted small">Demo data exists. Reset it first to regenerate.</span>}
      </div>
      <div className="stack-sm">
        <label className="field">
          <span className="field__label">Type {PHRASE} to confirm a reset (only the Demo database is affected)</span>
          <input className="input" value={phrase} onChange={(e) => setPhrase(e.target.value)} autoComplete="off" />
        </label>
        <div>
          <button type="button" className="btn btn--secondary" disabled={phrase !== PHRASE || busy || reset.isPending} onClick={() => reset.mutate()}>
            Reset demo data
          </button>
        </div>
      </div>
      {(generate.isError || reset.isError) && <p className="inline-error" role="alert">{(generate.error ?? reset.error)?.message}</p>}
    </section>
  );
}
