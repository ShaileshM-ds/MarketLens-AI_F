import { Link } from 'react-router-dom';
import { PageHeader } from '../PageHeader';
import { AdminGate, SignOutButton } from './AdminGate';
import { DemoPanel } from './DemoPanel';
import { STATUS_LABELS, useRuns } from '../../lib/imports';
import { formatCount, formatDateTime } from '../../lib/format';

export function AdminPage() {
  return (
    <div className="stack-lg">
      <PageHeader title="Data administration" note="Import datasets into Imported data. Demo and Live data are never touched by imports." />
      <AdminGate>
        <Runs />
        <DemoPanel />
      </AdminGate>
    </div>
  );
}

function Runs() {
  const runs = useRuns();
  return (
    <section className="card section-card" aria-labelledby="runs-title">
      <div className="section-head">
        <h2 id="runs-title">Ingestion runs</h2>
        <div className="row-gap">
          <Link to="/admin/import" className="btn btn--primary">
            New import
          </Link>
          <SignOutButton />
        </div>
      </div>
      {runs.isPending && <p className="muted">Loading imports…</p>}
      {runs.isError && (
        <p className="inline-error" role="alert">
          Couldn't load imports: {runs.error.message}
        </p>
      )}
      {runs.data && runs.data.runs.length === 0 && <p className="muted">No imports yet.</p>}
      {runs.data && runs.data.runs.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Started</th>
                <th scope="col">File</th>
                <th scope="col">Status</th>
                <th scope="col" className="num">Accepted</th>
                <th scope="col" className="num">Duplicates</th>
                <th scope="col" className="num">Quarantined</th>
                <th scope="col" className="num">Rows with warnings</th>
                <th scope="col">
                  <span className="visually-hidden">Open</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {runs.data.runs.map((r) => (
                <tr key={r.id}>
                  <td>{formatDateTime(r.created_at)}</td>
                  <td>{r.file.filename}</td>
                  <td>
                    <span className={`status status--${r.status}`}>{STATUS_LABELS[r.status]}</span>
                  </td>
                  <td className="num">{formatCount(r.summary?.accepted)}</td>
                  <td className="num">{formatCount(r.summary?.duplicate)}</td>
                  <td className="num">{formatCount(r.summary?.rejected)}</td>
                  <td className="num">{formatCount(r.summary?.warning_rows)}</td>
                  <td>
                    <Link to={`/admin/import/${r.id}`} className="link">
                      Open<span className="visually-hidden"> import of {r.file.filename}</span>
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
