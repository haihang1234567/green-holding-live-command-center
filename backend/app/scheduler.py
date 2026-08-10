from __future__ import annotations

import asyncio
import contextlib

from .config import get_settings
from .services import poll_live_statuses, process_due_refund_snapshots, sync_live_sessions

settings = get_settings()


async def _periodic(interval_seconds: int, func):
    while True:
        try:
            await func()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[scheduler] {func.__name__}: {exc}", flush=True)
        await asyncio.sleep(interval_seconds)


def start_background_tasks() -> list[asyncio.Task]:
    return [
        asyncio.create_task(_periodic(max(10, settings.polling_interval_seconds), poll_live_statuses), name="live_status_poll"),
        asyncio.create_task(_periodic(max(15, settings.metric_snapshot_interval_seconds), sync_live_sessions), name="live_metrics_sync"),
        asyncio.create_task(_periodic(180, process_due_refund_snapshots), name="refund_snapshots"),
    ]


async def stop_background_tasks(tasks: list[asyncio.Task]) -> None:
    for task in tasks:
        task.cancel()
    for task in tasks:
        with contextlib.suppress(asyncio.CancelledError):
            await task
