"""Delivery transports, kept apart from evaluation.

In-app delivery is the notification document itself. Email is a local outbox
record that states nothing was sent (SCOPE §5); no message ever leaves the app.
"""

from datetime import datetime

from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from ..db import EMAIL_OUTBOX

EMAIL_NOT_SENT_NOTE = "Email delivery is not configured. This is a local outbox record; nothing was sent."


def record_email_outbox(db: Database, notification: dict, now: datetime) -> None:
    try:
        db[EMAIL_OUTBOX].insert_one(
            {
                "_id": notification["_id"],
                "notification_id": notification["_id"],
                "user_id": notification["user_id"],
                "status": "not_sent",
                "note": EMAIL_NOT_SENT_NOTE,
                "created_at": now,
            }
        )
    except DuplicateKeyError:
        pass  # already recorded (retry)


def deliver(db: Database, notification: dict, now: datetime) -> None:
    record_email_outbox(db, notification, now)
