import sqlite3
import os
import tempfile
import shutil
from storage import EventStore


class TestEventStore:
    def setup_method(self):
        # 使用临时文件数据库，避免 :memory: 连接隔离问题
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.store = EventStore(self.db_path)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_tables_created(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        assert "events" in tables
        assert "daily_stats" in tables
        conn.close()

    def test_record_event(self):
        self.store.record("slouch", "severe", 0.85, '{"angle": 20}')
        events = self.store.get_recent_events(60)
        assert len(events) == 1
        assert events[0]["event_type"] == "slouch"
        assert events[0]["severity"] == "severe"
        assert events[0]["confidence"] == 0.85

    def test_record_sitting_minute(self):
        self.store.record_sitting_minute()
        self.store.record_sitting_minute()
        stats = self.store.get_stats_today()
        assert stats["total_sitting_minutes"] == 2

    def test_get_stats_today_empty(self):
        stats = self.store.get_stats_today()
        assert stats["total_sitting_minutes"] == 0
        assert stats["slouch_count"] == 0

    def test_daily_stats_counts_events(self):
        self.store.record("slouch", "severe", 0.9, "")
        self.store.record("slouch", "severe", 0.8, "")
        self.store.record("head_tilt", "severe", 0.7, "")
        stats = self.store.get_stats_today()
        assert stats["slouch_count"] == 2
        assert stats["head_tilt_count"] == 1
        assert stats["lean_forward_count"] == 0
