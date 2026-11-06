"""Import wizard state machine and worker job, stored in the Imported database.

profiled → mapped → queued → running → completed | failed
"""

import hashlib
import logging
import uuid
from datetime import datetime
from typing import Callable

from bson import Binary
from pymongo import ReturnDocument
from pymongo.database import Database

from ..db import INGESTION_RUNS, JOBS, REJECTED_RECORDS, SOURCE_FILES
from ..settings import DataMode, Settings
from . import SCHEMA_VERSION
from .config import TARGET_FIELDS, ImportConfig, config_problems, source_categories, suggest_config
from .engine import apply, describe, evaluate
from .parsing import FileFormatError, ParsedFile, detect_format, parse_file, profile
from .rows import REASON_LABELS, WARNING_LABELS, RowContext

log = logging.getLogger("marketlens.importer")
EDITABLE = ("profiled", "mapped")


class ServiceError(Exception):
    def __init__(self, status: int, message: str, problems: list[str] | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.problems = problems or []


def _get_run(db: Database, run_id: str) -> dict:
    run = db[INGESTION_RUNS].find_one({"_id": run_id})
    if not run:
        raise ServiceError(404, "That import doesn't exist.")
    return run


def _load(db: Database, run: dict, settings: Settings) -> ParsedFile:
    f = db[SOURCE_FILES].find_one({"_id": run["file"]["source_file_id"]})
    if not f:
        raise ServiceError(410, "The original file for this import is missing.")
    return parse_file(bytes(f["content"]), run["file"]["format"], settings.import_max_rows)


def _ctx(run: dict, now: datetime, config: ImportConfig) -> RowContext:
    return RowContext(
        run_id=run["_id"],
        source_file_id=run["file"]["source_file_id"],
        source_filename=run["file"]["filename"],
        now=now,
        timestamp_policy=config.timestamp_policy,
    )


def create_run(db: Database, *, filename: str, data: bytes, user: str, settings: Settings, now: datetime) -> dict:
    fmt = detect_format(filename)  # FileFormatError -> 400
    parsed = parse_file(data, fmt, settings.import_max_rows)
    sha = hashlib.sha256(data).hexdigest()
    file_id = uuid.uuid4().hex
    run_id = uuid.uuid4().hex
    db[SOURCE_FILES].insert_one(
        {
            "_id": file_id,
            "filename": filename,
            "format": fmt,
            "size_bytes": len(data),
            "sha256": sha,
            "content": Binary(data),  # original bytes, unchanged
            "uploaded_by": user,
            "uploaded_at": now,
        }
    )
    previous = db[INGESTION_RUNS].find_one(
        {"file.sha256": sha, "status": "completed"}, {"_id": 1, "finished_at": 1}, sort=[("created_at", -1)]
    )
    config, preset = suggest_config(parsed)
    run = {
        "_id": run_id,
        "mode": DataMode.IMPORTED.value,
        "status": "profiled",
        "file": {"source_file_id": file_id, "filename": filename, "format": fmt, "size_bytes": len(data), "sha256": sha},
        "profile": profile(parsed),
        "source_categories": source_categories(parsed, config),
        "preset": preset,
        "suggested_config": config.to_dict(),
        "config": None,
        "evaluation": None,
        "summary": None,
        "error": None,
        "previous_completed_run_id": previous["_id"] if previous else None,
        "schema_version": SCHEMA_VERSION,
        "created_by": user,
        "created_at": now,
        "updated_at": now,
    }
    db[INGESTION_RUNS].insert_one(run)
    return run


def update_config(db: Database, run_id: str, config_data: dict, *, settings: Settings, now: datetime) -> dict:
    run = _get_run(db, run_id)
    if run["status"] not in EDITABLE:
        raise ServiceError(409, f"This import is {run['status']} and can no longer be changed.")
    parsed = _load(db, run, settings)
    config = ImportConfig.from_dict(config_data)
    problems = config_problems(config, parsed.columns)
    if problems:
        raise ServiceError(422, "The mapping needs changes before it can be previewed.", problems)
    ev = evaluate(db, parsed, config, _ctx(run, now, config))
    description = describe(ev)
    if config.timestamp_policy == "require_utc":
        from .history_check import history_check

        description["history_check"] = history_check(ev, config)
    update = {
        "status": "mapped",
        "config": config.to_dict(),
        "source_categories": source_categories(parsed, config),
        "evaluation": {**description, "evaluated_at": now},
        "updated_at": now,
    }
    return db[INGESTION_RUNS].find_one_and_update(
        {"_id": run_id}, {"$set": update}, return_document=ReturnDocument.AFTER
    )


def confirm_run(db: Database, run_id: str, *, user: str, now: datetime) -> dict:
    run = db[INGESTION_RUNS].find_one_and_update(
        {"_id": run_id, "status": "mapped"},
        {"$set": {"status": "queued", "confirmed_by": user, "queued_at": now, "updated_at": now}},
        return_document=ReturnDocument.AFTER,
    )
    if not run:
        current = _get_run(db, run_id)
        raise ServiceError(409, f"This import is {current['status']}; review the mapping and preview before confirming.")
    db[JOBS].insert_one(
        {"_id": uuid.uuid4().hex, "type": "import", "run_id": run_id, "status": "queued", "created_at": now, "attempts": 0}
    )
    return run


def process_next_job(db: Database, *, settings: Settings, now_fn: Callable[[], datetime]) -> dict | None:
    """Claim and run one queued import job. Returns the finished run, or None if nothing was queued."""
    job = db[JOBS].find_one_and_update(
        {"status": "queued", "type": "import"},
        {"$set": {"status": "running", "started_at": now_fn()}, "$inc": {"attempts": 1}},
        sort=[("created_at", 1)],
        return_document=ReturnDocument.AFTER,
    )
    if not job:
        return None
    run_id = job["run_id"]
    db[INGESTION_RUNS].update_one({"_id": run_id}, {"$set": {"status": "running", "started_at": now_fn()}})
    try:
        run = _get_run(db, run_id)
        parsed = _load(db, run, settings)
        config = ImportConfig.from_dict(run["config"])
        ctx = _ctx(run, now_fn(), config)
        summary = apply(db, evaluate(db, parsed, config, ctx), ctx)
        finished = now_fn()
        db[JOBS].update_one({"_id": job["_id"]}, {"$set": {"status": "completed", "finished_at": finished}})
        if summary["created"]["observations"]:
            # Alerts are evaluated only after observations are durably stored, in a separate idempotent job.
            from ..alerts.engine import enqueue_alert_job

            enqueue_alert_job(db, run_id, finished)
        return db[INGESTION_RUNS].find_one_and_update(
            {"_id": run_id},
            {"$set": {"status": "completed", "summary": summary, "ingested_at": ctx.now, "finished_at": finished, "updated_at": finished}},
            return_document=ReturnDocument.AFTER,
        )
    except Exception as exc:  # record a plain failure; never leave the run "running"
        log.exception("Import job %s failed", job["_id"])
        message = exc.message if isinstance(exc, ServiceError) else (str(exc) if isinstance(exc, FileFormatError) else "The import failed unexpectedly; see the worker log.")
        finished = now_fn()
        db[JOBS].update_one({"_id": job["_id"]}, {"$set": {"status": "failed", "finished_at": finished, "error": message}})
        return db[INGESTION_RUNS].find_one_and_update(
            {"_id": run_id},
            {"$set": {"status": "failed", "error": message, "finished_at": finished, "updated_at": finished}},
            return_document=ReturnDocument.AFTER,
        )


def list_runs(db: Database, limit: int = 50) -> list[dict]:
    return list(
        db[INGESTION_RUNS].find(
            {}, {"profile": 0, "evaluation": 0, "suggested_config": 0, "config": 0, "source_categories": 0}
        ).sort("created_at", -1).limit(limit)
    )


def get_run(db: Database, run_id: str) -> dict:
    return _get_run(db, run_id)


def rejected_page(db: Database, run_id: str, page: int, page_size: int) -> dict:
    _get_run(db, run_id)
    q = {"run_id": run_id}
    total = db[REJECTED_RECORDS].count_documents(q)
    items = list(
        db[REJECTED_RECORDS].find(q, {"_id": 0}).sort("row_number", 1).skip((page - 1) * page_size).limit(page_size)
    )
    return {"total": total, "page": page, "page_size": page_size, "items": items}


def wizard_reference() -> dict:
    """Static labels the wizard needs (target fields, reason and warning labels)."""
    from ..catalog import LAUNCH_CATEGORIES

    return {
        "target_fields": [t.__dict__ for t in TARGET_FIELDS],
        "launch_categories": [{"slug": c.slug, "label": c.label} for c in LAUNCH_CATEGORIES],
        "reason_labels": REASON_LABELS,
        "warning_labels": WARNING_LABELS,
        "timestamp_policies": {
            "allow_timezone_unknown": "Snapshot: keep timestamps without a timezone as 'timezone unknown' (not usable for history)",
            "require_utc": "History: every row must have an ISO 8601 UTC timestamp, and rows whose stock and availability disagree are quarantined",
        },
    }
