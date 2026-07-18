"""Send a one-off SMTP test email via SMTPSettings (Brevo :2525 etc.)."""
from django.core.management.base import BaseCommand

from project.email_branding import render_branded_email, with_plain_footer
from project.smtp_utils import get_smtp_connection, send_smtp_mail


class Command(BaseCommand):
    help = "Тестовий лист через SMTPSettings (брендований HTML-шаблон)"

    def add_arguments(self, parser):
        parser.add_argument(
            "email",
            nargs="?",
            default="",
            help="Куди слати тест (default = SMTPSettings.server_email)",
        )

    def handle(self, *args, **options):
        try:
            smtp, conn = get_smtp_connection()
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"SMTPSettings: {exc}"))
            return

        to = (options.get("email") or "").strip() or smtp.server_email
        self.stdout.write(
            f"Host={smtp.host}:{smtp.port} TLS={smtp.use_tls} From={smtp.server_email} → {to}"
        )

        try:
            conn.open()
            self.stdout.write(self.style.SUCCESS("SMTP open OK"))
            conn.close()
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"SMTP open FAILED: {exc}"))
            self.stderr.write(
                "На DigitalOcean Gmail:587 заблокований. "
                "Постав Brevo: host=smtp-relay.brevo.com port=2525 TLS=on."
            )
            return

        html = render_branded_email(
            "emails/smtp_test.html",
            {"smtp_host": smtp.host, "smtp_port": smtp.port},
            eyebrow="Тест доставки",
            preheader="Тестовий брендований лист mr.Carpet",
        )
        plain = with_plain_footer(
            "Тестовий лист з mr.Carpet (HTML-шаблон).\n"
            f"Host: {smtp.host}:{smtp.port}\n"
            "Якщо бачиш це — SMTP працює.\n"
        )
        ok = send_smtp_mail(
            "mr.Carpet — SMTP test",
            plain,
            [to],
            fail_silently=True,
            html_message=html,
        )
        if ok:
            self.stdout.write(self.style.SUCCESS(f"Sent OK → {to}"))
        else:
            self.stderr.write(self.style.ERROR("Send FAILED (див. логи [smtp] FAILED)"))
