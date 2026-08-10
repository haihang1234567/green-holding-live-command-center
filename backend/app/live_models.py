from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LiveCoreSnapshot(Base):
    """Flexible per-3-minute LIVE metrics captured from the approved LIVE API.

    Raw JSON is always retained so new TikTok metrics can be mapped later without
    losing historical responses. Common dashboard fields are normalized too.
    """

    __tablename__ = "live_core_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("live_sessions.id"), index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    gmv: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    orders: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paid_orders: Mapped[int | None] = mapped_column(Integer, nullable=True)
    buyers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_viewers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    peak_viewers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ctr: Mapped[float | None] = mapped_column(Float, nullable=True)
    comments: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shares: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_watch_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_json: Mapped[str] = mapped_column(Text, default="{}")
