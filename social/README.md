# Social publishing (mr.Carpet)

## Потоки з адмінки

| Дія | Куди |
|---|---|
| **Social post** `media_kind=video` → Publish | Instagram Reels, Facebook Page video, TikTok video |
| **Social post** `media_kind=photos` → Publish | IG feed/carousel, FB multi-photo, TikTok photo slideshow |
| **Новий Product** (auto / admin action) | **лише** Telegram products channel |

UX: чернетка → кнопка **Publish** (не auto на Save).

## Коментарі → staff inbox

Публічні коментарі дзеркаляться в окрему групу **mr.Carpet comments** (не orders).

| Джерело | Статус |
|---|---|
| Telegram discussion під постом каналу | ✅ зараз |
| Instagram comments | пізніше (той самий `InboundComment` → `notify_staff_comment`) |
| Facebook comments | пізніше |

Формат алерту: платформа · пост · автор · час · текст.

Config (**Social settings**):
- `staff_comments_enabled`
- `staff_comments_chat_id` — порожньо = сімейна група
- `staff_comments_thread_id` — forum topic «mr.Carpet comments» (≠ orders topic)

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

### Telegram chats (ізоляція)

Один бот (`TelegramSettings.bot_token`). Сімейна супергрупа з Topics:

| Chat / topic | Config | Роль |
|---|---|---|
| Сімейна група | **Telegram settings** → `chat_id` | контейнер |
| Topic orders | **Telegram settings** → `message_thread_id` | ордери, AI, HITL |
| Topic comments | **Social settings** → `staff_comments_thread_id` (+ chat порожньо) | дзеркало коментарів TG/IG/FB |
| Канал `@mrcarpet24` | **Social settings** → `products_channel_id` | пости товарів |
| Discussion (linked) | **Social settings** → `products_discussion_chat_id` | публічні коментарі під постами |

1. Канал + Discussion; бот адмін
2. У сімейній групі: topic **mr.Carpet comments** (`createForumTopic` / вручну); бот з `can_manage_topics`
3. `staff_comments_thread_id` ≠ orders `message_thread_id`
4. `social_setup_check` → isolation OK
5. Автопост товарів за потреби; FAQ `products_bot_replies` краще вимкнено

Webhook: discussion **ніколи** → AI; людські коментарі → topic comments. AI лишається лише в orders topic.
