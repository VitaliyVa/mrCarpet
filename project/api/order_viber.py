"""Open a Viber chat with the order's buyer from a Telegram button.

Telegram buttons accept only http(s) links, so the bot links here and this
page hands over to viber://. The link carries a signed order id (never the
phone), expires after 30 days and is noindex.
"""

from urllib.parse import quote

from django.http import HttpResponse, HttpResponseNotFound
from django.utils.html import escape
from django.views.decorators.cache import never_cache

from order.customer_contact import normalize_phone, order_from_viber_token

_PAGE = """<!doctype html>
<html lang="uk"><head><meta charset="utf-8">
<meta name="robots" content="noindex, nofollow">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Viber</title>
<style>body{{font-family:system-ui,sans-serif;text-align:center;padding:48px 16px}}
a{{display:inline-block;margin-top:16px;padding:14px 24px;border-radius:10px;
background:#7360f2;color:#fff;text-decoration:none;font-size:18px}}</style>
</head><body>
<p>Відкриваємо Viber для {phone}…</p>
<a href="{url}">Відкрити Viber</a>
<script>location.href={url_js};</script>
</body></html>"""


@never_cache
def order_viber_redirect(request, token):
    order = order_from_viber_token(token)
    digits = normalize_phone(order.phone) if order else ""
    if not digits:
        return HttpResponseNotFound("Посилання застаріло")
    url = f"viber://chat?number={quote('+' + digits)}"
    page = _PAGE.format(
        phone=escape(f"+{digits}"),
        url=escape(url),
        url_js='"' + url.replace('"', "") + '"',
    )
    response = HttpResponse(page)
    response["X-Robots-Tag"] = "noindex, nofollow"
    response["Referrer-Policy"] = "no-referrer"
    return response
