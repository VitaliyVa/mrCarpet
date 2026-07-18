#!/usr/bin/env python3
import re
import sqlite3

c = sqlite3.connect("db.candidate.sqlite3")
print(
    "users_customuser exists?",
    c.execute(
        "SELECT name FROM sqlite_master WHERE name='users_customuser'"
    ).fetchone(),
)
print(
    "user-ish tables",
    [
        r[0]
        for r in c.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE '%user%'"
        )
    ],
)

path = "/tmp/mrcarpet_recover.sql"
pat = re.compile(r'INSERT INTO "lost_and_found" VALUES\((.*)\);$')


def split_sql_vals(raw: str):
    parts = []
    cur = []
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


emails = []
with open(path, encoding="utf-8", errors="replace") as f:
    for line in f:
        if "lost_and_found" not in line or "INSERT" not in line:
            continue
        if "@" not in line:
            continue
        m = pat.match(line.strip())
        if not m:
            continue
        parts = split_sql_vals(m.group(1))
        try:
            n = int(parts[2])
            root = parts[0]
        except Exception:
            continue
        if n >= 10:
            emails.append((root, n, parts[3:20]))

print("email-ish rows", len(emails))
for e in emails[:15]:
    print(e[0], e[1], e[2])
