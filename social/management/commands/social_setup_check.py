from django.core.management.base import BaseCommand

from social.models import SocialSettings
from social.services import meta, tiktok
from social.services.telegram_products import products_channel_configured
from social.services.tg_isolation import isolation_status


class Command(BaseCommand):
    help = "Check social publishing configuration (Meta / TikTok / TG products)"

    def handle(self, *args, **options):
        self.stdout.write("=== Meta ===")
        for k, v in meta.setup_status().items():
            self.stdout.write(f"  {k}: {v}")

        self.stdout.write("=== TikTok ===")
        for k, v in tiktok.setup_status().items():
            self.stdout.write(f"  {k}: {v}")

        self.stdout.write("=== Telegram products ===")
        social = SocialSettings.load()
        self.stdout.write(f"  channel_configured: {products_channel_configured()}")
        self.stdout.write(f"  channel_id: {social.products_channel_id or '—'}")
        self.stdout.write(
            f"  discussion_id: {social.products_discussion_chat_id or '—'}"
        )
        self.stdout.write(f"  auto_post: {social.auto_post_new_products_tg}")
        self.stdout.write(f"  bot_replies: {social.products_bot_replies}")

        self.stdout.write("=== Telegram chat isolation ===")
        iso = isolation_status()
        self.stdout.write(f"  family_chat_id: {iso['family_chat_id'] or '—'}")
        self.stdout.write(f"  products_channel_id: {iso['products_channel_id'] or '—'}")
        self.stdout.write(
            f"  products_discussion_chat_id: {iso['products_discussion_chat_id'] or '—'}"
        )
        if iso["ok"]:
            self.stdout.write(self.style.SUCCESS("  isolation: OK"))
        else:
            for issue in iso["issues"]:
                self.stdout.write(self.style.ERROR(f"  isolation: {issue}"))

        self.stdout.write(self.style.SUCCESS("Done. See social/README.md for Phase 0."))
