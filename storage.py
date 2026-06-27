import sqlite3
import os
from datetime import datetime, date


CREATE_EVENTS = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    confidence REAL DEFAULT 0.0,
    details TEXT DEFAULT ''
)
"""

CREATE_DAILY_STATS = """
CREATE TABLE IF NOT EXISTS daily_stats (
    date TEXT PRIMARY KEY,
    total_sitting_minutes INTEGER DEFAULT 0,
    slouch_count INTEGER DEFAULT 0,
    lean_forward_count INTEGER DEFAULT 0,
    head_tilt_count INTEGER DEFAULT 0,
    sedentary_alerts INTEGER DEFAULT 0,
    severe_alerts INTEGER DEFAULT 0
)
"""

UPSERT_STATS = """
INSERT INTO daily_stats (date, total_sitting_minutes, slouch_count,
    lean_forward_count, head_tilt_count, sedentary_alerts, severe_alerts)
VALUES (?, 1, ?, ?, ?, ?, ?)
ON CONFLICT(date) DO UPDATE SET
    total_sitting_minutes = total_sitting_minutes + 1,
    slouch_count = slouch_count + excluded.slouch_count,
    lean_forward_count = lean_forward_count + excluded.lean_forward_count,
    head_tilt_count = head_tilt_count + excluded.head_tilt_count,
    sedentary_alerts = sedentary_alerts + excluded.sedentary_alerts,
    severe_alerts = severe_alerts + excluded.severe_alerts
"""


class EventStore:
    def __init__(self, db_path: str = "data/posture.db"):
        self.db_path = db_path
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(CREATE_EVENTS)
            conn.execute(CREATE_DAILY_STATS)

    def record(self, event_type: str, severity: str,
               confidence: float = 0.0, details: str = ""):
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO events (timestamp, event_type, severity, confidence, details) "
                "VALUES (?, ?, ?, ?, ?)",
                (now, event_type, severity, confidence, details)
            )
            # 同时更新 daily_stats
            slouch = 1 if event_type == "slouch" else 0
            lean = 1 if event_type == "lean_forward" else 0
            tilt = 1 if event_type == "head_tilt" else 0
            sedentary = 1 if event_type == "sedentary" else 0
            severe = 1 if severity == "severe" else 0
            today = date.today().isoformat()
            conn.execute(UPSERT_STATS, (today, slouch, lean, tilt, sedentary, severe))

    def record_sitting_minute(self):
        today = date.today().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO daily_stats (date, total_sitting_minutes) VALUES (?, 1) "
                "ON CONFLICT(date) DO UPDATE SET "
                "total_sitting_minutes = total_sitting_minutes + 1",
                (today,)
            )

    def get_stats_today(self) -> dict:
        today = date.today().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM daily_stats WHERE date = ?", (today,)
            ).fetchone()
        if row is None:
            return {
                "total_sitting_minutes": 0, "slouch_count": 0,
                "lean_forward_count": 0, "head_tilt_count": 0,
                "sedentary_alerts": 0, "severe_alerts": 0
            }
        return {
            "total_sitting_minutes": row[1], "slouch_count": row[2],
            "lean_forward_count": row[3], "head_tilt_count": row[4],
            "sedentary_alerts": row[5], "severe_alerts": row[6]
        }

    def get_recent_events(self, minutes: int = 60) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM events ORDER BY timestamp DESC LIMIT 100"
            ).fetchall()
        return [dict(row) for row in rows]
