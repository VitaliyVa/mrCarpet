"""Clearer search snippets for 4 older articles with many impressions and few
clicks in Search Console (25.08-24.11.2026): polypropylene vs jute 567 shows /
0.5% CTR, rug size under sofa 404 / 1.2%, kids room 186 / 0%, long pile 96 / 1%.

The old descriptions all started with a generic «Дізнайтеся...». The new ones
say plainly what is inside (taken from each article's own headings).

Safety for prod: matched by slug; a field is changed only while it still holds
the old value (or is empty), so an edit made in the admin stays; idempotent,
never raises, reverse is a no-op.
"""

from django.db import migrations

CHANGES = {
    "polipropilen-poliester-i-dzhutova-osnova-porivniannia-kilimiv": {
        "old_title": "Як вибрати килим: поліпропілен, поліестер чи джут?",
        "title": "Поліпропілен, поліестер чи джут: який килим обрати",
        "old_description": "Дізнайтеся, чим відрізняються килими з поліпропілену, поліестеру та джутової основи за ціною, зносостійкістю та чисткою.",
        "description": "Порівнюємо килими з поліпропілену і поліестеру та килими на джутовій основі: ціна, зносостійкість, догляд і для яких кімнат кожен підходить.",
    },
    "iak-pidibrati-rozmir-kilima-pid-divan-i-lizhko-praktichni-poradi": {
        "old_title": "Як підібрати розмір килима під диван і ліжко",
        "title": "Розмір килима під диван і ліжко: скільки має виступати",
        "old_description": "Дізнайтеся, як правильно вибрати розмір килима під диван і ліжко, щоб створити затишок у вашому інтер'єрі.",
        "description": "Які розміри килима підходять під диван і ліжко, на скільки сантиметрів він має виступати, схеми розкладки і як виміряти кімнату.",
    },
    "kilim-u-ditiachu-kimnatu-bezpechni-materiali-ta-legkist-u-dogliadi": {
        "old_title": "Килим у дитячу кімнату: безпечні матеріали",
        "title": "Килим у дитячу кімнату: безпечні матеріали і догляд",
        "old_description": "Дізнайтеся, які килими безпечні для дітей, легко чистяться та не мають запаху. Вибір матеріалів для дитячої кімнати.",
        "description": "Які килими безпечні для дітей, чому безворсові легше чистити, як вивести пляму від соку і які килими без запаху.",
    },
    "chim-chistiti-kilim-z-dovgim-vorsom-udoma-poradi-ta-rekomendatsiyi": {
        "old_title": None,
        "title": None,
        "old_description": "Дізнайтеся, як правильно чистити килим з довгим ворсом вдома: суха та волога чистка, засоби, що псують ворс, та коли потрібна хімчистка.",
        "description": "Як чистити килим з довгим ворсом удома: суха і волога чистка, що робити із залежаним ворсом, які засоби його псують і коли краще віддати в хімчистку.",
    },
}


def forwards(apps, schema_editor):
    Article = apps.get_model("blog", "Article")
    changed = 0
    for slug, c in CHANGES.items():
        try:
            article = Article.objects.filter(slug=slug).first()
            if article is None:
                continue
            fields = []
            if c["title"] and (article.meta_title or "").strip() in ("", c["old_title"]):
                if article.meta_title != c["title"]:
                    article.meta_title = c["title"]
                    fields.append("meta_title")
            if (article.meta_description or "").strip() in ("", c["old_description"]):
                if article.meta_description != c["description"]:
                    article.meta_description = c["description"]
                    fields.append("meta_description")
            if fields:
                article.save(update_fields=fields)
                changed += 1
        except Exception as exc:  # pragma: no cover - defensive
            print(f"  [blog] {slug}: snippet not updated: {exc}")
    print(f"\n  [blog] clearer snippets: {changed} articles")


class Migration(migrations.Migration):
    dependencies = [("blog", "0012_seed_articles_2027_q1")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
