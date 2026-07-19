# Phase 0 — акаунти під API (зробити ДО першого публічного посту)
#
# Meta (Instagram + Facebook)
# 1. Створи Facebook Page «mr.Carpet»
# 2. Instagram → Professional/Business → прив’яжи до Page (Meta Business Suite)
# 3. developers.facebook.com → Create App (Business) → Instagram Graph API + Facebook Login for Business
# 4. Додай тестовий Page / IG у ролі Admin на додаток
# 5. Graph API Explorer / OAuth → long-lived Page access token з правами:
#    pages_show_list, pages_read_engagement, pages_manage_posts,
#    instagram_basic, instagram_content_publish (або актуальні instagram_business_* aliases)
# 6. У .env (НЕ в git):
#    META_PAGE_ACCESS_TOKEN=...
#    META_PAGE_ID=...
#    META_IG_USER_ID=...          # Instagram Business account id (не @username)
#    META_GRAPH_VERSION=v21.0
# 7. Перевірка: python manage.py social_setup_check
#
# TikTok
# 1. developers.tiktok.com → Create app → Content Posting API
# 2. OAuth свого акаунта → access_token + open_id
# 3. Verify HTTPS media URL prefix для mrcarpet24.com (PULL_FROM_URL)
# 4. .env:
#    TIKTOK_CLIENT_KEY=...
#    TIKTOK_CLIENT_SECRET=...
#    TIKTOK_ACCESS_TOKEN=...
#    TIKTOK_OPEN_ID=...
#    TIKTOK_AUDIT_PASSED=false   # true лише після успішного app audit
# 5. До audit Direct Post = SELF_ONLY (не публічно). Публічний go-live — після audit.
#
# Telegram products channel
# 1. Створи канал + увімкни Discussion (linked group)
# 2. Додай бота адміном каналу і групи обговорення
# 3. Admin → Telegram settings → Products channel ID / Discussion chat ID
# 4. Увімкни «Автопост нових товарів» за потреби
