"""Підписка Meta webhooks на коменти + статус.

FB (page/feed): підписуємо сторінку на власний app — цією командою.
IG (instagram/comments): підписка робиться на РІВНІ APP у dashboard
(Webhooks → Instagram → comments) або через POST /{app_id}/subscriptions
з app token (потрібен META_APP_SECRET) — команда підкаже стан.
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from social.services.meta import MetaPublishError, _graph, _page_id


class Command(BaseCommand):
    help = "Subscribe FB page to app webhooks (feed) and show comments-mirror status"

    def add_arguments(self, parser):
        parser.add_argument(
            "--subscribe",
            action="store_true",
            help="POST /{page_id}/subscribed_apps subscribed_fields=feed",
        )

    def handle(self, *args, **options):
        page_id = _page_id()
        verify = (
            getattr(settings, "META_WEBHOOK_VERIFY_TOKEN", "") or ""
        ).strip()
        app_secret = (getattr(settings, "META_APP_SECRET", "") or "").strip()
        site = (getattr(settings, "SITE_URL", "") or "").rstrip("/")

        self.stdout.write("=== Meta comments mirror ===")
        self.stdout.write(f"  webhook URL: {site}/api/meta/webhook/")
        self.stdout.write(f"  verify_token set: {bool(verify)}")
        self.stdout.write(
            f"  app_secret set: {bool(app_secret)} "
            f"{'' if app_secret else '(підпис подій НЕ перевіряється)'}"
        )

        if not page_id:
            self.stdout.write(self.style.ERROR("META_PAGE_ID empty — стоп"))
            return

        if options["subscribe"]:
            try:
                resp = _graph(
                    "POST",
                    f"{page_id}/subscribed_apps",
                    data={"subscribed_fields": "feed"},
                )
                self.stdout.write(
                    self.style.SUCCESS(f"  page subscribe: {resp}")
                )
            except MetaPublishError as exc:
                self.stdout.write(self.style.ERROR(f"  page subscribe failed: {exc}"))

        try:
            resp = _graph("GET", f"{page_id}/subscribed_apps")
            apps = resp.get("data") or []
            if apps:
                for app in apps:
                    self.stdout.write(
                        "  subscribed app: "
                        f"{app.get('name')} fields={app.get('subscribed_fields')}"
                    )
            else:
                self.stdout.write(
                    "  page has NO subscribed apps — run with --subscribe"
                )
        except MetaPublishError as exc:
            self.stdout.write(self.style.ERROR(f"  subscribed_apps check failed: {exc}"))

        self.stdout.write(
            "\nIG comments: App Dashboard → Webhooks → Instagram → "
            "subscribe field `comments` (callback URL і verify token вище). "
            "Для API-way потрібен META_APP_SECRET."
        )
