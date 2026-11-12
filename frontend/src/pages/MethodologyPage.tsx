import type { ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { PageHeader } from './PageHeader';
import { apiGet } from '../lib/api';
import { useDataMode } from '../lib/dataMode';
import { endOfDayUtc } from '../lib/history';
import { formatMoney } from '../lib/money';
import { formatDateTime } from '../lib/format';

/* Every number on this page comes from GET /api/v1/methodology, which reads the constants from the code. */
interface M {
  sections: string[];
  history: { windows: number[] };
  pricing: { discount_tolerance_points: number };
  evidence: { version: string; min_days: number; savings_threshold: number; full_savings: number; agreement_points: number[]; reference_increase: number; stale_days: number; weights: Record<string, number> };
  advice: { version: string; low_percentile: number; strong_savings: number; strong_percentile: number; fresh_hours: number; stale_days: number; missing_share: number; short_history_days: number; expectation_horizon: number };
  forecast: { version: string; horizons: number[]; models: Record<string, string>; median_days: number; min_train_days: number; min_origins: number; max_origins: number; min_improvement_percent: number; interval_level_percent: number; interval_method: string; min_residuals: number; lookback_days: number; stale_days: number };
  memory: { drop_percent: number; return_within_percent: number; further_percent: number; days: number[]; baseline_days: number };
  sync: { version: string; change_percent: number; max_gap_days: number; match_days: number; min_days: number; min_matches: number; min_share: number; stale_days: number; benign: string[] };
  audit: { version: string; urgency_min_days: number; low_stock: number; rules: { rule_id: string; title: string; version: string; kind: string; required: string }[] };
  dashboard: { version: string; max_products: number };
  alerts: Record<string, { label: string; description: string; family: string }>;
  alert_rules: { new_low_lookback_days: number; new_low_min_days: number; switch_fresh_days: number; default_min_score: number; min_score_range: number[]; window_days: number };
}
interface EvalH { days: number; points: number; first_origin: string | null; last_origin: string | null; mae_baseline_minor: number | null; mae_candidate_minor: number | null; mape_baseline_percent: number | null; mape_candidate_percent: number | null; candidate_chosen: number; baseline_chosen: number; calibrated: { points: number; coverage_percent: number | null; mean_width_percent: number | null }; previous: { points: number; coverage_percent: number | null; mean_width_percent: number | null } }
interface Eval { cutoff: string; version: string; level_percent: number; products_evaluated: number; listings_evaluated: number; synthetic: boolean; insufficient: { product_id: string; reason: string }[]; note: string; horizons: EvalH[] }

const TITLES: Record<string, string> = {
  ingestion: 'Data ingestion, validation and provenance', history: 'Historical prices and UTC cutoffs', prices: 'Listed price and confirmed delivered price',
  detector: 'Real Price Detector', score: 'Genuine Discount Score', advice: 'Buying advice and confidence', forecast: 'Forecasting and baseline selection',
  memory: 'Future Price Memory', sync: 'Seller synchronization', audit: 'Pricing practices audit', dashboard: 'Analyst dashboard', alerts: 'Alert types',
};

function Feature({ id, children, what, inputs, how, missing, meaning, limits }: { id: string; children?: ReactNode; what: ReactNode; inputs: ReactNode; how: ReactNode; missing: ReactNode; meaning: ReactNode; limits: ReactNode }) {
  return (
    <section id={id} className="card section-card stack-sm method" aria-labelledby={`${id}-h`}>
      <h2 id={`${id}-h`}>{TITLES[id]}</h2>
      <dl className="method__dl">
        <div><dt>What it does</dt><dd>{what}</dd></div>
        <div><dt>Input data</dt><dd>{inputs}</dd></div>
        <div><dt>Formulas and thresholds</dt><dd>{how}</dd></div>
        <div><dt>Missing or insufficient data</dt><dd>{missing}</dd></div>
        <div><dt>What the result means</dt><dd>{meaning}</dd></div>
        <div><dt>Limitations and false positives</dt><dd>{limits}</dd></div>
      </dl>
      {children}
    </section>
  );
}

export function MethodologyPage() {
  const q = useQuery({ queryKey: ['methodology'], queryFn: () => apiGet<M>('/api/v1/methodology') });
  return (
    <div className="stack-lg methodology">
      <PageHeader eyebrow="How it works" title="Methodology" note="How MarketLens AI turns stored observations into findings. Every threshold below is read from the running code." />
      <p className="muted small">Product photos are openly licensed stock images; authors and licences are listed on the <a href="/credits">Image credits</a> page.</p>
      <p className="callout callout--warn" role="note">
        Analytical indicators are not proof of misconduct. Audit flags, synchronization patterns and discount checks are evidence-based signals for review; each lists
        ordinary explanations. MarketLens AI is a decision aid, not a savings guarantee.
      </p>
      <p className="callout" role="note">
        Data modes never mix: <strong>Demo</strong> is synthetic data from a deterministic generator (every record is labelled synthetic; its planted scenarios are in a
        separate answer key that analytics never read), <strong>Imported</strong> is data an administrator uploaded, and <strong>Live</strong> stays unavailable until a
        provider is configured. Every historical analysis takes an explicit UTC cutoff and never reads an observation made after it, so results can't use future data.
      </p>
      {q.isPending && <p className="muted" role="status">Loading methodology…</p>}
      {q.isError && <p className="inline-error" role="alert">Couldn't load the methodology: {q.error.message}</p>}
      {q.data && <Body m={q.data} />}
    </div>
  );
}

function Body({ m }: { m: M }) {
  const e = m.evidence, a = m.advice, f = m.forecast, s = m.sync, mem = m.memory, au = m.audit;
  const level = f.interval_level_percent / 100;
  return (
    <>
      <nav aria-label="Methodology sections" className="card section-card method__toc">
        <ol>{m.sections.map((id) => <li key={id}><a href={`#${id}`}>{TITLES[id]}</a></li>)}</ol>
      </nav>

      <Feature id="ingestion"
        what="Imports CSV, JSON or JSONL files into the Imported workspace through profile → mapping → preview → validation → confirm, and writes results to products, store listings, observations and reviews."
        inputs="One row per observation: product, listing, seller, store, timestamp, price, reference price, shipping, stock, availability, provenance (source type) and optional reviews."
        how={<>Money is parsed with decimal arithmetic into integer minor units (₹1,380 = 138000); amounts with separators, symbols or extra decimals are rejected. Observation identity is <code>listing + UTC time</code> (or the original timestamp text when the timezone is unknown), so re-imports are duplicates, and a row that reuses an identity with different values is quarantined as an immutable conflict. Category mapping is explicit; unmapped categories are quarantined.</>}
        missing="Blank values stay unknown, never defaulted. Timestamps without a timezone are kept exactly but marked timezone-unknown and never become history. In history imports (UTC required), rows whose stock and availability disagree are quarantined; in snapshot imports they are kept and flagged."
        meaning="Every product, listing, observation and review carries its ingestion run, source file, row reference, schema version and a synthetic flag, and the original row is kept unchanged."
        limits="Validation checks structure and internal consistency, not whether a store's figures are true. Demo data comes only from the generator; imports always go to Imported." />

      <Feature id="history"
        what="Builds price history and the Time Machine from verified observations only."
        inputs="Observations with an explicit UTC (or offset) timestamp."
        how={<>A listing's daily value is the lowest observation that day up to the cutoff; the product line is the lowest listing that day. Windows: {m.history.windows.join(', ')} days ending at the cutoff. The Time Machine shows, per listing, the latest verified observation at or before the chosen time and the one before it, with changed fields.</>}
        missing="Missing days are gaps, never interpolated. Unknown shipping is a gap on the delivered basis. Mixed currencies produce no series."
        meaning="What was observed, as of the cutoff, nothing later."
        limits="Observation frequency depends on the source; a day's lowest price can hide intraday changes." />

      <Feature id="prices"
        what="Separates the listed (base) price from the confirmed delivered price."
        inputs="Base price, shipping cost and whether shipping is known."
        how={<>Delivered price = base price + known shipping. Three separate lowest measures are shown: lowest listed price, lowest confirmed delivered price, and lowest confirmed delivered price among offers in stock or limited stock. Advertised discounts are compared with the reduction from the seller's reference price; differences above {m.pricing.discount_tolerance_points} points are shown neutrally.</>}
        missing="Unknown shipping is never treated as free: the total reads “Total incomplete” and that listing can't be the confirmed cheapest. Coupons and payment offers are conditional and never subtracted."
        meaning="Which offer is cheapest on each definition, with ties listed."
        limits="Delivery fees can depend on location and order size, which the data may not capture." />

      <Feature id="detector"
        what="Checks whether the current price is genuinely below its usual level."
        inputs={`Verified observations of each store listing in the window (${m.history.windows.filter((w) => w >= 30).join('/')} days), with an advertised discount and reference price where reported.`}
        how={<>Per listing (same seller, store and currency). Usable observations: known price on the chosen basis, in stock or limited stock, no stock contradiction. Current = the listing's latest verified observation at or before the cutoff. Usual price = median of the daily lowest prices in the window, current observation excluded. Real savings % = 100 × (usual − current) ÷ usual. Verdict: “Genuine price reduction” at ≥ {e.savings_threshold}%, “Above its usual price” at ≤ −{e.savings_threshold}%, otherwise “No real reduction”. The seller's reference price is flagged as raised when it is ≥ {e.reference_increase}% above its window median. The product result uses the listing with the lowest current price.</>}
        missing={`Fewer than ${e.min_days} distinct observed days: “Insufficient historical evidence” and no verdict. An out-of-stock or unconfirmed latest price is never treated as current. Listings in different currencies are never compared.`}
        meaning="Whether today's price is low compared with this listing's own observed history, separately from what the seller advertises."
        limits={`A short window may not include the price before a long-running promotion. A latest observation older than ${e.stale_days} days is reported as a limitation.`} />

      <Feature id="score"
        what="Scores 0–100 how well observed prices support a discount."
        inputs="The Real Price Detector result for the headline listing."
        how={<><p>Score = {e.weights.savings}% real savings + {e.weights.percentile}% price percentile + {e.weights.agreement}% agreement with the advertised discount.</p>
          <p>Savings component: 0% or less scores 0, {e.full_savings}% or more scores 100, linear between. Percentile: share of observed days that were more expensive (ties count half). Agreement: advertised discount minus real savings; within {e.agreement_points[0]} points scores 100, {e.agreement_points[1]} points or more scores 0. Bands: 70+ strong, 40–69 some, below 40 little evidence.</p></>}
        missing={<>Under {e.min_days} distinct observed days the score is unavailable. Without an advertised discount the agreement weight is left out and the others are rescaled; this is disclosed.</>}
        meaning="A high score means the price is low against its own history and the advertised discount is roughly honest."
        limits="A permanent “MRP” far above the usual price lowers agreement even when the price itself is fair." />

      <Feature id="advice"
        what="Recommends Buy now, Consider waiting or Insufficient evidence from observed history."
        inputs="The Real Price Detector and score at the cutoff, plus the other price basis as a cross-check."
        how={<>Buy now only when real savings ≥ {e.savings_threshold}%; otherwise Consider waiting (an ordinary price is never presented as a bargain). Confidence starts high only for ≥ {a.strong_savings}% savings with a price lower than ≥ {a.strong_percentile}% of observed days (or ≥ {a.strong_savings}% above usual for waiting), medium at ≥ {e.savings_threshold}%, else low. It drops one level each when the latest observation is older than {a.fresh_hours} hours, more than {a.missing_share * 100}% of days are missing, fewer than {a.short_history_days} days were observed, or any signal disagrees (raised reference price, unsupported advertised discount, a different verdict on the other basis).</>}
        missing={`Abstains (Insufficient evidence) when evidence is unavailable, currencies are mixed, or the latest verified observation is more than ${a.stale_days} days before the cutoff.`}
        meaning={<>Whether history makes now a good time to buy. A {a.expectation_horizon}-day forecast is shown separately only when its model beat the last-price baseline, and it never changes the recommendation.</>}
        limits="Past prices don't guarantee future ones; Consider waiting doesn't promise a drop." />

      <Feature id="forecast"
        what={`Estimates the price ${f.horizons.join(', ')} days ahead for one store listing, tested against a simple baseline.`}
        inputs={`The headline listing's daily lowest usable verified price, up to ${f.lookback_days} days before the cutoff.`}
        how={<><p>Models: {Object.values(f.models).join(' and ')}. Rolling-origin backtest in date order: at each past day (after {f.min_train_days} observed days) a model sees only earlier prices and its guess is compared with the price actually observed exactly h days later; the last {f.max_origins} origins are used. Model choice is made separately for each forecast series (one store listing: one product, seller, store and currency) from its own backtest; other series never influence it. The candidate is used only if its mean absolute error is at least {f.min_improvement_percent}% lower than the baseline's for that series; otherwise the forecast uses the last observed price.</p>
          <p>{f.interval_level_percent}% range ({f.interval_method}, {f.version}): half-width = the ceil((n + 1) × {level})-th smallest of the n relative errors |actual ÷ predicted − 1|. Coverage and width are measured walk-forward, using at each origin only errors whose prices were observed by then. The {f.interval_level_percent}% is a nominal target; the measured coverage is reported next to it and can be lower.</p></>}
        missing={`No forecast for a horizon with fewer than ${f.min_origins} backtest points, no range with fewer than ${f.min_residuals} past errors, and none at all for stale (> ${f.stale_days} days), insufficient or mixed-currency data.`}
        meaning="An estimate with its measured backtest error, never an observed price."
        limits="Neither model knows about sales, stock or events. Measured coverage can fall short of the nominal level (see the evaluation below); the page then says so.">
        <ForecastEvaluation />
      </Feature>

      <Feature id="memory"
        what="Shows what happened after this product's past price drops."
        inputs="The same daily series as forecasting."
        how={<>A drop is a daily price at least {mem.drop_percent}% below the median of the previous {mem.baseline_days} observed days. After {mem.days.join('/')} days: “returned” when back within {mem.return_within_percent}% of the pre-drop median, “fell further” when at least {mem.further_percent}% below the drop price, otherwise “stayed low”. Episodes don't overlap: a new one can start only {Math.max(...mem.days)} days after the last.</>}
        missing="Outcomes whose day is after the cutoff are “not yet completed” and aren't counted; a missing day is “no observation”."
        meaning="Counts of past outcomes, not probabilities or predictions."
        limits="A few past episodes say little about the next one." />

      <Feature id="sync"
        what="Looks for store listings of one product whose prices change together."
        inputs="Repeated verified base prices from at least two listings, kept separate by seller, store and currency."
        how={<>A change is a move of ≥ {s.change_percent}% between consecutive observed days at most {s.max_gap_days} days apart. Two changes match when they go the same direction within {s.match_days} day. A pattern worth investigating needs ≥ {s.min_matches} matches covering ≥ {s.min_share * 100}% of the smaller set of changes. Otherwise: occasional, independent or no price changes.</>}
        missing={`Insufficient with fewer than ${s.min_days} days observed for both listings or no observation in the last ${s.stale_days} days; different currencies are “not comparable”.`}
        meaning="Correlation in timing, not coordination. Similar or equal prices alone are never a finding."
        limits={<>Ordinary causes include: {s.benign.join(' ')} These results are not proof of collusion.</>} />

      <Feature id="audit"
        what="Applies versioned rules that flag pricing practices worth reviewing."
        inputs="The Real Price Detector plus individual observations (urgency messages, stock, availability, displayed discounts)."
        how={<><ul className="bullets">{au.rules.map((r) => <li key={r.rule_id}><strong>{r.title}</strong> ({r.kind}, {au.version}/{r.version}) — needs {r.required}.</li>)}</ul>
          <p>Calculated rules use the Real Price Detector (unsupported discount; reference price raised, high severity when it rose 50%+ while the price stayed within 5%). The heuristic urgency rule needs the message on ≥ {au.urgency_min_days} days while stock stayed normal (In Stock with more than {au.low_stock} units). Observed rules report recorded contradictions directly.</p></>}
        missing="A rule whose data is missing is disabled and listed as such. Snapshot observations without a timezone count only if they were ingested by the cutoff."
        meaning="Each finding has a rule version, severity, confidence, supporting observations and ordinary explanations."
        limits="Flags for review, not legal findings. An urgency message can be a store-wide banner; a list price can be the manufacturer's." />

      <Feature id="dashboard"
        what="Summarises the active workspace at a cutoff."
        inputs="Every product's evidence, advice, audit, synchronization and forecast results, plus observation counts."
        how={<>Counts of products, listings, verified and snapshot observations, quarantined rows and data-quality flags; distributions of verdicts, advice, score bands and real savings; a price index = daily median across products of each product's lowest verified price as a % of its own window median (100 = usual). At most {m.dashboard.max_products} products per request; results are cached until the next import.</>}
        missing="Without verified history only the snapshot counts are shown."
        meaning="Where genuine discounts, audit flags or synchronization patterns concentrate, with links to each product's evidence."
        limits="Filters narrow products; each product is still analysed across all its listings." />

      <Feature id="alerts"
        what="Notifies you in the app (email is a local outbox record; nothing is sent)."
        inputs="Your rule, and observations imported after the rule became active."
        how={<p>Signal alerts run only when an import adds verified observations for the product; the analysis cutoff is the latest verified observation time, never the import time. State-based types record a baseline first and notify only on a real change. Meaningful discount defaults to a minimum score of {m.alert_rules.default_min_score} (range {m.alert_rules.min_score_range.join('–')}); new low compares with the previous {m.alert_rules.new_low_lookback_days} days and needs {m.alert_rules.new_low_min_days}+ earlier observed days; seller switch uses listings observed in the last {m.alert_rules.switch_fresh_days} days.</p>}
        missing="Insufficient evidence is recorded as an evaluation outcome and never notifies."
        meaning="Each notification links to its stored evidence and the analysis version that produced it."
        limits="Alerts depend on new imports; there is no continuous live monitoring.">
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Alert types">
          <table className="table table--compact">
            <thead><tr><th scope="col">Type</th><th scope="col">Kind</th><th scope="col">Triggers when</th></tr></thead>
            <tbody>{Object.entries(m.alerts).map(([k, t]) => <tr key={k}><td>{t.label}</td><td>{t.family}</td><td>{t.description}</td></tr>)}</tbody>
          </table>
        </div>
      </Feature>
    </>
  );
}

function EvalSummary({ e }: { e: Eval }) {
  const lost = e.horizons.filter((h) => h.points > 0 && (h.mae_baseline_minor ?? 0) < (h.mae_candidate_minor ?? 0)).map((h) => h.days);
  const below = e.horizons.filter((h) => h.calibrated.coverage_percent !== null && h.calibrated.coverage_percent < e.level_percent).map((h) => h.days);
  const wider = e.horizons.filter((h) => (h.calibrated.mean_width_percent ?? 0) > (h.previous.mean_width_percent ?? 0)).map((h) => h.days);
  const days = (xs: number[]) => xs.map((d) => `${d}-day`).join(', ');
  return (
    <ul className="bullets small">
      {lost.length > 0 && <li>Pooled over all series, the last observed price (baseline) is more accurate than the candidate at {days(lost)}. Each series still chooses its own model; the pooled figure is reported, not used to choose.</li>}
      {wider.length > 0 && <li>Higher coverage than the previous method came with wider ranges at {days(wider)}: compare the width column, not coverage alone.</li>}
      {below.length > 0 && <li>{days(below)} ranges remain below the nominal {e.level_percent}% target and are not calibrated.</li>}
    </ul>
  );
}

function ForecastEvaluation() {
  const { mode, unavailableReason } = useDataMode();
  const blocked = unavailableReason(mode);
  const meta = useQuery({ queryKey: ['dash-meta', mode], queryFn: () => apiGet<{ latest_verified_at: string | null }>('/api/v1/dashboard/meta', { mode }), enabled: !blocked });
  const day = meta.data?.latest_verified_at?.slice(0, 10) ?? null;
  const cutoff = day ? endOfDayUtc(day) : null;
  const q = useQuery({ queryKey: ['forecast-eval', mode, cutoff], queryFn: () => apiGet<Eval>('/api/v1/forecast-evaluation', { mode, cutoff: cutoff!, basis: 'base' }), enabled: cutoff !== null && !blocked });
  const pct = (x: number | null) => (x === null ? '—' : `${x}%`);
  return (
    <section className="stack-sm" aria-labelledby="fc-eval-h">
      <h3 id="fc-eval-h">Forecast evaluation ({mode} workspace)</h3>
      {blocked && <p className="muted">{blocked}</p>}
      {meta.data && !day && <p className="empty-inline">No verified history in this workspace, so there is nothing to evaluate.</p>}
      {q.isPending && cutoff && <p className="muted" role="status">Running the rolling-origin evaluation…</p>}
      {q.isError && <p className="inline-error" role="alert">Couldn't load the evaluation: {q.error.message}</p>}
      {q.data && (
        <>
          <p className="small">
            {q.data.products_evaluated} products ({q.data.listings_evaluated} store listings) up to {formatDateTime(q.data.cutoff)};{' '}
            {q.data.insufficient.length} with insufficient data. Nominal range {q.data.level_percent}%; arrows show previous method → calibrated ({q.data.version}).
          </p>
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Forecast evaluation region">
            <table className="table table--compact" aria-label="Forecast evaluation">
              <thead><tr><th scope="col">Horizon</th><th scope="col">Points</th><th scope="col">Period (origins)</th><th scope="col">Mean abs. error: baseline / candidate</th><th scope="col">MAPE: baseline / candidate</th><th scope="col">Candidate used (series)</th><th scope="col">Range coverage</th><th scope="col">Average range width</th></tr></thead>
              <tbody>
                {q.data.horizons.map((h) => (
                  <tr key={h.days}>
                    <td>{h.days} days</td><td>{h.points}</td><td>{h.first_origin} – {h.last_origin}</td>
                    <td>{formatMoney(h.mae_baseline_minor)} / {formatMoney(h.mae_candidate_minor)}</td>
                    <td>{pct(h.mape_baseline_percent)} / {pct(h.mape_candidate_percent)}</td>
                    <td>{h.candidate_chosen} of {h.candidate_chosen + h.baseline_chosen}</td>
                    <td>{pct(h.previous.coverage_percent)} → {pct(h.calibrated.coverage_percent)}</td>
                    <td>{pct(h.previous.mean_width_percent)} → {pct(h.calibrated.mean_width_percent)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <EvalSummary e={q.data} />
          <p className="muted small">{q.data.note}</p>
          {q.data.insufficient.length > 0 && <p className="muted small">Insufficient: {q.data.insufficient.map((i) => `${i.product_id} (${i.reason})`).join('; ')}</p>}
        </>
      )}
    </section>
  );
}
