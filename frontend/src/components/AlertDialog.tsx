import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { ApiError } from '../lib/api';
import { formatMoney, parseMajorToMinor } from '../lib/money';
import { ALERT_TYPES, usePersonalMutation, watchApi, type AlertRule } from '../lib/watch';

export interface AlertProduct {
  id: string;
  name: string;
  marketplaces: string[];
  currency: string;
}

const COOLDOWNS = [
  [0, 'No cooldown'],
  [6, '6 hours'],
  [12, '12 hours'],
  [24, '24 hours'],
  [72, '3 days'],
  [168, '7 days'],
] as const;

/** Create or edit a below-target alert. Rupees are typed; minor units are sent. */
export function AlertDialog({ product, rule, onClose, onSaved }: { product: AlertProduct; rule?: AlertRule; onClose: () => void; onSaved: (r: AlertRule) => void }) {
  const titleId = useId();
  const ref = useRef<HTMLDivElement>(null);
  const opener = useRef<HTMLElement | null>(typeof document !== 'undefined' ? (document.activeElement as HTMLElement) : null);
  const [type, setType] = useState<string>(rule?.type ?? 'below_target');
  const spec = ALERT_TYPES.find((t) => t.type === type) ?? ALERT_TYPES[0];
  const [minScore, setMinScore] = useState(String(rule?.min_score ?? 70));
  const [store, setStore] = useState(rule?.marketplace ?? '');
  const [basis, setBasis] = useState<'base' | 'delivered'>(rule?.basis ?? 'base');
  const [target, setTarget] = useState(rule && rule.target_price_minor !== null ? formatMoney(rule.target_price_minor, rule.currency ?? product.currency) : '');
  const [cooldown, setCooldown] = useState(rule?.cooldown_hours ?? 24);
  const [enabled, setEnabled] = useState(rule?.enabled ?? true);
  const [error, setError] = useState<string | null>(null);

  const save = usePersonalMutation(async (body: Record<string, unknown>, mode) =>
    rule ? watchApi.patchRule(rule.id, body, mode) : watchApi.createRule(body, mode),
  );

  const close = () => {
    onClose();
    opener.current?.focus?.();
  };

  useEffect(() => {
    ref.current?.querySelector<HTMLElement>('select, input')?.focus();
  }, []);

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      close();
      return;
    }
    if (e.key === 'Tab' && ref.current) {
      // Keep focus inside the dialog.
      const items = [...ref.current.querySelectorAll<HTMLElement>('button, select, input, a[href]')].filter((x) => !x.hasAttribute('disabled'));
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (type !== 'below_target') {
      const ms = Number(minScore);
      if (type === 'meaningful_discount' && (!Number.isInteger(ms) || ms < 40 || ms > 100)) {
        setError('Enter a whole-number minimum score from 40 to 100.');
        return;
      }
      setError(null);
      const fields: Record<string, unknown> = { cooldown_hours: cooldown };
      if (spec.store) fields.marketplace = store || null;
      if (spec.basis) fields.basis = basis;
      if (type === 'meaningful_discount') fields.min_score = ms;
      save.mutate(rule ? fields : { product_id: product.id, type, enabled, ...fields }, { onSuccess: (r) => { onSaved(r); close(); } });
      return;
    }
    const minor = parseMajorToMinor(target, product.currency);
    if (minor === null || minor <= 0) {
      setError('Enter a target price in rupees, for example 1,399 or 1399.50.');
      return;
    }
    setError(null);
    const body: Record<string, unknown> = rule
      ? { marketplace: store || null, basis, target_price_minor: minor, cooldown_hours: cooldown }
      : { product_id: product.id, marketplace: store || null, basis, target_price_minor: minor, currency: product.currency, cooldown_hours: cooldown, enabled };
    save.mutate(body, {
      onSuccess: (r) => {
        onSaved(r);
        close();
      },
    });
  };

  const serverError = save.error instanceof ApiError ? save.error.message : save.error ? 'The alert could not be saved.' : null;

  return (
    <div className="dialog-backdrop" onClick={close}>
      <div
        ref={ref}
        className="dialog card"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={onKeyDown}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id={titleId} className="h3">
          {type === 'below_target' ? 'Price alert' : 'Alert'} for {product.name}
        </h2>
        <p className="muted small">
          {type === 'below_target'
            ? "You'll be notified when a newly imported observation is at or below your target. Existing snapshot prices never trigger it."
            : `${spec.description} Checked only when new verified observations are imported; the first check records a baseline, so existing data never notifies.`}
        </p>
        <form className="form-stack" onSubmit={submit} noValidate>
          {!rule && (
            <label className="field">
              <span className="field__label">Alert type</span>
              <select className="select" value={type} onChange={(e) => { setType(e.target.value); setError(null); }}>
                {ALERT_TYPES.map((t) => <option key={t.type} value={t.type}>{t.label}</option>)}
              </select>
            </label>
          )}
          {spec.store && (
          <label className="field">
            <span className="field__label">Store</span>
            <select className="select" value={store} onChange={(e) => setStore(e.target.value)}>
              <option value="">Any store</option>
              {product.marketplaces.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
          )}
          {spec.basis && (
          <fieldset className="fieldset">
            <legend>Price basis</legend>
            <label className="radio">
              <input type="radio" name="basis" checked={basis === 'base'} onChange={() => setBasis('base')} />
              <span>Base price (listing price, excluding shipping)</span>
            </label>
            <label className="radio">
              <input type="radio" name="basis" checked={basis === 'delivered'} onChange={() => setBasis('delivered')} />
              <span>Confirmed delivered price (base + known shipping; unknown shipping never counts)</span>
            </label>
          </fieldset>
          )}
          {type === 'meaningful_discount' && (
            <label className="field">
              <span className="field__label">Minimum Genuine Discount Score (40–100)</span>
              <input className="input" inputMode="numeric" value={minScore} onChange={(e) => setMinScore(e.target.value)}
                aria-invalid={error ? true : undefined} aria-describedby={error ? `${titleId}-err` : undefined} />
            </label>
          )}
          {type === 'below_target' && (
          <label className="field">
            <span className="field__label">Target price (₹)</span>
            <input
              className="input"
              inputMode="decimal"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? `${titleId}-err` : undefined}
            />
          </label>
          )}
          {error && (
            <p id={`${titleId}-err`} className="inline-error" role="alert">
              {error}
            </p>
          )}
          <label className="field">
            <span className="field__label">Cooldown after a notification</span>
            <select className="select" value={cooldown} onChange={(e) => setCooldown(Number(e.target.value))}>
              {COOLDOWNS.map(([h, label]) => (
                <option key={h} value={h}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          {!rule && (
            <label className="checkbox">
              <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
              <span>Start active (otherwise saved as paused)</span>
            </label>
          )}
          {serverError && (
            <p className="inline-error" role="alert">
              {serverError}
            </p>
          )}
          <div className="row-gap">
            <button type="submit" className="btn btn--primary" disabled={save.isPending}>
              {save.isPending ? 'Saving…' : 'Save alert'}
            </button>
            <button type="button" className="btn btn--secondary" onClick={close}>
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
