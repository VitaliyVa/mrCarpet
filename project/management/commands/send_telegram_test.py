"""
Smoke-тест Telegram: python manage.py send_telegram_test
Потрібні заповнені TelegramSettings в адмінці (token, chat_id, увімкнено).
"""
from django.core.management.base import BaseCommand

from project.telegram_utils import send_telegram_message


class Command(BaseCommand):
    help = "Надіслати тестове повідомлення в налаштований Telegram chat"

    def handle(self, *args, **options):
        ok = send_telegram_message(
            "✅ mr.Carpet: тестове повідомлення з Django. Telegram підключено.",
            fail_silently=False,
        )
        if ok:
            self.stdout.write(self.style.SUCCESS("Надіслано OK"))
        else:
            self.stdout.write(
                self.style.ERROR(
                    "Не надіслано. Перевір TelegramSettings: увімкнено, token, chat_id."
                )
            )
