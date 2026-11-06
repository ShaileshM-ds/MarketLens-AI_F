import os
import uuid

import pytest
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from helpers import SAMPLE_PATH
from marketlens_core.db import ensure_mode_indexes
from marketlens_core.settings import DataMode, Settings

MONGO_URI = os.environ.get("TEST_MONGO_URI", "mongodb://localhost:27018")


@pytest.fixture(scope="session")
def mongo_client():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1500, tz_aware=True)
    try:
        client.admin.command("ping")
    except PyMongoError:
        pytest.skip(f"MongoDB not reachable at {MONGO_URI}; start it with `docker compose up -d mongo`")
    yield client
    client.close()


@pytest.fixture
def settings(mongo_client):
    """Fresh, uniquely named databases per test; dropped afterwards."""
    prefix = f"mltest_{uuid.uuid4().hex[:10]}"
    s = Settings(
        mongo_uri=MONGO_URI,
        mongo_db_demo=f"{prefix}_demo",
        mongo_db_imported=f"{prefix}_imported",
        mongo_db_live=f"{prefix}_live",
        mongo_db_accounts=f"{prefix}_accounts",
    )
    yield s
    for name in (s.mongo_db_demo, s.mongo_db_imported, s.mongo_db_live, s.mongo_db_accounts):
        mongo_client.drop_database(name)


@pytest.fixture
def dbs(mongo_client, settings):
    out = {}
    for mode in DataMode:
        db = mongo_client[settings.database_for(mode)]
        ensure_mode_indexes(db)
        out[mode] = db
    return out


@pytest.fixture(scope="module")
def sample_env(mongo_client):
    """The real sample imported once per module into throwaway databases, plus an API client."""
    from fastapi.testclient import TestClient

    from app.main import create_app
    from helpers import NOW
    from marketlens_core.importing import service

    if not SAMPLE_PATH.exists():
        pytest.skip("sample dataset missing")
    prefix = f"mltest_{uuid.uuid4().hex[:10]}"
    s = Settings(
        mongo_uri=MONGO_URI,
        mongo_db_demo=f"{prefix}_demo",
        mongo_db_imported=f"{prefix}_imported",
        mongo_db_live=f"{prefix}_live",
        mongo_db_accounts=f"{prefix}_accounts",
    )
    for m in DataMode:
        ensure_mode_indexes(mongo_client[s.database_for(m)])
    db = mongo_client[s.mongo_db_imported]
    run = service.create_run(db, filename="mens.csv", data=SAMPLE_PATH.read_bytes(), user="t", settings=s, now=NOW)
    service.update_config(db, run["_id"], run["suggested_config"], settings=s, now=NOW)
    service.confirm_run(db, run["_id"], user="t", now=NOW)
    service.process_next_job(db, settings=s, now_fn=lambda: NOW)
    with TestClient(create_app(s)) as client:
        yield {"client": client, "db": db, "settings": s, "mongo": mongo_client}
    for name in (s.mongo_db_demo, s.mongo_db_imported, s.mongo_db_live, s.mongo_db_accounts):
        mongo_client.drop_database(name)


P5_PASSWORDS = {"alice": "alice-test-password-1", "bob": "bob-test-password-1"}


def p5_row(lid, market, price, ship, pid="MCL0001", **kw):
    from helpers import SAMPLE_ROW

    return {**SAMPLE_ROW, "product_id": pid, "listing_id": lid, "seller_id": f"S-{lid}", "marketplace": market, "price": price, "shipping_cost": ship, **kw}


def p5_import(db, settings, rows, now, policy="allow_timezone_unknown", name="file.csv"):
    """Import through the real pipeline at a chosen ingestion time; returns the finished run."""
    from helpers import csv_bytes
    from marketlens_core.importing import service

    run = service.create_run(db, filename=name, data=csv_bytes(rows), user="t", settings=settings, now=now)
    cfg = dict(run["suggested_config"])
    cfg["timestamp_policy"] = policy
    if not cfg["category_map"]:  # files outside the snapshot preset: map explicitly, as an admin would
        cfg["category_map"] = {c: "mens-clothing" for c in run["source_categories"]}
    service.update_config(db, run["_id"], cfg, settings=settings, now=now)
    service.confirm_run(db, run["_id"], user="t", now=now)
    done = service.process_next_job(db, settings=settings, now_fn=lambda: now)
    assert done["status"] == "completed", done
    return done


@pytest.fixture
def p5(settings, dbs, mongo_client):
    """Two signed-in consumers (alice, bob), an anonymous client, and a tiny imported catalogue."""
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from app.auth import hash_password
    from app.main import create_app
    from helpers import NOW

    mongo_client[settings.mongo_db_accounts].users.insert_many(
        [{"_id": u, "username": u, "role": "consumer", "password_hash": hash_password(pw)} for u, pw in P5_PASSWORDS.items()]
    )
    db = dbs[DataMode.IMPORTED]
    seed = p5_import(
        db,
        settings,
        [
            p5_row("L-A", "Amazon", "1380", "60"),
            p5_row("L-F", "Flipkart", "1370", "60"),
            p5_row("L-M", "Myntra", "1480", "0"),
            p5_row("L-2A", "Amazon", "990", "40", pid="MCL0002", product_name="Other product"),
        ],
        NOW,
        name="seed.csv",
    )
    app = create_app(settings)
    with TestClient(app) as alice, TestClient(app) as bob, TestClient(app) as anon:
        for name, c in (("alice", alice), ("bob", bob)):
            assert c.post("/api/v1/auth/login", json={"username": name, "password": P5_PASSWORDS[name]}).status_code == 200
        yield SimpleNamespace(alice=alice, bob=bob, anon=anon, db=db, dbs=dbs, settings=settings, seed_run=seed, mongo=mongo_client)


@pytest.fixture(scope="session")
def sample_bytes() -> bytes:
    if not SAMPLE_PATH.exists():
        pytest.skip(f"sample dataset missing: {SAMPLE_PATH}")
    return SAMPLE_PATH.read_bytes()
