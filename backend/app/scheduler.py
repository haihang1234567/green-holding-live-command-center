from __future__ import annotations
import asyncio,contextlib
from .auto_monitor import monitor_cycle,refund_cycle
from .config import get_settings
settings=get_settings()
async def _periodic(interval_seconds:int,func):
    while True:
        try:await func()
        except asyncio.CancelledError:raise
        except Exception as exc:print(f"[scheduler] {func.__name__}: {exc}",flush=True)
        await asyncio.sleep(interval_seconds)
def start_background_tasks()->list[asyncio.Task]:
    interval=max(30,int(settings.polling_interval_seconds or 180))
    return [asyncio.create_task(_periodic(interval,monitor_cycle),name="two_shop_live_monitor"),asyncio.create_task(_periodic(180,refund_cycle),name="refund_snapshots")]
async def stop_background_tasks(tasks:list[asyncio.Task])->None:
    for task in tasks:task.cancel()
    for task in tasks:
        with contextlib.suppress(asyncio.CancelledError):await task
