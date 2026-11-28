import hashlib
import uuid
from decimal import Decimal

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from order.models import Order

from .models import AssistantSettings, Conversation, Message
from .service import messages_last_hour, run_turn, serialize_message, spent_today

MAX_MESSAGE_CHARS = 500
COOLDOWN_SECONDS = 60 * 10
# One conversation is one shopping trip. Past these the bot is being used for
# something else (or burned on purpose): ask to start over or call.
MAX_TURNS_PER_CONVERSATION = 40
MAX_COST_PER_CONVERSATION = Decimal("0.15")


def client_ip(request) -> str:
    # X-Real-IP is set by our nginx from the TCP peer. X-Forwarded-For is not
    # used: its first entry is whatever the visitor sent, so a spammer could
    # rotate it to dodge the limits.
    real = (request.META.get("HTTP_X_REAL_IP") or "").strip()
    if real:
        return real
    return request.META.get("REMOTE_ADDR") or ""


def _client_hash(request) -> str:
    ip = client_ip(request)
    return hashlib.sha256(f"mrcarpet-assistant:{ip}".encode()).hexdigest()[:32]


def _session_key(request) -> str:
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key or ""


def _own_conversation(request, raw_id):
    """A conversation is readable only from the browser session that started it."""
    try:
        conv_id = uuid.UUID(str(raw_id))
    except (TypeError, ValueError):
        return None
    session_key = request.session.session_key
    if not session_key:
        return None
    return Conversation.objects.filter(pk=conv_id, session_key=session_key).first()


def _too_many(retry_after: int, text: str):
    response = Response(
        {"error": text, "retry_after": retry_after},
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )
    response["Retry-After"] = str(retry_after)
    return response


def _state(conversation) -> dict:
    return {
        "conversation_id": str(conversation.pk),
        "pending_token": (conversation.pending_order or {}).get("token"),
        "order_number": conversation.order.order_number if conversation.order_id else None,
    }


class _SessionAPIView(APIView):
    # Same-origin widget on the shop's own session. No DRF auth classes, so a
    # guest is not asked for a CSRF token it may not have yet; nothing here
    # acts for a logged-in account beyond that browser's own cart.
    authentication_classes = []
    permission_classes = []


class AssistantMessageView(_SessionAPIView):
    def post(self, request):
        settings = AssistantSettings.load()
        if not settings.is_live:
            return Response(
                {"error": "Чат зараз вимкнений."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        text = str(request.data.get("message") or "").strip()
        if not text:
            return Response({"error": "Напишіть повідомлення."}, status=status.HTTP_400_BAD_REQUEST)
        text = text[:MAX_MESSAGE_CHARS]

        client_hash = _client_hash(request)
        mine = Conversation.objects.filter(client_hash=client_hash).values("pk")
        if messages_last_hour(mine) >= settings.messages_per_hour:
            return _too_many(
                COOLDOWN_SECONDS,
                "Забагато повідомлень. Спробуйте трохи пізніше або подзвоніть нам.",
            )
        if spent_today() >= settings.daily_budget_usd:
            return _too_many(
                COOLDOWN_SECONDS,
                "Чат зараз перевантажений. Подзвоніть нам: +380 96 398 88 75.",
            )

        session_key = _session_key(request)
        conversation = None
        if request.data.get("conversation_id"):
            conversation = _own_conversation(request, request.data.get("conversation_id"))
        if conversation is None:
            conversation = Conversation.objects.create(session_key=session_key, client_hash=client_hash)
        elif (
            conversation.messages.filter(role=Message.ROLE_USER).count() >= MAX_TURNS_PER_CONVERSATION
            or conversation.cost_usd >= MAX_COST_PER_CONVERSATION
        ):
            return _too_many(
                60,
                "Ця розмова вже задовга. Почніть нову (кнопка «Нова») або подзвоніть нам: +380 96 398 88 75.",
            )

        # The Django request: its user comes from AuthenticationMiddleware, so a
        # logged-in buyer gets the cart of their account, as on the site.
        page = request.data.get("page") if isinstance(request.data.get("page"), dict) else None
        reply = run_turn(request._request, conversation, text, settings=settings, page=page)
        conversation.refresh_from_db()
        return Response({**_state(conversation), "message": reply})


class AssistantConversationView(_SessionAPIView):
    def get(self, request, conversation_id):
        conversation = _own_conversation(request, conversation_id)
        if conversation is None:
            return Response({"error": "Розмову не знайдено."}, status=status.HTTP_404_NOT_FOUND)
        return Response(
            {
                **_state(conversation),
                "messages": [serialize_message(m) for m in conversation.messages.all()[:200]],
            }
        )


class AssistantOrderPlacedView(_SessionAPIView):
    """The widget created the order through /api/create-order/ on the buyer's
    click; link it to the conversation and close the card."""

    def post(self, request, conversation_id):
        conversation = _own_conversation(request, conversation_id)
        if conversation is None:
            return Response({"error": "Розмову не знайдено."}, status=status.HTTP_404_NOT_FOUND)
        pending = conversation.pending_order or {}
        token = str(request.data.get("token") or "")
        if not token or token != pending.get("token"):
            return Response({"error": "Картка застаріла."}, status=status.HTTP_409_CONFLICT)
        try:
            number = int(request.data.get("order_number"))
        except (TypeError, ValueError):
            return Response({"error": "Немає номера замовлення."}, status=status.HTTP_400_BAD_REQUEST)
        order = Order.objects.filter(order_number=number, phone=pending.get("phone")).first()
        if order is None:
            return Response({"error": "Замовлення не знайдено."}, status=status.HTTP_404_NOT_FOUND)

        if order.payment_type == Order.PAYMENT_LIQPAY:
            text = f"Замовлення №{order.order_number} створено. Зараз відкриється сторінка оплати карткою."
        else:
            text = (
                f"Дякуємо! Замовлення №{order.order_number} оформлено. Ми зателефонуємо, "
                "щоб підтвердити, і відправимо Новою Поштою."
            )
        history = list(conversation.api_messages or [])
        # Tell the model what happened, so it does not offer the card again.
        history.append(
            {
                "role": "user",
                "content": f"[Система] Покупець натиснув «Підтвердити». Замовлення №{order.order_number} створено.",
            }
        )
        history.append({"role": "assistant", "content": [{"type": "text", "text": text}]})
        conversation.api_messages = history
        conversation.order = order
        conversation.pending_order = {}
        conversation.save()
        message = Message.objects.create(conversation=conversation, role=Message.ROLE_ASSISTANT, content=text)
        return Response({**_state(conversation), "message": serialize_message(message)})


class AssistantConfigView(_SessionAPIView):
    """Category tiles for the «Підібрати килим» picker (cached 10 min)."""

    def get(self, request):
        from django.core.cache import cache

        data = cache.get("assistant:config:v1")
        if data is None:
            from django.db.models import Count

            from catalog.models import ProductCategory
            from catalog.thumbnails import thumbnail_url

            categories = []
            for cat in ProductCategory.objects.annotate(_n=Count("products")).filter(_n__gt=0).order_by("pk"):
                try:
                    image = thumbnail_url(cat.image, 240) if cat.image else ""
                except Exception:
                    image = ""
                categories.append({"id": cat.pk, "title": cat.title, "image": image, "url": cat.get_absolute_url()})
            data = {"categories": categories}
            cache.set("assistant:config:v1", data, 600)
        response = Response(data)
        response["Cache-Control"] = "public, max-age=600"
        return response


class AssistantCartView(_SessionAPIView):
    """The chat's own cart panel: the same session cart as the site.

    GET: items with photo, size and price. POST {action: add|remove, size_id,
    quantity?}: a size chip or the × in the panel, done at once without the model.
    """

    def get(self, request):
        return Response(cart_payload(request._request))

    def post(self, request):
        from .tools import ToolContext, add_to_cart, remove_from_cart

        action = request.data.get("action")
        try:
            size_id = int(request.data.get("size_id"))
        except (TypeError, ValueError):
            return Response({"error": "Немає розміру."}, status=status.HTTP_400_BAD_REQUEST)
        ctx = ToolContext(request._request, conversation=None)
        if action == "add":
            result = add_to_cart(ctx, size_id, request.data.get("quantity") or 1)
        elif action == "remove":
            result = remove_from_cart(ctx, size_id)
        else:
            return Response({"error": "Невідома дія."}, status=status.HTTP_400_BAD_REQUEST)
        if "error" in result:
            return Response({**cart_payload(request._request), "error": result["error"]}, status=status.HTTP_400_BAD_REQUEST)
        return Response({**cart_payload(request._request), "added": result.get("added"), "cart_events": ctx.cart_events})


def cart_payload(request) -> dict:
    from cart.utils import get_cart_readonly
    from project.free_shipping import free_shipping_for_total

    from .tools import _abs_image

    cart = get_cart_readonly(request)
    items = []
    if cart:
        rows = cart.cart_products.select_related("product_attr__product", "product_attr__size").prefetch_related(
            "product_attr__product__images"
        )
        for cp in rows:
            attr = cp.product_attr
            product = attr.product
            items.append(
                {
                    "size_id": attr.pk,
                    "title": product.title if product else "",
                    "url": product.get_absolute_url() if product else "",
                    "image": _abs_image(product) if product else "",
                    "size": attr.size.title if attr.size else (f"{cp.length} м" if cp.length else ""),
                    "quantity": cp.quantity,
                    "line_total": cp.cart_product_total_price(),
                }
            )
    total = cart.get_total_price() if items else 0
    fs = free_shipping_for_total(total)
    return {
        "items": items,
        "count": sum(i["quantity"] for i in items),
        "total": total,
        "free_delivery": fs["qualifies"],
        "to_free_delivery": fs["remaining"] if fs["enabled"] else 0,
    }
