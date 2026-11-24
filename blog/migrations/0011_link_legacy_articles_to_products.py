"""Add product cards and a category link to the 7 original articles (2026-11-24).

Audit: the 7 live articles bring almost all organic traffic, but none of them
linked a single product (only the generic /catalog/), so readers had no next
step and product pages got no internal links from the blog.

What it does, per article slug:
- inserts one short paragraph with a link to the matching category and one
  ``<div class="blog-products" data-products="...">`` block (rendered as live
  product cards by blog.services.product_cards) before the third <h2>, or at
  the end when the article has fewer headings.

Safety (runs on prod during deploy):
- skips an article that already has a "blog-products" block (idempotent, and
  an admin who added cards by hand is left alone);
- never deletes text; reverse is a no-op;
- product slugs were checked against the live in-stock feed on 24.11.2026; an
  unknown or sold-out slug is simply not rendered by the card service;
- every error is caught: web runs `migrate` before gunicorn.
"""

from django.db import migrations
from django.utils import timezone

LINKS = {
    "kilimok-u-vannu-iak-vibrati-shchob-ne-kovzav-i-shvidko-sokh": (
        "/catalog/categorie/dlia-vanni/",
        "Подивіться наші килимки для ванної",
        "kilim-zelenii-v-vannu,kilim-dimchastii-dlia-vanni-path,"
        "kilim-okeanichnii-dlia-vanni-efesto,kilim-dimchastii-dlia-vanni-silver",
    ),
    "kilim-na-kukhniu-iak-vibrati-bezvorsovii-ta-stiikii-do-pliam": (
        "/catalog/categorie/v-kukhniu/",
        "Килими, які ми радимо на кухню",
        "kilim-priamokutnii-sirii,kilim-priamokutnii-flex-bez-nazvi,"
        "kilim-priamokutnii-sirii-19689-811,kilim-priamokutnii-grafit-teppich-smile-507099805",
    ),
    "chim-chistiti-kilim-z-dovgim-vorsom-udoma-poradi-ta-rekomendatsiyi": (
        "/catalog/categorie/ukrayinski/",
        "Пухнасті килими з довгим ворсом у нашому каталозі",
        "kilim-ovalnii-sirii-fantasy-grey-1250016-o,kilim-priamokutnii-sirii-fantasy-grey-1250016,"
        "kilim-ovalnii-bezhevii-fantasy-beige-1250090-o,kilim-ovalnii-kremovii-fantasy-beige-1250010",
    ),
    "iak-pidibrati-rozmir-kilima-pid-divan-i-lizhko-praktichni-poradi": (
        "/catalog/categorie/turetski/",
        "Килими під диван і ліжко різних розмірів",
        "kilim-priamokutnii-siro-korichnevii-mira-24122162,kilim-priamokutnii-temno-sirii-la-rosa-gk503,"
        "kilim-priamokutnii-mira-24192261,kilim-priamokutnii-bezhevii-la-rosa-gk500",
    ),
    "iakii-kilim-mozhna-klasti-na-teplu-pidlogu-poradi-ta-rekomendatsiyi": (
        "/catalog/categorie/ukrayinski/",
        "Тонкі безворсові килими з нашого каталогу",
        "kilim-priamokutnii-mira-24192261,kilim-priamokutnii-korichnevii-flex-1952-m91,"
        "kilim-priamokutnii-flex-bez-nazvi",
    ),
    "kilim-u-ditiachu-kimnatu-bezpechni-materiali-ta-legkist-u-dogliadi": (
        "/catalog/categorie/v-ditiachu/",
        "Килими в дитячу, які в нас є зараз",
        "kilim-priamokutnii-pazli,kilim-priamokutnii-zelenii-misto,kilim-ovalnii-miki-maus",
    ),
    "polipropilen-poliester-i-dzhutova-osnova-porivniannia-kilimiv": (
        "/catalog/categorie/turetski/",
        "Килими з поліпропілену на джутовій і гумовій основі",
        "kilim-priamokutnii-temno-sirii-la-rosa-gk503,kilim-priamokutnii-sirii-mira-24031619,"
        "kilim-priamokutnii-korichnevii-flex-1952-m91,kilim-priamokutnii-bezhevii-la-rosa-gk500",
    ),
}


def build_block(url: str, text: str, slugs: str) -> str:
    return (
        f'<p><a href="{url}">{text}</a>. Ось кілька моделей, які зараз є в наявності.</p>\n'
        f'<div class="blog-products" data-products="{slugs}"></div>\n'
    )


def insert_block(html: str, block: str) -> str:
    pos, start = -1, 0
    for _ in range(3):
        pos = html.find("<h2", start)
        if pos < 0:
            break
        start = pos + 3
    if pos < 0:
        return html.rstrip() + "\n" + block
    return html[:pos] + block + html[pos:]


def forwards(apps, schema_editor):
    Article = apps.get_model("blog", "Article")
    done = 0
    for slug, (url, text, slugs) in LINKS.items():
        try:
            art = Article.objects.filter(slug=slug).first()
            if art is None or "blog-products" in (art.description or ""):
                continue
            Article.objects.filter(pk=art.pk).update(
                description=insert_block(art.description or "", build_block(url, text, slugs)),
                updated=timezone.now(),
            )
            done += 1
        except Exception as exc:  # pragma: no cover - defensive
            print(f"  [blog] {slug}: products not linked: {exc}")
    print(f"\n  [blog] linked products in {done} of {len(LINKS)} legacy articles")


class Migration(migrations.Migration):
    dependencies = [("blog", "0010_seed_articles_2027_01a")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
