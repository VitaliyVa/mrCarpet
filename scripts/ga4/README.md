# GA4 access for Cursor / local ops

Service account з правами **Адміністратор** на ресурсі GA4 → агент може читати звіти (Data API) і змінювати налаштування ресурсу (Admin API).

Секрети і **локальна пам’ятка про права/ID** — тільки в `ops/ga4/` (папка в `.gitignore`, **не в git**).  
Після сетапу дивись: `ops/ga4/README.md` (локально).

## One-time setup (ти в браузері)

### 1) Google Cloud

1. https://console.cloud.google.com → створи проєкт (напр. `mrcarpet-analytics`)
2. **APIs & Services → Library** → увімкни:
   - **Google Analytics Data API**
   - **Google Analytics Admin API**
3. **IAM & Admin → Service Accounts → Create**
   - name: `cursor-ga4`
   - Create and continue → роль на проєкті можна `Viewer` (доступ до GA дамо в Analytics)
4. Keys → **Add key → JSON** → збережи файл як:

```text
ops/ga4/service-account.json
```

5. Скопіюй email SA (вигляд `cursor-ga4@….iam.gserviceaccount.com`)

### 2) Google Analytics 4

1. https://analytics.google.com → ресурс **mr.Carpet** (сайт)
2. Адміністратор → **Керування доступом до ресурсу** (Property access management)
3. **+** → додати користувачів → встав email service account
4. Роль: **Адміністратор** (як просив — повне редагування; мінімум Editor)
5. Admin → **Налаштування ресурсу** → скопіюй **ІДЕНТИФІКАТОР РЕСУРСУ** (лише цифри, не `G-…`)

### 3) Локальний env

```bash
mkdir -p ops/ga4
cp scripts/ga4/.env.example ops/ga4/.env
# впиши GA4_PROPERTY_ID=...
# шлях до JSON вже в example
```

```bash
pip install -r requirements-ga4.txt
# якщо JWT RS256 падає: pip install "PyJWT[crypto]"
```

Скрипти ходять у **REST API** (без важких google-analytics-* клієнтів — ок на Python 3.14).

### 4) Smoke test

З кореня репо:

```bash
python scripts/ga4/smoke.py
python scripts/ga4/report.py --days 7
python scripts/ga4/report.py --realtime
python scripts/ga4/admin.py info
```

Якщо OK — агент у Cursor може ганяти ці ж команди.

## Що вміє API vs UI

| Можна через API | Краще в UI |
|-----------------|------------|
| Звіти, події, сторінки, realtime | Looker-красиві дашборди |
| Conversion events, custom dimensions (частина) | Деякі wizard-и / зв’язки з Ads |
| Data streams / property metadata | Дизайн звітів snapshot |

## Ecommerce events (сайт)

Після деплою в Realtime / DebugView мають з’являтись:

| Event | Коли |
|-------|------|
| `view_item` | PDP |
| `view_item_list` / `select_item` | каталог / клік по картці |
| `add_to_cart` / `remove_from_cart` | кошик |
| `view_cart` / `begin_checkout` | `/cart/` / `/checkout/` |
| `add_shipping_info` / `add_payment_info` | чекаут |
| `purchase` | success (cash одразу; liqpay після оплати) |
| `add_to_wishlist` | обране |
| `search` / `filter_apply` / `size_select` | UX |
| `generate_lead` | контакт / newsletter / наявність |
| `click_phone` / `click_email` / `cta_click` | кліки |

`item_id` = **Product.pk** (каталог), не ProductAttribute.

### Конверсії (Admin API)

```bash
python scripts/ga4/admin.py mark-conversion purchase
python scripts/ga4/admin.py mark-conversion generate_lead
python scripts/ga4/admin.py mark-conversion add_to_cart
python scripts/ga4/admin.py mark-conversion begin_checkout
python scripts/ga4/admin.py conversions
```

### UTM + Search Console

- Кампанії: `utm_source` / `utm_medium` / `utm_campaign` на лендинг.
- GSC ↔ GA4: Admin → Product links → Search Console (раз у UI).
- Canonical на сайті бажано `https://` (окремий фікс).

## Безпека

- Ніколи не коміть `ops/ga4/*.json` / `.env`
- Не кидай JSON в чат — лише шлях на диску
- Для відклику: видали ключ у GCP + прибери юзера SA з GA4
