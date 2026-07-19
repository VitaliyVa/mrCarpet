# Meta Phase 0 — handoff (стан на 2026-07-19)

Контекст для наступного агента / людини. Не комітити секрети. Токени лише в серверний `.env`.

## Де зупинились

| Що | Статус |
|---|---|
| Meta Developer account (Vitaliy St / `vistet1428@gmail.com`) | ✅ |
| App **mrCarpet** | ✅ App ID `2163865730849917` |
| Business portfolio **mr. carpet** | ✅ Business ID `4600165533563507` |
| Use cases: Instagram API + Manage Pages (Pages API) | ✅ |
| OAuth Facebook Login for Business (scopes нижче) | ✅ |
| Page + IG IDs відомі | ✅ |
| Prod `.env` META_* + `social_setup_check` → `ig_ready`/`fb_ready` True | ✅ |
| **Never-expire Page token** (System User або long-lived exchange) | ❌ ще ні |
| `pages_manage_posts` у app permissions («Готово к тестированию») | ❌ Meta давав «Произошла ошибка» при Add |
| TikTok Phase 0 | ❌ не починали |

**Поточний `META_PAGE_ACCESS_TOKEN` на проді** = Page token з `me/accounts` після short-lived user OAuth. Працює для тестів, але **згорить ~через 60 днів**. Треба замінити на never-expire.

User rule: якщо Meta просить **пароль** — агент стопає, юзер вводить, пише «готово».

---

## Канонічні акаунти

| Що | Значення |
|---|---|
| Facebook Page | https://www.facebook.com/mrcarpet24/ → **Page ID `1245208955340257`** |
| Instagram | https://www.instagram.com/mr.carpet.shop/ → **IG User ID `17841443251761380`** |
| Meta App | `mrCarpet` / `2163865730849917` |
| Business | `mr. carpet` / `4600165533563507` |
| Prod host | `dev234345@178.128.196.94`, repo `~/projects/mrCarpet` |
| Prod compose | `docker-compose.prod.yml` (прокидає `META_*`) |

Перевірка на проді:

```bash
cd ~/projects/mrCarpet
docker compose -f docker-compose.prod.yml exec -T web python manage.py social_setup_check
```

Очікувано зараз: Meta `token_set/ig_ready/fb_ready` True; TikTok `configured: False`.

---

## Env (сервер, НЕ git)

```
META_PAGE_ACCESS_TOKEN=<never-expire Page token>
META_PAGE_ID=1245208955340257
META_IG_USER_ID=17841443251761380
META_GRAPH_VERSION=v21.0
```

Після правки `.env`:

```bash
docker compose -f docker-compose.prod.yml up -d web
docker compose -f docker-compose.prod.yml exec -T web python manage.py social_setup_check
```

Deploy код/шаблони — тільки через git (див. workspace rule). `.env` на сервері правити ок.

---

## Scopes

### Вже видані на user token (debug_token)

`pages_show_list`, `pages_read_engagement`, `instagram_basic`, `instagram_content_publish`, `business_management`, `public_profile`

### Ще треба для FB create posts

`pages_manage_posts` (+ бажано `pages_manage_engagement`, `pages_manage_metadata`)

Де додати:  
App → Use Cases → **Manage Pages** (`use_case_enum=PAGES_API`) → Permissions → **Добавить** → статус «Готово к тестированию».

Раніше Add падав з «Произошла ошибка». Можливий фікс перед retry: App Settings → Basic → Privacy Policy URL + Category + Save (може знов попросити пароль).

Після Add — перевипустити token (System User regenerate або новий OAuth) з цими scopes.

Код publish: `social/services/meta.py` (+ `publish.py`). IG вистачає `instagram_content_publish`; FB photo/video без `pages_manage_posts` може дати Graph error.

---

## Шлях A (рекомендовано для прод): System User never-expire token

Офіційний прод-патерн: токен **System User**, не особистий User token з Graph Explorer / Access Token Tool.

### Передумови

1. Залогінений як адмін Business **mr. carpet** і App **mrCarpet**.
2. Page **Mr.Carpet** і IG **mr.carpet.shop** у цьому Business (або можна assign).
3. App у Business (вже є).

### Кроки (UI ~2026)

1. Відкрити [Business Settings](https://business.facebook.com/settings) → портфоліо **mr. carpet**.
2. **Users** → **System users** → **Add** (якщо немає).
   - Ім’я: напр. `mrCarpet-prod`
   - Роль: **Admin** (або Employee + явні asset permissions; для простоти Admin).
3. Відкрити створеного System User → **Add assets** / Assign assets:
   - **Pages** → Page **Mr.Carpet** → права з **Create content** / manage posts (мінімум те, що потрібно для publish).
   - За потреби **Apps** → **mrCarpet**.
   - Instagram зазвичай йде через linked Page; якщо просить окремо — assign IG professional.
4. На System User → **Generate token** (або Generate new token):
   - Вибрати app: **mrCarpet** (`2163865730849917`)
   - Permissions (чекбокси), мінімум:
     - `pages_show_list`
     - `pages_read_engagement`
     - `pages_manage_posts` ← якщо ще не в app — спочатку Add у Use Case
     - `instagram_basic`
     - `instagram_content_publish`
     - `business_management` (часто потрібен)
   - Термін: **Never** / no expiry (якщо UI дає вибір — Never).
5. Скопіювати token **один раз** (покажуть лише зараз).
6. Перевірити локально / з ноутбука (токен не світити в чат/git):

```bash
TOKEN='…'
curl -sS "https://graph.facebook.com/v21.0/me/accounts?fields=id,name,instagram_business_account&access_token=$TOKEN" | python -m json.tool
# очікуємо Page id 1245208955340257 і instagram_business_account.id 17841443251761380

curl -sS "https://graph.facebook.com/v21.0/1245208955340257?fields=id,name&access_token=$TOKEN"
curl -sS "https://graph.facebook.com/v21.0/17841443251761380?fields=id,username&access_token=$TOKEN"
```

7. На прод сервері замінити лише рядок токена:

```bash
ssh dev234345@178.128.196.94
cd ~/projects/mrCarpet
# відредагувати .env: META_PAGE_ACCESS_TOKEN=<system user token>
# PAGE_ID / IG_USER_ID уже правильні — не чіпати якщо збігаються
docker compose -f docker-compose.prod.yml up -d web
docker compose -f docker-compose.prod.yml exec -T web python manage.py social_setup_check
```

8. Опційний smoke: admin → Social post (photos або video draft) → Publish на IG (і FB якщо `pages_manage_posts` вже в токені).

### Якщо System User не бачить Page / IG

- Business Settings → Accounts → Pages / Instagram accounts → додати asset у Business.
- Page → Settings → Page access → переконатись що Business має контроль.
- IG має бути Professional і **прив’язаний до Page** Mr.Carpet (не окремий personal).

### Що НЕ класти в `.env`

- User token з https://developers.facebook.com/tools/accesstoken/ (текст Meta: тільки для тестів).
- App token `app_id|app_secret` — не для Page/IG publish.
- App Secret у git / чат.

---

## Шлях B (швидший fallback): long-lived Page token через App Secret

Якщо System User застряг:

1. Cursor Browser → https://developers.facebook.com/apps/2163865730849917/settings/basic/
2. **Секрет приложения** → **Показать** → якщо пароль — **СТОП**, юзер вводить, «готово».
3. Скопіювати App Secret (не комітити).
4. Взяти свіжий **User** token з scopes (Access Token Tool після «надати дозволи» або Graph Explorer Generate).
5. Exchange:

```bash
curl -sS -G "https://graph.facebook.com/v21.0/oauth/access_token" \
  --data-urlencode "grant_type=fb_exchange_token" \
  --data-urlencode "client_id=2163865730849917" \
  --data-urlencode "client_secret=$APP_SECRET" \
  --data-urlencode "fb_exchange_token=$USER_TOKEN"
# → long-lived user token (~60 днів)
```

6. Page token:

```bash
curl -sS "https://graph.facebook.com/v21.0/me/accounts?fields=id,name,access_token,instagram_business_account&access_token=$LONG_LIVED_USER"
# access_token у відповіді для Page 1245208955340257 → META_PAGE_ACCESS_TOKEN
# цей Page token від long-lived user зазвичай never-expire
```

7. Записати в прод `.env`, recreate `web`, `social_setup_check`.

**Нотатка:** раніше exchange з секретом з рядка App Token (`2163865730849917|…`) давав `Error validating client secret`. Берети Secret тільки з кнопки **Показать**, не з App Token tool.

Bash: `|` у `access_token=APP_ID|SECRET` треба URL-encode як `%7C` або лапки, інакше pipe зламає команду.

---

## Шлях C (тимчасово, вже зроблено)

Short-lived OAuth → `me/accounts` → Page token на прод.  
`social_setup_check` зелений, але токен **тимчасовий**. Замінити A або B.

---

## Корисні URL

| Що | URL |
|---|---|
| App dashboard | https://developers.facebook.com/apps/2163865730849917/dashboard/?business_id=4600165533563507 |
| App basic (secret) | https://developers.facebook.com/apps/2163865730849917/settings/basic/ |
| Pages API permissions | https://developers.facebook.com/apps/2163865730849917/use_cases/customize/?use_case_enum=PAGES_API&selected_tab=permissions |
| Instagram API permissions | https://developers.facebook.com/apps/2163865730849917/use_cases/customize/?use_case_enum=INSTAGRAM_BUSINESS&selected_tab=permissions |
| Access Token Tool | https://developers.facebook.com/tools/accesstoken/ |
| Graph Explorer | https://developers.facebook.com/tools/explorer/ |
| Business Settings | https://business.facebook.com/settings |
| Token debugger | https://developers.facebook.com/tools/debug/accesstoken/ |

---

## Наступні задачі (пріоритет)

1. **Never-expire token** — шлях A (System User) або B (App Secret + exchange); оновити prod `.env`.
2. Додати `pages_manage_posts` у PAGES_API use case → regenerate token з цим scope.
3. Smoke publish з адмінки (IG photos/reel; FB якщо scope є).
4. TikTok Phase 0 (див. `social/README.md`).
5. Пізніше: IG/FB comments → `InboundComment` / staff topic (TG comments уже є).

---

## Код (орієнтири)

- `social/services/meta.py` — Graph calls, config getters
- `social/services/publish.py` — fan-out
- `social/management/commands/social_setup_check.py`
- `core/settings.py` — `META_*` з env
- `docker-compose.prod.yml` — passthrough `META_*`

Не гарячити прод через scp; env на сервері — ок.
