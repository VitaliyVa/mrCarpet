"""Check the Buffer connection used to publish the daily video to TikTok.

Run this on prod once BUFFER_API_KEY is set to confirm the key works, the
organization resolves and a TikTok channel is connected — before enabling the
daily post. A blank TikTok channel here is the one setup step that only the
account owner can do (connect @mrcarpet24 in the Buffer app).
"""

from django.core.management.base import BaseCommand

from social.services import buffer


class Command(BaseCommand):
    help = "Show Buffer setup status (API key, organization, connected channels)."

    def handle(self, *args, **options):
        status = buffer.setup_status()

        self.stdout.write(f"api_key_set   : {status.get('api_key_set')}")
        if not status.get("configured"):
            self.stderr.write(self.style.ERROR("BUFFER_API_KEY empty — nothing to check"))
            return

        if status.get("error"):
            self.stderr.write(self.style.ERROR(f"error         : {status['error']}"))
            return

        self.stdout.write(f"organization  : {status.get('organization_id')}")
        self.stdout.write("channels      :")
        for ch in status.get("channels", []):
            self.stdout.write(f"  - {ch.get('service'):12} {ch.get('name')}")

        tiktok_id = status.get("tiktok_channel_id")
        if tiktok_id:
            self.stdout.write(self.style.SUCCESS(f"tiktok channel: {tiktok_id} — ready"))
        else:
            self.stderr.write(
                self.style.ERROR("tiktok channel: none — connect @mrcarpet24 in Buffer")
            )
