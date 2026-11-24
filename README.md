# Hemnet Watch

A self-hosted, multi-user website that archives [hemnet.se](https://www.hemnet.se) listings and alerts
users about new listings, price drops and final sale prices via **Telegram** or **email**.

(Formerly *hemnet_parser_bot*, a single-chat Telegram bot. All logic now lives in the web app; Telegram is
used only for login and notifications.)

## Features

- **Admin** chooses which Hemnet locations (municipalities, districts, …) and property types are scraped.
- **Archive**: every listing's data, price history, final sale price and the full image gallery
  (resized to WebP) are kept after Hemnet removes the ad.
- **Users** sign in with Telegram, save any number of searches (regions, districts, property type, price,
  rooms, living area, fee, price/m², year built, balcony/elevator, keywords, distance from a point on a
  map) and get notified:
  - 🏠 when a new listing matches,
  - 📉 when a listing they were notified about (or saved) drops in price,
  - 🔨 when it sells, with the final price, as a reply to the original Telegram message.
- Browse/filter the archive as a grid or a map, save/hide listings, keep private notes.

## How it works

```
hemnet.se ──(curl_cffi, Chrome TLS fingerprint)──► scanner ─► SQLite ─► matching ─► notification queue ─► Telegram / SMTP
                                                    │                                     ▲
                                                    └─► detail pages ─► image archive     └── React UI / REST API
```

Hemnet is a Next.js app behind Cloudflare. Plain HTTP clients get a 403, but impersonating Chrome's TLS
fingerprint (`curl_cffi`) is enough, so no headless browser is needed. Pages embed their data as React
Server Component payloads containing GraphQL-shaped JSON (`ListingCard`, `ActivePropertyListing`,
`SaleCard`, …), which `backend/app/hemnet/parse.py` extracts.

| Job | Default interval | What it does |
| --- | --- | --- |
| Seed scan | when a region is added | Archives every current listing **without notifying** anyone |
| Incremental scan | 15 min | `published_since=1d` search, finds new listings |
| Full scan | 24 h | Walks all result pages: price changes, listings that disappeared |
| Sold scan | 6 h | `/salda/bostader` for the region: final prices |
| Detail fetch | 30 s | Listing page: year built, districts, elevator, full gallery, description. New listings are matched against saved searches after this step |
| Removal check | 10 min | Disappeared listings: a `/bostad/` URL that redirects to `/salda/` means sold |
| Image archive | 30 s | Downloads originals, resizes to `IMAGE_MAX_SIZE` WebP (~1.2 MB per listing at defaults) |
| Notifications | 15 s | Sends the queue, retries failures, detects users who blocked the bot |

All of this runs inside one container (single uvicorn worker); data lives in `/data` (`hemnet.db` + `images/`).

## Running

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy its token.
2. `cp .env.example .env` and fill in at least `TELEGRAM_BOT_TOKEN`, `SECRET_KEY`, `PUBLIC_URL` and
   `ADMIN_TELEGRAM_IDS` (if empty, the first user to sign in becomes admin).
3. `docker compose up -d` and open `PUBLIC_URL`.
4. Sign in with Telegram, then go to **Admin → Regions** and add a location.

Login uses a bot deep link (`t.me/<bot>?start=login_<token>`) with an in-chat confirmation button, so it works
on a LAN address without registering a domain with BotFather. Signing in also lets the bot message the user.

Email notifications are optional: configure `SMTP_*`, then users add and verify an address under **Settings**.

See [.env.example](.env.example) for all settings (scan intervals, request delay, image size/quality,
`MIN_FREE_DISK_GB` to pause image archiving when the disk fills up, …).

### Sizing

Large regions are expensive: a full scan of all of Stockholm municipality is ~160 pages and its image archive
runs into tens of GB. Prefer districts or smaller municipalities, and keep an eye on **Admin → System**.
Hemnet returns at most 2 500 results (50 pages) per search, so for regions larger than that only the newest
2 500 listings are seen and removed-listing detection is skipped. Split such regions into districts.

## Development

```sh
# backend (Python 3.12)
cd backend
pip install -r requirements-dev.txt
DATA_DIR=./data DEV_LOGIN=true uvicorn app.main:app --reload   # DEV_LOGIN adds a login form without Telegram
pytest && ruff check . && ruff format --check .

# frontend (Node 22), proxies /api and /media to :8000
cd frontend
npm install
npm run dev
```

`DEV_LOGIN=true` exposes an unauthenticated login endpoint. Never enable it in production.

CI (`.github/workflows/build.yml`) runs lint, tests and typecheck, then publishes
`ghcr.io/liamniou/hemnet_parser_bot:<YYYY.M.D>.<run>` on pushes to `main`.
