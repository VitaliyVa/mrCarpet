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
| Перший тиждень | ~~Draft → ручний Publish~~ → **повне авто без ручної перевірки** (змінено 2026-07-20) |
| AIGC-мітка | **Так**, ставимо |

### Наслідки для плану

- **Phase 3 (музика/ffmpeg) викреслена** — мінус 0.5 дня. ffmpeg у
  Dockerfile.prod не потрібен. Якщо p-video віддасть тишу — повертаємось.
- **Phase 4 розпадається на два виклики** однієї команди:
  `tiktok_daily --generate` (04:00) + `tiktok_daily --publish` (18:00).
  Обидва крони працюють одразу — ручної перевірки не буде (рішення юзера
  2026-07-20). Контроль лишається через TG-звіт після кожного посту та
  `SELF_ONLY` до проходження audit.
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

### Phase 0 — ЗАВЕРШЕНА (2026-07-20)

Код: `TikTokToken` (міграція 0009) + `social/services/tiktok_auth.py` +
staff-only в'юхи `/api/tiktok/authorize/` та `/api/tiktok/callback/` +
розділ «TikTok token» в адмінці з кнопками авторизації/рефрешу.
`_access_token()` у `tiktok.py` тепер бере токен з БД і рефрешить за 10 хв
до протухання — решта модуля не змінювалась, бо все йде через `_headers()`.

**Перевірено на проді проти живого API (sandbox):**
- `creator_info` → `mrcarpet24` / `mr.carpet`
- примусовий рефреш → новий `expires_at`, помилок нема
- `creator_info` після рефрешу → ОК
- `open_id=-000_N8C_7uVP2JhQzZnwo8POyTYwnoGCoUw`, scope усі три,
  переавторизація потрібна через 364 дні

**`privacy_level_options` цього акаунта**: `PUBLIC_TO_EVERYONE`,
`MUTUAL_FOLLOW_FRIENDS`, `SELF_ONLY`. **`FOLLOWER_OF_CREATOR` НЕ підтримується** —
`ALLOWED_PRIVACY` у `tiktok.py` дозволяє його, TikTok відхилить. Врахувати
в Phase 4: брати список з `creator_info`, а не хардкодити.

**Граблі прод-деплою**: змінні з `docker-compose.prod.yml` → `environment:`
(там усі `TIKTOK_*`) потребують `up -d web` для перестворення контейнера.
`restart` лишає старий env, а decouple читає `os.environ` раніше за `.env` →
порожня compose-змінна перебиває правильне значення з файлу.

### Phase 1-5 — ЗРОБЛЕНО (2026-07-20)

Пайплайн: `pick → 9:16 фото → кліп → монтаж → TikTok → cleanup → TG-звіт`.

| Модуль | Роль |
|---|---|
| `tiktok_rotation.py` | пул is_ai, цикли без повторів; витрачає товар лише `published` |
| `tiktok_video.py` | gpt-image-2 → 9:16 (кешується на товар), далі p-video 6с |
| `tiktok_budget.py` | стеля $/міс; у леджер пишеться КОЖЕН виклик, і невдалий теж |
| `tiktok_music.py` | 20 треків musicgen, згенеровані разово, ротація по pick.pk |
| `tiktok_script.py` | гак (5 варіантів) + фіксований фінал + капшен з хештегами |
| `tiktok_montage.py` | ffmpeg: гак → відлік 3-2-1 → кліп з ціною → реверс-хвіст |
| `tiktok_publish.py` | PULL_FROM_URL, полінг, чистка після PUBLISH_COMPLETE |

Команди: `tiktok_daily --generate` (04:00), `tiktok_daily --publish` (18:00),
`tiktok_rotation_status`, `tiktok_music_library`.

**Формат відео (~14.5с)**: питання «Скільки б ви дали за такий килим 1.2 × 2.0 м?»
→ відлік 3-2-1 по 1.33с з тіками → кліп, ціна проявляється через 1.5с →
реверс-хвіст із «Вгадали? Пишіть у коментарях». Ціна — першого розміру,
розмір названий у питанні, тому відповідь однозначна.

**Граблі ffmpeg, задокументовані в коді:**
- анімований `fontsize` **валить ffmpeg** (0xC0000005) — рух робимо через `y`
- `
` у drawtext малює порожній гліф — рядки малюються окремо
- двокрапка у шляху шрифту ламає весь filtergraph (Windows-дев)
- плашки рядків перетинаються, якщо крок < 1.6× кегля

**Що НЕ зроблено**: DO-snapshot дропа перед першим бойовим запуском
(рекомендація з постмортему 2026-07-17, досі актуальна).

### ЖИВИЙ ЗАПУСК — стан на 2026-07-20 вечір

**Перший пост опублікований**: `external_id v_pub_url~v2-1.7664636366185089046`,
`SELF_ONLY`, товар #17 (килим 1.2×2.0, 2300 ₴). Відео реально видно в профілі —
тобто sandbox публікує по-справжньому, попри твердження деяких блогів.

Планувальник `tiktok-daily` піднятий: генерація 04:00, публікація 18:00 Kyiv.

**Три реальні перешкоди, на які пішов час:**

1. `url_ownership_unverified` — TikTok верифікує домен **окремо для кожного
   середовища**. Production і sandbox мають РІЗНІ токени. Роут
   `tiktok_site_verification_file` тепер віддає мапу токенів.
2. `unaudited_client_can_only_post_to_private_accounts` — це про приватність
   **акаунта**, не поста. `SELF_ONLY` недостатньо: до audit акаунт @mrcarpet24
   мусить бути приватним. Увімкнено 2026-07-20.
3. `Content-Type: application/octet-stream` на mp4 — блок `types` у nginx
   ЗАМІНЮЄ успадковані MIME-типи. Виправлено в `config/mrcarpet.docker`
   (не в `config/nginx.conf` — той на проді не використовується!).

**Грошовий баг, знайдений леджером**: `--force` означав і «обійти гейти», і
«перегенерувати» → кожен повтор публікації купував нове відео. Витрачено $0.48
замість $0.14. Розділено на `--force` / `--regenerate`.

**Docker-пастки, задокументовані в коді:**
- `/app/media` — це ТОМ, а не папка репозиторію. Заливати через
  `docker compose cp`, а не `scp` у `~/projects/mrCarpet/media/`
- bind-mount ОКРЕМОГО файлу тримається за inode: `scp` + `nginx -s reload`
  не працює, потрібен `restart` контейнера
- порожня compose-змінна перебиває значення з `.env`, бо decouple читає
  `os.environ` раніше за файл. Тому `tiktok-daily` НЕ оголошує `SECRET_KEY`
  і `TELEGRAM_BOT_TOKEN` (перший з .env, другий з БД)

### ПОДАНО НА AUDIT — 2026-07-20

Статус app: **In review**. Кнопка `Recall` відкликає подачу; редагувати конфіг
під час розгляду не можна.

Подано: 2 демо-відео (авторизація + публікація з адмінки), пояснення на 901
символ, Login Kit + Content Posting API з Direct Post, scopes
`user.info.basic` / `video.publish` / `video.upload`.

**`video.upload` прибрати НЕМОЖЛИВО** — він «Included in Content Posting API»
і йде в комплекті з продуктом. У поясненні написано прямо, що draft-upload ми
не викликаємо.

Термін: 3-5 днів (чистий випадок) … 1-2 тижні (типово) … 2-6 тижнів (з
відмовою). Прискорити неможливо. Найчастіша причина відмови — демо-відео не
покриває кожен scope.

**Поки триває розгляд** автопостинг працює: акаунт приватний, пости
`SELF_ONLY`, планувальник `tiktok-daily` генерує о 04:00 і публікує о 18:00.
Ця історія постів — аргумент для рецензента.

### Після схвалення (2 дії)

1. Юзер: вимкнути приватність акаунта в застосунку TikTok
2. `tiktok_audit_passed = True` в Social settings → код сам перемкнеться на
   `PUBLIC_TO_EVERYONE` (список береться з `creator_info`)

### Відкрите питання

Обкладинка поста #2 віддавала **403** з непідписаного CDN-хоста
(`p0-pu-image-no` замість `p16-common-sign`), через що замість прев'ю
показувався `alt` — тобто капшен із іконкою зламаної картинки. Схоже на
затримку TikTok. Мітигація: тепер шлемо `video_cover_timestamp_ms=700`
(питання вже видно, цифра відліку ще ні) замість дефолтного нульового кадру.
Перевірити, чи проблема повторюється на наступних постах.

### Що лишилось до публічних постів

| Крок | Хто |
|---|---|
| Прибрати scope `video.upload` (не використовується → ризик відмови) | я + переавторизація юзером |
| Демо-відео наскрізного флоу | **юзер** (запис екрана) |
| Заповнити Production-конфіг + submit | я |
| Розгляд TikTok: 3-5 днів … 2-6 тижнів | вони |
| Акаунт → публічний, `tiktok_audit_passed = True` | юзер + я |

Прискорити розгляд неможливо — платного треку TikTok не має.
Найчастіша причина відмови: демо-відео не покриває кожен запитаний scope.

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

---

### AUDIT ВІДХИЛЕНО — розворот на Buffer (2026-07-24)

TikTok **відхилив** production-доступ. Note рецензента:

> App will not be approved for personal or company internal use. TikTok for
> Developers currently does not support personal or internal company use. Not
> acceptable: Display posts from the TikTok account(s) you or your team manage
> on your website.

**Корінь**: відмова не про демо-відео/scope (як боявся весь план вище), а про
**сам use-case**. Content Posting API у проді TikTok дає лише **мульти-тенант**
продуктам, де сторонні креатори підключають свої акаунти. Один бренд, що постить
у власний акаунт `@mrcarpet24` = «internal use» = структурна авто-відмова. Recall
+ кращий опис не рятує — resubmit дасть ту саму відмову. У TikTok **немає**
легального API-шляху для single-account self-posting (на відміну від Meta/YT).

**Рішення**: публікуємо в TikTok через **Buffer**, у якого вже є схвалений
TikTok app. Ми віддаємо Buffer публічний HTTPS-URL відео (та сама модель, що
`PULL_FROM_URL`), він постить від нашого імені. Нашого audit не треба взагалі.
Free-план Buffer це дозволяє: новий GraphQL API — на всіх планах, доступ по
**personal API key** (не third-party OAuth, бо акаунт наш один).

Чому Buffer, а не інші (перевірено 2026-07-24):
- **Postiz / Mixpost (self-host)** — вимагають ТВІЙ TikTok dev app → та сама
  audit-стіна. Безкоштовно, але марно.
- **Ayrshare** — free = 20 постів, **images only** (відео нема). Платний $149/міс.
- **Buffer** ⭐ — free, personal-key GraphQL API, TikTok через їхній app.

**Зміни в коді (2026-07-24):**

| Файл | Що |
|---|---|
| `social/services/buffer.py` | новий GraphQL-клієнт: `organization_id()`, `tiktok_channel_id()`, `publish_video()`, `setup_status()`. Endpoint `POST https://api.buffer.com`, `Authorization: Bearer`. Мутація `createPost(mode addToQueue)`, медіа = public URL. Капшен екранується через `json.dumps` (GraphQL string literal == JSON string) |
| `social/services/video_networks.py` | `TikTokAdapter.publish` → тепер `buffer.publish_video` замість `tiktok.publish_video`. `is_configured` → `buffer.buffer_configured()`. `private=False` (Buffer-app публічний). Direct-post код (`tiktok.py`, `tiktok_auth.py`) лишається для OAuth/admin-діагностики, але **не на шляху публікації** |
| `core/settings.py` | `BUFFER_API_KEY`, `BUFFER_ORG_ID`, `BUFFER_TIKTOK_CHANNEL_ID` (два останні опційні — резолвляться з ключа) |
| `docker-compose.prod.yml` | `BUFFER_*` passthrough у секції `web` і `tiktok-daily` |
| `social/management/commands/buffer_status.py` | нова команда — перевірка підключення на проді |
| `social/tests/test_tiktok_publish.py` | моки `tiktok.*` → `buffer.*`; прибрано privacy/music/AIGC-ассерти (тепер керує Buffer). Уся сюїта social: **372 tests OK** |

**Втрачено при переході** (керується тепер у Buffer, не в нашому коді):
- privacy_level (SELF_ONLY/PUBLIC) — акаунт має бути публічним, Buffer постить публічно
- **AIGC-мітка** (`made_with_ai`) — API createPost Buffer її не приймає в
  документованому прикладі. TikTok вимагає позначати синтетику. **TODO: увімкнути
  AI-content toggle у налаштуваннях TikTok-каналу в Buffer** (або per-post), інакше
  ризик по TikTok-політиці. Перевірити, чи Buffer має цей параметр у повній схемі.
- music_usage_confirmed — Buffer/TikTok розбираються самі

**Ризик під живу перевірку**: `mode: addToQueue` публікує в наступний слот
черги каналу. Треба, щоб у Buffer був заданий розклад постингу для TikTok-каналу
в межах доби (інакше відео чекає, а cleanup через 24 год видалить файл). Або
підняти `MEDIA_RETENTION_HOURS`. Перевірити на першому пості.

**Кроки юзера (щоб увімкнути):**
1. Створити акаунт Buffer (free), перемкнути `@mrcarpet24` на **публічний**
2. Підключити TikTok-канал у застосунку Buffer
3. Згенерувати personal API key: `https://publish.buffer.com/settings/api`
4. Увімкнути AI-content toggle для TikTok-каналу в Buffer (мітка синтетики)

**Кроки мої (після ключа):**
1. `BUFFER_API_KEY` у прод `.env` + `docker compose up -d web tiktok-daily`
   (порожня compose-змінна перебиває .env — тому `up -d`, не `restart`)
2. `docker compose exec web python manage.py buffer_status` — підтвердити канал
3. Тестовий пост через адмінку → перевірити, що зʼявився в TikTok
4. `tiktok_auto_enabled = True` (якщо ще не) — планувальник підхопить о 18:00

### LIVE — розгорнуто і перевірено наживо (2026-07-24)

Buffer-акаунт створений (free), TikTok-канал `mrcarpet24` підключений, акаунт
**публічний**. Personal API key згенерований (**термін 1 рік — протухає
2027-07-24**, ротація в порталі; збережений в `ops/CREDENTIALS.md` + прод/локал
`.env`). Org id `6a63596fb088b578e20690d3`, channel id `6a635998e2638b94d7c7ff8f`.

Endpoint/схема підтверджені живими викликами (200): `account.organizations`,
`channels`, `createPost`. **Тест наскрізь**: `buffer.publish_video` з реальним
montage pick #7 (`https://mrcarpet24.com/media/.../pick-7.mp4`, 6.95 MB, 200
video/mp4) → Buffer прийняв на free-плані, поставив у чергу TikTok, `status
scheduled`, `dueAt` = наступний слот черги (~18:29 UTC). Тестовий пост потім
**видалено** (`deletePost(input:{id})` → union `DeletePostSuccess`/`VoidMutationError`),
щоб планувальник о 18:00 Kyiv відпрацював без дубля.

**Граблі деплою**: на проді є **авто-pull** — він підтягнув push і перестворив
`web`, той OOM-нувся (`Exited 137`), сайт впав у 502. Підняв `web` окремо (пам'ять
здорова, 2.9 ГБ вільно — не як у постмортемі 07-17). Далі додав `BUFFER_*` у прод
`.env` і перестворив `web` та `tiktok-daily` **по одному** (stop→sleep→up→curl 200).
Обидва бачать ключ (`buffer_status` → ready).

**Стан**: повністю робоче. Планувальник `tiktok-daily` о 18:00 Kyiv публікує
pick #7 у TikTok через Buffer (+ фан-аут у Meta/YT/Threads як раніше).

**Єдиний TODO по політиці**: AIGC-мітка — Buffer `createPost` її в API не має,
увімкнути AI-content toggle у налаштуваннях TikTok-каналу в Buffer вручну.
