"""
Local long-polling for AI agent.
Do NOT run on prod together with webhook.

  docker compose exec web python manage.py telegram_poll
"""
import time

from django.core.management.base import BaseCommand

from project.models import TelegramSettings
from project.telegram_api import delete_webhook, get_updates
from project.telegram_bot import handle_update


class Command(BaseCommand):
    help = "Long-poll Telegram updates for AI agent (local/dev)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--timeout",
            type=int,
            default=25,
            help="getUpdates long-poll timeout seconds",
        )

    def handle(self, *args, **options):
        settings = TelegramSettings.load()
        if not settings.bot_token.strip():
            self.stderr.write("bot_token empty")
            return
        if not settings.ai_ready:
            self.stdout.write(
                self.style.WARNING(
                    "ai_enabled/chat_id not ready — still polling; enable AI in admin"
                )
            )

        # avoid conflict with leftover webhook
        delete_webhook(drop_pending=False)
        self.stdout.write(self.style.SUCCESS("telegram_poll started (Ctrl+C to stop)"))

        offset = None
        timeout = options["timeout"]
        while True:
            try:
                data = get_updates(offset=offset, timeout=timeout)
                if not data.get("ok"):
                    self.stderr.write(f"getUpdates failed: {data}")
                    time.sleep(3)
                    continue
                for update in data.get("result") or []:
                    uid = update.get("update_id")
                    if uid is not None:
                        offset = uid + 1
                    handle_update(update)
            except KeyboardInterrupt:
                self.stdout.write("stopped")
                return
            except Exception as exc:
                self.stderr.write(f"poll error: {exc}")
                time.sleep(3)
