# GREEN HOLDING LIVE COMMAND CENTER v3

Hệ thống hiện giám sát **1 TikTok Shop**. Dashboard không phát LIVE. TikTok/LIVE Studio bắt đầu phiên ở bên ngoài; server tự phát hiện trạng thái, tự tạo/chốt phiên và ghi nhận dữ liệu theo chu kỳ cố định. Kiến trúc vẫn sẵn sàng mở Shop 2 sau này bằng cấu hình.

## Luồng production

`Shop 1 API -> fetch every 180s -> upsert every TikTok live_id -> save metrics -> close ended sessions -> T+0/T+1H/T+3H/T+6H/T+12H/T+24H/T+48H/FINAL`

- `ACTIVE_SHOP_COUNT=1` bảo đảm dashboard, báo cáo, lịch sử và polling chỉ dùng Shop 1.
- Một scheduler duy nhất chạy mỗi `POLLING_INTERVAL_SECONDS=180`; nó vừa kiểm tra trạng thái vừa sync phiên LIVE, tránh race condition.
- API lỗi/UNKNOWN không tự đóng phiên. Chỉ OFFLINE hợp lệ mới chốt phiên.
- Khi OFFLINE, hệ thống final-sync Orders/Returns/Ads/LIVE metrics trước rồi mới tạo T+0.
- Snapshot hoàn/hủy lưu riêng từng mốc, không ghi đè.
- LIVE core response giữ raw JSON trong `live_core_snapshots`, đồng thời map metric phổ biến nếu API được cấp.
- `live_sessions` là lịch sử lâu dài: một `live_id` TikTok tương ứng một phiên, cập nhật không tạo trùng.
- Mỗi chu kỳ lưu mọi báo cáo phiên TikTok trả về, không chỉ phiên có GMV cao nhất hoặc phiên mới nhất.
- Mỗi 24 giờ hệ thống tự đồng bộ bù 30 ngày gần nhất để khôi phục những phiên bị lỡ khi Render restart/sleep.

## Chạy local

```bash
cp .env.example .env
docker compose up --build -d
```

## Khi TikTok cấp API

```env
DATA_PROVIDER=TIKTOK
LIVE_STATUS_PROVIDER=AUTO
ACTIVE_SHOP_COUNT=1
POLLING_INTERVAL_SECONDS=180
SEED_MOCK_DATA=false
```

Chỉ điền `TIKTOK_SHOP_APP_KEY`, `TIKTOK_SHOP_APP_SECRET`, `TIKTOK_OAUTH_STATE` và các biến `SHOP1_*` cần thiết trong Render Environment. Không cần cấu hình `SHOP2_*`. Map `*_JSON_PATH` theo đúng JSON response thực tế TikTok cấp; không cần sửa lại UI/database.

## Render

React + FastAPI chạy chung service, PostgreSQL riêng. Để polling 3 phút chạy liên tục 24/7, service production phải **không bị sleep**; trước khi dùng API thật hãy chọn Render plan always-on phù hợp.

## Security

Không commit `.env`, access token, refresh token hay app secret. Repo nên chuyển Private trước khi đưa credentials thật vào Render.
