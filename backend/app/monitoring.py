from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from .config import get_settings
from .database import SessionLocal
from .models import Channel, LiveSession, SessionStatus
from .providers import providers
from .realtime import manager
from .services import _choose_team, local_shift, start_session, stop_session, sync_session_external

settings = get_settings()


async def poll_live_statuses_v2() -> None:
    """Poll both shops and turn external state changes into session lifecycle events.

    Rules:
    - Dashboard never starts TikTok LIVE.
    - LIVE detected externally => create DB session immediately, notify UI, then initial sync.
    - OFFLINE detected externally => final Shop/Ads sync first, then close session and freeze T+0.
    - UNKNOWN/error => keep current state; never stop a session because an API response is missing.
    """
    if settings.live_status_provider.upper() == "MANUAL":
        return

    events: list[dict[str, Any]] = []
    started_ids: list[int] = []

    with SessionLocal() as db:
        channels = db.scalars(select(Channel).where(Channel.polling_enabled.is_(True)).order_by(Channel.id)).all()
        for channel in channels:
            try:
                external_status = await providers.live.get_channel_status(channel)
            except Exception as exc:
                from .services import create_alert
                create_alert(
                    db,
                    "LIVE_STATUS_ERROR",
                    "LIVE STATUS ERROR",
                    f"{channel.name}: {exc}",
                    severity="WARNING",
                    channel_id=channel.id,
                )
                db.commit()
                continue

            # Unknown means "no trustworthy signal". Do not change state.
            if external_status is None:
                continue

            active = db.scalar(
                select(LiveSession)
                .options(joinedload(LiveSession.team), joinedload(LiveSession.channel))
                .where(LiveSession.channel_id == channel.id, LiveSession.status == SessionStatus.LIVE.value)
            )

            if external_status == "LIVE" and not active:
                shift = local_shift()
                team = _choose_team(db, channel, shift)
                session = start_session(db, channel, team, shift, "AUTO_API")
                db.commit()  # make session visible to the initial sync transaction
                started_ids.append(session.id)
                events.append({"channel_id": channel.id, "status": "LIVE", "session_id": session.id})

            elif external_status == "OFFLINE" and active:
                session_id = active.id
                # Capture the final 3-minute window before T+0 is frozen.
                if settings.data_provider.upper() == "TIKTOK":
                    try:
                        await sync_session_external(session_id)
                    except Exception as exc:
                        from .services import create_alert
                        create_alert(
                            db,
                            "FINAL_SYNC_WARNING",
                            "FINAL LIVE SYNC WARNING",
                            f"{channel.name}: {exc}",
                            severity="WARNING",
                            session_id=session_id,
                            channel_id=channel.id,
                        )
                stop_session(db, active)
                db.commit()
                events.append({"channel_id": channel.id, "status": "OFFLINE", "session_id": session_id})

    # Start collecting immediately instead of waiting for the next 180-second metric tick.
    if settings.data_provider.upper() == "TIKTOK":
        for session_id in started_ids:
            try:
                await sync_session_external(session_id)
            except Exception:
                # The regular 3-minute scheduler will retry; session remains LIVE.
                pass

    for event in events:
        await manager.broadcast("channel.status", event)
