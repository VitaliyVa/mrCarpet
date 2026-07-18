#!/usr/bin/env python3
"""
Build db.live_ready.sqlite3 carefully:
- Base = local healthy DB (full schema, migrations, NP warehouses)
- Catalog rows = from db.candidate.sqlite3 (recovered products)
- Never invent product field values; copy verbatim from candidate
- Verify checksums of products that were "good" in candidate
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
from pathlib import Path

LOCAL = Path("db.local.ok.sqlite3")
CANDIDATE = Path("db.candidate.sqlite3")
OUT = Path("db.live_ready.sqlite3")
RECOVER_SQL = Path("/tmp/mrcarpet_recover.sql")
GOOD_CHECKSUM = Path("/tmp/good_products_checksum_before.json")

PAT = re.compile(r'INSERT INTO "lost_and_found" VALUES\((.*)\);$')

# Tables fully replaced from candidate when present in both
REPLACE_TABLES = [
    "catalog_product",
    "catalog_productattribute",
    "catalog_productimage",
    "catalog_product_categories",
    "catalog_product_colors",
    "catalog_productspecification",
    "catalog_relatedproduct",
    "catalog_productattribute_width",
    "catalog_productsale",
    "catalog_productsale_products",
    "catalog_favouriteproducts",
    "catalog_size",
    "catalog_productcategory",
    "catalog_productwidth",
    "catalog_productcolor",
    "catalog_colorgroup",
    "catalog_specification",
    "catalog_specificationvalue",
    "catalog_promocode",
]


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


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        is not None
    )


def copy_table(src: sqlite3.Connection, dst: sqlite3.Connection, table: str) -> int:
    if not table_exists(src, table):
        print(f"  skip {table}: missing in candidate")
        return 0
    if not table_exists(dst, table):
        # create from candidate schema
        row = src.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if not row or not row[0]:
            print(f"  skip {table}: no schema")
            return 0
        dst.execute(row[0])
        print(f"  created {table} from candidate schema")

    src_cols = [r[1] for r in src.execute(f"PRAGMA table_info({table})")]
    dst_cols = [r[1] for r in dst.execute(f"PRAGMA table_info({table})")]
    cols = [c for c in src_cols if c in dst_cols]
    if not cols:
        print(f"  skip {table}: no common cols")
        return 0

    dst.execute(f"DELETE FROM {table}")
    col_list = ",".join(f'"{c}"' for c in cols)
    placeholders = ",".join("?" for _ in cols)
    rows = src.execute(f"SELECT {col_list} FROM {table}").fetchall()
    dst.executemany(
        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})", rows
    )
    print(f"  copied {table}: {len(rows)} rows ({len(cols)} cols)")
    return len(rows)


def product_checksums(conn: sqlite3.Connection, ids: list[int] | None = None) -> dict:
    q = """
        SELECT id, title, slug, image, hover_image, description,
               has_discount, is_new, active_color_id, color_group_id,
               ar_status, ar_texture
        FROM catalog_product
    """
    if ids is not None:
        q += " WHERE id IN ({})".format(",".join(str(i) for i in ids))
    q += " ORDER BY id"
    out = {}
    for r in conn.execute(q):
        payload = "|".join("" if x is None else str(x) for x in r)
        out[str(r[0])] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return out


def restore_users(dst: sqlite3.Connection) -> None:
    """Upsert 3 users from recover dump into users_customuser."""
    users = {}
    with RECOVER_SQL.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if 'INSERT INTO "lost_and_found"' not in line or "@" not in line:
                continue
            m = PAT.match(line.strip())
            if not m:
                continue
            parts = split_sql_vals(m.group(1))
            if parts[0] != "103":
                continue
            try:
                n = int(parts[2])
            except Exception:
                continue
            if n != 16:
                continue
            vals = [unq(x) for x in parts[3:]]
            # id, NULL, password, last_login, is_superuser, first, last, is_staff, is_active, date_joined, email, phone, city, settlement_ref, wh, wh_id, wh_ref
            try:
                uid = int(vals[0])
            except Exception:
                continue
            email = vals[10]
            if not isinstance(email, str) or "@" not in email:
                continue
            users[uid] = {
                "id": uid,
                "password": vals[2],
                "last_login": vals[3],
                "is_superuser": int(vals[4] or 0),
                "first_name": vals[5] or "",
                "last_name": vals[6] or "",
                "is_staff": int(vals[7] or 0),
                "is_active": int(vals[8] or 1),
                "date_joined": vals[9],
                "email": email,
                "phone_number": vals[11],
                "delivery_city": vals[12] or "",
                "delivery_settlement_ref": vals[13] or "",
                "delivery_warehouse": vals[14] or "",
                "delivery_warehouse_id": vals[15] or "",
                "delivery_warehouse_ref": vals[16] or "",
            }

    print("users from dump:", list(users))
    for u in users.values():
        exists = dst.execute(
            "SELECT id FROM users_customuser WHERE id=? OR email=?",
            (u["id"], u["email"]),
        ).fetchone()
        if exists:
            dst.execute(
                """
                UPDATE users_customuser SET
                  password=?, last_login=?, is_superuser=?, first_name=?, last_name=?,
                  is_staff=?, is_active=?, date_joined=?, email=?, phone_number=?,
                  delivery_city=?, delivery_settlement_ref=?, delivery_warehouse=?,
                  delivery_warehouse_id=?, delivery_warehouse_ref=?
                WHERE id=?
                """,
                (
                    u["password"],
                    u["last_login"],
                    u["is_superuser"],
                    u["first_name"],
                    u["last_name"],
                    u["is_staff"],
                    u["is_active"],
                    u["date_joined"],
                    u["email"],
                    u["phone_number"],
                    u["delivery_city"],
                    u["delivery_settlement_ref"],
                    u["delivery_warehouse"],
                    u["delivery_warehouse_id"],
                    u["delivery_warehouse_ref"],
                    exists[0],
                ),
            )
            print("  updated user", u["email"])
        else:
            dst.execute(
                """
                INSERT INTO users_customuser (
                  id, password, last_login, is_superuser, first_name, last_name,
                  is_staff, is_active, date_joined, email, phone_number,
                  delivery_city, delivery_settlement_ref, delivery_warehouse,
                  delivery_warehouse_id, delivery_warehouse_ref
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    u["id"],
                    u["password"],
                    u["last_login"],
                    u["is_superuser"],
                    u["first_name"],
                    u["last_name"],
                    u["is_staff"],
                    u["is_active"],
                    u["date_joined"],
                    u["email"],
                    u["phone_number"],
                    u["delivery_city"],
                    u["delivery_settlement_ref"],
                    u["delivery_warehouse"],
                    u["delivery_warehouse_id"],
                    u["delivery_warehouse_ref"],
                ),
            )
            print("  inserted user", u["email"])


def main() -> None:
    if not LOCAL.exists() or not CANDIDATE.exists():
        raise SystemExit("Need db.local.ok.sqlite3 and db.candidate.sqlite3")

    shutil.copy2(LOCAL, OUT)
    src = sqlite3.connect(CANDIDATE)
    dst = sqlite3.connect(OUT)
    dst.execute("PRAGMA foreign_keys=OFF")

    # Freeze expected checksums for originally-good candidate products
    if GOOD_CHECKSUM.exists():
        good_ids = [int(k) for k in json.loads(GOOD_CHECKSUM.read_text(encoding="utf-8"))]
    else:
        good_ids = [
            r[0]
            for r in src.execute(
                "SELECT id FROM catalog_product WHERE slug NOT LIKE 'product-%' ORDER BY id"
            )
        ]
        # after stubs fixed, all non-ghost are good; use checksum file from before stubs for the 67
        good_ids = sorted(good_ids)[:67]  # fallback unsafe — prefer file

    # Prefer exact ids from checksum file
    if GOOD_CHECKSUM.exists():
        good_ids = sorted(int(k) for k in json.loads(GOOD_CHECKSUM.read_text(encoding="utf-8")))

    cand_checks = product_checksums(src, good_ids)
    print("candidate good ids:", len(cand_checks))

    print("Replacing catalog tables from candidate...")
    for t in REPLACE_TABLES:
        copy_table(src, dst, t)

    print("Restoring users from recover dump...")
    restore_users(dst)

    dst.commit()

    live_checks = product_checksums(dst, good_ids)
    bad = [i for i in cand_checks if cand_checks[i] != live_checks.get(i)]
    if bad:
        raise SystemExit(f"ABORT: product checksum mismatch after merge: {bad[:20]}")

    # Sanity
    for label, conn in ("candidate", src), ("live_ready", dst):
        p = conn.execute("SELECT COUNT(*) FROM catalog_product").fetchone()[0]
        a = conn.execute("SELECT COUNT(*) FROM catalog_productattribute").fetchone()[0]
        print(f"{label}: products={p} attrs={a}")

    if dst.execute("SELECT COUNT(*) FROM catalog_product").fetchone()[0] != src.execute(
        "SELECT COUNT(*) FROM catalog_product"
    ).fetchone()[0]:
        raise SystemExit("ABORT: product count mismatch")
    if dst.execute("SELECT COUNT(*) FROM catalog_productattribute").fetchone()[
        0
    ] != src.execute("SELECT COUNT(*) FROM catalog_productattribute").fetchone()[0]:
        raise SystemExit("ABORT: attr count mismatch")

    integrity = dst.execute("PRAGMA integrity_check").fetchone()[0]
    print("integrity", integrity)
    if integrity != "ok":
        raise SystemExit("ABORT: integrity failed")

    users = dst.execute(
        "SELECT id,email,is_staff,is_superuser FROM users_customuser ORDER BY id"
    ).fetchall()
    print("users:", users)
    print("OK wrote", OUT)

    # reset sequences for sqlite autoincrement
    for table in ("catalog_product", "catalog_productattribute", "catalog_productimage"):
        if table_exists(dst, "sqlite_sequence"):
            mx = dst.execute(f"SELECT COALESCE(MAX(id),0) FROM {table}").fetchone()[0]
            exists = dst.execute(
                "SELECT 1 FROM sqlite_sequence WHERE name=?", (table,)
            ).fetchone()
            if exists:
                dst.execute(
                    "UPDATE sqlite_sequence SET seq=? WHERE name=?", (mx, table)
                )
            else:
                dst.execute(
                    "INSERT INTO sqlite_sequence(name,seq) VALUES (?,?)", (table, mx)
                )
    dst.commit()
    src.close()
    dst.close()


if __name__ == "__main__":
    main()
