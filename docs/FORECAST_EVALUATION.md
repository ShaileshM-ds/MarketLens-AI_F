# Forecast evaluation (forecast-2)

**Data:** the synthetic Demo workspace (deterministic generator, seed 20261031), base price, cutoff 2026-10-31T23:59:59Z.

> Synthetic data: these results show the method behaves as designed on controlled data. They are not evidence of real-market performance.

Reproduce with `GET /api/v1/forecast-evaluation?mode=demo&cutoff=2026-10-31T23:59:59Z&basis=base`. The same table appears on the Methodology page.

## Setup

- **Scope:** one store listing per product, the evidence headline (the lowest current price). Sellers, stores and currencies are never mixed.
- **Evaluated:** 39 products and 39 listings.
- **Insufficient:** 1 product. DEMO-P-011 has 10 observed days, fewer than the 14 needed.
- **Backtest:** rolling origin in date order, each horizon separately, with the last 120 origins per listing.
  - At each origin a model sees only the prices observed up to that day.
  - The target is the price observed exactly h days later. Origins whose target day is missing are skipped.
- **Models:**
  - Baseline: the last observed price.
  - Candidate: the median of the last 14 observed days.
  - Model choice is made separately for each forecast series: one store listing, so one product, seller, store and currency.
  - The candidate is used only when its mean absolute error in that series' own backtest is at least 5% lower than the baseline's.
  - Other series never influence the choice. Pooled figures below are for reporting only.
  - On Demo the candidate is chosen for 0 of 39 series at 7 days, 3 at 14 days and 9 at 30 days; the rest use the baseline.
- **Interval** (calibrated, `conformal-relative-abs`):
  - The half-width is the ⌈(n+1)·0.8⌉-th smallest of the n relative errors |actual ÷ predicted − 1|.
  - At each origin only errors whose target day had already been observed are used, so later evaluation errors never shape earlier intervals.
  - No interval is given with fewer than 10 known errors.
- **Previous interval** (forecast-1): signed-error nearest-rank 10th and 90th percentiles. It is measured on the same walk-forward points for comparison.

## Errors: baseline vs candidate

Pooled over all rolling-origin points.

| Horizon | Points | Origins | MAE baseline | MAE candidate | MAPE baseline | MAPE candidate | Candidate used (per series) |
|---|---:|---|---:|---:|---:|---:|---:|
| 7 days | 4,613 | 2026-05-16 – 2026-10-24 | ₹60.79 | ₹74.89 | 1.15% | 1.51% | 0 of 39 |
| 14 days | 4,616 | 2026-05-16 – 2026-10-17 | ₹82.84 | ₹92.13 | 1.66% | 1.95% | 3 of 39 |
| 30 days | 4,601 | 2026-05-22 – 2026-10-01 | ₹113.99 | ₹118.84 | 2.34% | 2.37% | 9 of 39 |

Pooled over all series, the baseline is more accurate at every horizon. The candidate is selected only for series where it beat the baseline in that series' own backtest.

## Interval coverage and width: before vs after calibration

Width is the average interval size as a % of the prediction.

| Horizon | Walk-forward points | Coverage before | Coverage after | Width before | Width after |
|---|---:|---:|---:|---:|---:|
| 7 days | 3,994 | 75.66% | **78.92%** | 3.42% | 3.73% |
| 14 days | 3,728 | 65.67% | **75.75%** | 4.29% | 4.74% |
| 30 days | 3,099 | 51.40% | **70.80%** | 4.54% | 6.21% |

- **Where coverage improved:** every horizon.
  - The gain comes from scaling errors by the price level and from the finite-sample rank.
  - **The better coverage came with wider intervals:** width rose 9–37% while coverage rose 3–19 points. Compare both columns, not coverage alone.
- **Where it falls short:** coverage is still below the nominal 80% at all three horizons.
  - The shortfall is clearest at 14 and 30 days.
  - Errors aren't exchangeable over time. The planted price events (sudden 15–20% moves) and the random-walk drift make later errors larger than the earlier errors available at each origin.
- **What the UI shows:** 80% is a nominal target, shown separately from the measured coverage, and any horizon below 80% is marked "Not calibrated". The ranges are not calibrated 80% intervals.

## Limitations

- Synthetic data with simple dynamics: a 0.8%-a-day random walk plus planted scenarios. Real prices may behave differently.
- Errors are pooled across listings. Per-listing coverage varies, and with fewer than 10 known errors no interval is shown.
- One listing per product. Other listings aren't evaluated.
- Imported data has no verified history, so it can't be evaluated. The report says so.
