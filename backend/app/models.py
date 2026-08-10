from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SessionStatus(str, Enum):
    OFFLINE = "OFFLINE"
    LIVE = "LIVE"
    ENDED = "ENDED"


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    TEAM = "TEAM"


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    target_gmv: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Channel(Base):
    __tablename__ = "channels"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    handle: Mapped[str] = mapped_column(String(120), default="")
    tiktok_shop_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shop_cipher: Mapped[str | None] = mapped_column(String(512), nullable=True)
    advertiser_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    live_source_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=SessionStatus.OFFLINE.value)
    mock_is_live: Mapped[bool] = mapped_column(Boolean, default=False)
    polling_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default=UserRole.TEAM.value)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    team: Mapped[Team | None] = relationship()


class LiveSession(Base):
    __tablename__ = "live_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    shift: Mapped[str] = mapped_column(String(20), default="CA_SANG")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default=SessionStatus.LIVE.value, index=True)
    source: Mapped[str] = mapped_column(String(30), default="MOCK")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    channel: Mapped[Channel] = relationship()
    team: Mapped[Team] = relationship()


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[str] = mapped_column(String(255), index=True)
    sku_id: Mapped[str] = mapped_column(String(255), index=True)
    product_name: Mapped[str] = mapped_column(String(500), default="")
    price: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    currency: Mapped[str] = mapped_column(String(12), default="VND")
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (UniqueConstraint("sku_id", "channel_id", name="uq_product_sku_channel"),)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    parent_order_id: Mapped[str] = mapped_column(String(255), index=True, default="")
    live_session_id: Mapped[int | None] = mapped_column(ForeignKey("live_sessions.id"), nullable=True, index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    sku_id: Mapped[str] = mapped_column(String(255), default="")
    product_id: Mapped[str] = mapped_column(String(255), default="")
    product_name: Mapped[str] = mapped_column(String(500), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    payment_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    currency: Mapped[str] = mapped_column(String(12), default="VND")
    order_status: Mapped[str] = mapped_column(String(80), default="UNKNOWN", index=True)
    refund_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    cancelled_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    session: Mapped[LiveSession | None] = relationship()


class AdsSnapshot(Base):
    __tablename__ = "ads_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    live_session_id: Mapped[int] = mapped_column(ForeignKey("live_sessions.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    spend: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    orders: Mapped[int] = mapped_column(Integer, default=0)
    gross_revenue: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    roas: Mapped[float] = mapped_column(Float, default=0)


class LiveMetricSnapshot(Base):
    __tablename__ = "live_metric_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("live_sessions.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    gmv: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    orders: Mapped[int] = mapped_column(Integer, default=0)
    ads_spend: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    buyers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_quantity: Mapped[int] = mapped_column(Integer, default=0)
    current_viewers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    peak_viewers: Mapped[int | None] = mapped_column(Integer, nullable=True)


class RefundSnapshot(Base):
    __tablename__ = "refund_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("live_sessions.id"), index=True)
    snapshot_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    hours_after_live: Mapped[int] = mapped_column(Integer, index=True)
    snapshot_type: Mapped[str] = mapped_column(String(20), index=True)
    original_gmv: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    refund_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    cancelled_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    refund_cancel_rate: Mapped[float] = mapped_column(Float, default=0)
    net_revenue: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    total_orders: Mapped[int] = mapped_column(Integer, default=0)
    cancelled_orders: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint("session_id", "snapshot_type", name="uq_refund_session_type"),)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("live_sessions.id"), nullable=True, index=True)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id"), nullable=True, index=True)
    alert_type: Mapped[str] = mapped_column(String(80), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="INFO")
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


Index("ix_orders_session_created", Order.live_session_id, Order.created_at)
Index("ix_metric_session_time", LiveMetricSnapshot.session_id, LiveMetricSnapshot.timestamp)

class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(80), default="TIKTOK")
    event_type: Mapped[str] = mapped_column(String(120), default="UNKNOWN", index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
