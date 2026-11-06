"""MarketLens background worker.

Runs separately from the API. Polls each available data mode's `jobs`
collection and runs queued jobs (currently: imports). Writes a heartbeat file
that the container health check reads.
"""

import logging
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from marketlens_core.db import prepare_databases
from marketlens_core.alerts.engine import process_next_alert_job, requeue_stale_alert_jobs
from marketlens_core.demo.generator import process_next_demo_job
from marketlens_core.explorer import ensure_summaries_current
from marketlens_core.importing.service import process_next_job
from marketlens_core.settings import DataMode, get_settings

HEARTBEAT_FILE = Path("/tmp/worker-heartbeat")
log = logging.getLogger("marketlens.worker")
_stopping = False


def _request_stop(signum, _frame) -> None:
    global _stopping
    log.info("Received signal %s; stopping.", signum)
    _stopping = True


def _connect(uri: str) -> MongoClient:
    client = MongoClient(uri, serverSelectionTimeoutMS=3000, tz_aware=True)
    for attempt in range(1, 31):
        try:
            client.admin.command("ping")
            return client
        except PyMongoError as exc:
            log.warning("MongoDB not reachable (attempt %d): %s", attempt, type(exc).__name__)
            time.sleep(2)
    raise SystemExit("MongoDB unreachable; worker exiting.")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)

    client = _connect(settings.mongo_uri)
    prepare_databases(client, settings)
    # Derived explorer read model only; source collections are never written here.
    for mode in DataMode:
        rebuilt = ensure_summaries_current(client[settings.database_for(mode)])
        if rebuilt:
            log.info("Rebuilt %d product summaries in %s (read model was out of date).", rebuilt, mode.value)
        requeued = requeue_stale_alert_jobs(client[settings.database_for(mode)], now=_utcnow())
        if requeued:
            log.info("Requeued %d interrupted alert jobs in %s (evaluation is idempotent).", requeued, mode.value)
    modes = []
    for mode in DataMode:
        reason = settings.mode_unavailable_reason(mode)
        log.info("Mode %s -> database %s (%s)", mode.value, settings.database_for(mode), reason or "available")
        if reason is None:
            modes.append(mode)
    log.info("Worker started. Job handlers: import, alerts.")

    while not _stopping:
        try:
            client.admin.command("ping")
            HEARTBEAT_FILE.write_text(str(int(time.time())))
            worked = False
            for mode in modes:
                db = client[settings.database_for(mode)]
                run = process_next_job(db, settings=settings, now_fn=_utcnow)
                if run:
                    worked = True
                    log.info("Import %s in %s finished: %s", run["_id"], mode.value, run["status"])
                try:
                    job = process_next_alert_job(db, now_fn=_utcnow)
                except Exception:  # noqa: BLE001 - recorded on the job; retried later
                    log.exception("Alert evaluation failed in %s; it will be retried.", mode.value)
                    job = None
                if job:
                    worked = True
                    log.info("Alert evaluation for import %s in %s finished.", job["run_id"], mode.value)
                if mode is DataMode.DEMO:
                    demo_job = process_next_demo_job(db, export_dir=Path(settings.demo_export_dir), now_fn=_utcnow)
                    if demo_job:
                        worked = True
                        log.info("Demo job %s (%s) finished.", demo_job["_id"], demo_job["type"])
            if worked:
                continue  # look for more work straight away
        except PyMongoError as exc:
            log.warning("MongoDB error: %s", type(exc).__name__)
        for _ in range(settings.worker_poll_seconds):
            if _stopping:
                break
            time.sleep(1)

    client.close()
    log.info("Worker stopped.")


if __name__ == "__main__":
    main()
