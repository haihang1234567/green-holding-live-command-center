from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.security import hash_password
from app.models import Team, Channel, ChannelShiftAssignment, User, LiveSession, Order, LiveMetricSnapshot, RefundSnapshot, Alert


def seed_database(db: Session):
    settings = get_settings()
    if db.query(Team).count() == 0:
        for name in ["Hoàng Ảnh", "Lam Dần", "Hạo Ưng", "Long Tài"]:
            db.add(Team(name=name, target_gmv=500_000_000))
        db.commit()

    if db.query(Channel).count() == 0:
        db.add_all([
            Channel(name="Kênh TikTok 01", status="OFFLINE", external_channel_id="channel-01"),
            Channel(name="Kênh TikTok 02", status="OFFLINE", external_channel_id="channel-02"),
        ])
        db.commit()

    if db.query(ChannelShiftAssignment).count() == 0:
        teams = db.query(Team).order_by(Team.id).all()
        channels = db.query(Channel).order_by(Channel.id).all()
        if len(teams) >= 4 and len(channels) >= 2:
            db.add_all([
                ChannelShiftAssignment(channel_id=channels[0].id, team_id=teams[0].id, shift="MORNING", start_hour=5, end_hour=17),
                ChannelShiftAssignment(channel_id=channels[0].id, team_id=teams[2].id, shift="EVENING", start_hour=17, end_hour=5),
                ChannelShiftAssignment(channel_id=channels[1].id, team_id=teams[1].id, shift="MORNING", start_hour=5, end_hour=17),
                ChannelShiftAssignment(channel_id=channels[1].id, team_id=teams[3].id, shift="EVENING", start_hour=17, end_hour=5),
            ])
            db.commit()

    if not db.query(User).filter_by(username=settings.admin_username).first():
        db.add(User(username=settings.admin_username, password_hash=hash_password(settings.admin_password), role="ADMIN"))
    for team in db.query(Team).all():
        uname = "team" + str(team.id)
        if not db.query(User).filter_by(username=uname).first():
            db.add(User(username=uname, password_hash=hash_password(settings.team_default_password), role="TEAM", team_id=team.id))
    db.commit()

    if db.query(LiveSession).count() == 0:
        now = datetime.now(timezone.utc)
        teams = db.query(Team).order_by(Team.id).all()
        channels = db.query(Channel).order_by(Channel.id).all()
        sample = [
            (teams[0], channels[0], "MORNING", 359_081_653, 4571, 7_558_000, 6, 0),
            (teams[1], channels[1], "MORNING", 281_450_000, 3650, 6_120_000, 28, 1),
            (teams[2], channels[0], "EVENING", 198_600_000, 2530, 4_810_000, 52, 2),
            (teams[3], channels[1], "EVENING", 243_900_000, 3022, 5_240_000, 76, 3),
        ]
        for idx, (team, channel, shift, gmv, orders, ads, hours_ago, day_offset) in enumerate(sample):
            started = now - timedelta(days=day_offset, hours=hours_ago + 3)
            ended = now - timedelta(days=day_offset, hours=hours_ago)
            session = LiveSession(session_code=f"DEMO-{idx+1:03d}", channel_id=channel.id, team_id=team.id, shift=shift, started_at=started, ended_at=ended, status="ENDED", initial_gmv=gmv, current_gmv=gmv, current_orders=orders, current_ads_spend=ads, attributed_ads_revenue=int(gmv*0.65), buyers=int(orders*0.82), product_quantity=int(orders*1.3))
            db.add(session)
            db.flush()
            for j, amount in enumerate([int(gmv*.30), int(gmv*.24), int(gmv*.18), int(gmv*.12)]):
                db.add(Order(order_id=f"SEED-{session.id}-{j}", live_session_id=session.id, sku_id=f"SKU00{j+1}", product_id=f"P00{j+1}", product_name=f"Sản phẩm {chr(65+j)}", quantity=max(1, orders//(j+3)), amount=amount, payment_amount=amount, order_status="PAID"))
            for p in range(8):
                db.add(LiveMetricSnapshot(session_id=session.id, timestamp=started + timedelta(minutes=20*p), gmv=int(gmv*(p+1)/8), orders=int(orders*(p+1)/8), ads_spend=int(ads*(p+1)/8), buyers=int(orders*.82*(p+1)/8), product_quantity=int(orders*1.3*(p+1)/8)))
            rates = {"T0": 5.0, "T1H": 7.5, "T3H": 12.0, "T6H": 13.2, "T12H": 14.1, "T24H": 15.0, "T48H": 16.3, "FINAL": 18.0}
            for stype, rate in rates.items():
                loss = int(gmv * rate / 100)
                db.add(RefundSnapshot(session_id=session.id, snapshot_time=ended, hours_after_live=None, snapshot_type=stype, original_gmv=gmv, refund_amount=int(loss*.55), cancelled_amount=int(loss*.45), refund_cancel_rate=rate, net_revenue=gmv-loss, total_orders=orders, cancelled_orders=int(orders*rate/100)))
        db.add(Alert(alert_type="INFO", severity="INFO", title="Mock mode sẵn sàng", message="Hệ thống đang chạy bằng dữ liệu mô phỏng."))
        db.commit()
