from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from .database import Base
from .models import Channel, Team, utcnow

VN_TZ = timezone(timedelta(hours=7))


class DailyTeamAssignment(Base):
    """Team assignment for one Vietnam business date, channel and shift."""

    __tablename__ = "daily_team_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    work_date: Mapped[date] = mapped_column(Date, index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), index=True)
    shift: Mapped[str] = mapped_column(String(20), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    channel: Mapped[Channel] = relationship()
    team: Mapped[Team] = relationship()

    __table_args__ = (
        UniqueConstraint("work_date", "channel_id", "shift", name="uq_daily_team_date_channel_shift"),
    )


def vietnam_date(now: datetime | None = None) -> date:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(VN_TZ).date()


def scheduled_team(db: Session, channel: Channel, shift: str, *, work_date: date | None = None) -> Team:
    target_date = work_date or vietnam_date()
    assignment = db.scalar(
        select(DailyTeamAssignment).where(
            DailyTeamAssignment.work_date == target_date,
            DailyTeamAssignment.channel_id == channel.id,
            DailyTeamAssignment.shift == shift,
        )
    )
    if not assignment:
        shift_label = "Ca sáng" if shift == "CA_SANG" else "Ca tối"
        raise RuntimeError(
            f"Chưa phân ca ngày {target_date.strftime('%d/%m/%Y')} • {channel.name} • {shift_label}"
        )
    team = db.get(Team, assignment.team_id)
    if not team:
        raise RuntimeError(f"Lịch ngày {target_date.isoformat()} đang trỏ tới team không tồn tại")
    return team


def day_schedule(db: Session, work_date: date) -> dict[str, int | None]:
    result: dict[str, int | None] = {
        "channel_1_ca_sang_team_id": None,
        "channel_1_ca_toi_team_id": None,
        "channel_2_ca_sang_team_id": None,
        "channel_2_ca_toi_team_id": None,
    }
    rows = db.scalars(
        select(DailyTeamAssignment).where(DailyTeamAssignment.work_date == work_date)
    ).all()
    for row in rows:
        key = f"channel_{row.channel_id}_{row.shift.lower()}_team_id"
        if key in result:
            result[key] = row.team_id
    return result
