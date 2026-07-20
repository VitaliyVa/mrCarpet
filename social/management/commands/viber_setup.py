"""Реєстрація Viber webhook + статус каналу.

Viber блокує Post API (`status: 10, webhookNotSet`), поки webhook не
зареєстрований. Endpoint має бути ЖИВИЙ на проді до виклику --set:
Viber одразу шле на нього валідаційний callback і чекає 200.
"""

import json

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

VIBER_API = "https://chatapi.viber.com/pa"
TIMEOUT = 30

# Мінімум подій: доставку/прочитання не тягнемо, щоб не смітити
EVENT_TYPES = ["failed", "subscribed", "unsubscribed", "conversation_started"]


class Command(BaseCommand):
    help = "Set/check Viber webhook (required for Post API)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--set", action="store_true", help="register webhook URL"
        )
        parser.add_argument(
            "--remove", action="store_true", help="unset webhook (disables Post API)"
        )

    def _post(self, path: str, payload: dict, token: str) -> dict:
        resp = requests.post(
            f"{VIBER_API}/{path}",
            json=payload,
            headers={"X-Viber-Auth-Token": token},
            timeout=TIMEOUT,
        )
        return resp.json() if resp.content else {}

    def handle(self, *args, **options):
        token = (getattr(settings, "VIBER_AUTH_TOKEN", "") or "").strip()
        site = (getattr(settings, "SITE_URL", "") or "").rstrip("/")
        hook_url = f"{site}/api/viber/webhook/"

        self.stdout.write("=== Viber ===")
        self.stdout.write(f"  token set: {bool(token)}")
        self.stdout.write(f"  webhook URL: {hook_url}")
        if not token:
            self.stdout.write(self.style.ERROR("  VIBER_AUTH_TOKEN empty — стоп"))
            return

        if options["remove"]:
            data = self._post("set_webhook", {"url": ""}, token)
            self.stdout.write(f"  remove: {json.dumps(data, ensure_ascii=False)}")
            return

        if options["set"]:
            data = self._post(
                "set_webhook",
                {"url": hook_url, "event_types": EVENT_TYPES, "send_name": True},
                token,
            )
            if data.get("status") == 0:
                self.stdout.write(self.style.SUCCESS(f"  set_webhook OK: {data}"))
            else:
                self.stdout.write(
                    self.style.ERROR(f"  set_webhook FAILED: {data}")
                )
                return

        info = self._post("get_account_info", {}, token)
        if info.get("status") == 0:
            self.stdout.write(f"  channel: {info.get('name')}")
            for member in info.get("members", []):
                if member.get("role") == "superadmin":
                    self.stdout.write(f"  superadmin: {member.get('name')}")
            # get_account_info каналів не повертає поле webhook — стан
            # webhook видно лише за результатом set_webhook / постингу
            self.stdout.write(
                "  (стан webhook Viber не віддає; ознака робочого — "
                "успішний пост без status:10 webhookNotSet)"
            )
        else:
            self.stdout.write(self.style.ERROR(f"  account info failed: {info}"))
