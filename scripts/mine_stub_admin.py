#!/usr/bin/env python3
import re
from collections import defaultdict

path = "/tmp/mrcarpet_recover.sql"
pat = re.compile(r'INSERT INTO "lost_and_found" VALUES\((.*)\);$')
IMG_RE = re.compile(
    r"products/(?:additional/)?[A-Za-z0-9_./%\-]+\.(?:webp|jpg|png|jpeg)"
)

want = {
    5,
    6,
    12,
    13,
    14,
    15,
    16,
    93,
    95,
    96,
    97,
    98,
    99,
    100,
    102,
    104,
    105,
    106,
    107,
    108,
    109,
    110,
    111,
    112,
    113,
    114,
}


def split(raw):
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


def unq(p):
    if p == "NULL":
        return None
    if p.startswith("'") and p.endswith("'"):
        return p[1:-1].replace("''", "'")
    if re.fullmatch(r"-?\d+", p):
        return int(p)
    return p


hits = defaultdict(list)
ct_for_kilim = []
with open(path, encoding="utf-8", errors="replace") as f:
    for line in f:
        if "lost_and_found" not in line:
            continue
        m = pat.match(line.strip())
        if not m:
            continue
        parts = split(m.group(1))
        try:
            n = int(parts[2])
        except Exception:
            continue
        if n != 8:
            continue
        vals = [unq(x) for x in parts[3:]]
        try:
            oid = int(vals[2])
        except Exception:
            continue
        title = vals[3]
        ct = vals[6] if len(vals) > 6 else None
        if isinstance(title, str) and title.startswith("Килим"):
            ct_for_kilim.append(ct)
        if oid not in want:
            continue
        imgs = IMG_RE.findall(m.group(1))
        hits[oid].append(
            {
                "ct": ct,
                "title": title,
                "action": vals[4] if len(vals) > 4 else None,
                "imgs": imgs[:5],
                "time": vals[8] if len(vals) > 8 else None,
            }
        )

from collections import Counter

print("content_type for Килим titles:", Counter(ct_for_kilim).most_common(5))
for oid in sorted(hits):
    print("===", oid, "events", len(hits[oid]))
    for h in hits[oid][-6:]:
        print(" ", h)
