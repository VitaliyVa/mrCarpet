from django.shortcuts import render
from django.http import HttpResponse
from django.db.models import Prefetch

from catalog.models import Product, ProductAttribute, ProductSale
from blog.models import Article
from cart.utils import get_cart
from project.seo_jsonld import dumps_jsonld, faq_graph, get_faq_items

# Create your views here.
def index(request):
    product_attrs = Prefetch(
        "product_attr",
        queryset=ProductAttribute.objects.select_related("size").order_by("sort_order", "id"),
    )
    # Product.objects manager already filters/orders by stock + created
    products = Product.objects.prefetch_related(product_attrs)[:24]
    main_sale = (
        ProductSale.objects.filter(main_sale=True)
        .prefetch_related(Prefetch("products", queryset=Product.objects.prefetch_related(product_attrs)))
        .first()
    )
    if main_sale:
        main_sale_date = main_sale.date_end
        sale_products = main_sale.products.all()[:24]
    else:
        main_sale_date = None
        sale_products = []
    posts = list(Article.objects.order_by("-id")[:12])
    return render(
        request,
        "index.html",
        context={
            "products": products,
            "posts": posts,
            "sale_products": sale_products,
            "main_sale_date": main_sale_date,
        },
    )


def about(request):
    return render(request, 'about.html')


def checkout(request):
    cart = get_cart(request)
    context = {
        'cart': cart,
    }
    return render(request, 'checkout.html', context)


def delivery(request):
    return render(request, 'delivery.html')


def faq(request):
    faq_items = get_faq_items()
    return render(
        request,
        "faq.html",
        {
            "faq_items": faq_items,
            "faq_jsonld": dumps_jsonld(faq_graph(faq_items)),
        },
    )


def refund_page(request):
    return render(request, 'refund.html')


def terms(request):
    return render(request, 'terms.html')


def policy(request):
    return render(request, 'policy.html')


def newsletter_unsubscribe_preview(request):
    """Demo page for admin email preview (не реальна відписка)."""
    return render(
        request,
        "unsubscribe.html",
        {"state": "preview"},
    )


def newsletter_unsubscribe(request, token):
    """One-click відписка з листа (GET confirm → POST)."""
    from project.models import Subscription
    from project.newsletter import unsubscribe_subscription

    sub = Subscription.objects.filter(unsubscribe_token=token).first()
    if not sub:
        return render(
            request,
            "unsubscribe.html",
            {"state": "not_found"},
            status=404,
        )

    if request.method == "POST":
        unsubscribe_subscription(sub)
        return render(
            request,
            "unsubscribe.html",
            {"state": "done", "email": sub.email},
        )

    if not sub.is_active:
        return render(
            request,
            "unsubscribe.html",
            {"state": "already", "email": sub.email},
        )

    return render(
        request,
        "unsubscribe.html",
        {"state": "confirm", "email": sub.email, "token": token},
    )


def success(request):
    """
    Emit GA4 purchase only for eligible orders.
    LiqPay: callback may lag behind result_url — one short retry while awaiting_payment.
    """
    from order.models import Order
    from project.ga4_ecommerce import order_allows_purchase_event

    purchase = None
    purchase_retry = False
    session = getattr(request, "session", None)

    if session is not None:
        pending = session.get("ga4_purchase")
        if pending and pending.get("transaction_id"):
            tx = pending["transaction_id"]
            order = Order.objects.filter(order_number=tx).first()
            if order is None:
                try:
                    order = Order.objects.filter(order_number=int(tx)).first()
                except (TypeError, ValueError):
                    order = None

            if order_allows_purchase_event(order):
                purchase = session.pop("ga4_purchase", None)
                session.pop("ga4_purchase_retry", None)
            elif order and order.status == Order.STATUS_AWAITING_PAYMENT:
                # Race with LiqPay server_url callback — reload once.
                if session.get("ga4_purchase_retry"):
                    session.pop("ga4_purchase", None)
                    session.pop("ga4_purchase_retry", None)
                else:
                    session["ga4_purchase_retry"] = 1
                    purchase_retry = True
            else:
                # cancelled / unknown — drop stale payload
                session.pop("ga4_purchase", None)
                session.pop("ga4_purchase_retry", None)

    return render(
        request,
        "success.html",
        {
            "analytics_purchase": purchase,
            "analytics_purchase_retry": purchase_retry,
        },
    )

def reset_password(request):
    return render(request, 'reset_password.html')


def robots_txt(request):
    """
    robots.txt gated by SEO_INDEXING_ENABLED (default False = full Disallow).

    Go-live: set SEO_INDEXING_ENABLED=true — see docs/seo.md.
    Private paths stay Disallow even when open (basket/checkout/profile/…).
    """
    from project.seo_indexing import SITE_CANONICAL_ORIGIN, build_robots_txt

    sitemap_url = f"{SITE_CANONICAL_ORIGIN}/sitemap.xml"
    if getattr(request, "get_host", None):
        try:
            sitemap_url = request.build_absolute_uri("/sitemap.xml")
        except Exception:
            pass
    return HttpResponse(
        build_robots_txt(sitemap_url=sitemap_url),
        content_type="text/plain; charset=utf-8",
    )


def google_site_verification_file(request):
    """Google Search Console HTML-file ownership verification."""
    return HttpResponse(
        "google-site-verification: google67459f697e641b7f.html" + chr(10),
        content_type="text/html; charset=utf-8",
    )


def tiktok_site_verification_file(request):
    """
    TikTok for Developers URL-prefix ownership verification (signature file).

    Required for the Content Posting API pull_by_url transfer and for the
    Terms/Privacy URLs on the app profile. Served from the site root.
    """
    return HttpResponse(
        "tiktok-developers-site-verification="
        "xfkAe8tZDvfpCs644EJmGm1b51LUG1xX" + chr(10),
        content_type="text/plain; charset=utf-8",
    )
