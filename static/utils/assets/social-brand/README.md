# mr.Carpet — соцмережі: асети + тексти для швидкого старту

**Канонічна копія (в git):** `static/utils/assets/social-brand/`  
Локальний дубль: `ops/social-brand/` (`ops/` у `.gitignore`).

Згенеровано через Replicate (`black-forest-labs/flux-schnell`), палітра під бренд сайту: terracotta `#A46C46`, walnut `#7A4A2E`, ivory.

## Що куди ставити (рекомендація)

| Файл | Ідея | Куди |
|---|---|---|
| **`avatars/avatar-v3-footprint.png`** | Слід босої ноги на круглому килимі — «дім починається без взуття» | **Кандидат #1** TT / IG / FB / TG |
| **`avatars/avatar-v3-flight.png`** | Літаючий килим-гліф (без персонажа) | Кандидат #2 — динамічний |
| **`avatars/avatar-v3-catloaf.png`** | Кіт-калачик на круглому килимі | Кандидат #3 — теплий TikTok |
| `avatars/avatar-v3-planet.png` | Круглий килим = планета дому | Філософія / сторіс |
| `avatars/avatar-v3-spiral.png` | Згорнутий килим (спіраль / «вініл») | Текстурний / преміум |
| `avatars/avatar-v3-rollmark.png` | Плоский лого-спіраль (якщо є) | Іконка / app-style |
| **`covers/cover-living-a.png`** | — | **Facebook Page cover** |
| `covers/cover-living-b.png` | — | Альтернативний lifestyle cover |
| `covers/cover-texture.png` | — | Текстура килима (фон / сторіс) |
| `stories/highlight-*.png` | — | IG Highlights |

Сайтовий логотип — для UI; для соцмереж — ці асети. Старі аватари (gentleman / illusion / light-a) видалені.

Розміри: аватари `1024×1024`, cover `1344×768` (~16:9). FB Page можна додатково обрізати до ~820×312 у Canva.

---

## Єдині назви (копіюй 1:1)

| Платформа | Display name | Username | URL |
|---|---|---|---|
| Instagram | mr. carpet / mr.Carpet | `@mr.carpet.shop` | https://www.instagram.com/mr.carpet.shop/ |
| TikTok | mr.Carpet | `@mrcarpet24` | https://www.tiktok.com/@mrcarpet24 |
| Facebook Page | Mr.Carpet / mr.Carpet | `mrcarpet24` | https://www.facebook.com/mrcarpet24/ |
| Telegram канал | mr.Carpet \| Килими | `@mrcarpet24` | https://t.me/mrcarpet24 |

> IG username свідомо **не** `@mrcarpet24` — зайнятий/недоступний; канон: `@mr.carpet.shop`.

---

## Біо / описи

### Instagram / TikTok
```
Килими від українських і турецьких виробників
Підберемо розмір і стиль під твій інтер’єр
➜ mrcarpet24.com
```

Коротший варіант:
```
Килим, який пасує саме тобі.
Каталог → mrcarpet24.com
```

### Facebook — короткий About
```
mr.Carpet — інтернет-магазин килимів. Українські та турецькі виробники, доставка Новою Поштою по Україні. Допомагаємо підібрати розмір і стиль під кімнату.
```

Довгий About:
```
mr.Carpet — онлайн-магазин килимів для дому.

У каталозі — килими від українських і турецьких виробників: у вітальню, дитячу, ванну, під двері, на кухню. Різні розміри й форми, актуальна наявність на сайті.

Доставка по Україні (Нова Пошта). Сайт: https://mrcarpet24.com
Питання — у Direct / Telegram.
```

Категорія FB: **Home goods** / Shopping & retail.

### Telegram канал — опис
```
Новинки та підбірки килимів від mr.Carpet.
Каталог: https://mrcarpet24.com
Питання в коментарях — відповімо
```

Pinned post:
```
Привіт — це канал mr.Carpet

Тут:
• новинки з каталогу
• підбірки «в дитячу / у вітальню / овальні»
• промокоди

Сайт: https://mrcarpet24.com
Пиши в коментарях розмір кімнати — підкажемо варіанти.
```

---

## Link in bio (UTM)

- IG: `https://mrcarpet24.com/?utm_source=instagram&utm_medium=social&utm_campaign=profile`
- TT: `…utm_source=tiktok…`
- FB: `…utm_source=facebook…`
- TG: `…utm_source=telegram…`

---

## Порядок створення (30–60 хв)

1. FB Page «mr.Carpet» → аватар з `avatar-v3-*` (рекомендація: `footprint` або `flight`) → cover `cover-living-a`
2. IG Professional → прив’язка до Page → той самий аватар + біо
3. TikTok `@mrcarpet24` → той самий аватар + біо
4. TG канал + Discussion → фото = аватар → бот адміном → IDs у Social settings
5. Meta/TikTok developer apps → токени в `.env` (`social/README.md`)

Якщо жоден `v3` не зайшов — скажи що змінити (тон / ідея / контраст).
