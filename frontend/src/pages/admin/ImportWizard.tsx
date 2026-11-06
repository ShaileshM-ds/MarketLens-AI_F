import { useMemo, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { PageHeader } from '../PageHeader';
import { AdminGate } from './AdminGate';
import { ApiError, apiGet, apiSend } from '../../lib/api';
import {
  STATUS_LABELS,
  useReference,
  useRun,
  type ImportConfig,
  type ImportRun,
  type PreviewRow,
  type Reference,
  type RejectedPage,
} from '../../lib/imports';
import { formatBytes, formatCount, formatDateTime } from '../../lib/format';
import { formatMoney } from '../../lib/money';

const STEPS = [
  { id: 'choose', label: 'Choose file' },
  { id: 'profile', label: 'Profile' },
  { id: 'map', label: 'Map fields' },
  { id: 'preview', label: 'Preview' },
  { id: 'validate', label: 'Validation' },
  { id: 'confirm', label: 'Confirm' },
  { id: 'results', label: 'Results' },
] as const;
type StepId = (typeof STEPS)[number]['id'];

const DONE_STATES = ['queued', 'running', 'completed', 'failed'];

function availableSteps(run: ImportRun | undefined): Set<StepId> {
  if (!run) return new Set(['choose']);
  const s = new Set<StepId>(['profile', 'map']);
  if (run.evaluation) ['preview', 'validate', 'confirm'].forEach((x) => s.add(x as StepId));
  if (DONE_STATES.includes(run.status)) {
    s.delete('confirm');
    s.add('results');
  }
  return s;
}

function defaultStep(run: ImportRun): StepId {
  if (DONE_STATES.includes(run.status)) return 'results';
  return run.status === 'mapped' ? 'preview' : 'profile';
}

export function ImportWizard() {
  return (
    <div className="stack-lg">
      <PageHeader eyebrow="Data administration" title="Import a dataset" note="Imports always go to Imported data, kept separate from Demo and Live." />
      <AdminGate>
        <Wizard />
      </AdminGate>
    </div>
  );
}

function Wizard() {
  const { runId } = useParams();
  const [params, setParams] = useSearchParams();
  const run = useRun(runId);
  const reference = useReference();

  const available = availableSteps(run.data);
  const requested = params.get('step') as StepId | null;
  const step: StepId = !runId
    ? 'choose'
    : requested && available.has(requested)
      ? requested
      : run.data
        ? defaultStep(run.data)
        : 'profile';
  const go = (s: StepId) => setParams({ step: s });

  return (
    <>
      <Stepper current={step} available={available} onSelect={go} />
      {runId && run.isPending && <p className="muted">Loading import…</p>}
      {run.isError && (
        <p className="inline-error" role="alert">
          {run.error.message} <Link to="/admin" className="link">Back to imports</Link>
        </p>
      )}
      {reference.isError && <p className="inline-error" role="alert">Couldn't load the importer: {reference.error.message}</p>}
      {step === 'choose' && <ChooseStep />}
      {run.data && reference.data && (
        <>
          {step === 'profile' && <ProfileStep run={run.data} onNext={() => go('map')} />}
          {step === 'map' && <MapStep run={run.data} reference={reference.data} onDone={() => go('preview')} />}
          {step === 'preview' && <PreviewStep run={run.data} onNext={() => go('validate')} />}
          {step === 'validate' && <ValidateStep run={run.data} reference={reference.data} onNext={() => go('confirm')} />}
          {step === 'confirm' && <ConfirmStep run={run.data} onDone={() => go('results')} />}
          {step === 'results' && <ResultsStep run={run.data} reference={reference.data} />}
        </>
      )}
    </>
  );
}

function Stepper({ current, available, onSelect }: { current: StepId; available: Set<StepId>; onSelect: (s: StepId) => void }) {
  return (
    <nav aria-label="Import steps">
      <ol className="steps">
        {STEPS.map((s, i) => {
          const isCurrent = s.id === current;
          const can = available.has(s.id) && s.id !== 'choose';
          return (
            <li key={s.id} className={`steps__item${isCurrent ? ' steps__item--current' : ''}`}>
              {can && !isCurrent ? (
                <button type="button" className="steps__button" onClick={() => onSelect(s.id)}>
                  <span className="steps__num">{i + 1}</span> {s.label}
                </button>
              ) : (
                <span className="steps__button" aria-current={isCurrent ? 'step' : undefined} aria-disabled={!isCurrent || undefined}>
                  <span className="steps__num">{i + 1}</span> {s.label}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

/* ---------- 1. Choose file ---------- */
function ChooseStep() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const upload = useMutation({
    mutationFn: (f: File) => {
      const fd = new FormData();
      fd.append('file', f);
      return apiSend<ImportRun>('POST', '/api/v1/admin/imports', fd);
    },
    onSuccess: (run) => {
      qc.setQueryData(['imports', 'run', run.id], run);
      qc.invalidateQueries({ queryKey: ['imports', 'list'] });
      navigate(`/admin/import/${run.id}?step=profile`);
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (file) upload.mutate(file);
  };
  return (
    <section className="card section-card">
      <h2>Choose a file</h2>
      <p className="muted">CSV, JSON or JSONL, up to 10 MB. The original file is kept unchanged. Nothing is imported until you confirm.</p>
      <form onSubmit={submit} className="form-stack">
        <label className="field">
          <span className="field__label">Dataset file</span>
          <input
            type="file"
            className="input input--file"
            accept=".csv,.json,.jsonl,.ndjson"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>
        {upload.isError && <ErrorBox error={upload.error} />}
        <div>
          <button type="submit" className="btn btn--primary" disabled={!file || upload.isPending}>
            {upload.isPending ? 'Reading file…' : 'Upload and profile'}
          </button>
          {!file && <span className="muted hint">Choose a file first.</span>}
        </div>
      </form>
    </section>
  );
}

/* ---------- 2. Profile ---------- */
function ProfileStep({ run, onNext }: { run: ImportRun; onNext: () => void }) {
  const p = run.profile!;
  return (
    <section className="card section-card stack-md">
      <h2>Profile</h2>
      <dl className="facts">
        <Fact label="File" value={run.file.filename} />
        <Fact label="Format" value={run.file.format.toUpperCase()} />
        <Fact label="Size" value={formatBytes(run.file.size_bytes)} />
        <Fact label="Rows" value={formatCount(p.row_count)} />
        <Fact label="Columns" value={formatCount(p.columns.length)} />
        <Fact label="Malformed rows" value={formatCount(p.rows_with_problems)} />
        <Fact label="Uploaded" value={`${formatDateTime(run.created_at)} by ${run.created_by}`} />
      </dl>
      {run.preset === 'mens-clothing-snapshot' && (
        <p className="note">
          This matches the men's clothing snapshot. The suggested mapping follows the recorded decisions: timestamps kept as
          "timezone unknown", sub-categories mapped to Men's clothing.
        </p>
      )}
      {run.previous_completed_run_id && (
        <p className="note">This exact file was imported before. Re-importing it adds nothing new; rows count as duplicates.</p>
      )}
      <div className="table-wrap">
        <table className="table">
          <caption className="visually-hidden">Columns in the file</caption>
          <thead>
            <tr>
              <th scope="col">Column</th>
              <th scope="col" className="num">Blank</th>
              <th scope="col" className="num">Distinct values</th>
              <th scope="col">Most common values</th>
            </tr>
          </thead>
          <tbody>
            {p.columns.map((c) => (
              <tr key={c.name}>
                <th scope="row" className="mono">{c.name}</th>
                <td className="num">{formatCount(c.blank)}</td>
                <td className="num">{formatCount(c.distinct)}</td>
                <td className="examples">{c.examples.join(' · ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div>
        <button type="button" className="btn btn--primary" onClick={onNext}>
          Next: map fields
        </button>
      </div>
    </section>
  );
}

/* ---------- 3. Map fields ---------- */
function MapStep({ run, reference, onDone }: { run: ImportRun; reference: Reference; onDone: () => void }) {
  const qc = useQueryClient();
  const editable = run.status === 'profiled' || run.status === 'mapped';
  const [cfg, setCfg] = useState<ImportConfig>(() => structuredClone(run.config ?? run.suggested_config!));
  const columns = run.profile!.columns.map((c) => c.name);

  const categoryColumn = cfg.field_map.category;
  // Source categories come from the file via the server; refresh after saving if the category column changes.
  const sourceCats = run.source_categories ?? [];

  const save = useMutation({
    mutationFn: () => apiSend<ImportRun>('PUT', `/api/v1/admin/imports/${run.id}/config`, cfg),
    onSuccess: (updated) => {
      qc.setQueryData(['imports', 'run', run.id], updated);
      onDone();
    },
  });

  const setField = (name: string, col: string) => setCfg({ ...cfg, field_map: { ...cfg.field_map, [name]: col || null } });
  const setCat = (src: string, slug: string) => {
    const next = { ...cfg.category_map };
    if (slug) next[src] = slug;
    else delete next[src];
    setCfg({ ...cfg, category_map: next });
  };

  return (
    <section className="card section-card stack-md">
      <h2>Map fields</h2>
      {!editable && <p className="note">This import has been confirmed, so its mapping can't be changed.</p>}
      <fieldset className="fieldset" disabled={!editable}>
        <legend>Timestamp rule</legend>
        {Object.entries(reference.timestamp_policies).map(([value, label]) => (
          <label key={value} className="radio">
            <input
              type="radio"
              name="policy"
              value={value}
              checked={cfg.timestamp_policy === value}
              onChange={() => setCfg({ ...cfg, timestamp_policy: value as ImportConfig['timestamp_policy'] })}
            />
            <span>{label}</span>
          </label>
        ))}
      </fieldset>
      <fieldset className="fieldset" disabled={!editable}>
        <legend>Provenance</legend>
        <label className="checkbox">
          <input type="checkbox" checked={cfg.declare_synthetic} onChange={(e) => setCfg({ ...cfg, declare_synthetic: e.target.checked })} />
          <span>Treat every row as synthetic (otherwise the Source type column decides; rows without it are quarantined)</span>
        </label>
      </fieldset>

      <div className="table-wrap">
        <table className="table">
          <caption className="table-caption">Fields</caption>
          <thead>
            <tr>
              <th scope="col">Field</th>
              <th scope="col">Column in your file</th>
              <th scope="col">Notes</th>
            </tr>
          </thead>
          <tbody>
            {reference.target_fields.map((t) => (
              <tr key={t.name}>
                <th scope="row">
                  {t.label} {t.required && <span className="tag">Required</span>}
                </th>
                <td>
                  <label className="visually-hidden" htmlFor={`map-${t.name}`}>
                    Column for {t.label}
                  </label>
                  <select
                    id={`map-${t.name}`}
                    className="select"
                    value={cfg.field_map[t.name] ?? ''}
                    onChange={(e) => setField(t.name, e.target.value)}
                    disabled={!editable}
                  >
                    <option value="">Not supplied</option>
                    {columns.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="muted">{t.help}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="table-wrap">
        <table className="table">
          <caption className="table-caption">Categories</caption>
          <thead>
            <tr>
              <th scope="col">Category in your file</th>
              <th scope="col">Launch category</th>
            </tr>
          </thead>
          <tbody>
            {!categoryColumn && (
              <tr>
                <td colSpan={2} className="muted">Map the Category field first.</td>
              </tr>
            )}
            {sourceCats.map((src) => (
              <tr key={src}>
                <th scope="row">{src}</th>
                <td>
                  <label className="visually-hidden" htmlFor={`cat-${src}`}>
                    Launch category for {src}
                  </label>
                  <select id={`cat-${src}`} className="select" value={cfg.category_map[src] ?? ''} onChange={(e) => setCat(src, e.target.value)} disabled={!editable}>
                    <option value="">Not mapped (rows are quarantined)</option>
                    {reference.launch_categories.map((c) => (
                      <option key={c.slug} value={c.slug}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {save.isError && <ErrorBox error={save.error} />}
      {editable && (
        <div>
          <button type="button" className="btn btn--primary" onClick={() => save.mutate()} disabled={save.isPending}>
            {save.isPending ? 'Checking every row…' : 'Save mapping and preview'}
          </button>
        </div>
      )}
    </section>
  );
}

/* ---------- 4. Preview ---------- */
function PreviewStep({ run, onNext }: { run: ImportRun; onNext: () => void }) {
  const ev = run.evaluation!;
  const confirmed = DONE_STATES.includes(run.status);
  return (
    <section className="card section-card stack-md">
      <h2>Preview</h2>
      <p className="muted">
        {confirmed
          ? `The first ${ev.preview_rows.length} rows as checked on ${formatDateTime(ev.evaluated_at)}, before this import was confirmed. See Results for what was stored.`
          : `The first ${ev.preview_rows.length} rows as they would be stored. Prices are converted to exact amounts; nothing has been imported yet.`}
      </p>
      <PreviewTable rows={ev.preview_rows} caption="First rows of the file" />
      <div>
        <button type="button" className="btn btn--primary" onClick={onNext}>
          Next: validation
        </button>
      </div>
    </section>
  );
}

const ROW_STATUS: Record<PreviewRow['status'], string> = {
  accepted: 'New',
  duplicate: 'Already imported',
  rejected: 'Quarantined',
};
const QUALITY: Record<string, string> = {
  timezone_unknown: 'Timezone unknown',
  utc: 'UTC',
  offset_converted: 'Converted to UTC',
};

function Shipping({ r }: { r: PreviewRow }) {
  if (!r.shipping_known) return <span className="muted">Not supplied</span>;
  if (r.shipping_minor === 0) return <>Free</>;
  return <>{formatMoney(r.shipping_minor, r.currency ?? 'INR')}</>;
}

function PreviewTable({ rows, caption }: { rows: PreviewRow[]; caption: string }) {
  if (rows.length === 0) return <p className="muted">None.</p>;
  return (
    <div className="table-wrap">
      <table className="table table--compact">
        <caption className="visually-hidden">{caption}</caption>
        <thead>
          <tr>
            <th scope="col" className="num">Row</th>
            <th scope="col">Result</th>
            <th scope="col">Listing</th>
            <th scope="col">Product</th>
            <th scope="col">Store</th>
            <th scope="col">Source time</th>
            <th scope="col" className="num">Price</th>
            <th scope="col" className="num">Reference price</th>
            <th scope="col">Shipping</th>
            <th scope="col">Availability</th>
            <th scope="col" className="num">Stock</th>
            <th scope="col">Notes</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.row_number}>
              <td className="num">{r.row_number}</td>
              <td>
                <span className={`status status--${r.status}`}>{ROW_STATUS[r.status]}</span>
              </td>
              <td className="mono">{r.listing_id}</td>
              <td className="mono">{r.product_id}</td>
              <td>{r.marketplace}</td>
              <td>
                {r.source_timestamp}
                {r.timestamp_quality && <span className="sub">{QUALITY[r.timestamp_quality] ?? r.timestamp_quality}</span>}
              </td>
              <td className="num">{formatMoney(r.price_minor, r.currency ?? 'INR')}</td>
              <td className="num">{formatMoney(r.reference_price_minor, r.currency ?? 'INR')}</td>
              <td>{r.status === 'rejected' ? null : <Shipping r={r} />}</td>
              <td>{r.availability}</td>
              <td className="num">{r.stock_quantity ?? ''}</td>
              <td className="notes">
                {[...r.reasons, ...r.warnings].map((n, i) => (
                  <span key={i} className={i < r.reasons.length ? 'note-reason' : 'note-warning'}>
                    {n}
                  </span>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ---------- 5. Validation ---------- */
function ValidateStep({ run, reference, onNext }: { run: ImportRun; reference: Reference; onNext: () => void }) {
  const ev = run.evaluation!;
  const c = ev.counts;
  return (
    <section className="card section-card stack-md">
      <h2>Validation</h2>
      <p className="muted">
        Checked every row on {formatDateTime(ev.evaluated_at)} against data already in Imported
        {DONE_STATES.includes(run.status) ? ', before this import was confirmed. See Results for what was stored.' : '.'}
      </p>
      <Stats
        items={[
          ['Rows in file', c.rows_total],
          ['Would be added', c.accepted],
          ['Already imported', c.duplicate],
          ['Would be quarantined', c.rejected],
          ['Rows with warnings', c.warning_rows],
          ['Warnings in total', c.warning_count],
        ]}
      />
      <CountTable title="Quarantine reasons" labels={reference.reason_labels} counts={c.rejected_by_reason} empty="No rows would be quarantined." />
      <CountTable title="Warnings" labels={reference.warning_labels} counts={c.warnings_by_type} empty="No warnings." note="Warnings are kept and flagged on the record, never corrected." />
      {ev.rejected_examples.length > 0 && (
        <>
          <h3>Rows that would be quarantined{ev.rejected_examples.length < c.rejected ? ` (first ${ev.rejected_examples.length})` : ''}</h3>
          <PreviewTable rows={ev.rejected_examples} caption="Rows that would be quarantined" />
        </>
      )}
      {ev.warning_examples.length > 0 && (
        <>
          <h3>Rows with warnings{ev.warning_examples.length < c.warning_rows ? ` (first ${ev.warning_examples.length})` : ''}</h3>
          <PreviewTable rows={ev.warning_examples} caption="Rows with warnings" />
        </>
      )}
      <div>
        <button type="button" className="btn btn--primary" onClick={onNext}>
          Next: confirm
        </button>
      </div>
    </section>
  );
}

/* ---------- 6. Confirm ---------- */
function ConfirmStep({ run, onDone }: { run: ImportRun; onDone: () => void }) {
  const qc = useQueryClient();
  const c = run.evaluation!.counts;
  const confirm = useMutation({
    mutationFn: () => apiSend<ImportRun>('POST', `/api/v1/admin/imports/${run.id}/confirm`),
    onSuccess: (updated) => {
      qc.setQueryData(['imports', 'run', run.id], updated);
      qc.invalidateQueries({ queryKey: ['imports', 'list'] });
      onDone();
    },
  });
  return (
    <section className="card section-card stack-md">
      <h2>Confirm</h2>
      <p>
        Import <strong>{run.file.filename}</strong> into <span className="mode-badge mode-badge--imported">Imported data</span>.
      </p>
      <ul className="bullets">
        <li>{formatCount(c.accepted)} new observations would be added; {formatCount(c.duplicate)} rows already imported are skipped.</li>
        <li>{formatCount(c.rejected)} rows would be quarantined with their reasons. They can be reviewed afterwards.</li>
        <li>Stored observations are never changed or replaced. Demo and Live data are not touched.</li>
      </ul>
      {confirm.isError && <ErrorBox error={confirm.error} />}
      <div>
        <button type="button" className="btn btn--primary" onClick={() => confirm.mutate()} disabled={confirm.isPending}>
          {confirm.isPending ? 'Starting…' : 'Confirm import'}
        </button>
      </div>
    </section>
  );
}

/* ---------- 7. Results ---------- */
function ResultsStep({ run, reference }: { run: ImportRun; reference: Reference }) {
  const s = run.summary;
  return (
    <section className="card section-card stack-md" aria-live="polite">
      <h2>Results</h2>
      <p>
        <span className={`status status--${run.status}`}>{STATUS_LABELS[run.status]}</span>
        {run.finished_at && <span className="muted"> · Finished {formatDateTime(run.finished_at)}</span>}
      </p>
      {(run.status === 'queued' || run.status === 'running') && <p className="muted">The worker is processing this import. This page updates by itself.</p>}
      {run.status === 'failed' && <p className="inline-error" role="alert">{run.error}</p>}
      {s && (
        <>
          <Stats
            items={[
              ['Rows in file', s.rows_total],
              ['Accepted', s.accepted],
              ['Duplicates', s.duplicate],
              ['Quarantined', s.rejected],
              ['Rows with warnings', s.warning_rows],
              ['Warnings in total', s.warning_count],
            ]}
          />
          <div className="table-wrap">
            <table className="table">
              <caption className="table-caption">Records</caption>
              <thead>
                <tr>
                  <th scope="col">Record</th>
                  <th scope="col" className="num">Created</th>
                  <th scope="col" className="num">Already stored</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th scope="row">Products</th>
                  <td className="num">{formatCount(s.created.products)}</td>
                  <td className="num"></td>
                </tr>
                <tr>
                  <th scope="row">Listings</th>
                  <td className="num">{formatCount(s.created.offers)}</td>
                  <td className="num"></td>
                </tr>
                <tr>
                  <th scope="row">Observations</th>
                  <td className="num">{formatCount(s.created.observations)}</td>
                  <td className="num">{formatCount(s.duplicate)}</td>
                </tr>
                <tr>
                  <th scope="row">Reviews</th>
                  <td className="num">{formatCount(s.created.reviews)}</td>
                  <td className="num">{formatCount(s.reviews_duplicate)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <CountTable title="Warnings" labels={reference.warning_labels} counts={s.warnings_by_type} empty="No warnings." />
          <CountTable title="Quarantine reasons" labels={reference.reason_labels} counts={s.rejected_by_reason} empty="No rows were quarantined." />
          {s.rejected > 0 && <RejectedRows runId={run.id} />}
        </>
      )}
      <p>
        <Link to="/admin" className="link">Back to imports</Link>
      </p>
    </section>
  );
}

function RejectedRows({ runId }: { runId: string }) {
  const [page, setPage] = useState(1);
  const q = useQuery({
    queryKey: ['imports', 'rejected', runId, page],
    queryFn: () => apiGet<RejectedPage>(`/api/v1/admin/imports/${runId}/rejected`, { page: String(page), page_size: '25' }),
  });
  const pages = q.data ? Math.max(1, Math.ceil(q.data.total / q.data.page_size)) : 1;
  return (
    <div className="stack-md">
      <h3>Quarantined rows</h3>
      {q.isError && <p className="inline-error">{q.error.message}</p>}
      {q.data && (
        <div className="table-wrap">
          <table className="table table--compact">
            <thead>
              <tr>
                <th scope="col" className="num">Row</th>
                <th scope="col">Reasons</th>
                <th scope="col">Original values</th>
              </tr>
            </thead>
            <tbody>
              {q.data.items.map((r) => (
                <tr key={r.row_number}>
                  <td className="num">{r.row_number}</td>
                  <td className="notes">
                    {r.reasons.map((x, i) => (
                      <span key={i} className="note-reason">{x.message}</span>
                    ))}
                  </td>
                  <td>
                    <details>
                      <summary>Show values</summary>
                      <dl className="kv">
                        {Object.entries(r.raw).map(([k, v]) => (
                          <div key={k}>
                            <dt>{k}</dt>
                            <dd>{v}</dd>
                          </div>
                        ))}
                      </dl>
                    </details>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {pages > 1 && (
        <div className="pager">
          <button type="button" className="btn btn--secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
          <span className="muted">Page {page} of {pages}</span>
          <button type="button" className="btn btn--secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      )}
    </div>
  );
}

/* ---------- shared bits ---------- */
function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="facts__item">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function Stats({ items }: { items: [string, number][] }) {
  return (
    <dl className="stats">
      {items.map(([label, n]) => (
        <div key={label} className="stats__item">
          <dt>{label}</dt>
          <dd>{formatCount(n)}</dd>
        </div>
      ))}
    </dl>
  );
}

function CountTable({ title, labels, counts, empty, note }: { title: string; labels: Record<string, string>; counts: Record<string, number>; empty: string; note?: string }) {
  const entries = useMemo(() => Object.entries(counts).sort((a, b) => b[1] - a[1]), [counts]);
  return (
    <div className="stack-sm">
      <h3>{title}</h3>
      {note && <p className="muted">{note}</p>}
      {entries.length === 0 ? (
        <p className="muted">{empty}</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Type</th>
                <th scope="col" className="num">Rows</th>
              </tr>
            </thead>
            <tbody>
              {entries.map(([code, n]) => (
                <tr key={code}>
                  <th scope="row">{labels[code] ?? code}</th>
                  <td className="num">{formatCount(n)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ErrorBox({ error }: { error: Error }) {
  const problems = error instanceof ApiError ? error.problems : [];
  return (
    <div className="error-box" role="alert">
      <p>{error.message}</p>
      {problems.length > 0 && (
        <ul>
          {problems.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
