"""Admin access and the importer wizard over HTTP (real MongoDB)."""

import pytest
from fastapi.testclient import TestClient

from app.auth import hash_password
from app.main import create_app
from helpers import NOW, SAMPLE_ROW, csv_bytes
from marketlens_core.importing import service
from marketlens_core.settings import DataMode

pytestmark = pytest.mark.integration

ADMIN_PW = "test-admin-password-1"
USER_PW = "test-consumer-password-1"


@pytest.fixture
def client(settings, dbs, mongo_client):
    accounts = mongo_client[settings.mongo_db_accounts]
    accounts.users.insert_many(
        [
            {"_id": "admin1", "username": "admin1", "role": "admin", "password_hash": hash_password(ADMIN_PW)},
            {"_id": "shopper1", "username": "shopper1", "role": "consumer", "password_hash": hash_password(USER_PW)},
        ]
    )
    with TestClient(create_app(settings)) as c:
        yield c


def login(client, username, password):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def upload(client, data=None, name="mens.csv"):
    data = data if data is not None else csv_bytes([SAMPLE_ROW])
    return client.post("/api/v1/admin/imports", files={"file": (name, data, "text/csv")})


def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200 and r.json()["mongo"] == "ok"


def test_admin_endpoints_require_sign_in(client):
    assert client.get("/api/v1/admin/imports").status_code == 401
    assert upload(client).status_code == 401


def test_non_admin_is_forbidden(client):
    assert login(client, "shopper1", USER_PW).status_code == 200
    assert client.get("/api/v1/admin/imports").status_code == 403
    assert upload(client).status_code == 403


def test_login_failure_and_cookie_flags(client):
    bad = login(client, "admin1", "wrong-password")
    assert bad.status_code == 401 and "incorrect" in bad.json()["detail"]
    ok = login(client, "admin1", ADMIN_PW)
    assert ok.status_code == 200 and ok.json()["role"] == "admin"
    cookie = ok.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert client.get("/api/v1/auth/me").json()["username"] == "admin1"
    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/auth/me").status_code == 401


def test_cross_site_requests_blocked(client):
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "admin1", "password": ADMIN_PW},
        headers={"Origin": "https://evil.example"},
    )
    assert r.status_code == 403


def test_upload_limits_and_formats(client, settings):
    login(client, "admin1", ADMIN_PW)
    r = upload(client, b"x", name="notes.txt")
    assert r.status_code == 400 and "CSV, JSON and JSONL" in r.json()["detail"]
    settings.import_max_bytes = 10
    r = upload(client)
    assert r.status_code == 413 and "limit" in r.json()["detail"]


def test_wizard_end_to_end_writes_only_imported(client, dbs, settings, sample_bytes):
    login(client, "admin1", ADMIN_PW)

    r = upload(client, sample_bytes, name="mens_clothing_dataset_enriched.csv")
    assert r.status_code == 201, r.text
    run = r.json()
    assert run["status"] == "profiled" and run["mode"] == "imported"
    assert run["profile"]["row_count"] == 1500 and len(run["profile"]["columns"]) == 31
    assert run["preset"] == "mens-clothing-snapshot"

    r = client.put(f"/api/v1/admin/imports/{run['id']}/config", json=run["suggested_config"])
    assert r.status_code == 200, r.text
    ev = r.json()["evaluation"]
    assert ev["counts"]["accepted"] == 1500 and ev["counts"]["warning_rows"] == 44
    assert len(ev["preview_rows"]) == 20
    assert ev["preview_rows"][0]["price_minor"] == 138000

    r = client.post(f"/api/v1/admin/imports/{run['id']}/confirm")
    assert r.status_code == 200 and r.json()["status"] == "queued"
    service.process_next_job(dbs[DataMode.IMPORTED], settings=settings, now_fn=lambda: NOW)

    r = client.get(f"/api/v1/admin/imports/{run['id']}")
    done = r.json()
    assert done["status"] == "completed"
    assert done["summary"]["accepted"] == 1500
    assert client.get(f"/api/v1/admin/imports/{run['id']}/rejected").json()["total"] == 0
    assert any(x["id"] == run["id"] for x in client.get("/api/v1/admin/imports").json()["runs"])

    def count(mode):
        cats = client.get(f"/api/v1/categories?mode={mode}").json()["categories"]
        return {c["slug"]: c["product_count"] for c in cats}["mens-clothing"]

    assert count("imported") == 500
    assert count("demo") == 0
    for mode in (DataMode.DEMO, DataMode.LIVE):
        assert dbs[mode].observations.count_documents({}) == 0
        assert dbs[mode].ingestion_runs.count_documents({}) == 0
