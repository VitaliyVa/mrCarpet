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
