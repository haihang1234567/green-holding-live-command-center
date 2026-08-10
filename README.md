# GREEN HOLDING LIVE COMMAND CENTER

Full-stack web app for managing and monitoring company TikTok livestream operations in real-time / near-real-time. It is usable today in **MOCK MODE** and is structured so TikTok credentials can be plugged in later without rewriting the dashboard or database.

## Included

- FastAPI backend + JWT authentication
- PostgreSQL database
- React/Vite responsive Command Center
- WebSocket dashboard refresh
- 2 TikTok channels + 4 seeded teams: Hoàng Ảnh, Lam Dần, Hạo Ưng, Long Tài
- Admin vs Team access control
- LIVE session lifecycle and manual fallback
- GMV / Orders / AOV / Ads / Ads% / ROAS / GMV-hour KPIs
- Top SKU and team ranking
- Refund/cancel snapshots: T+0, 1H, 3H, 6H, 12H, 24H, 48H, FINAL
- Threshold alerts: LIVE start/end, GMV velocity, Ads/GMV, Refund, integration errors
- Mock simulator: start/stop, orders, GMV, ads, cancel/refund
- TikTok Shop adapter + signing + token refresh + orders/returns + webhook receiver
- TikTok Marketing API report adapter
- Optional generic LIVE status endpoint adapter
- Channel/Shop/Advertiser mapping UI
- User management UI
- Auto team mapping per channel / shift
- Filterable reports + Excel/PDF export
- Docker Compose deployment

## Start immediately

```bash
cp .env.example .env
docker compose up --build -d
```

Open `http://localhost:8080`.

Default demo login (change before production):

- Admin: `admin` / `admin123`
- Team demo: `hoanganh`, `lamdan`, `haoung`, `longtai` / `team123`

## When TikTok approves the APIs

Edit `.env`:

```env
DATA_PROVIDER=TIKTOK
LIVE_STATUS_PROVIDER=MANUAL
TIKTOK_SHOP_APP_KEY=...
TIKTOK_SHOP_APP_SECRET=...
TIKTOK_SHOP_ACCESS_TOKEN=...
TIKTOK_SHOP_REFRESH_TOKEN=...
TIKTOK_ADS_APP_ID=...
TIKTOK_ADS_SECRET=...
TIKTOK_ADS_ACCESS_TOKEN=...
```

Then restart:

```bash
docker compose up -d --build
```

In the admin UI:

1. **Kênh TikTok** → enter `shop_cipher`, Shop ID and `advertiser_id` for each of the two channels.
2. **Cấu hình API** → test Shop / Ads and configure channel+shift → team mapping.
3. If there is no approved LIVE status source, keep `LIVE_STATUS_PROVIDER=MANUAL` and use **LIVE hiện tại** to start/stop sessions. Real Shop/Ads data still syncs into those sessions.

See `docs/TIKTOK_INTEGRATION.md` for the full checklist.

## API health

- UI: `http://localhost:8080`
- Backend health through proxy: `http://localhost:8080/health`
- FastAPI docs when accessing backend directly: `/docs`

## Security

- Never commit `.env`.
- App secrets/tokens are backend-only.
- Change admin password, PostgreSQL password and `SECRET_KEY` before production.
- The current GitHub repository should be private before real credentials or company-sensitive implementation details are added.
