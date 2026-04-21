"""
SQLite DB — 발송된 판례 영구 저장 및 기간 조회
"""

import sqlite3
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "cases_db.sqlite"

_DDL = """
CREATE TABLE IF NOT EXISTS sent_cases (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    sent_date     TEXT NOT NULL,
    seq           TEXT,
    title         TEXT,
    case_num      TEXT,
    court         TEXT,
    case_type     TEXT,
    decision_date TEXT,
    ai_summary    TEXT,
    statutes      TEXT,
    link          TEXT,
    is_priority   INTEGER DEFAULT 0,
    is_fresh      INTEGER DEFAULT 0
)
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(_DDL)
    conn.commit()
    return conn


def save_cases(cases: list[dict]) -> None:
    """발송된 판례를 DB에 저장"""
    today = datetime.now().strftime("%Y-%m-%d")
    with _connect() as conn:
        for c in cases:
            conn.execute(
                """
                INSERT INTO sent_cases
                    (sent_date, seq, title, case_num, court, case_type,
                     decision_date, ai_summary, statutes, link, is_priority, is_fresh)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    today,
                    c.get("seq", ""),
                    c.get("title", ""),
                    c.get("case_num", ""),
                    c.get("court", ""),
                    c.get("case_type", ""),
                    c.get("date", ""),
                    c.get("summary", ""),
                    c.get("statutes", ""),
                    c.get("link", ""),
                    1 if c.get("priority") else 0,
                    1 if c.get("is_fresh") else 0,
                ),
            )
    logger.info(f"DB 저장 완료: {len(cases)}건 ({today})")


def query_cases(start_date: str, end_date: str) -> list[dict]:
    """기간(YYYY-MM-DD ~ YYYY-MM-DD)으로 발송 판례 조회"""
    with _connect() as conn:
        cur = conn.execute(
            """
            SELECT * FROM sent_cases
            WHERE sent_date >= ? AND sent_date <= ?
            ORDER BY sent_date DESC, is_priority DESC, decision_date DESC
            """,
            (start_date, end_date),
        )
        return [dict(row) for row in cur.fetchall()]
