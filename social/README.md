# Social publishing (mr.Carpet)

## Потоки з адмінки

| Дія | Куди |
|---|---|
| **Social post** `media_kind=video` → Publish | Instagram Reels, Facebook Page video, TikTok video |
| **Social post** `media_kind=photos` → Publish | IG feed/carousel, FB multi-photo, TikTok photo slideshow |
| **Новий Product** (auto / admin action) | **лише** Telegram products channel |

UX: чернетка → кнопка **Publish** (не auto на Save).

## Phase 0 — акаунти під API (до першого публічного посту)

### Meta (Instagram + Facebook)
1. Facebook Page «mr.Carpet» + Instagram Professional, прив’язка до Page
2. developers.facebook.com → App (Business) → Instagram Graph API + Facebook Login for Business
3. Long-lived Page access token з правами:
   `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`,
   `instagram_basic`, `instagram_content_publish` (або актуальні aliases)
4. У `.env` (НЕ в git):
   ```
   META_PAGE_ACCESS_TOKEN=...
   META_PAGE_ID=...
   META_IG_USER_ID=...          # IG Business account id (не @username)
   META_GRAPH_VERSION=v21.0
   ```
5. `python manage.py social_setup_check`

### TikTok
1. developers.tiktok.com → Content Posting API
2. OAuth → `access_token` + `open_id`
3. Verify HTTPS media URL prefix для `mrcarpet24.com` (PULL_FROM_URL) — і для video, і для photo
4. `.env`:
   ```
   TIKTOK_CLIENT_KEY=...
   TIKTOK_CLIENT_SECRET=...
   TIKTOK_ACCESS_TOKEN=...
   TIKTOK_OPEN_ID=...
   TIKTOK_AUDIT_PASSED=false   # true лише після app audit
   ```
5. До audit Direct Post = `SELF_ONLY`. Публічний go-live — після audit.

### Telegram products channel (ізоляція від сімейної групи)

Один бот (`TelegramSettings.bot_token`), **три різні numeric chat id**:

| Chat | Config | Роль |
|---|---|---|
| Сімейна / замовлення | Admin → **Telegram settings** → `chat_id` | ордери, AI, HITL |
| Канал `@mrcarpet24` | Admin → **Social settings** → `products_channel_id` | лише пости товарів |
| Discussion (linked) | Admin → **Social settings** → `products_discussion_chat_id` | лише FAQ whitelist |

1. Створи канал + Discussion (linked group)
2. Додай бота адміном каналу і групи обговорення
3. Заповни IDs у **Social settings** (не Telegram settings)
4. Переконайся: family ≠ channel ≠ discussion (`social_setup_check` покаже isolation)
5. Увімкни «Автопост нових товарів» за потреби

Webhook: updates з discussion **ніколи** не йдуть в AI агента сімейної групи.
