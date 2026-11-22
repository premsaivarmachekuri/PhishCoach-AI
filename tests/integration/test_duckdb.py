import uuid
from pathlib import Path

from app.main import app
from app.services.auth import hash_password
from app.services.config import get_settings
from app.services.db import DuckDBClient, get_db
from fastapi.testclient import TestClient


def test_duckdb_schema_auth_and_kb_search(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "duckdb-test-secret-32-bytes-long!!")
    get_settings.cache_clear()

    db_file = str(tmp_path / "test.duckdb")
    db = DuckDBClient(db_file)
    app.dependency_overrides[get_db] = lambda: db

    # Verify default app_config was seeded by DuckDB migration
    cfg = db.select("app_config", filters={"key": "min_cohort_size"}, limit=1)
    assert cfg and cfg[0]["value_json"]["min_cohort_size"] == 5

    # Insert KB chunk and search
    db.insert(
        "kb_chunks",
        {"source": "test.md", "title": "Sender Mismatch", "body": "Always inspect the sender domain."},
    )
    hits = db.search_kb("sender domain", limit=1)
    assert len(hits) == 1
    assert hits[0]["title"] == "Sender Mismatch"

    # Create auth account + user and test /auth/login + /auth/me
    auth_uid = str(uuid.uuid4())
    db.insert(
        "auth_accounts",
        {"id": auth_uid, "email": "duck@example.com", "password_hash": hash_password("Secret123!")},
    )
    db.upsert(
        "users",
        {
            "anon_id": "emp_duck",
            "role_name": "Analyst",
            "department": "Finance",
            "seniority": "mid",
            "arm": "treatment",
            "app_role": "employee",
            "is_synthetic": False,
            "auth_user_id": auth_uid,
        },
        on_conflict="anon_id",
    )

    client = TestClient(app)
    login_res = client.post("/auth/login", json={"email": "duck@example.com", "password": "Secret123!"})
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]

    me_res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    assert me_res.json()["anon_id"] == "emp_duck"

    app.dependency_overrides.clear()
    db.conn.close()
