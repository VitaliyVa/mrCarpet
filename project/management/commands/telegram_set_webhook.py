"""
Register Telegram webhook (prod).

  python manage.py telegram_set_webhook https://mrcarpet24.com/api/telegram/webhook/
"""
import secrets

from django.core.management.base import BaseCommand

from project.models import TelegramSettings
from project.telegram_api import set_webhook


class Command(BaseCommand):
    help = "setWebhook for Telegram AI agent"

    def add_arguments(self, parser):
        parser.add_argument("url", type=str, help="Public HTTPS webhook URL")
        parser.add_argument(
            "--generate-secret",
            action="store_true",
            help="Generate and save webhook_secret if empty",
        )

    def handle(self, *args, **options):
        settings = TelegramSettings.load()
        if not settings.bot_token.strip():
            self.stderr.write("bot_token empty")
            return

        secret = (settings.webhook_secret or "").strip()
        if options["generate_secret"] and not secret:
            secret = secrets.token_urlsafe(32)
            settings.webhook_secret = secret
            settings.save(update_fields=["webhook_secret"])
            self.stdout.write(f"saved webhook_secret={secret}")

        data = set_webhook(options["url"], secret_token=secret)
        if data.get("ok"):
            self.stdout.write(self.style.SUCCESS(f"webhook set → {options['url']}"))
        else:
            self.stderr.write(str(data))
