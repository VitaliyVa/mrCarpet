"""Load GA4 credentials from ops/ga4/.env or process env."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OPS_ENV = REPO_ROOT / "ops" / "ga4" / ".env"


def load_dotenv(path: Path = OPS_ENV) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


def credentials_path() -> Path:
    load_dotenv()
    raw = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "ops/ga4/service-account.json")
    path = Path(raw)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def property_id() -> str:
    load_dotenv()
    pid = (os.environ.get("GA4_PROPERTY_ID") or "").strip()
    if not pid or not pid.isdigit():
        raise SystemExit(
            "Set GA4_PROPERTY_ID (digits only) in ops/ga4/.env — "
            "GA4 Admin → Property settings → Property ID"
        )
    return pid


def ensure_credentials() -> Path:
    path = credentials_path()
    if not path.is_file():
        raise SystemExit(
            f"Missing service account JSON: {path}\n"
            "See scripts/ga4/README.md"
        )
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(path)
    return path
