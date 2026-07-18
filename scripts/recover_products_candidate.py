#!/usr/bin/env python3
"""Rebuild catalog_product / attributes / images from sqlite .recover lost_and_found."""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
from pathlib import Path

RECOVER_SQL = Path("/tmp/mrcarpet_recover.sql")
BASE_DB = Path("db.recovered2.sqlite3")
OUT_DB = Path("db.candidate.sqlite3")
EXPORT_JSON = Path("/tmp/mrcarpet_products_export.json")

PAT = re.compile(r'INSERT INTO "lost_and_found" VALUES\((.*)\);$')
IMG_RE = re.compile(
    r"products/(?:additional/)?[A-Za-z0-9_./%\-]+\.(?:webp|jpg|png|jpeg)"
)


def split_sql_vals(raw: str) -> list[str]:
    parts: list[str] = []
    cur: list[str] = []
    ins = False
    for ch in raw:
        if ch == "'":
            ins = not ins
            cur.append(ch)
        elif ch == "," and not ins:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append("".join(cur).strip())
    return parts


def unq(p: str):
    if p == "NULL":
        return None
    if p.startswith("'") and p.endswith("'"):
        return p[1:-1].replace("''", "'")
    if re.fullmatch(r"-?\d+", p):
        return int(p)
    if re.fullmatch(r"-?\d+\.\d+", p):
        return float(p)
    return p


def main() -> None:
    products: dict[int, dict] = {}
    attrs: list[dict] = []
    images: list[dict] = []
    admin_titles: dict[int, str] = {}

    with RECOVER_SQL.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if 'INSERT INTO "lost_and_found"' not in line:
                continue
            m = PAT.match(line.strip())
            if not m:
                continue
            parts = split_sql_vals(m.group(1))
            if len(parts) < 5:
                continue
            root = parts[0]
            try:
                n = int(parts[2])
            except ValueError:
                continue
            vals = [unq(x) for x in parts[3:]]

            if root == "2665" and n in (18, 19) and isinstance(vals[0], int):
                title_i = None
                for i, v in enumerate(vals):
                    if (
                        isinstance(v, str)
                        and v.startswith("Килим")
                        and i + 1 < len(vals)
                        and isinstance(vals[i + 1], str)
                        and vals[i + 1].startswith("kilim-")
                    ):
                        title_i = i
                        break
                if title_i is None:
                    continue
                pid = vals[0]
                dts = [
                    v
                    for v in vals[1:title_i]
                    if isinstance(v, str) and v.startswith("20")
                ]
                created = dts[0] if dts else None
                updated = dts[1] if len(dts) > 1 else created
                title = vals[title_i]
                slug = vals[title_i + 1]
                desc = vals[title_i + 2]
                image = vals[title_i + 3] if title_i + 3 < len(vals) else None
                has_discount = vals[title_i + 4] if title_i + 4 < len(vals) else 0
                is_new = vals[title_i + 5] if title_i + 5 < len(vals) else 1
                active_color = vals[title_i + 6] if title_i + 6 < len(vals) else None
                hover = vals[title_i + 7] if title_i + 7 < len(vals) else None
                color_group = vals[title_i + 8] if title_i + 8 < len(vals) else None
                ar_texture = vals[title_i + 9] if title_i + 9 < len(vals) else None
                ar_status = vals[title_i + 10] if title_i + 10 < len(vals) else "none"
                ar_error = vals[title_i + 11] if title_i + 11 < len(vals) else ""
                ar_updated = vals[title_i + 12] if title_i + 12 < len(vals) else None
                if not isinstance(image, str):
                    image = "products/default.png"
                if not isinstance(hover, str):
                    hover = ""
                if not isinstance(ar_status, str):
                    ar_status = "none"
                if ar_error is None:
                    ar_error = ""
                products[pid] = {
                    "id": pid,
                    "created": created,
                    "updated": updated,
                    "meta_title": None,
                    "meta_description": None,
                    "meta_keys": None,
                    "title": title,
                    "slug": slug,
                    "description": desc if isinstance(desc, str) else "",
                    "image": image,
                    "has_discount": int(has_discount or 0),
                    "is_new": int(is_new if is_new is not None else 1),
                    "active_color_id": active_color
                    if isinstance(active_color, int)
                    else None,
                    "hover_image": hover,
                    "color_group_id": color_group
                    if isinstance(color_group, int)
                    else None,
                    "ar_texture": ar_texture if isinstance(ar_texture, str) else None,
                    "ar_status": ar_status,
                    "ar_error": ar_error if isinstance(ar_error, str) else "",
                    "ar_updated_at": ar_updated
                    if isinstance(ar_updated, str)
                    else None,
                }

            if root == "4658" and n == 11 and isinstance(vals[0], int):
                aid = vals[0]
                price = vals[2]
                product_id = vals[3]
                size_id = vals[4]
                discount = vals[1] if vals[1] is not None else vals[5]
                quantity = vals[6] if vals[6] is not None else 1
                custom = vals[7] if vals[7] is not None else 0
                max_len = vals[8]
                min_len = vals[9]
                custom_price = vals[10]
                sort_order = (
                    vals[11]
                    if len(vals) > 11 and vals[11] is not None
                    else 0
                )
                if not isinstance(product_id, int) or not isinstance(price, int):
                    continue
                attrs.append(
                    {
                        "id": aid,
                        "price": price,
                        "product_id": product_id,
                        "size_id": size_id if isinstance(size_id, int) else None,
                        "discount": discount if isinstance(discount, int) else None,
                        "quantity": int(quantity),
                        "custom_attribute": int(custom),
                        "max_len": max_len,
                        "min_len": min_len,
                        "custom_price": custom_price,
                        "sort_order": int(sort_order)
                        if isinstance(sort_order, int)
                        else 0,
                    }
                )

            if n == 8 and len(vals) >= 4:
                try:
                    oid = int(vals[2]) if not isinstance(vals[2], int) else vals[2]
                except (TypeError, ValueError):
                    oid = None
                title = vals[3]
                if oid and isinstance(title, str) and title.startswith("Килим"):
                    admin_titles[oid] = title

    print("products", len(products), "attrs", len(attrs), "admin_titles", len(admin_titles))

    conn_r = sqlite3.connect(BASE_DB)
    cat_ids = [
        r[0]
        for r in conn_r.execute(
            "SELECT DISTINCT product_id FROM catalog_product_categories"
        )
    ]
    missing = [pid for pid in cat_ids if pid not in products]
    print("missing product rows", len(missing), missing)

    for pid in missing:
        title = admin_titles.get(pid, f"Товар #{pid}")
        products[pid] = {
            "id": pid,
            "created": None,
            "updated": None,
            "meta_title": None,
            "meta_description": None,
            "meta_keys": None,
            "title": title,
            "slug": f"product-{pid}",
            "description": "",
            "image": "products/default.png",
            "has_discount": 0,
            "is_new": 1,
            "active_color_id": None,
            "hover_image": "",
            "color_group_id": None,
            "ar_texture": None,
            "ar_status": "none",
            "ar_error": "",
            "ar_updated_at": None,
            "_stub": True,
        }

    with RECOVER_SQL.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if "products/" not in line or "lost_and_found" not in line:
                continue
            m = PAT.match(line.strip())
            if not m:
                continue
            parts = split_sql_vals(m.group(1))
            try:
                n = int(parts[2])
            except ValueError:
                continue
            vals = [unq(x) for x in parts[3:]]

            if n == 8 and len(vals) >= 3:
                try:
                    oid = int(vals[2])
                except (TypeError, ValueError):
                    continue
                if oid not in products or not products[oid].get("_stub"):
                    continue
                imgs = IMG_RE.findall(m.group(1))
                main = [i for i in imgs if not i.startswith("products/additional")]
                if main and products[oid]["image"] == "products/default.png":
                    products[oid]["image"] = main[0]
                for j, im in enumerate(
                    [i for i in imgs if i.startswith("products/additional")]
                ):
                    images.append(
                        {
                            "product_id": oid,
                            "image": im,
                            "sort_order": (j + 1) * 10,
                            "is_ai": 0,
                        }
                    )

            if n in (5, 6) and "products/additional/" in line and "[{" not in line:
                img = None
                pid = None
                iid = vals[0] if vals else None
                for v in vals:
                    if isinstance(v, str) and v.startswith("products/additional/"):
                        img = v
                for v in vals[1:]:
                    if isinstance(v, int) and v in products:
                        pid = v
                        break
                if img and pid and isinstance(iid, int):
                    images.append(
                        {
                            "id": iid,
                            "product_id": pid,
                            "image": img,
                            "alt": None,
                            "sort_order": 10,
                            "is_ai": 0,
                        }
                    )

    print("images candidates", len(images))
    print("stub products", sum(1 for p in products.values() if p.get("_stub")))

    export = {
        "products": list(products.values()),
        "attrs": attrs,
        "images": images,
    }
    EXPORT_JSON.write_text(
        json.dumps(export, ensure_ascii=False, indent=0), encoding="utf-8"
    )
    print("wrote", EXPORT_JSON)

    shutil.copy2(BASE_DB, OUT_DB)
    conn = sqlite3.connect(OUT_DB)
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.executescript(
        """
CREATE TABLE IF NOT EXISTS catalog_product (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created datetime NULL,
  updated datetime NULL,
  meta_title TEXT NULL,
  meta_description TEXT NULL,
  meta_keys TEXT NULL,
  title varchar(512) NULL,
  slug varchar(512) NULL,
  description TEXT NULL,
  image varchar(512) NOT NULL,
  has_discount bool NOT NULL,
  is_new bool NOT NULL,
  active_color_id bigint NULL,
  hover_image varchar(512) NOT NULL,
  color_group_id INTEGER NULL,
  ar_texture varchar(100) NULL,
  ar_status varchar(16) NOT NULL,
  ar_error TEXT NOT NULL,
  ar_updated_at datetime NULL
);
CREATE TABLE IF NOT EXISTS catalog_productattribute (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  price INTEGER NULL,
  product_id bigint NULL,
  size_id bigint NULL,
  discount INTEGER NULL,
  quantity smallint unsigned NOT NULL,
  custom_attribute bool NOT NULL,
  max_len decimal NULL,
  min_len decimal NULL,
  custom_price decimal NULL,
  sort_order integer unsigned NOT NULL
);
CREATE TABLE IF NOT EXISTS catalog_productimage (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  image varchar(100) NOT NULL,
  alt varchar(500) NULL,
  product_id bigint NOT NULL,
  sort_order integer unsigned NOT NULL,
  is_ai bool NOT NULL
);
"""
    )
    conn.execute("DELETE FROM catalog_product")
    conn.execute("DELETE FROM catalog_productattribute")
    conn.execute("DELETE FROM catalog_productimage")

    for p in products.values():
        conn.execute(
            """
INSERT INTO catalog_product
(id,created,updated,meta_title,meta_description,meta_keys,title,slug,description,
 image,has_discount,is_new,active_color_id,hover_image,color_group_id,ar_texture,
 ar_status,ar_error,ar_updated_at)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
""",
            (
                p["id"],
                p["created"],
                p["updated"],
                p["meta_title"],
                p["meta_description"],
                p["meta_keys"],
                p["title"],
                p["slug"],
                p["description"],
                p["image"] or "products/default.png",
                p["has_discount"],
                p["is_new"],
                p["active_color_id"],
                p["hover_image"] or "",
                p["color_group_id"],
                p["ar_texture"],
                p["ar_status"] or "none",
                p["ar_error"] or "",
                p["ar_updated_at"],
            ),
        )

    for a in attrs:
        conn.execute(
            """
INSERT INTO catalog_productattribute
(id,price,product_id,size_id,discount,quantity,custom_attribute,max_len,min_len,
 custom_price,sort_order)
VALUES (?,?,?,?,?,?,?,?,?,?,?)
""",
            (
                a["id"],
                a["price"],
                a["product_id"],
                a["size_id"],
                a["discount"],
                a["quantity"],
                a["custom_attribute"],
                a["max_len"],
                a["min_len"],
                a["custom_price"],
                a["sort_order"],
            ),
        )

    seen: set[tuple] = set()
    used_ids: set[int] = set()
    iid = 1
    for im in images:
        key = (im["product_id"], im["image"])
        if key in seen:
            continue
        seen.add(key)
        raw_id = im.get("id")
        if isinstance(raw_id, int) and raw_id not in used_ids:
            img_id = raw_id
        else:
            while iid in used_ids:
                iid += 1
            img_id = iid
            iid += 1
        used_ids.add(img_id)
        conn.execute(
            """
INSERT INTO catalog_productimage (id,image,alt,product_id,sort_order,is_ai)
VALUES (?,?,?,?,?,?)
""",
            (
                img_id,
                im["image"],
                im.get("alt"),
                im["product_id"],
                im.get("sort_order", 10),
                im.get("is_ai", 0),
            ),
        )

    conn.commit()
    print("CANDIDATE COUNTS:")
    for t in [
        "catalog_product",
        "catalog_productattribute",
        "catalog_productimage",
        "catalog_product_categories",
        "catalog_size",
    ]:
        print(t, conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
    print(
        "products with attrs",
        conn.execute(
            "SELECT COUNT(DISTINCT product_id) FROM catalog_productattribute"
        ).fetchone()[0],
    )
    print("integrity", conn.execute("PRAGMA integrity_check").fetchone()[0])
    for r in conn.execute(
        "SELECT id,title,substr(image,1,40),slug FROM catalog_product ORDER BY id LIMIT 8"
    ):
        print(r)
    conn.close()
    conn_r.close()
    print("OK", OUT_DB)


if __name__ == "__main__":
    main()
