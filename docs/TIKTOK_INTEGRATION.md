# TikTok integration checklist

The application is deliberately tolerant of missing TikTok fields. Unknown/optional metrics remain null and the UI displays **Chưa có dữ liệu**.

## 1. TikTok Shop

Configure this exact Seller authorization redirect URL in Partner Center:

```text
https://green-holding-live-command-center.onrender.com/api/integrations/tiktok/callback
```

The callback exchanges the one-time authorization code on the backend, encrypts
the resulting access/refresh tokens with `SECRET_KEY`, and stores them in
PostgreSQL. Tokens are never rendered in the browser. The current deployment
uses one active shop (`ACTIVE_SHOP_COUNT=1`).

Set `TIKTOK_OAUTH_STATE` to an unpredictable value and include it in the
authorization link. To map automatically, use
`state=<TIKTOK_OAUTH_STATE>:shop1`. With one active shop, the callback maps the
returned shop cipher to Shop 1 automatically.

Fill the backend environment variables:

- `TIKTOK_SHOP_APP_KEY`
- `TIKTOK_SHOP_APP_SECRET`
- `TIKTOK_OAUTH_STATE`

Do not configure `SHOP2_*`. The callback stores the access/refresh token securely;
then open **Kênh TikTok** to verify the Shop Cipher and Shop ID mapping.

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
