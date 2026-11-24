"""Fill the new category page texts and refresh weak meta tags (2026-11-24).

Texts come from catalog/data/category_texts_2026_11.json, written from the live
catalog and feed (sizes, materials, backing, prices "від"), simple Ukrainian,
no dashes. Exact counts were left out on purpose so the copy does not go stale.

Safety (runs on prod during deploy):
- intro / body / faq are filled only when empty (an admin edit wins);
- meta_title / meta_description are replaced only when they are empty or still
  exactly the value that was live on 24.11.2026 (several had long dashes);
- only rows found by slug; nothing deleted; reverse is a no-op; errors caught.
"""

import json
from pathlib import Path

from django.db import migrations

DATA = Path(__file__).resolve().parent.parent / "data" / "category_texts_2026_11.json"

OLD_META = {
    "ukrayinski": (
        "Українські килими купити",
        "Українські килими з поліпропілену: прямокутні, овальні, доріжки. Понад 60 моделей, розміри від 50х80 до 200х300 см. Доставка Новою поштою по Україні.",
    ),
    "turetski": (
        "Турецькі килими купити в Україні",
        "Турецькі килими La Rosa, Modern, Craft, Eldora: класичні та сучасні орнаменти, розміри до 200х300 см. Ціни від 450 грн. Доставка Новою поштою.",
    ),
    "dlia-vanni": (
        "Килими для ванної кімнати 60х100",
        "Турецькі килимки для ванної 60х100 см: м'який ворс, антиковзна основа, швидко сохнуть. 12 кольорів від 600 грн. Доставка Новою поштою по Україні.",
    ),
    "pid-dveri": (
        "Килими під двері купити — придверні килимки",
        "Придверні килимки: гумові, напівкруглі, прямокутні від 40х60 до 70х120 см. Не ковзають, затримують бруд. Ціни від 300 грн. Доставка по Україні.",
    ),
    "v-kukhniu": (
        "Килими в кухню купити",
        "Кухонні килими та доріжки з низьким ворсом: легко миються, не ковзають. Розміри 50х100 – 67х140 см, від 400 грн. Доставка Новою поштою.",
    ),
    "v-ditiachu": (
        "Дитячі килими купити — Місто, Пазли, Міккі",
        "Дитячі килими з дорогами, пазлами та героями мультфільмів: м'які, яскраві, безпечні. Розміри 80х150 – 200х300 см. Доставка по Україні.",
    ),
}


def forwards(apps, schema_editor):
    Category = apps.get_model("catalog", "ProductCategory")
    try:
        texts = json.loads(DATA.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        print(f"  [category texts] skipped: {exc}")
        return
    filled = meta = 0
    for slug, t in texts.items():
        try:
            cat = Category.objects.filter(slug=slug).first()
            if cat is None:
                continue
            upd = {}
            if not (cat.intro or "").strip():
                upd["intro"] = t["intro"]
            if not (cat.body or "").strip():
                upd["body"] = t["body"]
            if not cat.faq:
                upd["faq"] = t["faq"]
            old_title, old_desc = OLD_META.get(slug, (None, None))
            if (cat.meta_title or "").strip() in ("", old_title):
                upd["meta_title"] = t["meta_title"]
            if (cat.meta_description or "").strip() in ("", old_desc):
                upd["meta_description"] = t["meta_description"]
            if upd:
                Category.objects.filter(pk=cat.pk).update(**upd)
                filled += any(k in upd for k in ("intro", "body", "faq"))
                meta += "meta_title" in upd or "meta_description" in upd
        except Exception as exc:  # pragma: no cover - defensive
            print(f"  [category texts] {slug}: {exc}")
    print(f"\n  [category texts] texts in {filled}, meta in {meta} of {len(texts)} categories")


class Migration(migrations.Migration):
    dependencies = [("catalog", "0048_category_page_text")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
