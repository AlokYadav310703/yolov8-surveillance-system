"""Tiny SQLite layer: one connection, one lock, plain SQL."""
from __future__ import annotations

import json
import sqlite3
import threading

from . import config

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None
_settings = dict(config.DEFAULT_SETTINGS)

SCHEMA = """
CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    vec BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    person_id INTEGER,
    person_name TEXT NOT NULL,
    camera_id TEXT NOT NULL,
    camera_name TEXT NOT NULL,
    similarity REAL,
    snapshot TEXT
);
CREATE INDEX IF NOT EXISTS idx_detections_ts ON detections(ts);
CREATE TABLE IF NOT EXISTS cameras (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source TEXT NOT NULL,
    kind TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def init() -> None:
    global _conn
    with _lock:
        _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA foreign_keys=ON")
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.executescript(SCHEMA)
        cols = [r["name"] for r in _conn.execute("PRAGMA table_info(cameras)")]
        if "enabled" not in cols:                       # database created by an older version
            _conn.execute("ALTER TABLE cameras ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1")
            _conn.commit()
        for row in _conn.execute("SELECT key, value FROM settings"):
            if row["key"] in _settings:
                _settings[row["key"]] = json.loads(row["value"])


def execute(sql: str, params: tuple = ()) -> int:
    with _lock:
        cur = _conn.execute(sql, params)
        _conn.commit()
        return cur.lastrowid


def query(sql: str, params: tuple = ()) -> list[dict]:
    with _lock:
        return [dict(r) for r in _conn.execute(sql, params).fetchall()]


def one(sql: str, params: tuple = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def get_settings() -> dict:
    return dict(_settings)


def update_settings(new: dict) -> dict:
    clean = {}
    if "threshold" in new:
        clean["threshold"] = min(0.9, max(0.1, float(new["threshold"])))
    if "cooldown" in new:
        clean["cooldown"] = min(3600, max(1, int(new["cooldown"])))
    if "log_unknown" in new:
        clean["log_unknown"] = bool(new["log_unknown"])
    for key, value in clean.items():
        _settings[key] = value
        execute("INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))
    return get_settings()
