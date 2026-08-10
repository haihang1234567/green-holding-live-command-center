from datetime import datetime, timezone
from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


def utcnow():
    return datetime.now(timezone.utc)


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    target_gmv: Mapped[int] = mapped_column(BigInteger, default=500_000_000)
    users = relationship("User", back_populates="team")
    sessions = relationship("LiveSession", back_populates="team")


class Channel(Base):
    __tablename__ = "channels"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    tiktok_shop_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    advertiser_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    external_channel_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="OFFLINE")
    sessions = relationship("LiveSession", back_populates="channel")


class ChannelShiftAssignment(Base):
    __tablename__ = "channel_shift_assignments"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    shift: Mapped[str] = mapped_column(String(20))
    start_hour: Mapped[int] = mapped_column(Integer, default=6)
    end_hour: Mapped[int] = mapped_column(Integer, default=18)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    channel = relationship("Channel")
    team = relationship("Team")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="TEAM")
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    team = relationship("Team", back_populates="users")


class LiveSession(Base):
    __tablename__ = "live_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    shift: Mapped[str] = mapped_column(String(20), default="MORNING")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="LIVE")
    initial_gmv: Mapped[int] = mapped_column(BigInteger, default=0)
    current_gmv: Mapped[int] = mapped_column(BigInteger, default=0)
    current_orders: Mapped[int] = mapped_column(Integer, default=0)
    current_ads_spend: Mapped[int] = mapped_column(BigInteger, default=0)
    attributed_ads_revenue: Mapped[int] = mapped_column(BigInteger, default=0)
    buyers: Mapped[int] = mapped_column(Integer, default=0)
    product_quantity: Mapped[int] = mapped_column(Integer, default=0)
    channel = relationship("Channel", back_populates="sessions")
    team = relationship("Team", back_populates="sessions")
    orders = relationship("Order", back_populates="session", cascade="all, delete-orphan")
    metric_snapshots = relationship("LiveMetricSnapshot", back_populates="session", cascade="all, delete-orphan")
    ads_snapshots = relationship("AdsSnapshot", back_populates="session", cascade="all, delete-orphan")
    refund_snapshots = relationship("RefundSnapshot", back_populates="session", cascade="all, delete-orphan")


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[str] = mapped_column(String(120), index=True)
    sku_id: Mapped[str] = mapped_column(String(120), index=True)
    product_name: Mapped[str] = mapped_column(String(255))
    price: Mapped[int] = mapped_column(BigInteger, default=0)
    __table_args__ = (UniqueConstraint("product_id", "sku_id", name="uq_product_sku"),)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    live_session_id: Mapped[int] = mapped_column(ForeignKey("live_sessions.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    sku_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    product_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    amount: Mapped[int] = mapped_column(BigInteger, default=0)
    payment_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    order_status: Mapped[str] = mapped_column(String(40), default="PAID")
    refund_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    cancelled_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    cancellation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    session = relationship("LiveSession", back_populates="orders")


class AdsSnapshot(Base):
    __tablename__ = "ads_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    live_session_id: Mapped[int] = mapped_column(ForeignKey("live_sessions.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    spend: Mapped[int] = mapped_column(BigInteger, default=0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    orders: Mapped[int] = mapped_column(Integer, default=0)
    gross_revenue: Mapped[int] = mapped_column(BigInteger, default=0)
    roas: Mapped[float] = mapped_column(Float, default=0)
    session = relationship("LiveSession", back_populates="ads_snapshots")


class LiveMetricSnapshot(Base):
    __tablename__ = "live_metric_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("live_sessions.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    gmv: Mapped[int] = mapped_column(BigInteger, default=0)
    orders: Mapped[int] = mapped_column(Integer, default=0)
    ads_spend: Mapped[int] = mapped_column(BigInteger, default=0)
    buyers: Mapped[int] = mapped_column(Integer, default=0)
    product_quantity: Mapped[int] = mapped_column(Integer, default=0)
    session = relationship("LiveSession", back_populates="metric_snapshots")


class RefundSnapshot(Base):
    __tablename__ = "refund_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("live_sessions.id"), index=True)
    snapshot_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    hours_after_live: Mapped[float | None] = mapped_column(Float, nullable=True)
    snapshot_type: Mapped[str] = mapped_column(String(20))
    original_gmv: Mapped[int] = mapped_column(BigInteger, default=0)
    refund_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    cancelled_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    refund_cancel_rate: Mapped[float] = mapped_column(Float, default=0)
    net_revenue: Mapped[int] = mapped_column(BigInteger, default=0)
    total_orders: Mapped[int] = mapped_column(Integer, default=0)
    cancelled_orders: Mapped[int] = mapped_column(Integer, default=0)
    session = relationship("LiveSession", back_populates="refund_snapshots")
    __table_args__ = (UniqueConstraint("session_id", "snapshot_type", name="uq_session_snapshot_type"),)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    live_session_id: Mapped[int | None] = mapped_column(ForeignKey("live_sessions.id"), nullable=True)
    alert_type: Mapped[str] = mapped_column(String(50))
    severity: Mapped[str] = mapped_column(String(20), default="WARNING")
    title: Mapped[str] = mapped_column(String(180))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)


class AppSetting(Base):
    __tablename__ = "app_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True)
    value: Mapped[str] = mapped_column(String(255))
