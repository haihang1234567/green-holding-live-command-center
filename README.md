# Live Command Center

Full-stack web app quản lý và theo dõi livestream TikTok theo kiến trúc **API-ready**. Hiện chạy hoàn toàn bằng `MOCK`, sau khi TikTok cấp quyền chuyển provider sang `TIKTOK` mà không phải viết lại UI, database, snapshot logic hay cảnh báo.

## Giao diện

- **Admin:** desktop only, tối ưu màn hình máy tính / TV điều hành.
- **Team/User Desktop:** dashboard riêng của team.
- **Team/User Mobile:** layout riêng cho điện thoại, không phải chỉ co nhỏ bản desktop.
- Chủ đạo **màu trắng**, khung mảnh, chữ tối, KPI lớn, ít chi tiết thừa.

## Stack

- Backend: FastAPI + SQLAlchemy + JWT auth
- Database: PostgreSQL production, SQLite fallback khi chạy local
- Frontend: React + Vite + Recharts
- Realtime: WebSocket
- Scheduler: background loop polling / snapshot
- Deploy: Docker Compose

## Chạy ngay bằng MOCK DATA

```bash
cp .env.example .env
docker compose up --build
```

Mở `http://localhost:3000`.

Tài khoản demo mặc định:

- Admin: `admin / admin123`
- Hoàng Ảnh: `team1 / team123`
- Lam Dần: `team2 / team123`
- Hạo Ưng: `team3 / team123`
- Long Tài: `team4 / team123`

> Hãy đổi mật khẩu và `SECRET_KEY` trước khi dùng production.

## Các chức năng đã triển khai

### Admin desktop

- Trạng thái 2 kênh LIVE/OFFLINE
- KPI: GMV, Orders, Ads, AOV, Ads/GMV, ROAS, Net Revenue, Refund Rate
- Ranking 4 team
- Lịch sử phiên LIVE
- Session Detail với GMV timeline và Top SKU
- Refund snapshot dropdown: T+0, T+1H, T+3H, T+6H, T+12H, T+24H, T+48H, FINAL
- Refund Rate Timeline
- Alerts
- Developer / Mock Control
- API / System status

### Team/User

- Chỉ nhìn dữ liệu team của tài khoản
- Desktop layout riêng
- Mobile layout riêng
- LIVE status, GMV, đơn, Ads, AOV, ROAS, target progress, Top SKU, hoàn/hủy

### Mock simulator

- START / STOP LIVE trên 2 kênh
- Add 1 / 10 orders
- Increase GMV
- Add Ads Spend
- Cancel order
- Refund order
- Auto tick để số liệu tiếp tục chạy khi đang LIVE

### Backend / data

Có model riêng cho:

- Team
- Channel
- ChannelShiftAssignment
- User
- LiveSession
- Order
- Product
- AdsSnapshot
- LiveMetricSnapshot
- RefundSnapshot
- Alert
- AppSetting

Refund snapshots **không ghi đè** nhau.

## Khi TikTok cấp API

1. Điền credentials vào `.env`.
2. Điền endpoint thực tế mà API package được duyệt cung cấp.
3. Nếu response field khác chuẩn, thay `MAP_*` trong `.env` hoặc mapping trong `backend/app/providers/tiktok.py`.
4. Đổi:

```env
DATA_PROVIDER=TIKTOK
```

5. Restart:

```bash
docker compose up -d --build
```

`sync_engine.py` sẽ:

- Poll LIVE status nếu endpoint tồn tại.
- OFFLINE -> LIVE: tự tạo session theo ChannelShiftAssignment.
- LIVE -> OFFLINE: đóng session và tạo T+0.
- Đồng bộ orders / Ads.
- Lưu metric snapshots.
- Tạo refund snapshots theo thời gian.

Nếu TikTok không cấp LIVE status API, adapter trả `UNKNOWN`; hệ thống không crash và UI hiển thị trạng thái thiếu dữ liệu thay vì tự đoán.

## Quan trọng về TikTok API

Repo không giả định TikTok cấp mọi metric. `RealTikTok*Provider` là lớp cách ly API. Khi có bộ quyền/API cụ thể, phần cần xác nhận cuối cùng chỉ là **endpoint, request signing và field mapping theo đúng tài liệu của gói API được cấp**. Toàn bộ dashboard và business logic phía sau đã tách khỏi lớp này.

## Cấu trúc

```text
backend/
  app/
    core/          # config, security
    providers/     # Mock / Real TikTok adapters
    routers/       # REST + WebSocket API
    services/      # KPI, sync, snapshot, alerts, mock engine
    models.py
    db.py
    main.py
frontend/
  src/
    components/
    pages/
  Dockerfile
  nginx.conf
docker-compose.yml
.env.example
```
