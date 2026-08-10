# Architecture

```text
TikTok Shop API ─┐
TikTok Ads API  ─┼─> Provider adapters ─> FastAPI ─> PostgreSQL
LIVE provider   ─┘          │               │           │
                            │               ├─ WebSocket│
                            │               ├─ Scheduler│
                            │               └─ Alerts   │
                            └───────────────────────────> React Dashboard
```

## Boundary principle

Controllers/UI never know TikTok request signatures or tokens. All external calls live in `backend/app/providers.py`.

- `MockShopProvider`, `MockAdsProvider`, `MockLiveProvider`
- `TikTokShopProvider`, `TikTokAdsProvider`
- `ManualLiveProvider`, `EndpointLiveProvider`

The switch is environment driven: `DATA_PROVIDER=MOCK|TIKTOK` and `LIVE_STATUS_PROVIDER=MOCK|MANUAL|TIKTOK_ENDPOINT`.

## Realtime

The backend writes normalized data to PostgreSQL and emits lightweight WebSocket invalidation events. The browser refetches canonical API state when an event arrives, so reconnects do not lose data.

## Refund snapshots

`refund_snapshots` is append-only by `(session_id, snapshot_type)`. The scheduler creates T+0, T+1H, T+3H, T+6H, T+12H, T+24H, T+48H and FINAL. In TikTok mode, the service first refreshes orders/returns and only then freezes the new snapshot.

## Deployment note

The bundled backend runs as one scheduler process. Keep one backend scheduler instance. If horizontal scaling is needed later, move scheduled jobs into a dedicated worker/queue so multiple app replicas do not poll the same integrations simultaneously.
