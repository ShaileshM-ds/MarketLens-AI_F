import { useEffect, useState } from 'react';
import { DATA_MODES, MODE_LABELS, useDataMode, type DataMode } from '../lib/dataMode';

/**
 * Data-mode switcher plus the persistent badge (CLAUDE.md: Provenance).
 * Unavailable modes stay focusable and explain why instead of silently failing.
 */
export function ModeSwitcher() {
  const { mode, setMode, unavailableReason } = useDataMode();
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!notice) return;
    const t = window.setTimeout(() => setNotice(null), 6000);
    return () => window.clearTimeout(t);
  }, [notice]);

  const choose = (m: DataMode) => {
    const reason = unavailableReason(m);
    if (reason) {
      setNotice(reason);
      return;
    }
    setNotice(null);
    setMode(m);
  };

  return (
    <div className="mode">
      <div className="segmented" role="group" aria-label="Data mode">
        {DATA_MODES.map((m) => {
          const reason = unavailableReason(m);
          return (
            <button
              key={m}
              type="button"
              className="segmented__item"
              aria-pressed={mode === m}
              aria-disabled={reason ? true : undefined}
              title={reason ?? `Show ${MODE_LABELS[m].name.toLowerCase()} data`}
              onClick={() => choose(m)}
            >
              {MODE_LABELS[m].name}
            </button>
          );
        })}
      </div>
      <span className={`mode-badge mode-badge--${mode}`} aria-label={`Active data mode: ${MODE_LABELS[mode].badge}`}>
        {MODE_LABELS[mode].badge}
      </span>
      <div className="mode__notice" role="status" aria-live="polite">
        {notice && <span className="popover">{notice}</span>}
      </div>
    </div>
  );
}
