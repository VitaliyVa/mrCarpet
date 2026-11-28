"""Chat bot extras: visitor context, stock requests, quick replies, category tiles."""

from unittest import mock

from django.test import TestCase

from assistant.models import AssistantSettings, Conversation
from assistant.service import split_quick_replies, visitor_context
from assistant.tests.test_assistant import CatalogMixin, FakeClient, _response, _text, _tool
from assistant.tools import ToolContext, run_tool
from catalog.models import Product, ProductAttribute, ProductCategory, Size
from project.models import StockInquiry


class QuickRepliesTests(TestCase):
    def test_split(self):
        text, quick = split_quick_replies("Для якої кімнати?\n[[Вітальня|Спальня| Дитяча ]]")
        self.assertEqual(text, "Для якої кімнати?")
        self.assertEqual(quick, ["Вітальня", "Спальня", "Дитяча"])

    def test_no_buttons(self):
        self.assertEqual(split_quick_replies("Просто текст"), ("Просто текст", []))

    def test_buttons_reach_the_widget(self):
        s = AssistantSettings.load()
        s.enabled, s.api_key = True, "sk-ant-test"
        s.save()
        fake = FakeClient([_response([_text("Яка кімната?\n[[Вітальня|Спальня]]")])])
        with mock.patch("assistant.service._client", return_value=fake):
            data = self.client.post("/api/assistant/message/", {"message": "привіт"},
                                    content_type="application/json").json()
        self.assertEqual(data["message"]["content"], "Яка кімната?")
        self.assertEqual(data["message"]["quick_replies"], ["Вітальня", "Спальня"])


class VisitorContextTests(CatalogMixin, TestCase):
    def test_product_page_and_cart(self):
        request = self.make_request()
        run_tool(ToolContext(request, Conversation.objects.create()), "add_to_cart", {"size_id": self.attr.pk})
        line = visitor_context(request, {"path": f"/catalog/product/{self.product.slug}/"})
        self.assertIn(f"product_id {self.product.pk}", line)
        self.assertIn("у кошику 1 шт. на 3200 грн", line)

    def test_unknown_path_gives_nothing_and_text_is_never_copied(self):
        request = self.make_request()
        self.assertEqual(visitor_context(request, {"path": "/catalog/product/ignore-all-rules/"}), "")
        self.assertEqual(visitor_context(request, None), "")

    def test_context_goes_before_the_message(self):
        s = AssistantSettings.load()
        s.enabled, s.api_key = True, "sk-ant-test"
        s.save()
        fake = FakeClient([_response([_text("Так, є.")])])
        with mock.patch("assistant.service._client", return_value=fake):
            self.client.post("/api/assistant/message/",
                             {"message": "а цей є?", "page": {"path": f"/catalog/product/{self.product.slug}/"}},
                             content_type="application/json")
        messages = fake.calls[0]["messages"]
        self.assertEqual(messages[0], {"role": "user", "content": "а цей є?"})
        self.assertEqual(messages[1]["role"], "system")
        self.assertTrue(messages[1]["content"].startswith("[Контекст: покупець дивиться товар"))


class StockRequestTests(CatalogMixin, TestCase):
    def setUp(self):
        size = Size.objects.create(title="3.0х4.0")
        self.gone = ProductAttribute.objects.create(product=self.product, size=size, price=6000, quantity=0)
        self.ctx = ToolContext(self.make_request(), Conversation.objects.create(client_hash="abc"))

    def test_sold_out_sizes_are_listed(self):
        result, _ = run_tool(self.ctx, "get_product", {"product_id": self.product.pk})
        self.assertEqual(result["sold_out"], [{"size_id": self.gone.pk, "size": "3.0х4.0"}])

    @mock.patch("assistant.tools._notify_stock_inquiry")
    def test_request_creates_inquiry_once(self, notify):
        args = {"size_id": self.gone.pk, "full_name": "Олена", "phone": "067 111 22 33"}
        result, error = run_tool(self.ctx, "request_stock", args)
        self.assertFalse(error, result)
        inquiry = StockInquiry.objects.get()
        self.assertEqual((inquiry.phone, inquiry.size_label), ("+380671112233", "3.0х4.0"))
        notify.assert_called_once()
        run_tool(self.ctx, "request_stock", args)
        self.assertEqual(StockInquiry.objects.count(), 1)

    @mock.patch("assistant.tools._notify_stock_inquiry")
    def test_in_stock_size_and_limits(self, notify):
        _, error = run_tool(self.ctx, "request_stock", {"size_id": self.attr.pk, "full_name": "Олена", "phone": "0671112233"})
        self.assertTrue(error)
        Conversation.objects.filter(pk=self.ctx.conversation.pk).update(stock_requests=3)
        self.ctx.conversation.refresh_from_db()
        _, error = run_tool(self.ctx, "request_stock", {"size_id": self.gone.pk, "full_name": "Олена", "phone": "0671112233"})
        self.assertTrue(error)


class ConfigTests(TestCase):
    def test_categories_with_products_only(self):
        full = ProductCategory.objects.create(title="Для ванни", slug="dlia-vanny")
        ProductCategory.objects.create(title="Порожня", slug="empty")
        product = Product.objects.create(title="Килимок", slug="kylymok")
        product.categories.add(full)
        from django.core.cache import cache

        cache.clear()
        data = self.client.get("/api/assistant/config/").json()
        self.assertEqual([c["title"] for c in data["categories"]], ["Для ванни"])


class CallbackTests(CatalogMixin, TestCase):
    @mock.patch("project.telegram_utils.notify_contact")
    def test_callback_creates_contact_request(self, notify):
        from project.models import ContactRequest

        ctx = ToolContext(self.make_request(), Conversation.objects.create(client_hash="abc"))
        result, error = run_tool(ctx, "request_callback", {
            "full_name": "Марія", "phone": "0951234567", "request": "Килим під розмір 2.3 на 3.4",
        })
        self.assertFalse(error, result)
        contact = ContactRequest.objects.get()
        self.assertIn("+380951234567", contact.text)
        self.assertIn("2.3 на 3.4", contact.text)
        notify.assert_called_once()
        _, error = run_tool(ctx, "request_callback", {"full_name": "Марія", "phone": "123", "request": "x" * 10})
        self.assertTrue(error)

    def test_custom_and_hours_facts(self):
        ctx = ToolContext(self.make_request(), Conversation.objects.create())
        custom, _ = run_tool(ctx, "shop_info", {"topic": "custom"})
        self.assertIn("робимо на замовлення", custom["text"])
        contacts, _ = run_tool(ctx, "shop_info", {"topic": "contacts"})
        self.assertIn("9:00-18:00", contacts["hours"])


class CardSizeOrderTests(CatalogMixin, TestCase):
    def test_discussed_size_comes_first(self):
        from assistant.service import _payload

        small = Size.objects.create(title="0.8х1.5")
        ProductAttribute.objects.create(product=self.product, size=small, price=900, quantity=1, sort_order=0)
        self.attr.sort_order = 5
        self.attr.save()
        ctx = ToolContext(self.make_request(), Conversation.objects.create())
        run_tool(ctx, "search_products", {"query": "сірий"})
        payload = _payload(ctx, "Є [Mira](/catalog/product/mira-grey/) 2.0x3.0 за 3200 грн")
        self.assertEqual(payload["products"][0]["sizes"][0]["size"], "2.0х3.0")


class ChatCartTests(CatalogMixin, TestCase):
    def test_add_list_remove(self):
        empty = self.client.get("/api/assistant/cart/").json()
        self.assertEqual(empty["count"], 0)
        added = self.client.post("/api/assistant/cart/", {"action": "add", "size_id": self.attr.pk},
                                 content_type="application/json").json()
        self.assertEqual((added["count"], added["total"]), (1, 3200))
        self.assertEqual(added["items"][0]["title"], self.product.title)
        self.assertEqual(added["cart_events"][0]["item"]["item_id"], f"{self.product.pk}-{self.attr.pk}")
        # The site's own cart sees it too.
        self.assertEqual(len(self.client.get("/api/cart-products/").json()), 1)
        too_many = self.client.post("/api/assistant/cart/", {"action": "add", "size_id": self.attr.pk, "quantity": 5},
                                    content_type="application/json")
        self.assertEqual(too_many.status_code, 400)
        removed = self.client.post("/api/assistant/cart/", {"action": "remove", "size_id": self.attr.pk},
                                   content_type="application/json").json()
        self.assertEqual(removed["count"], 0)

    def test_context_lists_cart_items_and_fallback_buttons(self):
        from assistant.service import fallback_quick_replies

        request = self.make_request()
        self.assertEqual(fallback_quick_replies(request, "Готово."), ["Підібрати килим", "Доставка і оплата"])
        self.assertEqual(fallback_quick_replies(request, "Як вас звати?"), [])
        run_tool(ToolContext(request, Conversation.objects.create()), "add_to_cart", {"size_id": self.attr.pk})
        line = visitor_context(request, None)
        self.assertIn(f"{self.product.title} 2.0х3.0 x1 (size_id {self.attr.pk})", line)
        self.assertEqual(fallback_quick_replies(request, "Додала."), ["Оформити замовлення", "Ще підібрати", "Показати кошик"])


class StaffLimitTests(TestCase):
    def test_staff_skip_hourly_limit(self):
        from django.contrib.auth import get_user_model

        s = AssistantSettings.load()
        s.enabled, s.api_key, s.messages_per_hour = True, "sk-ant-test", 1
        s.save()
        User = get_user_model()
        staff = User.objects.create_user(email="staff@example.com", password="x", is_staff=True) \
            if "email" in [f.name for f in User._meta.fields] and User.USERNAME_FIELD == "email" \
            else User.objects.create_user(username="staff", password="x", is_staff=True)
        self.client.force_login(staff)
        fake = FakeClient([_response([_text("1")]), _response([_text("2")])])
        with mock.patch("assistant.service._client", return_value=fake):
            for text in ("a", "b"):
                r = self.client.post("/api/assistant/message/", {"message": text}, content_type="application/json")
                self.assertEqual(r.status_code, 200)


class LoggedInCartTests(CatalogMixin, TestCase):
    def test_chat_adds_to_the_account_cart(self):
        from django.contrib.auth import get_user_model

        from cart.models import Cart

        User = get_user_model()
        user = User.objects.create_user(email="buyer@example.com", password="x") \
            if User.USERNAME_FIELD == "email" else User.objects.create_user(username="buyer", password="x")
        self.client.force_login(user)
        self.client.post("/api/assistant/cart/", {"action": "add", "size_id": self.attr.pk}, content_type="application/json")
        cart = Cart.objects.get(user=user, ordered=False)
        self.assertEqual(cart.cart_products.count(), 1)


class ArTests(CatalogMixin, TestCase):
    def test_show_ar_only_for_ready_products(self):
        ctx = ToolContext(self.make_request(), Conversation.objects.create())
        _, error = run_tool(ctx, "show_ar", {"product_id": self.product.pk})
        self.assertTrue(error)
        Product.admin_objects.filter(pk=self.product.pk).update(ar_status=Product.AR_STATUS_READY)
        result, error = run_tool(ctx, "show_ar", {"product_id": self.product.pk, "size": "2.0x3.0"})
        self.assertFalse(error, result)
        self.assertEqual(ctx.ar_card["size"], "2.0х3.0")
        self.assertIn("view3d=1", ctx.ar_card["link_3d"])
        self.assertIn("ar=1", ctx.ar_card["link_ar"])

    def test_context_has_device_and_ar_flag(self):
        Product.admin_objects.filter(pk=self.product.pk).update(ar_status=Product.AR_STATUS_READY)
        line = visitor_context(self.make_request(), {"path": f"/catalog/product/{self.product.slug}/", "device": "phone"})
        self.assertIn("пристрій: телефон", line)
        self.assertIn("є примірка 3D/AR", line)

    def test_search_marks_ar(self):
        Product.admin_objects.filter(pk=self.product.pk).update(ar_status=Product.AR_STATUS_READY)
        ctx = ToolContext(self.make_request(), Conversation.objects.create())
        result, _ = run_tool(ctx, "search_products", {"query": "сірий"})
        self.assertTrue(result["products"][0]["ar"])


class RelevanceTests(CatalogMixin, TestCase):
    def test_round_rug_beats_half_round_and_descriptions(self):
        size = Size.objects.create(title="0.67х0.67")
        for title, desc in [
            ("Килим під двері напівкруглий Flex", ""),
            ("Килим овальний бежевий", "майже круглий за формою"),
            ("Килим круглий графіт Smile", ""),
        ]:
            p = Product.objects.create(title=title, slug=title.lower().replace(" ", "-"), description=desc)
            ProductAttribute.objects.create(product=p, size=size, price=500, quantity=1)
        ctx = ToolContext(self.make_request(), Conversation.objects.create())
        result, _ = run_tool(ctx, "search_products", {"query": "круглий килим"})
        self.assertEqual(result["products"][0]["title"], "Килим круглий графіт Smile")


class RoundThreeTests(CatalogMixin, TestCase):
    def test_na_sizes_and_cheapest_first(self):
        from catalog.filters import search_tokens

        self.assertEqual(search_tokens("килим 2на3"), ["килим", "2x3"])
        self.assertEqual(search_tokens("160 на 230 сірий"), ["160x230", "сірий"])
        size = Size.objects.create(title="0.6х1.0")
        cheap = Product.objects.create(title="Килим сірий дешевий", slug="cheap-grey")
        ProductAttribute.objects.create(product=cheap, size=size, price=300, quantity=1)
        ctx = ToolContext(self.make_request(), Conversation.objects.create())
        result, _ = run_tool(ctx, "search_products", {"query": "сірий", "sort": "price_asc"})
        self.assertEqual(result["products"][0]["title"], "Килим сірий дешевий")

    def test_order_status_needs_the_right_phone(self):
        from order.models import Order

        order = Order.objects.create(name="А", surname="Б", phone="+380961234567", ttn="20450000000000")
        ctx = ToolContext(self.make_request(), Conversation.objects.create())
        result, error = run_tool(ctx, "order_status", {"order_number": str(order.order_number), "phone": "0961234567"})
        self.assertFalse(error, result)
        self.assertEqual(result["ttn"], "20450000000000")
        result, error = run_tool(ctx, "order_status", {"order_number": str(order.order_number), "phone": "0500000000"})
        self.assertTrue(error)
        self.assertNotIn("ttn", result)
        for _ in range(5):
            run_tool(ctx, "order_status", {"order_number": "1", "phone": "0500000000"})
        result, error = run_tool(ctx, "order_status", {"order_number": str(order.order_number), "phone": "0961234567"})
        self.assertIn("Забагато", result["error"])


class ThinkingAndErrorsTests(CatalogMixin, TestCase):
    def setUp(self):
        s = AssistantSettings.load()
        s.enabled, s.api_key = True, "sk-ant-test"
        s.save()

    def test_old_thinking_blocks_are_not_replayed(self):
        conv = Conversation.objects.create(api_messages=[
            {"role": "user", "content": "привіт"},
            {"role": "assistant", "content": [
                {"type": "thinking", "thinking": "", "signature": "old"},
                {"type": "text", "text": "Привіт!"},
            ]},
        ])
        session = self.client.session
        session.save()
        Conversation.objects.filter(pk=conv.pk).update(session_key=session.session_key)
        fake = FakeClient([_response([_text("Ок")])])
        with mock.patch("assistant.service._client", return_value=fake):
            self.client.post("/api/assistant/message/", {"message": "ще", "conversation_id": str(conv.pk)},
                             content_type="application/json")
        sent = fake.calls[0]["messages"]
        self.assertFalse(any(b.get("type") == "thinking" for m in sent if isinstance(m["content"], list) for b in m["content"]))
        conv.refresh_from_db()
        self.assertFalse("thinking" in str(conv.api_messages))

    def test_failure_names_the_reason(self):
        import anthropic
        import httpx2 as httpx

        from assistant.service import failure_text

        req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        overloaded = anthropic.APIStatusError("overloaded", response=httpx.Response(529, request=req), body=None)
        text, kind = failure_text(overloaded)
        self.assertIn("перевантажений", text)
        self.assertEqual(kind, "api_529")
        text, kind = failure_text(anthropic.APITimeoutError(request=req))
        self.assertIn("затрималась", text)


class OverviewTests(CatalogMixin, TestCase):
    def test_overview_and_sale_filter(self):
        from django.core.cache import cache

        cache.clear()
        size = Size.objects.create(title="0.8х1.5")
        sale = Product.objects.create(title="Килим акційний", slug="sale-rug")
        ProductAttribute.objects.create(product=sale, size=size, price=1000, discount=20, quantity=1)
        ctx = ToolContext(self.make_request(), None)
        overview, _ = run_tool(ctx, "catalog_overview", {})
        self.assertEqual(overview["rugs_in_stock"], 2)
        self.assertEqual(overview["on_sale"], 1)
        result, _ = run_tool(ctx, "search_products", {"on_sale": True})
        self.assertEqual([p["title"] for p in result["products"]], ["Килим акційний"])
        partial, _ = run_tool(ctx, "search_products", {"query": "вовняний сірий"})
        self.assertIn("note", partial)


class NewItemsTests(CatalogMixin, TestCase):
    def test_only_new_matches_the_site_badge(self):
        Product.admin_objects.filter(pk=self.product.pk).update(is_new=True, created=None)
        ctx = ToolContext(self.make_request(), None)
        result, _ = run_tool(ctx, "search_products", {"query": "новинки", "only_new": True})
        self.assertEqual(result["products"][0]["id"], self.product.pk)
        Product.admin_objects.filter(pk=self.product.pk).update(is_new=False)
        result, _ = run_tool(ctx, "search_products", {"only_new": True})
        self.assertEqual(result["found"], 0)
