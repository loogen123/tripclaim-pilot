from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


DB_PATH = Path("data/tripclaim.db")


def init_db(db_path: Path = DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_path TEXT NOT NULL,
                status TEXT NOT NULL,
                decision TEXT,
                result_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS manual_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL,
                reviewer TEXT NOT NULL,
                decision TEXT NOT NULL,
                comment TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(case_id) REFERENCES cases(id)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def create_case(folder_path: str, db_path: Path = DB_PATH) -> int:
    init_db(db_path)
    now = _now()
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO cases (folder_path, status, decision, result_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (folder_path, "created", None, None, now, now),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def update_case_result(case_id: int, result: dict[str, Any], db_path: Path = DB_PATH) -> None:
    init_db(db_path)
    now = _now()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            UPDATE cases
            SET status = ?, decision = ?, result_json = ?, updated_at = ?
            WHERE id = ?
            """,
            ("auto_reviewed", result.get("decision"), json.dumps(result, ensure_ascii=False), now, case_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_case(case_id: int, db_path: Path = DB_PATH) -> dict[str, Any] | None:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        if not row:
            return None
        result_json = row["result_json"]
        return {
            "id": row["id"],
            "folder_path": row["folder_path"],
            "status": row["status"],
            "decision": row["decision"],
            "result": json.loads(result_json) if result_json else None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "manual_reviews": list_reviews(case_id, db_path),
        }
    finally:
        conn.close()


def add_manual_review(
    case_id: int,
    reviewer: str,
    decision: str,
    comment: str,
    db_path: Path = DB_PATH,
) -> None:
    init_db(db_path)
    now = _now()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO manual_reviews (case_id, reviewer, decision, comment, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (case_id, reviewer, decision, comment, now),
        )
        conn.execute(
            """
            UPDATE cases
            SET status = ?, decision = ?, updated_at = ?
            WHERE id = ?
            """,
            ("manual_reviewed", decision, now, case_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_reviews(case_id: int, db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM manual_reviews WHERE case_id = ? ORDER BY id DESC",
            (case_id,),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "case_id": row["case_id"],
                "reviewer": row["reviewer"],
                "decision": row["decision"],
                "comment": row["comment"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]
    finally:
        conn.close()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
