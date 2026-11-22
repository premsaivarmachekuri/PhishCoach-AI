import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt

TEST_JWT_SECRET = "test-secret-for-pytest-only-32bytes!"


def make_test_token(auth_user_id: str) -> str:
    exp = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
    return jwt.encode({"sub": auth_user_id, "exp": exp}, TEST_JWT_SECRET, algorithm="HS256")


class InMemoryDB:
    """In-memory DB test double implementing DBProtocol (lives strictly under /tests)."""

    def __init__(self):
        self.tables: dict[str, list[dict[str, Any]]] = {
            "users": [],
            "red_flags": [],
            "kb_chunks": [],
            "campaigns": [],
            "templates": [],
            "simulations": [],
            "events": [],
            "coaching_sessions": [],
            "risk_scores": [],
            "remediation_queue": [],
            "app_config": [],
            "audit_log": [],
            "llm_calls": [],
        }
        self._seed_defaults()

    def _seed_defaults(self):
        self.tables["app_config"] = [
            {
                "key": "risk_weights",
                "value_json": {"opened": 2.0, "clicked": 15.0, "replied": 20.0, "submitted": 30.0, "ignored": 5.0, "reported": -15.0},
            },
            {"key": "decay_half_life_days", "value_json": {"days": 30.0}},
            {"key": "role_multipliers", "value_json": {"finance": 1.3, "default": 1.0}},
            {"key": "band_thresholds", "value_json": {"medium": 35.0, "high": 65.0}},
            {"key": "difficulty_map", "value_json": {"Low": 1, "Medium": 2, "High": 3}},
            {"key": "chat_turn_cap", "value_json": {"max_turns": 6}},
            {"key": "min_cohort_size", "value_json": {"min_cohort_size": 5}},
            {"key": "rate_limits", "value_json": {"events_per_min": 60, "chat_per_min": 20, "coach_per_min": 20}},
            {
                "key": "llm_token_budget",
                "value_json": {
                    "coach_max_input_tokens": 1200,
                    "coach_max_output_tokens": 350,
                    "chat_max_output_tokens": 250,
                    "generate_max_output_tokens": 800,
                },
            },
            {
                "key": "control_static_feedback",
                "value_json": {
                    "clicked": "Static control message: Always inspect links before clicking.",
                    "reported": "Static control message: Thank you for reporting.",
                },
            },
        ]
        # Load playbook from authored markdown files
        root = Path(__file__).resolve().parents[1]
        from tools.ingest_kb import parse_red_flags, parse_safe_habits

        rf_text = (root / "content/playbook/red_flags.md").read_text(encoding="utf-8")
        sh_text = (root / "content/playbook/safe_habits.md").read_text(encoding="utf-8")
        flags, rf_chunks = parse_red_flags(rf_text)
        sh_chunks = parse_safe_habits(sh_text)
        for f in flags:
            self.insert("red_flags", f)
        for c in rf_chunks + sh_chunks:
            self.insert("kb_chunks", c)

    def select(
        self,
        table: str,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        order: str | None = None,
        desc: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        rows = list(self.tables.get(table, []))
        if filters:
            for k, v in filters.items():
                if isinstance(v, list):
                    rows = [r for r in rows if r.get(k) in v]
                else:
                    rows = [r for r in rows if r.get(k) == v]
        if order:
            rows.sort(key=lambda r: str(r.get(order, "")), reverse=desc)
        if limit:
            rows = rows[:limit]
        return [dict(r) for r in rows]

    def insert(self, table: str, data: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
        items = data if isinstance(data, list) else [data]
        inserted = []
        for item in items:
            row = dict(item)
            if "id" not in row and table not in ("risk_scores", "app_config"):
                row["id"] = str(uuid.uuid4())
            if "created_at" not in row and table in ("users", "campaigns", "templates", "remediation_queue"):
                row["created_at"] = datetime.now(timezone.utc).isoformat()
            self.tables[table].append(row)
            inserted.append(dict(row))
        return inserted

    def upsert(self, table: str, data: dict[str, Any] | list[dict[str, Any]], on_conflict: str) -> list[dict[str, Any]]:
        items = data if isinstance(data, list) else [data]
        out = []
        for item in items:
            key_val = item.get(on_conflict)
            existing = None
            for idx, r in enumerate(self.tables[table]):
                if r.get(on_conflict) == key_val:
                    existing = idx
                    break
            if existing is not None:
                self.tables[table][existing].update(item)
                out.append(dict(self.tables[table][existing]))
            else:
                out.extend(self.insert(table, item))
        return out

    def update(self, table: str, data: dict[str, Any], filters: dict[str, Any]) -> list[dict[str, Any]]:
        updated = []
        for r in self.tables[table]:
            if all(r.get(k) == v for k, v in filters.items()):
                r.update(data)
                updated.append(dict(r))
        return updated

    def delete(self, table: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
        kept = []
        deleted = []
        for r in self.tables[table]:
            if all(r.get(k) == v for k, v in filters.items()):
                deleted.append(dict(r))
            else:
                kept.append(r)
        self.tables[table] = kept
        return deleted

    def search_kb(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        terms = [t.lower() for t in query.split() if t.strip()]
        scored = []
        for c in self.tables["kb_chunks"]:
            hay = f"{c['title']} {c['body']}".lower()
            score = sum(1 for t in terms if t in hay)
            scored.append((score, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [dict(c) for _, c in scored[:limit]]
