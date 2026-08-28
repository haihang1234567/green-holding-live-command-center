from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.auto_monitor import _ingest_performance_reports
from app.database import Base
from app.live_models import LiveCoreSnapshot
from app.models import Channel, LiveMetricSnapshot, LiveSession, SessionStatus


class LiveHistoryIngestionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        with self.Session() as db:
            db.add(Channel(id=1, name="Shop 1", handle="@greenholding.01"))
            db.commit()

    @staticmethod
    def report(live_id: str, start: datetime, gmv: int, orders: int, *, ended: bool = True):
        return {
            "id": live_id,
            "title": f"LIVE {live_id}",
            "start_time": int(start.timestamp()),
            "end_time": int((start + timedelta(hours=2)).timestamp()) if ended else None,
            "status": "ENDED" if ended else "LIVE",
            "sales_performance": {
                "gmv": {"amount": str(gmv), "currency": "VND"},
                "created_sku_orders": orders,
                "sku_orders": orders,
                "customers": max(1, orders - 1),
            },
        }

    def test_every_live_id_becomes_a_separate_history_row(self):
        start = datetime.now(timezone.utc) - timedelta(days=2)
        rows = [self.report("live-a", start, 1_000_000, 10), self.report("live-b", start + timedelta(hours=3), 2_000_000, 20)]
        with self.Session() as db:
            channel = db.get(Channel, 1)
            first = _ingest_performance_reports(db, channel, rows)
            second = _ingest_performance_reports(db, channel, rows)
            db.commit()
            self.assertEqual(first["sessions_saved"], 2)
            self.assertEqual(second["sessions_saved"], 2)
            sessions = db.scalars(select(LiveSession).order_by(LiveSession.started_at)).all()
            self.assertEqual([x.session_code for x in sessions], ["TTS-1-live-a", "TTS-1-live-b"])
            self.assertTrue(all(x.status == SessionStatus.ENDED.value for x in sessions))
            self.assertEqual(db.scalar(select(func.count(LiveCoreSnapshot.id))), 2)
            self.assertEqual(db.scalar(select(func.count(LiveMetricSnapshot.id))), 2)

    def test_changed_metrics_append_snapshot_without_duplicate_session(self):
        start = datetime.now(timezone.utc) - timedelta(minutes=30)
        first = self.report("live-current", start, 500_000, 5, ended=False)
        changed = self.report("live-current", start, 750_000, 7, ended=False)
        with self.Session() as db:
            channel = db.get(Channel, 1)
            _ingest_performance_reports(db, channel, [first], active_report_id="live-current")
            _ingest_performance_reports(db, channel, [changed], active_report_id="live-current")
            db.commit()
            self.assertEqual(db.scalar(select(func.count(LiveSession.id))), 1)
            self.assertEqual(db.scalar(select(func.count(LiveCoreSnapshot.id))), 2)
            self.assertEqual(db.scalar(select(func.count(LiveMetricSnapshot.id))), 2)
            session = db.scalar(select(LiveSession))
            self.assertEqual(session.status, SessionStatus.LIVE.value)

    def test_newest_active_report_is_the_only_live_session(self):
        now = datetime.now(timezone.utc)
        newer = self.report("newer", now - timedelta(minutes=10), 300_000, 3, ended=False)
        older = self.report("older", now - timedelta(hours=2), 200_000, 2, ended=False)
        with self.Session() as db:
            channel = db.get(Channel, 1)
            # TikTok sorts by GMV, not start time; ingestion must still retain
            # the chronologically newest live_id as the active session.
            _ingest_performance_reports(db, channel, [newer, older], active_report_id="newer")
            db.commit()
            live_rows = db.scalars(select(LiveSession).where(LiveSession.status == SessionStatus.LIVE.value)).all()
            self.assertEqual([x.session_code for x in live_rows], ["TTS-1-newer"])


if __name__ == "__main__":
    unittest.main()
