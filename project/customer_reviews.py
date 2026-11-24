"""
Google Customer Reviews opt-in on the order success page.

After an order Google can offer the buyer a short survey that it emails once
the parcel should have arrived. The answers become seller ratings (the stars
next to the shop in Shopping ads). The opt-in needs four facts: our Merchant
Center id, the order id, the buyer's email and when the parcel should arrive.

Without an email there is nothing to send the survey to, so the snippet is
not rendered at all. Email stays optional at checkout: asking for it only to
feed this would cost orders.

The order is found through the session, never through the URL: /success/ is
public, and an order id in the query string would let anyone open the opt-in
for someone else's purchase.
"""

from __future__ import annotations

from django.conf import settings
from django.utils import timezone

#: Session key the checkout writes the new order's pk into.
SESSION_KEY = "gcr_order_id"

#: Everything ships inside Ukraine (Нова Пошта).
DELIVERY_COUNTRY = "UA"

#: Days from the order to the survey email. Google sends the survey shortly
#: after this date, so it should be when the rug is surely home, not the
#: earliest it could be.
DELIVERY_DAYS = 5


def remember_order(request, order) -> None:
    """Called by checkout once the order exists."""
    session = getattr(request, "session", None)
    if session is not None and getattr(order, "pk", None):
        session[SESSION_KEY] = order.pk


def _usable_email(order) -> str:
    email = (getattr(order, "email", "") or "").strip()
    # Checkout used to fill a placeholder for buyers without one.
    if not email or "@" not in email or email.endswith("@temp.com"):
        return ""
    return email


def estimated_delivery_date(order) -> str:
    created = getattr(order, "created", None) or timezone.now()
    day = timezone.localdate(created) if timezone.is_aware(created) else created.date()
    return (day + timezone.timedelta(days=DELIVERY_DAYS)).isoformat()


def optin_payload(order) -> dict | None:
    """The object `gapi.surveyoptin.render` takes, or None to render nothing."""
    merchant_id = str(getattr(settings, "GOOGLE_MERCHANT_ID", "") or "").strip()
    if not merchant_id.isdigit() or order is None:
        return None
    email = _usable_email(order)
    if not email:
        return None
    return {
        "merchant_id": int(merchant_id),
        "order_id": str(order.order_number or order.pk),
        "email": email,
        "delivery_country": DELIVERY_COUNTRY,
        "estimated_delivery_date": estimated_delivery_date(order),
    }


def pop_optin(request) -> dict | None:
    """
    Opt-in data for the order this browser just placed, shown once.

    A card payment can land here before the LiqPay callback marks the order
    paid. That order is kept in the session and the opt-in waits for a later
    visit, rather than asking about a purchase that may still fail.
    """
    from order.models import Order
    from project.ga4_ecommerce import order_allows_purchase_event

    session = getattr(request, "session", None)
    if session is None:
        return None
    order_id = session.get(SESSION_KEY)
    if not order_id:
        return None

    order = Order.objects.filter(pk=order_id).first()
    if order is not None and order.status == Order.STATUS_AWAITING_PAYMENT:
        return None

    session.pop(SESSION_KEY, None)
    if not order_allows_purchase_event(order):
        return None
    return optin_payload(order)
