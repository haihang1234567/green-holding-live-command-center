from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from .config import get_settings
from .attribution_models import OrderAttribution
from .live_models import LiveCoreSnapshot
from .models import Alert, AdsSnapshot, AppSetting, Channel, LiveMetricSnapshot, LiveSession, Order, RefundSnapshot, SessionStatus, Team, User, UserRole
from .schedule import DailyTeamAssignment
from .security import hash_password
from .services import add_mock_ads, add_mock_orders, create_metric_snapshot, create_refund_snapshot

settings = get_settings()


def purge_mock_data(db: Session) -> None:
    """Remove demo LIVE data while preserving users, teams and TikTok credentials."""
    mock_session_ids = select(LiveSession.id).where(LiveSession.source == "MOCK")
    mock_channel_ids = select(LiveSession.channel_id).where(LiveSession.source == "MOCK")
    db.execute(delete(OrderAttribution).where(OrderAttribution.session_id.in_(mock_session_ids)))
    db.execute(delete(LiveCoreSnapshot).where(LiveCoreSnapshot.session_id.in_(mock_session_ids)))
    db.execute(delete(Alert).where(Alert.session_id.in_(mock_session_ids)))
    db.execute(delete(RefundSnapshot).where(RefundSnapshot.session_id.in_(mock_session_ids)))
    db.execute(delete(LiveMetricSnapshot).where(LiveMetricSnapshot.session_id.in_(mock_session_ids)))
    db.execute(delete(AdsSnapshot).where(AdsSnapshot.live_session_id.in_(mock_session_ids)))
    db.execute(delete(Order).where(Order.live_session_id.in_(mock_session_ids)))
    db.execute(
        update(Channel)
        .where(Channel.id.in_(mock_channel_ids))
        .values(status=SessionStatus.OFFLINE.value, mock_is_live=False)
    )
    db.execute(delete(LiveSession).where(LiveSession.source == "MOCK"))
    db.commit()


def seed_database(db: Session) -> None:
    db.execute(delete(DailyTeamAssignment))
    db.execute(
        delete(Alert).where(
            Alert.alert_type.in_(
                [
                    "SCHEDULE_MISSING",
                    "AFFILIATE_ATTRIBUTION_WARNING",
                    "LIVE_METRIC_WARNING",
                    "ADS_SYNC_WARNING",
                ]
            )
        )
    )
    db.commit()

    if settings.purge_mock_data:
        purge_mock_data(db)

    if db.scalar(select(Team.id).limit(1)):
        return

    teams = [
        Team(name="Hoàng Ảnh", target_gmv=500_000_000),
        Team(name="Lam Dần", target_gmv=500_000_000),
        Team(name="Hạo Ưng", target_gmv=500_000_000),
        Team(name="Long Tài", target_gmv=500_000_000),
    ]
    db.add_all(teams)
    db.flush()

    channels = [
        Channel(name="Kênh TikTok 01", handle="@greenholding.01", status="OFFLINE", mock_is_live=False),
        Channel(name="Kênh TikTok 02", handle="@greenholding.02", status="OFFLINE", mock_is_live=False),
    ]
    db.add_all(channels)
    db.flush()

    db.add(User(username=settings.admin_username, password_hash=hash_password(settings.admin_password), role=UserRole.ADMIN.value))
    team_usernames = ["hoanganh", "lamdan", "haoung", "longtai"]
    for team, username in zip(teams, team_usernames):
        db.add(User(username=username, password_hash=hash_password("team123"), role=UserRole.TEAM.value, team_id=team.id))

    db.add_all([
        AppSetting(key="refund_warning_percent", value="20"),
        AppSetting(key="ads_gmv_warning_percent", value="8"),
        AppSetting(key="gmv_velocity_drop_percent", value="30"),
        AppSetting(key="channel_1_ca_sang_team_id", value=str(teams[0].id)),
        AppSetting(key="channel_1_ca_toi_team_id", value=str(teams[3].id)),
        AppSetting(key="channel_2_ca_sang_team_id", value=str(teams[2].id)),
        AppSetting(key="channel_2_ca_toi_team_id", value=str(teams[1].id)),
    ])
    db.commit()

    if not settings.seed_mock_data:
        return

    # Provide a convincing initial MOCK dashboard while keeping all data in the real database tables.
    now = datetime.now(timezone.utc)
    session = LiveSession(
        session_code="HA-MOCK-LIVE",
        channel_id=channels[0].id,
        team_id=teams[0].id,
        shift="CA_SANG",
        started_at=now - timedelta(hours=2, minutes=35),
        status=SessionStatus.LIVE.value,
        source="MOCK",
    )
    channels[0].status = "LIVE"
    channels[0].mock_is_live = True
    db.add(session)
    db.flush()
    add_mock_orders(db, session, count=420, gmv_increment=359_081_653)
    db.flush()
    add_mock_ads(db, session, 7_558_000)
    create_metric_snapshot(db, session)

    old_session = LiveSession(
        session_code="HU-MOCK-YESTERDAY",
        channel_id=channels[1].id,
        team_id=teams[2].id,
        shift="CA_TOI",
        started_at=now - timedelta(days=1, hours=4),
        ended_at=now - timedelta(days=1, hours=1),
        status=SessionStatus.ENDED.value,
        source="MOCK",
    )
    db.add(old_session)
    db.flush()
    add_mock_orders(db, old_session, count=90, gmv_increment=58_890_561)
    db.flush()
    add_mock_ads(db, old_session, 4_046_000)
    # Introduce some cancellation/refund history so snapshot UI is populated.
    old_orders = db.scalars(select(Order).where(Order.live_session_id == old_session.id).limit(12)).all()
    for idx, order in enumerate(old_orders):
        if idx < 5:
            order.cancelled_amount = order.payment_amount
            order.order_status = "CANCELLED"
        else:
            order.refund_amount = order.payment_amount
            order.order_status = "REFUNDED"
    db.flush()
    create_refund_snapshot(db, old_session, 0)
    # Add representative frozen snapshots without mutating the previous one.
    totals = {0: 5.0, 1: 8.0, 3: 12.0, 6: 13.5, 12: 14.2, 24: 15.0, 48: 16.0}
    original = 58_890_561.0
    for hours, rate in totals.items():
        stype = "T+0" if hours == 0 else f"T+{hours}H"
        existing = db.scalar(select(RefundSnapshot).where(RefundSnapshot.session_id == old_session.id, RefundSnapshot.snapshot_type == stype))
        if existing:
            existing.refund_cancel_rate = rate
            existing.refund_amount = original * rate / 100
            existing.cancelled_amount = 0
            existing.net_revenue = original * (1 - rate / 100)
            continue
        db.add(RefundSnapshot(
            session_id=old_session.id,
            snapshot_time=old_session.ended_at + timedelta(hours=hours),
            hours_after_live=hours,
            snapshot_type=stype,
            original_gmv=original,
            refund_amount=original * rate / 100,
            cancelled_amount=0,
            refund_cancel_rate=rate,
            net_revenue=original * (1 - rate / 100),
            total_orders=90,
            cancelled_orders=round(90 * rate / 100),
        ))
    db.commit()
