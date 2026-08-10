# TikTok integration checklist

The application is deliberately tolerant of missing TikTok fields. Unknown/optional metrics remain null and the UI displays **Chưa có dữ liệu**.

## 1. TikTok Shop

Fill the backend environment variables:

- `TIKTOK_SHOP_APP_KEY`
- `TIKTOK_SHOP_APP_SECRET`
- access/refresh token(s)

For two shops, use the JSON token maps keyed by `shop_cipher`. Then open **Kênh TikTok** in the admin UI and map each company channel to its `shop_cipher` and Shop ID.

Implemented adapter responsibilities:

- HMAC-SHA256 request signing
- authorized shops test
- order polling / normalization
- return/refund polling / normalization
- refresh-token retry on authentication failure
- raw payload retention for later remapping
- webhook endpoint `/api/webhooks/tiktok-shop`

## 2. TikTok Ads / Marketing API

Fill:

- `TIKTOK_ADS_APP_ID`
- `TIKTOK_ADS_SECRET`
- `TIKTOK_ADS_ACCESS_TOKEN`

Map each channel to its `advertiser_id`. The report adapter queries hourly advertiser-level metrics and aggregates only rows inside the session window. Revenue/ROAS metric names are configurable because availability can differ by account/product/API permission.

## 3. LIVE start detection

Do **not** assume a general LIVE status endpoint exists for your account.

- If an approved endpoint/webhook is provided, configure `TIKTOK_ENDPOINT` and its JSON mapping.
- Otherwise set `LIVE_STATUS_PROVIDER=MANUAL` and start/stop sessions from **LIVE hiện tại**. Shop/Ads data can still run in real mode.

## 4. Switch from demo to real data

1. Stop the stack.
2. Set `DATA_PROVIDER=TIKTOK`.
3. Set `LIVE_STATUS_PROVIDER=MANUAL` initially unless an actual LIVE status source has been approved.
4. Fill credentials in `.env`.
5. Restart: `docker compose up -d --build`.
6. Admin → **Kênh TikTok**: map Shop Cipher / Shop ID / Advertiser ID.
7. Admin → **Cấu hình API**: test Shop and Ads.
8. Keep webhook/public HTTPS routing configured if using TikTok webhook delivery.

No frontend rewrite is required for this switch.
