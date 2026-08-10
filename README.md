# GREEN HOLDING LIVE COMMAND CENTER v3

Hệ thống giám sát **2 TikTok Shop độc lập**. Dashboard không phát LIVE. TikTok/LIVE Studio bắt đầu phiên ở bên ngoài; server tự phát hiện trạng thái, tự tạo/chốt phiên và ghi nhận dữ liệu theo chu kỳ cố định.

## Luồng production

`Shop 1 API + Shop 2 API -> detect LIVE -> create session -> sync every 180s -> detect OFFLINE -> final sync -> close session -> T+0/T+1H/T+3H/T+6H/T+12H/T+24H/T+48H/FINAL`

- SHOP 1 và SHOP 2 có App Key/Secret/Access Token/Refresh Token/Shop Cipher/Ads Token riêng.
- Không dùng chéo token giữa hai shop.
- Một scheduler duy nhất chạy mỗi `POLLING_INTERVAL_SECONDS=180`; nó vừa kiểm tra trạng thái vừa sync phiên LIVE, tránh race condition.
- API lỗi/UNKNOWN không tự đóng phiên. Chỉ OFFLINE hợp lệ mới chốt phiên.
- Khi OFFLINE, hệ thống final-sync Orders/Returns/Ads/LIVE metrics trước rồi mới tạo T+0.
- Snapshot hoàn/hủy lưu riêng từng mốc, không ghi đè.
- LIVE core response giữ raw JSON trong `live_core_snapshots`, đồng thời map metric phổ biến nếu API được cấp.

## Chạy local

```bash
cp .env.example .env
docker compose up --build -d
```

## Khi TikTok cấp API

```env
DATA_PROVIDER=TIKTOK
LIVE_STATUS_PROVIDER=AUTO
POLLING_INTERVAL_SECONDS=180
SEED_MOCK_DATA=false
```

Điền toàn bộ `SHOP1_*` và `SHOP2_*` trong Render Environment. Map `*_JSON_PATH` theo đúng JSON response thực tế TikTok cấp; không cần sửa lại UI/database.

## Render

React + FastAPI chạy chung service, PostgreSQL riêng. Để polling 3 phút chạy liên tục 24/7, service production phải **không bị sleep**; trước khi dùng API thật hãy chọn Render plan always-on phù hợp.

## Security

Không commit `.env`, access token, refresh token hay app secret. Repo nên chuyển Private trước khi đưa credentials thật vào Render.
