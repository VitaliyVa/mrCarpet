"""
Ask a buyer for a review, once, a few days after the rug arrived.

The delay is the whole design. Asking on delivery day means asking someone
who has not unrolled it yet; asking a month later means asking someone who
has forgotten. A few days in is when the rug is on the floor and the opinion
is formed but still fresh.

Each link carries a signed token so the form knows which order it belongs to.
That buys two things a bare link cannot: the name and email are filled in
already — one less reason to close the tab — and the review can be marked a
verified purchase without asking the customer to prove anything.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.template.loader import render_to_string
from django.utils import timezone

from project.seo_urls import google_review_url

logger = logging.getLogger(__name__)

#: Days after the order became "Виконано". Long enough that the rug has
#: been lived with rather than merely unwrapped.
DELAY_DAYS = 10

#: How long a review link stays usable. Long enough that a reply weeks later
#: still works, short enough that a leaked link is not permanent.
TOKEN_MAX_AGE_DAYS = 90

SALT = "product-review-invite"
SITE = "https://mrcarpet24.com"


def make_token(order) -> str:
    return TimestampSigner(salt=SALT).sign(str(order.pk))


def read_token(token: str):
    """Return the Order the token points at, or None."""
    try:
        raw = TimestampSigner(salt=SALT).unsign(
            token, max_age=TOKEN_MAX_AGE_DAYS * 86400
        )
    except (BadSignature, SignatureExpired):
        return None
    try:
        from order.models import Order

        return Order.objects.filter(pk=int(raw)).first()
    except (TypeError, ValueError):
        return None


def review_url(order, product) -> str:
    """
    Product page with the review modal already open.

    `review=<token>` rather than a bare flag: the page opens the same way
    either way, but a token also says who is writing.
    """
    return f"{SITE}{product.get_absolute_url()}?review={make_token(order)}"


def products_in(order) -> list:
    """Distinct products in the order, in cart order."""
    seen: set[int] = set()
    out = []
    try:
        rows = order.cart.cart_products.select_related(
            "product_attr__product"
        ).all()
    except Exception:
        return out
    for row in rows:
        product = getattr(getattr(row, "product_attr", None), "product", None)
        if product and product.pk not in seen:
            seen.add(product.pk)
            out.append(product)
    return out


def due_orders(*, now=None, delay_days: int = DELAY_DAYS):
    """
    Completed orders old enough to ask about, that we have not asked yet.

    Counted from `completed_at`, not from `updated`. `updated` moves on every
    edit, so correcting a phone number would push the invitation further away
    each time someone touched the order.

    Filtering on `review_request_sent_at` rather than on a date window makes
    this safe to run twice in a day and safe to run after a week of downtime:
    it asks about the backlog once, not once per missed day.
    """
    from order.models import Order

    now = now or timezone.now()
    return (
        Order.objects.filter(
            status=Order.STATUS_COMPLETED,
            review_request_sent_at__isnull=True,
            completed_at__isnull=False,
            completed_at__lte=now - timezone.timedelta(days=delay_days),
        )
        .exclude(email="")
        # Placeholder addresses never reach anyone. They go to the staff
        # route below instead of coming due, and failing, every single day.
        .exclude(email__iendswith="@temp.com")
        .select_related("cart")
    )


#: Past this, a nudge to message the buyer by hand comes out of the blue for
#: both sides, and the link's token is closer to expiring. Also stops the
#: first run from flooding the staff chat with every old phone-only order.
STAFF_NUDGE_MAX_AGE_DAYS = 45


def due_orders_without_email(*, now=None, delay_days: int = DELAY_DAYS):
    """
    The same orders as `due_orders`, but the ones a letter cannot reach.

    There is no customer channel besides email in this code (no SMS, and a
    Telegram bot cannot write first to a phone number), so these go to the
    staff chat as a ready message to forward in Viber or Telegram by hand.
    """
    from django.db.models import Q

    from order.models import Order

    now = now or timezone.now()
    return (
        Order.objects.filter(
            status=Order.STATUS_COMPLETED,
            review_request_sent_at__isnull=True,
            completed_at__isnull=False,
            completed_at__lte=now - timezone.timedelta(days=delay_days),
            completed_at__gte=now - timezone.timedelta(days=STAFF_NUDGE_MAX_AGE_DAYS),
        )
        .filter(Q(email="") | Q(email__iendswith="@temp.com"))
        .select_related("cart")
    )


def build_staff_nudge(order) -> str | None:
    """Staff chat text with the buyer's phone and a message ready to forward."""
    products = products_in(order)
    if not products:
        return None
    items = [
        {"title": p.title, "url": review_url(order, p)} for p in products[:4]
    ]
    return render_to_string(
        "emails/review_request_messenger.txt",
        {
            "order": order,
            "customer": f"{order.name or ''} {order.surname or ''}".strip(),
            "phone": (order.phone or "").strip(),
            "items": items,
            "google_review_url": google_review_url(),
        },
    ).strip()


def ask_staff_for(order) -> bool:
    """
    Hand a phone-only order to staff so they can ask for the review by hand.

    Marked only when the staff chat accepted the message: a failed send costs
    nothing to retry, since the buyer is not contacted by this step. With no
    phone and no items there is nothing anyone can do, so it is marked and
    dropped.
    """
    text = build_staff_nudge(order) if (order.phone or "").strip() else None
    if not text:
        type(order).objects.filter(pk=order.pk).update(
            review_request_sent_at=timezone.now()
        )
        return False

    from social.services.comment_notify import notify_staff_text

    result = notify_staff_text(text) or {}
    if not result.get("ok"):
        return False
    type(order).objects.filter(pk=order.pk).update(
        review_request_sent_at=timezone.now()
    )
    return True


def ask_staff_due(*, limit: int = 20, now=None) -> int:
    asked = 0
    for order in due_orders_without_email(now=now)[:limit]:
        try:
            if ask_staff_for(order):
                asked += 1
        except Exception:
            logger.exception("staff review nudge failed for order %s", order.pk)
    return asked


def build_email(order) -> tuple[str, str, str] | None:
    products = products_in(order)
    if not products:
        return None

    items = [
        {"title": p.title, "url": review_url(order, p), "product": p}
        for p in products[:4]
    ]
    context = {
        "order": order,
        "name": (order.name or "").strip(),
        "items": items,
        "site": SITE,
        "google_review_url": google_review_url(),
    }
    subject = "Як вам килим? Поділіться враженням"
    html = render_to_string("emails/review_request.html", context)
    text = render_to_string("emails/review_request.txt", context)
    return subject, text, html


def send_for(order) -> bool:
    """
    Send one invitation. Marks the order before sending, not after.

    A crash between "sent" and "recorded" would ask the same person again on
    the next run, and a shop that nags is worse than one that never asks.
    Losing an invitation is the cheaper failure.
    """
    from project.smtp_utils import send_smtp_mail

    email = (order.email or "").strip()
    if not email or email.endswith("@temp.com"):
        return False

    built = build_email(order)
    if not built:
        # The order's cart has no rows, so there is nothing to link to. Marked
        # anyway: left unmarked it would come due again every single day and
        # log into the void. Staff are told once, because an order whose
        # contents cannot be found is worth a human look — the only real order
        # on record when this was written had exactly this shape, and whether
        # that is a data artefact or a live bug is not yet known.
        type(order).objects.filter(pk=order.pk).update(
            review_request_sent_at=timezone.now()
        )
        logger.warning("review request skipped for order %s: cart is empty", order.pk)
        try:
            from social.services.comment_notify import notify_staff_text

            notify_staff_text(
                f"⚠️ Замовлення №{order.order_number} — не вдалось зібрати склад "
                f"для листа про відгук: кошик порожній. Лист не пішов."
            )
        except Exception:
            pass
        return False

    type(order).objects.filter(pk=order.pk).update(
        review_request_sent_at=timezone.now()
    )

    subject, text, html = built
    return bool(
        send_smtp_mail(subject, text, [email], fail_silently=True, html_message=html)
    )


def send_due(*, limit: int = 50, now=None) -> int:
    sent = 0
    for order in due_orders(now=now)[:limit]:
        try:
            if send_for(order):
                sent += 1
        except Exception:
            logger.exception("review request failed for order %s", order.pk)
    return sent
