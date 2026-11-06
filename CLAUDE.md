# MarketLens AI — Standing rules

Read these before every task. Also read docs/SCOPE.md, docs/DECISIONS.md, docs/DESIGN.md and docs/DATA_REQUIREMENTS.md.

## Stack
- Frontend: React + TypeScript + Vite.
- API: FastAPI.
- Database: MongoDB.
- A separate Python worker for background jobs.
- Everything runs under Docker Compose.

## Money
- Store every price as an integer in minor units (₹1,380 = 138000). Never store floats for money.
- Display money only through ONE shared formatting function. Chart axes, tooltips, tables, filters and inputs all use it. No ad-hoc formatting anywhere.
- User price inputs (targets, filters) are always entered in rupees and converted to minor units at the boundary.

## Unknown values
- Unknown values stay blank. Never guess, default or infer them.
- Unknown shipping is never free. Show "Total incomplete" instead of a total.

## Provenance and data modes
- Every record carries a synthetic flag and a source label.
- A persistent data-mode badge (Demo / Imported / Live) shows on every screen and carries into exports and notifications.
- Demo, Imported and Live data live in SEPARATE databases and are never mixed.

## Reviews
- Review text is rendered as plain text only. Never render it as HTML or Markdown.

## Historical analysis
- Every historical analysis takes an explicit cutoff date and never uses data observed after it.

## Scope
- Do not add features outside CLAUDE.md or docs/SCOPE.md. Ask first.
- Not in scope: chatbot, sentiment analysis, review summaries, fake-review detection.
