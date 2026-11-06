# Design

Reference mockups: `docs/design/Home.png`, `Product explorer.png`, `Product page.png`, `Watchlist and alerts.png`.

## Mockup content is illustrative
The mockups show brand names (Nike, Adidas, Levi's…) and sizes on cards. These are placeholders. In the real app, brand stays blank when the data has no brand, and size/colour are never parsed from titles (see docs/DECISIONS.md). Myntra's "free shipping" in the mockup only appears when shipping is known to be zero.

## Layout
- **App shell:** fixed left sidebar (white) with the logo (gradient square + "MarketLens AI") and nav: Overview, Product explorer, Watchlist & alerts, Analyst dashboard, Data administration, Methodology.
- **Top bar:** breadcrumb ("Workspace / Page") on the left; on the right the data-mode badge (e.g. "Demo · synthetic data", pale amber pill) and an "Alerts N" pill. The badge is on every screen.
- **Content:** cards on a lavender-to-white background, generous spacing, two-column grids on wide screens, single column on mobile.

## Visual language
- **Background:** vertical gradient from soft lavender at the top to near-white.
- **Cards:** white, large rounded corners (~16px), soft diffuse shadow, thin faint border.
- **Sidebar active item:** solid blue fill, white bold text, rounded. Inactive items are plain dark-grey text.
- **Primary buttons:** blue gradient (blue → indigo), white bold text, rounded (e.g. Search, Track price, Compare N selected, highlighted Visit store).
- **Secondary buttons:** pale blue/white fill, blue text, thin border (Edit, Pause, Add to comparison, Visit store, Track price on cards).
- **Filter chips:** white rounded pills with blue text (Category, Marketplace, Price, Coverage, Sort, Grid | Table).
- **Pills/badges:** green pill for percent-off and unread counts; red/pink pill for "Lowest price"; lavender pill for "Synthetic sample review" / "Synthetic data".
- **Headings:** bold dark navy; accent words in blue (e.g. "Shop with evidence.", "explorer"). Small uppercase letter-spaced eyebrow labels above titles.
- **Category / feature tiles:** pastel rounded-square letter icons, title and one-line subtitle.

## Key components
- **Buying Advice card:** pale green gradient card, green-bordered. "BUYING ADVICE" eyebrow, solid green verdict pill (BUY NOW / CONSIDER WAITING / INSUFFICIENT EVIDENCE), one-sentence reason, forecast range and confidence in smaller text, then "A decision aid, not a savings guarantee." with a "Why this verdict?" link.
- **Price-history chart:** purple line with a soft purple area fill beneath it, current-price marker dot and purple value label at the end. Presets 7D | 30D | 90D | 180D in the card header, active one bold.
- **Store rows (Price comparison):** store letter avatar, store name, item price + shipping breakdown, known total, and a "Visit store" button. The cheapest known total gets the primary gradient button. Unknown shipping shows "Total incomplete".
- **Product header:** breadcrumb, image with thumbnails, title, product rating · review count · condition · synthetic label, "Lowest price" pill, large price, percent-off pill, M.R.P. struck through, cheapest known total, Track price + Add to comparison.
- **Tabs:** Timeline / Evidence / Forecast with a blue underline on the active tab.
- **Customer reviews:** "Review rating N / 5" bold, synthetic label pill, plain-text body, dividers between reviews, empty-state line.
- **Product cards (explorer):** lavender image panel, brand (blank if unknown), title, price, percent-off pill, product rating · store count, Compare checkbox, Track price button.
- **Watchlist & alerts:** two cards — Tracked products (target in rupees, alert types, Edit/Pause) and Notifications (title, readable UTC date · In app · Open product link, "N unread" pill).

## Typography and accessibility
- Minimum text size 12px everywhere, including chart labels and badges.
- Readable contrast in both themes; visible focus rings; respects reduced motion.
- Dates shown in readable form (e.g. "4 Nov 2026, 10:35 UTC"), never raw ISO strings.

## Themes
- **Light:** as in the mockups.
- **Dark:** deep navy/indigo background gradient in place of lavender→white, dark slate cards with subtle borders, same blue/indigo accents, green and purple kept but tuned for contrast. Charts are theme-aware.
- All colours come from shared design tokens, so both themes stay in sync.
