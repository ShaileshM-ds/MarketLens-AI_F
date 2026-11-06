# MarketLens AI

Explainable marketplace intelligence: compare offers, check whether discounts are genuine, and look back at observed price history. It's a decision aid, not a savings guarantee.

Rules for contributors (and coding agents) are in [CLAUDE.md](CLAUDE.md); scope, decisions, design and data requirements are in [docs/](docs/).

## Layout

| Path | What it is |
| --- | --- |
| `frontend/` | React + TypeScript + Vite web app (served by nginx in Docker) |
| `backend/` | FastAPI API (`/api/v1/...`) |
| `worker/` | Separate Python background worker |
| `shared/` | `marketlens_core`: business logic shared by the API and worker |
| `docker-compose.yml` | MongoDB, API, worker and web app |
| `data/samples/` | Sample datasets (not loaded automatically) |

Demo, Imported and Live data use three separate MongoDB databases (`marketlens_demo`, `marketlens_imported`, `marketlens_live`). They are never mixed.

## Run with Docker (recommended)

Requires Docker Desktop (Compose v2). From the repository root:

```bash
cp .env.example .env
```

```bash
docker compose up --build -d
```

```bash
docker compose ps
```

All four services should show `healthy` (the first build takes a few minutes). Then open:

- Web app: http://localhost:8080
- API health: http://localhost:8080/api/v1/health (or directly at http://localhost:8000/api/v1/health)
- API docs: http://localhost:8000/api/docs

Logs and shutdown:

```bash
docker compose logs -f api worker
```

```bash
docker compose down
```

To also delete the MongoDB volume (all local data, every mode):

```bash
docker compose down -v
```

MongoDB is exposed on host port 27018 (to avoid clashing with a local MongoDB on 27017). If port 8080, 8000 or 27018 is already in use, change `WEB_PORT`, `API_PORT` or `MONGO_PORT` in `.env`.

## Run for development (hot reload)

Start only MongoDB in Docker:

```bash
docker compose up -d mongo
```

API (Python 3.11+), in one terminal from the repository root:

```bash
python -m venv .venv
```

```bash
source .venv/Scripts/activate   # Windows (Git Bash); on macOS/Linux: source .venv/bin/activate
```

```bash
pip install -r backend/requirements.txt -e shared
```

Point the API and worker at the Docker MongoDB (host port 27018). Run this in each terminal that starts the API or worker:

```bash
export MONGO_URI=mongodb://localhost:27018
```

```bash
cd backend && uvicorn app.main:app --reload --port 8000
```

Worker, in a second terminal (activate the same virtualenv and set `MONGO_URI` as above, from the repository root):

```bash
cd worker && python -m marketlens_worker.main
```

Web app, in a third terminal:

```bash
cd frontend && npm install && npm run dev
```

Open http://localhost:5173. The Vite dev server proxies `/api` to http://localhost:8000.

## Create an administrator

There are no default accounts. With the stack running, create one (you'll be asked for a password of at least 12 characters):

```bash
docker compose exec api python -m app.cli create-user --username your-name --role admin
```

Then sign in under **Data administration** at http://localhost:8080/admin and choose **New import**. Imports always go to Imported data.

## Tests

The Python tests need MongoDB on port 27018 (`docker compose up -d mongo`). Integration tests use throwaway `mltest_*` databases and are skipped if MongoDB isn't reachable. From the repository root:

```bash
python -m venv .venv && source .venv/Scripts/activate && pip install -r requirements-dev.txt
```

```bash
python -m pytest
```

Frontend tests and typecheck:

```bash
cd frontend && npm test
```

```bash
cd frontend && npm run typecheck
```

## Product Explorer

Open http://localhost:8080/products and choose **Imported** in the data-mode switcher. The explorer reads a derived `product_summaries` collection. It's kept current by every import; to rebuild it by hand (only that collection is written):

```bash
docker compose exec api python -m app.cli rebuild-summaries --mode imported
```

See [docs/PHASE3_PRODUCT_EXPLORER.md](docs/PHASE3_PRODUCT_EXPLORER.md) for routes, parameters, sorting, filter and price rules.

## Demo data and price history

- **Generate Demo data:** sign in as an administrator, then Data administration → **Generate demo data**.
  - It's deterministic and synthetic, and writes only to the Demo database.
  - The CSV export and a separate `answer_key.json` are written to `data/demo-export/`.
  - **Reset demo data** requires typing `RESET DEMO`.
- **See history:** choose **Demo** and open any product. The Price History chart (7/30/90/180 days) and the Timeline tab (Time Machine) use only verified UTC observations, with an explicit cutoff.
- **Imported snapshot products** without verified history say so.
- **API:**
  - `GET /api/v1/products/{id}/history?mode=&cutoff=2026-10-31T23:59:59Z&window=30&basis=base`
  - `GET /api/v1/products/{id}/as-of?mode=&at=…Z`
  - Admin: `/api/v1/admin/demo/{status,generate,reset}`

## Watchlists, price alerts and notifications

- Sign in at http://localhost:8080/signin. Accounts are created with `python -m app.cli create-user`; there's no self sign-up. Use **Watch** on any product.
- Open **Watchlist & alerts** to:
  - create target-price alerts (base or confirmed delivered price, any store or one store)
  - manage your alerts
  - read notifications
- Alerts are evaluated by the worker when **new** observations are imported. Existing snapshot prices never trigger them.
- Email is a local outbox only; nothing is sent.
- Details: [docs/PHASE5_WATCHLISTS_ALERTS.md](docs/PHASE5_WATCHLISTS_ALERTS.md).

## Comparison and price intelligence

- Tick **Compare** on up to 4 product cards (or use **Add to comparison** on a product page), then open **Compare** in the tray, or go to http://localhost:8080/compare.
- Product pages show the three lowest-price measures, delivered-price and price-composition charts, discount transparency, availability, ratings and data provenance.
- Formulas and limits: [docs/PHASE4_PRICE_INTELLIGENCE.md](docs/PHASE4_PRICE_INTELLIGENCE.md).
- The worker rebuilds the explorer read model at startup if it's out of date; nothing else is written.

## API

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/api/v1/health` | Service status, MongoDB ping, and which data modes are available. Returns 503 if MongoDB is unreachable. |
| GET | `/api/v1/categories?mode=demo` | The eight launch categories with product counts for that mode only. Live returns 409 until a provider is configured. |
| POST | `/api/v1/auth/login`, `/api/v1/auth/logout`; GET `/api/v1/auth/me` | Session sign-in (HttpOnly cookie). |
| GET, POST | `/api/v1/admin/imports` | Admin only. List runs; upload a CSV/JSON/JSONL file (max 10 MB) to profile it. |
| GET | `/api/v1/admin/imports/{id}` | Admin only. Run status, profile, preview, validation and results. |
| PUT | `/api/v1/admin/imports/{id}/config` | Admin only. Save the mapping; evaluates every row for preview and validation. |
| POST | `/api/v1/admin/imports/{id}/confirm` | Admin only. Queue the import for the worker. |
| GET | `/api/v1/admin/imports/{id}/rejected` | Admin only. Quarantined rows with plain reasons, paged. |
| GET | `/api/v1/products?mode=` | Explorer listing: search, store-level filters, sort, pagination. Read-only. |
| GET | `/api/v1/products/filters?mode=` | Filter options and data-basis flags from the active workspace. |
| GET | `/api/v1/products/{id}?mode=` | Product, store listings with current observation, comparison, review summary, price-history status. |
| GET | `/api/v1/products/{id}/reviews?mode=` | Paged reviews as plain text with store and synthetic labels. |
| GET, PUT, DELETE | `/api/v1/watchlist[/{product_id}]?mode=` | Signed in. Your watchlist; PUT adds or merges notes and watch-until date. |
| GET, POST, PATCH, DELETE | `/api/v1/alerts[/{id}]?mode=` | Signed in. Below-target price alerts; `/{id}/events` shows the evaluation log. |
| GET, POST | `/api/v1/notifications…?mode=` | Signed in. List, unread count, detail with evidence, read, dismiss, read-all. |
| GET | `/api/v1/compare?mode=&ids=…` | Up to 4 products side by side: three lowest-price measures, discount and rating ranges, availability, quality labels, comparability warnings. Read-only. |
