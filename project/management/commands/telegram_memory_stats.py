"""
Show / smoke-test Telegram agent memory caps.

  python manage.py telegram_memory_stats
  python manage.py telegram_memory_stats --fill 50
"""
from django.core.management.base import BaseCommand

from project.models import TelegramSettings
from project.telegram_agent import memory as mem


class Command(BaseCommand):
    help = "Inspect Telegram AI memory window / overflow caps"

    def add_arguments(self, parser):
        parser.add_argument(
            "--fill",
            type=int,
            default=0,
            help="Append N dummy user messages then show stats (tests overflow trim)",
        )

    def handle(self, *args, **options):
        s = TelegramSettings.load()
        chat_id = s.chat_id or "test-chat"
        thread_id = s.message_thread_id or ""
        n = options["fill"]
        if n > 0:
            for i in range(n):
                mem.append_message(chat_id, thread_id, "user", f"dummy memory msg #{i+1}")
            self.stdout.write(f"appended {n} dummy messages")
        stats = mem.memory_stats(chat_id, thread_id)
        for k, v in stats.items():
            self.stdout.write(f"{k}: {v}")
        if stats["db_messages"] > stats["db_keep_limit"]:
            self.stderr.write(self.style.ERROR("DB keep limit broken"))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"OK: prompt uses ≤{stats['window_limit']} turns; "
                    f"DB keeps ≤{stats['db_keep_limit']}; "
                    f"older than {stats['retention_days']}d deleted"
                )
            )
