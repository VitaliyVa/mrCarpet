"""Site chat bot: tools, the agent loop with a fake Claude client, the API,
and an order placed from the chat card through /api/create-order/."""

from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TestCase

from assistant.models import AssistantSettings, Conversation, Message
from assistant.tools import ToolContext, normalize_phone, run_tool
from cart.models import CartProduct
from catalog.models import Product, ProductAttribute, Size
from nova_poshta.models import Settlement, Warehouse, WarehouseType
from order.models import Order


def _usage():
    return SimpleNamespace(input_tokens=1000, output_tokens=100, cache_read_input_tokens=0, cache_creation_input_tokens=0)


def _text(text):
    return SimpleNamespace(type="text", text=text, model_dump=lambda **kw: {"type": "text", "text": text})


def _tool(tool_id, name, args):
    data = {"type": "tool_use", "id": tool_id, "name": name, "input": args}
    return SimpleNamespace(type="tool_use", id=tool_id, name=name, input=args, model_dump=lambda **kw: data)


def _response(blocks, stop="end_turn"):
    return SimpleNamespace(content=blocks, stop_reason=stop, usage=_usage())


class FakeClient:
    """Replays scripted Messages API responses and records the requests."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


class CatalogMixin:
    @classmethod
    def setUpTestData(cls):
        size = Size.objects.create(title="2.0х3.0")
        cls.product = Product.objects.create(title="Килим прямокутний сірий Mira", slug="mira-grey")
        cls.attr = ProductAttribute.objects.create(product=cls.product, size=size, price=3200, quantity=2)
        cls.city = Settlement.objects.create(title="Тернопіль")
        cls.warehouse = Warehouse.objects.create(
            title="Відділення №12 (до 30 кг): вул. Чайковського, 40",
            short_address="вул. Чайковського, 40",
            settlement=cls.city,
        )
        postomat_type = WarehouseType.objects.create(title="Поштомат")
        cls.postomat = Warehouse.objects.create(
            title="Поштомат №5001: вул. Руська, 1", short_address="вул. Руська, 1",
            settlement=cls.city, type=postomat_type,
        )

    def make_request(self):
        request = RequestFactory().get("/")
        request.session = SessionStore()
        request.user = AnonymousUser()
        return request


class ToolsTests(CatalogMixin, TestCase):
    def setUp(self):
        self.request = self.make_request()
        self.conv = Conversation.objects.create()
        self.ctx = ToolContext(self.request, self.conv)

    def test_search_returns_prices_from_the_database(self):
        result, error = run_tool(self.ctx, "search_products", {"query": "сірий 200x300"})
        self.assertFalse(error)
        self.assertEqual(result["products"][0]["sizes"][0], {
            "size_id": self.attr.pk, "size": "2.0х3.0", "price": 3200, "old_price": None,
        })
        self.assertIn(self.product.pk, self.ctx.products)

    def test_search_keeps_best_partial_match(self):
        result, _ = run_tool(self.ctx, "search_products", {"query": "сірий килим для вітальні"})
        self.assertEqual(result["found"], 1)

    def test_add_to_cart_checks_stock(self):
        result, error = run_tool(self.ctx, "add_to_cart", {"size_id": self.attr.pk, "quantity": 3})
        self.assertTrue(error)
        result, error = run_tool(self.ctx, "add_to_cart", {"size_id": self.attr.pk, "quantity": 2})
        self.assertFalse(error)
        self.assertEqual(result["cart"]["total"], 6400)
        self.assertEqual(CartProduct.objects.get().quantity, 2)
        self.assertEqual(self.ctx.cart_events[0]["item"]["item_id"], f"{self.product.pk}-{self.attr.pk}")

    def test_warehouses_skip_postomats(self):
        result, _ = run_tool(self.ctx, "find_warehouse", {"city_id": self.city.pk})
        self.assertEqual([w["warehouse_id"] for w in result["warehouses"]], [self.warehouse.pk])
        result, _ = run_tool(self.ctx, "find_warehouse", {"city_id": self.city.pk, "query": "12"})
        self.assertEqual(result["total"], 1)

    def test_find_city_ignores_case(self):
        result, _ = run_tool(self.ctx, "find_city", {"name": "тернопіль"})
        self.assertEqual(result["cities"][0]["city_id"], self.city.pk)

    def test_prepare_order_needs_cart_and_valid_data(self):
        args = {"full_name": "Іван Петренко", "phone": "096 123 45 67", "city_id": self.city.pk,
                "warehouse_id": self.warehouse.pk, "payment": "cash"}
        result, error = run_tool(self.ctx, "prepare_order", args)
        self.assertTrue(error)  # empty cart
        run_tool(self.ctx, "add_to_cart", {"size_id": self.attr.pk})
        result, error = run_tool(self.ctx, "prepare_order", {**args, "phone": "123"})
        self.assertTrue(error)
        result, error = run_tool(self.ctx, "prepare_order", {**args, "warehouse_id": self.postomat.pk})
        self.assertTrue(error)
        result, error = run_tool(self.ctx, "prepare_order", {**args, "full_name": "Іван"})
        self.assertTrue(error)
        result, error = run_tool(self.ctx, "prepare_order", args)
        self.assertFalse(error)
        draft = Conversation.objects.get(pk=self.conv.pk).pending_order
        self.assertEqual(draft["phone"], "+380961234567")
        self.assertEqual(draft["address"], self.warehouse.title)
        self.assertEqual(draft["total"], 3200)
        self.assertFalse(Order.objects.exists())  # a card, never an order

    def test_normalize_phone(self):
        self.assertEqual(normalize_phone("+38 (096) 123-45-67"), "+380961234567")
        self.assertEqual(normalize_phone("961234567"), "+380961234567")
        self.assertIsNone(normalize_phone("12345"))


class ApiTests(CatalogMixin, TestCase):
    def setUp(self):
        self.settings_obj = AssistantSettings.load()
        self.settings_obj.enabled = True
        self.settings_obj.api_key = "sk-ant-test"
        self.settings_obj.save()

    def _post(self, text, conversation_id=None):
        body = {"message": text}
        if conversation_id:
            body["conversation_id"] = conversation_id
        return self.client.post("/api/assistant/message/", body, content_type="application/json")

    def test_disabled_bot_answers_503_and_hides_widget(self):
        self.settings_obj.enabled = False
        self.settings_obj.save()
        self.assertEqual(self._post("привіт").status_code, 503)
        page = self.client.get("/delivery/")
        self.assertNotContains(page, "pages/assistant/index.js")

    def test_widget_loads_when_live(self):
        page = self.client.get("/delivery/")
        self.assertContains(page, "pages/assistant/index.js")

    def test_full_chat_order_flow(self):
        fake = FakeClient([
            _response([_tool("t1", "search_products", {"query": "сірий"})], stop="tool_use"),
            _response([_text("Ось сірий [килим Mira](/catalog/product/mira-grey/), 3200 грн.")]),
            _response([_tool("t2", "add_to_cart", {"size_id": self.attr.pk})], stop="tool_use"),
            _response([_tool("t3", "find_city", {"name": "Тернопіль"})], stop="tool_use"),
            _response([_tool("t4", "prepare_order", {
                "full_name": "Іван Петренко", "phone": "0961234567", "city_id": self.city.pk,
                "warehouse_id": self.warehouse.pk, "payment": "cash", "comment": "дзвоніть після 18",
            })], stop="tool_use"),
            _response([_text("Перевірте дані і натисніть «Підтвердити».")]),
        ])
        with mock.patch("assistant.service._client", return_value=fake):
            first = self._post("хочу сірий килим").json()
            conv_id = first["conversation_id"]
            self.assertEqual(first["message"]["products"][0]["id"], self.product.pk)
            self.assertIn("Mira", first["message"]["content"])
            second = self._post("беру, Іван Петренко 0961234567 Тернопіль 12, оплата при отриманні", conv_id).json()

        # The model gets our tools, low effort, and the whole history each time.
        self.assertEqual(fake.calls[0]["output_config"], {"effort": "low"})
        self.assertEqual(fake.calls[2]["messages"][0]["content"], "хочу сірий килим")
        order_card = second["message"]["order"]
        self.assertTrue(second["message"]["cart_changed"])
        self.assertEqual(second["pending_token"], order_card["token"])
        self.assertFalse(Order.objects.exists())

        # The buyer clicks «Підтвердити»: the widget posts the card to the checkout API.
        created = self.client.post("/api/create-order/", {
            "name": order_card["name"], "surname": order_card["surname"], "email": "",
            "phone": order_card["phone"], "city": order_card["city"], "address": order_card["address"],
            "payment_type": order_card["payment_type"],
            "message": f"Оформлено через чат-бот. {order_card['comment']}",
        }, content_type="application/json")
        self.assertEqual(created.status_code, 201, created.content)
        order = Order.objects.get()
        self.assertEqual(order.total_price, 3200)
        self.assertEqual(order.source, Order.SOURCE_SITE)
        self.assertTrue(order.message.startswith("Оформлено через чат-бот."))

        placed = self.client.post(
            f"/api/assistant/conversations/{conv_id}/order-placed/",
            {"token": order_card["token"], "order_number": created.json()["order_number"]},
            content_type="application/json",
        )
        self.assertEqual(placed.status_code, 200)
        conv = Conversation.objects.get(pk=conv_id)
        self.assertEqual(conv.order, order)
        self.assertEqual(conv.pending_order, {})
        self.assertGreater(conv.cost_usd, 0)
        # The same card cannot be reused.
        again = self.client.post(
            f"/api/assistant/conversations/{conv_id}/order-placed/",
            {"token": order_card["token"], "order_number": order.order_number},
            content_type="application/json",
        )
        self.assertEqual(again.status_code, 409)

        history = self.client.get(f"/api/assistant/conversations/{conv_id}/").json()
        self.assertEqual(history["order_number"], order.order_number)
        self.assertEqual(history["messages"][0]["content"], "хочу сірий килим")

    def test_conversation_is_private_to_its_session(self):
        fake = FakeClient([_response([_text("Привіт!")])])
        with mock.patch("assistant.service._client", return_value=fake):
            conv_id = self._post("привіт").json()["conversation_id"]
        self.client.cookies.clear()
        self.assertEqual(self.client.get(f"/api/assistant/conversations/{conv_id}/").status_code, 404)

    def test_api_failure_gives_phone_number(self):
        broken = mock.Mock()
        broken.messages.create.side_effect = RuntimeError("boom")
        with mock.patch("assistant.service._client", return_value=broken):
            data = self._post("привіт").json()
        self.assertIn("+380 96 398 88 75", data["message"]["content"])
        conv = Conversation.objects.get(pk=data["conversation_id"])
        self.assertEqual(conv.api_messages[-1]["role"], "assistant")

    def test_rate_limit_and_daily_budget(self):
        self.settings_obj.messages_per_hour = 1
        self.settings_obj.save()
        fake = FakeClient([_response([_text("Привіт!")])])
        with mock.patch("assistant.service._client", return_value=fake):
            self.assertEqual(self._post("привіт").status_code, 200)
            limited = self._post("ще")
        self.assertEqual(limited.status_code, 429)
        self.assertTrue(limited["Retry-After"])

        self.settings_obj.messages_per_hour = 100
        self.settings_obj.daily_budget_usd = 0
        self.settings_obj.save()
        self.assertEqual(self._post("ще").status_code, 429)

    def test_unfinished_tool_rounds_end_with_assistant_turn(self):
        loop = [_response([_tool(f"t{i}", "view_cart", {})], stop="tool_use") for i in range(8)]
        with mock.patch("assistant.service._client", return_value=FakeClient(loop)):
            data = self._post("що в кошику").json()
        conv = Conversation.objects.get(pk=data["conversation_id"])
        self.assertEqual(conv.api_messages[-1]["role"], "assistant")
        self.assertTrue(data["message"]["content"])
        self.assertEqual(Message.objects.filter(conversation=conv).count(), 2)


class SecurityTests(CatalogMixin, TestCase):
    def setUp(self):
        s = AssistantSettings.load()
        s.enabled = True
        s.api_key = "sk-ant-test"
        s.save()
        self.request = self.make_request()
        self.args = {"full_name": "Іван Петренко", "phone": "0961234567", "city_id": self.city.pk,
                     "warehouse_id": self.warehouse.pk, "payment": "cash"}

    def _ctx(self, client_hash="abc"):
        conv = Conversation.objects.create(client_hash=client_hash)
        return ToolContext(self.request, conv)

    def test_order_cards_are_limited_per_conversation(self):
        ctx = self._ctx()
        run_tool(ctx, "add_to_cart", {"size_id": self.attr.pk})
        for _ in range(4):
            _, error = run_tool(ctx, "prepare_order", self.args)
            self.assertFalse(error)
        result, error = run_tool(ctx, "prepare_order", self.args)
        self.assertTrue(error)
        self.assertIn("+380 96 398 88 75", result["error"])

    def test_chat_orders_are_limited_per_visitor_per_day(self):
        for _ in range(2):
            order = Order.objects.create(name="A", surname="B", phone="+380961234567")
            Conversation.objects.create(client_hash="abc", order=order)
        ctx = self._ctx()
        run_tool(ctx, "add_to_cart", {"size_id": self.attr.pk})
        result, error = run_tool(ctx, "prepare_order", self.args)
        self.assertTrue(error)
        # Another visitor is not affected.
        other = self._ctx(client_hash="other")
        _, error = run_tool(other, "prepare_order", self.args)
        self.assertFalse(error)

    def test_spoofed_forwarded_for_does_not_dodge_the_limit(self):
        s = AssistantSettings.load()
        s.messages_per_hour = 1
        s.save()
        fake = FakeClient([_response([_text("Привіт!")])])
        with mock.patch("assistant.service._client", return_value=fake):
            ok = self.client.post("/api/assistant/message/", {"message": "1"}, content_type="application/json",
                                  HTTP_X_REAL_IP="9.9.9.9", HTTP_X_FORWARDED_FOR="1.1.1.1")
            again = self.client.post("/api/assistant/message/", {"message": "2"}, content_type="application/json",
                                     HTTP_X_REAL_IP="9.9.9.9", HTTP_X_FORWARDED_FOR="2.2.2.2")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(again.status_code, 429)

    def test_long_or_costly_conversation_is_stopped(self):
        fake = FakeClient([_response([_text("Привіт!")])])
        with mock.patch("assistant.service._client", return_value=fake):
            conv_id = self.client.post("/api/assistant/message/", {"message": "1"},
                                       content_type="application/json").json()["conversation_id"]
        Conversation.objects.filter(pk=conv_id).update(cost_usd="0.2")
        again = self.client.post("/api/assistant/message/", {"message": "2", "conversation_id": conv_id},
                                 content_type="application/json")
        self.assertEqual(again.status_code, 429)
        self.assertIn("Нова", again.json()["error"])

    def test_cards_follow_the_products_the_reply_links(self):
        size = Size.objects.create(title="0.8х1.5")
        beige = Product.objects.create(title="Килим бежевий Mira", slug="mira-beige")
        ProductAttribute.objects.create(product=beige, size=size, price=900, quantity=1)
        fake = FakeClient([
            _response([_tool("t1", "search_products", {"query": "килим"})], stop="tool_use"),
            _response([_text("Ось [сірий](/catalog/product/mira-grey/).")]),
        ])
        with mock.patch("assistant.service._client", return_value=fake):
            data = self.client.post("/api/assistant/message/", {"message": "килим"},
                                    content_type="application/json").json()
        self.assertEqual([p["id"] for p in data["message"]["products"]], [self.product.pk])
