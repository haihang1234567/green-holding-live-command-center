from sqlalchemy.orm import Session
from app.models import Alert, LiveSession, RefundSnapshot


def create_alert(db: Session, alert_type: str, title: str, message: str, session_id: int | None = None, severity: str = "WARNING"):
    alert = Alert(live_session_id=session_id, alert_type=alert_type, severity=severity, title=title, message=message)
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def evaluate_session_alerts(db: Session, session: LiveSession):
    gmv = session.current_gmv or 0
    ads = session.current_ads_spend or 0
    ads_pct = ads / gmv * 100 if gmv else 0
    if gmv and ads_pct > 8:
        recent = db.query(Alert).filter(Alert.live_session_id == session.id, Alert.alert_type == "ADS_WARNING").order_by(Alert.id.desc()).first()
        if not recent:
            create_alert(db, "ADS_WARNING", "Ads/GMV vượt ngưỡng", f"Ads/GMV hiện tại {ads_pct:.2f}% > 8%", session.id)


def evaluate_refund_alert(db: Session, snapshot: RefundSnapshot):
    if snapshot.refund_cancel_rate > 20:
        existing = db.query(Alert).filter(Alert.live_session_id == snapshot.session_id, Alert.alert_type == "REFUND_WARNING", Alert.message.contains(snapshot.snapshot_type)).first()
        if not existing:
            create_alert(db, "REFUND_WARNING", "Tỷ lệ hoàn/hủy cao", f"{snapshot.snapshot_type}: {snapshot.refund_cancel_rate:.2f}% > 20%", snapshot.session_id, "CRITICAL")
