"""
Smoke-test AI agent stack without Telegram message:
  - settings / replicate token
  - one read tool
  - optional LLM JSON plan

  python manage.py telegram_ai_test
  python manage.py telegram_ai_test --llm
"""
from django.conf import settings as django_settings
from django.core.management.base import BaseCommand

from project.models import TelegramSettings
from project.telegram_agent.tools import execute_read_tool


class Command(BaseCommand):
    help = "Smoke-test Telegram AI agent (tools + optional LLM)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--llm",
            action="store_true",
            help="Also call Replicate for a tiny plan",
        )

    def handle(self, *args, **options):
        s = TelegramSettings.load()
        self.stdout.write(f"ai_ready={s.ai_ready} ai_enabled={s.ai_enabled}")
        self.stdout.write(f"chat_id={s.chat_id!r} thread={s.message_thread_id!r}")
        self.stdout.write(f"model={s.replicate_model!r}")
        self.stdout.write(
            f"REPLICATE_API_TOKEN set={bool(django_settings.REPLICATE_API_TOKEN)}"
        )

        result = execute_read_tool("count_orders", {})
        self.stdout.write(f"count_orders → {result}")
        result = execute_read_tool("count_products", {})
        self.stdout.write(f"count_products → {result}")

        if options["llm"]:
            from project.telegram_agent import llm as agent_llm

            model = (s.replicate_model or "meta/meta-llama-3-8b-instruct").strip()
            plan = agent_llm.plan_once(
                model,
                summary="",
                history=[],
                user_text="Скільки зараз замовлень? Використай tool count_orders.",
            )
            self.stdout.write(f"llm plan → {plan}")

        self.stdout.write(self.style.SUCCESS("telegram_ai_test done"))
