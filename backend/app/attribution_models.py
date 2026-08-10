from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OrderAttribution(Base):
    """TikTok-provided content attribution for an order/SKU.

    This table is intentionally separate from `orders`: existing databases can be
    upgraded with Base.metadata.create_all() without destructive ALTER TABLE work.
    Only EXACT_LIVE_CURRENT rows are allowed to attach an Order to a LiveSession.
    """

    __tablename__ = "order_attributions"

    id: Mapped[int] = mapped_column(primary_key=True)
    attribution_key: Mapped[str] = mapped_column(String(700), unique=True, index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("live_sessions.id"), nullable=True, index=True)
    order_id: Mapped[str] = mapped_column(String(255), index=True)
    sku_id: Mapped[str] = mapped_column(String(255), default="", index=True)
    product_id: Mapped[str] = mapped_column(String(255), default="")
    creator_username: Mapped[str] = mapped_column(String(255), default="")
    content_type: Mapped[str] = mapped_column(String(40), default="UNKNOWN", index=True)
    content_id: Mapped[str] = mapped_column(String(255), default="", index=True)
    source_bucket: Mapped[str] = mapped_column(String(60), default="UNKNOWN", index=True)
    confidence: Mapped[str] = mapped_column(String(30), default="UNRESOLVED")
    is_affiliate: Mapped[bool] = mapped_column(Boolean, default=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    attributed_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    currency: Mapped[str] = mapped_column(String(12), default="VND")
    raw_json: Mapped[str] = mapped_column(Text, default="{}")
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint("channel_id", "order_id", "sku_id", "content_type", "content_id", name="uq_order_content_attribution"),
        Index("ix_attr_session_source", "session_id", "source_bucket"),
    )
