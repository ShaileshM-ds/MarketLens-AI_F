import { Link } from 'react-router-dom';
import { MAX_COMPARE, compareHref, useCompare } from '../lib/compareSelection';

/** Bottom tray listing the products picked for comparison. */
export function CompareTray() {
  const { items, error, remove, reset } = useCompare();
  if (items.length === 0 && !error) return null;
  return (
    <aside className="compare-tray card" aria-label="Comparison tray">
      <div className="compare-tray__inner">
        <p className="compare-tray__count">
          {items.length} of {MAX_COMPARE} selected
        </p>
        <ul className="compare-tray__list">
          {items.map((x) => (
            <li key={x.id} className="compare-chip">
              <span className="compare-chip__name">{x.name}</span>
              <button type="button" className="compare-chip__remove" aria-label={`Remove ${x.name} from comparison`} onClick={() => remove(x.id)}>
                ×
              </button>
            </li>
          ))}
        </ul>
        <div className="compare-tray__actions">
          {items.length > 0 && (
            <Link to={compareHref(items.map((x) => x.id))} className="btn btn--primary">
              Compare ({items.length})
            </Link>
          )}
          <button type="button" className="btn btn--secondary" onClick={reset}>
            Clear
          </button>
        </div>
        {items.length === 1 && <p className="muted small compare-tray__hint">Add another product to compare side by side.</p>}
        {error && (
          <p className="inline-error compare-tray__hint" role="alert">
            {error}
          </p>
        )}
      </div>
    </aside>
  );
}
