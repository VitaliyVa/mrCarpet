#!/usr/bin/env python3
"""Improve stub products ONLY (slug LIKE 'product-%'). Never mutate good rows."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from pathlib import Path

DB = Path("db.candidate.sqlite3")
RECOVER_SQL = Path("/tmp/mrcarpet_recover.sql")
CHECKSUM_BEFORE = Path("/tmp/good_products_checksum_before.json")
CHECKSUM_AFTER = Path("/tmp/good_products_checksum_after.json")
PRODUCT_CT = 13

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


def slugify_ua(text: str) -> str:
    table = str.maketrans(
        {
            "а": "a",
            "б": "b",
            "в": "v",
            "г": "h",
            "ґ": "g",
            "д": "d",
            "е": "e",
            "є": "ie",
            "ж": "zh",
            "з": "z",
            "и": "y",
            "і": "i",
            "ї": "i",
            "й": "i",
            "к": "k",
            "л": "l",
            "м": "m",
            "н": "n",
            "о": "o",
            "п": "p",
            "р": "r",
            "с": "s",
            "т": "t",
            "у": "u",
            "ф": "f",
            "х": "kh",
            "ц": "ts",
            "ч": "ch",
            "ш": "sh",
            "щ": "shch",
            "ь": "",
            "ю": "iu",
            "я": "ia",
            "ы": "y",
            "э": "e",
            "ъ": "",
        }
    )
    s = text.lower().translate(table)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:500] or "product"


def good_checksums(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        """
        SELECT id, title, slug, image, hover_image, description,
               has_discount, is_new, active_color_id, color_group_id,
               ar_status, ar_texture
        FROM catalog_product
        WHERE slug NOT LIKE 'product-%'
        ORDER BY id
        """
    ).fetchall()
    out = {}
    for r in rows:
        payload = "|".join("" if x is None else str(x) for x in r)
        out[str(r[0])] = {
            "row": list(r),
            "sha": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        }
    return out


def mine_product_admin() -> dict[int, dict]:
    data: dict[int, dict] = {}
    with RECOVER_SQL.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if 'INSERT INTO "lost_and_found"' not in line:
                continue
            m = PAT.match(line.strip())
            if not m:
                continue
            parts = split_sql_vals(m.group(1))
            if len(parts) < 8:
                continue
            try:
                n = int(parts[2])
            except ValueError:
                continue
            if n != 8:
                continue
            vals = [unq(x) for x in parts[3:]]
            if len(vals) < 7:
                continue
            ct = vals[6]
            if ct != PRODUCT_CT:
                continue
            try:
                oid = int(vals[2])
            except (TypeError, ValueError):
                continue
            title = vals[3]
            if not isinstance(title, str):
                continue
            bucket = data.setdefault(
                oid, {"titles": [], "mains": [], "hovers": [], "additional": []}
            )
            bucket["titles"].append(title)
            for im in IMG_RE.findall(m.group(1)):
                low = im.lower()
                if "hover" in low or "ховер" in low:
                    bucket["hovers"].append(im)
                elif im.startswith("products/additional/"):
                    bucket["additional"].append(im)
                else:
                    bucket["mains"].append(im)
    return data


def normalize_title(title: str) -> str:
    t = title.strip()
    if t.startswith("Килим"):
        return t
    # short model names from early admin edits
    if t in {"Під двері"} or t.startswith("Mira") or t.startswith("Flex"):
        return f"Килим {t}" if not t.startswith("Килим") else t
    if not t.startswith("Килим"):
        return f"Килим {t}"
    return t


def main() -> None:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    before = good_checksums(conn)
    CHECKSUM_BEFORE.write_text(
        json.dumps(before, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("good products frozen:", len(before))

    stubs = conn.execute(
        """
        SELECT id, title, slug, image, hover_image
        FROM catalog_product
        WHERE slug LIKE 'product-%'
        ORDER BY id
        """
    ).fetchall()
    print("stubs:", [s["id"] for s in stubs])

    admin = mine_product_admin()
    print("product admin ids:", len(admin))

    # Ghost stubs: no Product admin events AND zero attributes -> remove
    ghosts = []
    for s in stubs:
        pid = s["id"]
        attr_n = conn.execute(
            "SELECT COUNT(*) FROM catalog_productattribute WHERE product_id=?",
            (pid,),
        ).fetchone()[0]
        if pid not in admin and attr_n == 0:
            ghosts.append(pid)
    print("ghost stubs to remove:", ghosts)
    for pid in ghosts:
        conn.execute(
            "DELETE FROM catalog_product_categories WHERE product_id=?", (pid,)
        )
        conn.execute("DELETE FROM catalog_product_colors WHERE product_id=?", (pid,))
        conn.execute("DELETE FROM catalog_productimage WHERE product_id=?", (pid,))
        conn.execute(
            "DELETE FROM catalog_product WHERE id=? AND slug LIKE 'product-%'",
            (pid,),
        )
        print("  deleted ghost", pid)

    stubs = conn.execute(
        """
        SELECT id, title, slug, image, hover_image
        FROM catalog_product
        WHERE slug LIKE 'product-%'
        ORDER BY id
        """
    ).fetchall()

    used_slugs = {
        r[0]
        for r in conn.execute(
            "SELECT slug FROM catalog_product WHERE slug NOT LIKE 'product-%'"
        )
    }
    max_img_id = (
        conn.execute("SELECT COALESCE(MAX(id),0) FROM catalog_productimage").fetchone()[
            0
        ]
        or 0
    )

    for s in stubs:
        pid = s["id"]
        info = admin.get(pid, {})
        titles = [t for t in info.get("titles", []) if isinstance(t, str)]
        title = None
        for t in reversed(titles):
            if t.startswith("Килим"):
                title = t
                break
        if title is None and titles:
            title = normalize_title(titles[-1])
        if title is None:
            title = s["title"]
            if title.startswith("Товар #"):
                title = f"Килим (відновлено #{pid})"

        mains = info.get("mains", [])
        hovers = info.get("hovers", [])
        additional = info.get("additional", [])
        # dedupe preserve order
        def uniq(seq):
            seen = set()
            out = []
            for x in seq:
                if x not in seen:
                    seen.add(x)
                    out.append(x)
            return out

        mains, hovers, additional = uniq(mains), uniq(hovers), uniq(additional)

        image = s["image"]
        hover = s["hover_image"] or ""
        if mains:
            image = mains[-1]
        elif additional:
            image = additional[0]
        if hovers:
            hover = hovers[-1]

        slug = slugify_ua(title)
        base = slug
        i = 2
        while slug in used_slugs:
            slug = f"{base}-{i}"
            i += 1
        used_slugs.add(slug)

        cur = conn.execute(
            """
            UPDATE catalog_product
            SET title=?, slug=?, image=?, hover_image=?
            WHERE id=? AND slug LIKE 'product-%'
            """,
            (title, slug, image or "products/default.png", hover or "", pid),
        )
        if cur.rowcount != 1:
            raise SystemExit(f"ABORT: stub update failed id={pid} rowcount={cur.rowcount}")

        # ensure additional images exist (do not delete existing)
        existing = {
            r[0]
            for r in conn.execute(
                "SELECT image FROM catalog_productimage WHERE product_id=?",
                (pid,),
            )
        }
        for j, im in enumerate(additional):
            if im in existing:
                continue
            max_img_id += 1
            conn.execute(
                """
                INSERT INTO catalog_productimage (id, image, alt, product_id, sort_order, is_ai)
                VALUES (?, ?, NULL, ?, ?, 0)
                """,
                (max_img_id, im, pid, (j + 1) * 10),
            )

        print(f"OK stub {pid}: {title!r} | {image[:60]} | {slug}")

    conn.commit()

    after = good_checksums(conn)
    CHECKSUM_AFTER.write_text(
        json.dumps(after, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    bad = [k for k in before if before[k]["sha"] != after.get(k, {}).get("sha")]
    missing = [k for k in before if k not in after]
    if bad or missing:
        raise SystemExit(f"ABORT: good products damaged bad={bad} missing={missing}")

    attrs = conn.execute("SELECT COUNT(*) FROM catalog_productattribute").fetchone()[0]
    prods = conn.execute("SELECT COUNT(*) FROM catalog_product").fetchone()[0]
    stubs_left = conn.execute(
        "SELECT COUNT(*) FROM catalog_product WHERE slug LIKE 'product-%'"
    ).fetchone()[0]
    default_imgs = conn.execute(
        "SELECT id, title FROM catalog_product WHERE image='products/default.png' ORDER BY id"
    ).fetchall()
    print("SAFE: 67 good checksums unchanged")
    print("products", prods, "attrs", attrs, "stubs_left", stubs_left)
    print("default image left:", [dict(r) for r in default_imgs])
    conn.close()


if __name__ == "__main__":
    main()
