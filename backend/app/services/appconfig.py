"""Typed access to the app_config table. No in-code defaults: a missing row is an error."""
from typing import Any

from app.services.config import ConfigMissingError
from app.services.db import DBProtocol


def get_all_config(db: DBProtocol) -> dict[str, Any]:
    return {r["key"]: r["value_json"] for r in db.select("app_config")}


def require_config(cfg: dict[str, Any], key: str) -> dict[str, Any]:
    value = cfg.get(key)
    if not isinstance(value, dict) or not value:
        raise ConfigMissingError(f"app_config['{key}'] is missing or empty; seed or restore it from the Config tab.")
    return value


def get_config(db: DBProtocol, key: str) -> dict[str, Any]:
    rows = db.select("app_config", filters={"key": key}, limit=1)
    return require_config({r["key"]: r["value_json"] for r in rows}, key)


def require_field(section: dict[str, Any], key: str, field: str) -> Any:
    if field not in section:
        raise ConfigMissingError(f"app_config['{key}'] is missing field '{field}'.")
    return section[field]
