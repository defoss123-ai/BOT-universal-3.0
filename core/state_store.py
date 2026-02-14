"""SQLite-backed state persistence for pair configs/runtime and app state."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class StateStore:
    """Simple SQLite JSON store for application state."""

    def __init__(self, db_path: str = "bot_state.db") -> None:
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pairs_state (
                    pair_id TEXT PRIMARY KEY,
                    config_json TEXT NOT NULL,
                    runtime_json TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS app_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    data_json TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def save_pair_config(self, pair_id: str, data_json: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pairs_state(pair_id, config_json, runtime_json, updated_at)
                VALUES(?, ?, COALESCE((SELECT runtime_json FROM pairs_state WHERE pair_id = ?), '{}'), CURRENT_TIMESTAMP)
                ON CONFLICT(pair_id) DO UPDATE SET
                    config_json = excluded.config_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (pair_id, json.dumps(data_json), pair_id),
            )

    def save_pair_runtime(self, pair_id: str, data_json: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pairs_state(pair_id, config_json, runtime_json, updated_at)
                VALUES(?, COALESCE((SELECT config_json FROM pairs_state WHERE pair_id = ?), '{}'), ?, CURRENT_TIMESTAMP)
                ON CONFLICT(pair_id) DO UPDATE SET
                    runtime_json = excluded.runtime_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (pair_id, pair_id, json.dumps(data_json)),
            )

    def load_all_pairs(self) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT pair_id, config_json, runtime_json FROM pairs_state").fetchall()
        out: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        for row in rows:
            config = json.loads(row["config_json"] or "{}")
            runtime = json.loads(row["runtime_json"] or "{}")
            out.append((str(row["pair_id"]), config, runtime))
        return out

    def delete_pair(self, pair_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM pairs_state WHERE pair_id = ?", (pair_id,))

    def save_app_state(self, data_json: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO app_state(id, data_json, updated_at)
                VALUES(1, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    data_json = excluded.data_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (json.dumps(data_json),),
            )

    def load_app_state(self) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT data_json FROM app_state WHERE id = 1").fetchone()
        if row is None:
            return {}
        return json.loads(row["data_json"] or "{}")
