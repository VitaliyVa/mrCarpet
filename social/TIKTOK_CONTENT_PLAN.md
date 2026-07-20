# TikTok: щоденний авто-контент — план розробки (2026-07-20)

Мета: 1 раз/день береться 1 випадковий килим (з фото `is_ai` — інтер'єрні,
перевірені) → генерується відео через Replicate → публікується в TikTok
з описом/хештегами → всі файли чистяться після успішного аплоаду.

## Стан зараз (що вже є в коді)

| Компонент | Файл | Стан |
|---|---|---|
| TikTok Direct Post (video init → PULL_FROM_URL → status poll) | `social/services/tiktok.py` | ✅ готовий, не тестований (немає токенів) |
| Replicate I2V генерація відео з фото | `social/services/wan_i2v.py` | ✅ працює (Wan 2.2 fast) |
| Розмітка інтер'єрних фото | `ProductImage.is_ai` | ✅ **50 товарів** у пулі (з 87), 51 фото |
| Капшен-білдер | `social/services/post_content.py` | ✅ адаптувати під TT-стиль |
| Денний AI-бюджет | `SocialAiGenerationLog` | ✅ reuse |
| TikTok compliance поля | `SocialPost.tt_*` | ✅ готові |

**Блокер №1: TikTok Phase 0 не початий** — немає developer app, токенів
(`TIKTOK_*` env порожні). Без цього постити нікуди.

---

## Ключові рішення (обґрунтовані)

### Модель генерації відео

Пошук по Replicate (2026-07):

| Модель | Ціна | Аудіо | Нотатки |
|---|---|---|---|
| **prunaai/p-video** ⭐ рекомендація | **$0.02/с 720p** (~$0.12 за 6с; draft-режим $0.005/с для тестів) | ✅ **native audio** (фонова музика/звук генеруються разом з відео) | i2v, 9:16 напряму, 1-10с |
| wan-video/wan-2.2-i2v-fast (уже інтегрований) | ~$0.05-0.10/відео (перевірити по білінгу) | ❌ без звуку | перевірений на наших килимах; fallback |
| kling-v2.5-turbo-pro / seedance-2.0 / veo-3.1 | дорожчі | ✅ | якість вища, для цієї задачі overkill |

⭐ **p-video з native audio вирішує ДВІ проблеми одразу**: музика (згенерована
= нуль ліцензійних питань) і монтаж (він не потрібен — модель віддає готовий
MP4 9:16 зі звуком). Бюджет: ~$3.6-4/міс при 1 відео/день.

### Музика — юридична частина (ВАЖЛИВО)

**Чужу музику з авторським правом використовувати НЕ МОЖНА**, і монетизація
тут ні до чого — це питання ліцензії:
- Через Content Posting API музику з TikTok-бібліотеки додати неможливо
  (бібліотека доступна тільки в редакторі застосунку).
- Бейкнути чужий трек у файл = Content ID мутить звук / страйк / бан
  акаунта за повтори. Для бізнес-акаунтів правила ще жорсткіші.

Легальні варіанти:
1. **Native audio від моделі (p-video)** — основний шлях, нуль питань.
2. Fallback: royalty-free бібліотеки → скачати 10-20 треків один раз у
   `media/social/music/`, ротувати рандомно, міксувати ffmpeg-ом:
   - Pixabay Music (найкращий: безкоштовно, комерційне ок, без атрибуції)
   - Free Music Archive (CC), Uppbeat (freemium), Incompetech (CC-BY, треба згадка)

`tt_music_usage_confirmed=True` ставимо автоматично — ліцензія наша/чиста.

### Монтаж на сервері

З p-video монтаж **не потрібен взагалі**. Fallback-сценарій (wan + музика):
ffmpeg "прикласти аудіо" = copy відеопотоку + AAC-енкод аудіо → 1-3 секунди
CPU на 6с 720p. Навіть повне перекодування ≈ 20-60с на 1 vCPU. При 1
відео/день, вночі (04:00), під `nice -n 19` і `timeout 300` — сервер не
помітить. ffmpeg у Dockerfile.prod: +~80MB образу.

**Передумова-бекап (до першого запуску)**: WAL checkpoint + копія db.sqlite3
(вже є в deploy) + **DigitalOcean snapshot дропа** (рекомендація ще з
постмортема 2026-07-17 — досі не зроблена, цей план — привід).

### Ротація без повторів

Нова модель `TikTokDailyPick(product FK, cycle_number, picked_at, status
generated/published/failed, social_post FK)`:
- Пул: `Product.admin_objects.filter(images__is_ai=True).distinct()`
- Вибірка: пул мінус published-піки поточного циклу, `order_by('?')`
- Пул вичерпано → `cycle_number += 1`, все з нуля (вимога)
- `failed` пік НЕ ховає товар з пулу (може випасти знову)
- Ідемпотентність: якщо сьогодні вже є successful pick — команда виходить

### Опис / мета / хештеги

TikTok-стиль (коротший за IG): назва + ціна/розмір рядок + "🛒 Лінк у
профілі" (лінки в описі неклікабельні; в bio — лінк на каталог з utm) +
хештеги: статичні `#килим #килими #інтерєр #декор #дім #українськийбізнес`
+ з категорії товару. Ліміт 2200. Пишеться в `SocialPost.caption_tt`.
**AIGC-мітка**: позначати відео як AI-generated (параметр API) — рекомендую,
TikTok вимагає для синтетики.

### Видалення файлів (вимога)

Видаляти MP4 + проміжні файли ТІЛЬКИ після `PUBLISH_COMPLETE` від TikTok
(PULL_FROM_URL тягне файл з нашого сервера асинхронно — рано видаляти
не можна). При фейлі — файл лишається для дебагу + алерт у TG.

### Токени TikTok — те, про що легко забути

TikTok `access_token` живе **24 години**, `refresh_token` — 365 днів.
Статичний токен у .env (як зараз задумано в tiktok.py) працюватиме один
день! Потрібен авто-рефреш: модель/сховище TikTokToken + рефреш перед
кожним постом (або крон). Це обов'язкова доробка Phase 0.

---

## Фази розробки

### Phase 0 — TikTok Developer (руками + браузер, ~1-2 дні очікувань TikTok)
1. developers.tiktok.com → створити app (категорія: business/commerce)
2. Увімкнути продукти: Login Kit + Content Posting API
3. OAuth-флоу (можна одноразовим скриптом): scope `video.publish`,
   отримати `access_token` + `refresh_token` + `open_id` → прод `.env`
4. **Код: авто-рефреш токенів** (модель + рефреш у `_access_token()`)
5. `social_setup_check` розширити перевіркою рефрешу
6. До проходження audit — усі пости `SELF_ONLY` (код уже форсить)

### Phase 1 — Ротація (код, ~0.5 дня)
1. Модель `TikTokDailyPick` + міграція
2. `social/services/tiktok_rotation.py`: `pick_product_for_today()`
   (пул is_ai, цикли, ідемпотентність)
3. Тести (пул/цикл/reset/failed-логіка)

### Phase 2 — Генерація відео (код, ~1 день)
1. Узагальнити wan_i2v під конфігуровану модель: primary
   `prunaai/p-video` (i2v, 9:16, 6с, audio=on), fallback wan-fast
2. Промпт під продаж килимів (камера-панорама по інтер'єру, затишок,
   без тексту/вотермарок) + негативи
3. Бюджет-гард: reuse `SocialAiGenerationLog` + грошова стеля на місяць
   у SocialSettings
4. Тест draft-режимом p-video ($0.005/с) перед бойовим

### Phase 3 — Музика-fallback (код, ~0.5 дня, ОПЦІЙНО якщо p-video аудіо ок)
1. ffmpeg у Dockerfile.prod
2. `media/social/music/` + 10-20 Pixabay-треків
3. `mix_audio(video, track)` через ffmpeg subprocess (nice, timeout)

### Phase 4 — Пайплайн публікації (код, ~1 день)
1. Команда `tiktok_daily_post`: pick → SocialPost(caption_tt, hashtags,
   AIGC) → generate → [mix] → `tiktok.publish_video` → poll
   `PUBLISH_COMPLETE` → **cleanup MP4+ісходників** → TG-звіт
   (успіх з лінком / фейл з помилкою) у сімейну групу
2. Всі кроки з ретраями; будь-який фейл = алерт, файли лишаються
3. Тести пайплайна (мок Replicate/TikTok)

### Phase 5 — Шедулер + бекапи (~0.5 дня)
1. **Перед першим запуском: DO snapshot дропа + перевірка бекап-флоу**
2. Cron 04:00 Kyiv: host crontab або compose-сервіс типу ga4-weekly
3. Тиждень у SELF_ONLY: перевіряємо якість відео/капшенів у профілі

### Phase 6 — Audit і публічність (~тиждень очікування TikTok)
1. Подати app на audit (потрібна історія постів — SELF_ONLY тиждень дає її)
2. Після approve: `tiktok_audit_passed=True` в Social settings →
   `PUBLIC_TO_EVERYONE`
3. Моніторинг 2 тижні: вартість по білінгу Replicate, якість, реакція

Разом кодової роботи: ~3.5-4 дні + очікування TikTok (audit).

---

## Рішення юзера (зафіксовано 2026-07-20)

| Питання | Рішення |
|---|---|
| TikTok developer | Акаунт на developers.tiktok.com **є**, app **не створений** — Phase 0 стартує зі створення app |
| TikTok-акаунт бренду | **personal** — треба перемкнути на Business (інакше немає клікабельного лінка в bio) |
| Музика | **Native audio від p-video**, без ffmpeg-міксу → **Phase 3 скасовується** |
| Бюджет | **$5/міс** стеля (жорстко — див. нижче) |
| Довжина відео | **6 секунд** → $0.12/відео ≈ $3.6/міс, запас ~$1.4 на ретраї |
| Час | **Генерація 04:00 Kyiv, публікація 18:00 Kyiv** — два кроки, не один |
| Перший тиждень | **Draft → ручний Publish з адмінки** + TG-прев'ю |
| AIGC-мітка | **Так**, ставимо |

### Наслідки для плану

- **Phase 3 (музика/ffmpeg) викреслена** — мінус 0.5 дня. ffmpeg у
  Dockerfile.prod не потрібен. Якщо p-video віддасть тишу — повертаємось.
- **Phase 4 розпадається на дві команди** замість однієї:
  `tiktok_generate_daily` (04:00, створює draft) + `tiktok_publish_daily`
  (18:00, публікує вчорашній/сьогоднішній draft). Перший тиждень другий
  крон вимкнений, publish руками з адмінки.
- **Бюджет-гард жорсткий**: $5/міс при $3.6 споживання = 72% утилізації.
  Кожен невдалий retry генерації коштує повний $0.12. Гард має рахувати
  **всі** прогони, включно з фейленими, і глушити генерацію на місяць з
  TG-алертом. Тестові прогони робити в draft-режимі p-video ($0.005/с).
- **Перемикання акаунта на Business — до OAuth**, бо scope і доступність
  Content Posting API залежать від типу акаунта.

### Developer app — фактичний стан (2026-07-20)

Developer-акаунт: `mr.carpet.shop@gmail.com` (створений 2026-07-20, окремий
від TikTok-акаунта). TikTok-акаунт бренду: username **`mrcarpet24`**,
Name `mr.carpet` (нік дублює чужий існуючий `@mr.carpet` — не плутати).

App **mrCarpet**, ID `7664562732305516551`, статус **Draft**:

| Поле | Значення |
|---|---|
| Ownership | Individual (Transfer App → Organization можливий, незворотний) |
| App type | Other (змінити не можна) |
| Category | Shopping |
| Platforms | Web |
| Web/Desktop URL | `https://mrcarpet24.com/` (зі слешем — має збігатись з префіксом!) |
| Redirect URI | `https://mrcarpet24.com/api/tiktok/callback/` |
| Terms of Service | `https://mrcarpet24.com/terms/` |
| Privacy Policy | `https://mrcarpet24.com/policy/` |
| Products | Login Kit + Content Posting API |
| Direct Post | увімкнено |
| Scopes | `user.info.basic`, `video.publish`, `video.upload` |
| Іконка | лого 1024×1024 на `#fffcf2` |

**Верифікація домену: ЗРОБЛЕНО.** Метод — URL prefix / signature file
(не DNS). Префікс `https://mrcarpet24.com/` → статус Verified. Файл
віддається роутом `tiktok_site_verification_file` у `project/urls.py`
(вміст `tiktok-developers-site-verification=xfkAe8tZDvfpCs644EJmGm1b51LUG1xX`).
Цей самий префікс покриває і `pull_by_url` — окрема верифікація доменів у
блоці Content Posting API веде в той самий реєстр і вже зелена.

**Граблі**: `Web/Desktop URL` без кінцевого слеша не матчиться з
верифікованим префіксом і дає помилку «URL is not verified».

**Блокер збереження**: форма не зберігається, доки не залито демо-відео
(«Upload at least one demo video»). Тобто конфіг вище доведеться ввести
повторно, якщо вкладку закрито. Демо-відео знімається в **Sandbox** —
TikTok прямо вимагає sandbox для ще не схвалених app.

### Sandbox `mrcarpet-dev` — ГОТОВИЙ до розробки

ID `7664571787149477895`. Конфіг застосований (Apply changes, 0 помилок):
той самий набір, що в Production, + Direct Post ON + іконка.
Sandbox **не клонує** Production навіть із галочкою — вводилось окремо.

- **Target User**: `mrcarpet24` авторизований 2026-07-20 14:30
- **Креденшели окремі від Production**, ключ має префікс `sb`
- У локальному `.env`: `TIKTOK_CLIENT_KEY` (sbawmikcnj2shq8kdb) +
  `TIKTOK_CLIENT_SECRET` + порожні `TIKTOK_ACCESS_TOKEN` / `TIKTOK_OPEN_ID`
  + `TIKTOK_AUDIT_PASSED=false`. Перевірено, що Django їх читає.
- Sandbox-секрет засвітився в транскрипті сесії 2026-07-20 — за потреби
  перегенерувати в порталі (ризик низький: тестове оточення, 1 акаунт).

Тобто Phase 1-5 можна писати і ганяти проти реального API **без audit**.
Прод-креденшели знадобляться лише на Phase 6.

### Найближчі кроки коду (Phase 0 хвіст)

1. `/api/tiktok/callback/` — роут уже вписаний у TikTok, у коді його НЕМА
2. Модель `TikTokToken` + авто-рефреш у `_access_token()` (перезаписувати
   і refresh_token теж!) + алерт за 30 днів до `refresh_expires_at`
3. Одноразовий OAuth-скрипт/адмін-дія, щоб отримати перший токен

### Досліджено окремо (2026-07-20)

Вічного токена в TikTok не існує (перевірено по офіційних доках): 
`expires_in` = 86400 (24 год), `refresh_expires_in` = 31536000 (365 днів
від initial issuance, не rolling). Аналога Meta System User token
(`expires: NEVER`) немає. App-level `client_credentials` токен (2 год) 
вміє лише публічні дані — постити ним не можна. Business API — той самий 
життєвий цикл, не рятує.

Стандартний патерн: зберігати refresh_token, оновлювати access раз на день
фоново (без участі юзера). Ручний OAuth — раз на 365 днів.

**Пастка з доків**: при рефреші повертається **новий refresh_token** і
старий вмирає ("You must use the newly-returned token if the value is
different"). Не перезаписати його = інтеграція відвалиться. Топ-1 причина
поламаних TikTok-інтеграцій.

**Ще**: якщо юзер відкличе доступ app у налаштуваннях TikTok — refresh
помирає миттєво незалежно від дат. Обробка 401 має слати алерт, не мовчки
ретраїти. Плюс TG-алерт за 30 днів до `refresh_expires_at`.
