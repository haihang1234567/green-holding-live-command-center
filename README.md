# GREEN HOLDING LIVE COMMAND CENTER — Frontend Prototype

Bản giao diện chạy hoàn toàn bằng **MOCK DATA** trong lúc chờ TikTok API.

## Màn hình có sẵn
- `index.html`: Admin Command Center
- `live-session.html`: Live Session Detail
- `team-dashboard.html`: Team User Dashboard

## Chức năng demo tương tác
- Start / Stop LIVE cho 2 kênh
- Add order / +10 orders
- Increase GMV / Ads Spend
- Cancel / Refund mock action
- Dropdown hoàn/hủy T+0, T+1H, T+3H, T+6H, T+12H, T+24H, T+48H, FINAL
- Các KPI hoàn/hủy cập nhật theo snapshot đã chọn
- Bật/tắt so sánh các mốc refund
- Responsive desktop / tablet / mobile

## Chạy trên máy
Không cần npm package nào.

```bash
python3 -m http.server 8080
```

Mở: `http://localhost:8080`

Hoặc mở trực tiếp `index.html` bằng trình duyệt.

## Giai đoạn nối API
Giao diện hiện độc lập với TikTok. Khi có API, thay phần dữ liệu mock trong `app.js` bằng client gọi FastAPI/WebSocket/SSE, không cần thiết kế lại UI.
