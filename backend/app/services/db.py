import contextvars
import json
import re
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import duckdb
from app.services.config import get_settings

JSON_COLUMNS = {
    "brief_json",
    "target_filter",
    "email_json",
    "planted_flags",
    "messages_json",
    "value_json",
    "meta",
}

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ConflictError(Exception):
    """Raised when a UNIQUE/PRIMARY KEY constraint rejects a write (e.g. a duplicate event)."""


_sql_trace: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar("sql_trace", default=None)


def _safe_ident(name: str) -> str:
    if not IDENT_RE.match(name):
        raise ValueError(f"Invalid SQL identifier: {name}")
    return name


class DBProtocol(Protocol):
    def select(
        self,
        table: str,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        order: str | None = None,
        desc: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...

    def insert(
        self, table: str, data: dict[str, Any] | list[dict[str, Any]]
    ) -> list[dict[str, Any]]: ...

    def upsert(
        self, table: str, data: dict[str, Any] | list[dict[str, Any]], on_conflict: str
    ) -> list[dict[str, Any]]: ...

    def update(
        self, table: str, data: dict[str, Any], filters: dict[str, Any]
    ) -> list[dict[str, Any]]: ...

    def delete(self, table: str, filters: dict[str, Any]) -> list[dict[str, Any]]: ...

    def search_kb(self, query: str, limit: int = 3) -> list[dict[str, Any]]: ...


class DuckDBClient:
    """Thread-safe DuckDB repository implementing DBProtocol."""

    def __init__(self, db_path: str = "./data/phishcoach.duckdb"):
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = duckdb.connect(db_path)
        self._init_schema()

    def _init_schema(self) -> None:
        schema_path = Path(__file__).resolve().parents[3] / "db" / "migrations" / "001_duckdb_schema.sql"
        sql_text = schema_path.read_text(encoding="utf-8")
        with self._lock:
            self.conn.execute(sql_text)  # schema bootstrap; intentionally not traced

    @contextmanager
    def capture_sql(self):
        """Record the SQL statements executed inside this context (powers the honest 'Show SQL' view)."""
        buf: list[str] = []
        token = _sql_trace.set(buf)
        try:
            yield buf
        finally:
            _sql_trace.reset(token)

    def _exec(self, sql: str, params: list[Any] | None = None):
        buf = _sql_trace.get()
        if buf is not None:
            buf.append(sql)
        try:
            return self.conn.execute(sql, params or [])
        except duckdb.ConstraintException as exc:
            raise ConflictError(str(exc)) from exc

    def _serialize_val(self, col: str, val: Any) -> Any:
        if col in JSON_COLUMNS and not isinstance(val, str):
            return json.dumps(val)
        return val

    def _deserialize_row(self, cols: list[str], row: tuple[Any, ...]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for col, val in zip(cols, row):
            if col in JSON_COLUMNS and isinstance(val, str):
                try:
                    val = json.loads(val)
                except Exception:
                    pass
            elif isinstance(val, datetime):
                # DuckDB TIMESTAMP is naive UTC; emit an explicit offset so browsers don't parse it as local time.
                if val.tzinfo is None:
                    val = val.replace(tzinfo=timezone.utc)
                val = val.isoformat()
            out[col] = val
        return out

    def _build_where(self, filters: dict[str, Any] | None) -> tuple[str, list[Any]]:
        if not filters:
            return "", []
        clauses: list[str] = []
        params: list[Any] = []
        for k, v in filters.items():
            col = _safe_ident(k)
            if v is None:
                clauses.append(f"{col} IS NULL")
            elif isinstance(v, (list, set, tuple)):
                v = list(v)
                if not v:
                    clauses.append("1=0")
                else:
                    placeholders = ", ".join(["?"] * len(v))
                    clauses.append(f"{col} IN ({placeholders})")
                    params.extend(v)
            else:
                clauses.append(f"{col} = ?")
                params.append(v)
        return " WHERE " + " AND ".join(clauses), params

    def select(
        self,
        table: str,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        order: str | None = None,
        desc: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        tbl = _safe_ident(table)
        cols_sql = "*" if columns.strip() == "*" else ", ".join(_safe_ident(c.strip()) for c in columns.split(","))
        where_sql, params = self._build_where(filters)
        sql = f"SELECT {cols_sql} FROM {tbl}{where_sql}"
        if order:
            sql += f" ORDER BY {_safe_ident(order)} {'DESC' if desc else 'ASC'}"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        with self._lock:
            cur = self._exec(sql, params)
            col_names = [d[0] for d in cur.description]
            rows = cur.fetchall()
        return [self._deserialize_row(col_names, r) for r in rows]

    def insert(
        self, table: str, data: dict[str, Any] | list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        tbl = _safe_ident(table)
        items = data if isinstance(data, list) else [data]
        if not items:
            return []
        inserted: list[dict[str, Any]] = []
        with self._lock:
            for item in items:
                row = dict(item)
                if "id" not in row and tbl not in ("risk_scores", "app_config"):
                    row["id"] = str(uuid.uuid4())
                if "created_at" not in row and tbl in (
                    "users",
                    "auth_accounts",
                    "kb_chunks",
                    "campaigns",
                    "templates",
                    "remediation_queue",
                ):
                    row["created_at"] = datetime.now(timezone.utc).isoformat()
                cols = [_safe_ident(k) for k in row.keys()]
                vals = [self._serialize_val(k, row[k]) for k in cols]
                placeholders = ", ".join(["?"] * len(cols))
                sql = f"INSERT INTO {tbl} ({', '.join(cols)}) VALUES ({placeholders}) RETURNING *"
                cur = self._exec(sql, vals)
                col_names = [d[0] for d in cur.description]
                res_rows = cur.fetchall()
                inserted.extend(self._deserialize_row(col_names, r) for r in res_rows)
        return inserted

    def upsert(
        self, table: str, data: dict[str, Any] | list[dict[str, Any]], on_conflict: str
    ) -> list[dict[str, Any]]:
        tbl = _safe_ident(table)
        conflict_col = _safe_ident(on_conflict)
        items = data if isinstance(data, list) else [data]
        if not items:
            return []
        out: list[dict[str, Any]] = []
        with self._lock:
            for item in items:
                row = dict(item)
                if "id" not in row and tbl not in ("risk_scores", "app_config"):
                    # Preserve existing id on conflict if present
                    existing = self.select(tbl, columns="id", filters={conflict_col: row.get(conflict_col)}, limit=1)
                    row["id"] = existing[0]["id"] if existing else str(uuid.uuid4())
                cols = [_safe_ident(k) for k in row.keys()]
                vals = [self._serialize_val(k, row[k]) for k in cols]
                placeholders = ", ".join(["?"] * len(cols))
                update_cols = [c for c in cols if c not in (conflict_col, "id")]
                if update_cols:
                    set_sql = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
                    sql = (
                        f"INSERT INTO {tbl} ({', '.join(cols)}) VALUES ({placeholders}) "
                        f"ON CONFLICT ({conflict_col}) DO UPDATE SET {set_sql} RETURNING *"
                    )
                else:
                    sql = (
                        f"INSERT INTO {tbl} ({', '.join(cols)}) VALUES ({placeholders}) "
                        f"ON CONFLICT ({conflict_col}) DO NOTHING RETURNING *"
                    )
                cur = self._exec(sql, vals)
                col_names = [d[0] for d in cur.description]
                res_rows = cur.fetchall()
                out.extend(self._deserialize_row(col_names, r) for r in res_rows)
        return out

    def update(
        self, table: str, data: dict[str, Any], filters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        tbl = _safe_ident(table)
        set_cols = [_safe_ident(k) for k in data.keys()]
        set_vals = [self._serialize_val(k, data[k]) for k in set_cols]
        set_sql = ", ".join(f"{c} = ?" for c in set_cols)
        where_sql, where_params = self._build_where(filters)
        sql = f"UPDATE {tbl} SET {set_sql}{where_sql} RETURNING *"
        with self._lock:
            cur = self._exec(sql, set_vals + where_params)
            col_names = [d[0] for d in cur.description]
            rows = cur.fetchall()
        return [self._deserialize_row(col_names, r) for r in rows]

    def delete(self, table: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
        tbl = _safe_ident(table)
        where_sql, params = self._build_where(filters)
        sql = f"DELETE FROM {tbl}{where_sql} RETURNING *"
        with self._lock:
            cur = self._exec(sql, params)
            col_names = [d[0] for d in cur.description]
            rows = cur.fetchall()
        return [self._deserialize_row(col_names, r) for r in rows]

    def search_kb(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        terms = {t for t in re.split(r"[^a-z0-9]+", query.lower()) if len(t) > 2}
        rows = self.select("kb_chunks", columns="id,source,title,body")
        if not terms:
            return rows[:limit]
        scored = []
        for r in rows:
            title = str(r.get("title", "")).lower()
            hay = f"{title} {r.get('body', '')}".lower()
            # Red-flag chunks carry their code in the title, e.g. "(sender_mismatch)"; weight title hits higher.
            score = sum(2 if t in title else 1 for t in terms if t in hay)
            scored.append((score, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        hits = [r for score, r in scored[:limit] if score > 0]
        return hits or rows[:limit]


_db_instance: DuckDBClient | None = None


def get_db() -> DBProtocol:
    global _db_instance
    if _db_instance is None:
        settings = get_settings()
        _db_instance = DuckDBClient(settings.duckdb_path)
    return _db_instance
