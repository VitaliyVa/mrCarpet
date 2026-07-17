from django.template.loader import render_to_string


def build_stock_inquiry_customer_email(inquiry):
    subject = "mr.Carpet — ми отримали ваш запит про наявність"
    context = {
        "name": inquiry.name,
        "product_title": inquiry.product_title,
        "size_label": inquiry.size_label,
    }
    text = (
        f"Дякуємо, {inquiry.name}!\n\n"
        f"Ми отримали запит щодо товару «{inquiry.product_title}», "
        f"розмір {inquiry.size_label}.\n"
        f"Менеджер зв’яжеться з вами найближчим часом.\n\n"
        f"— mr.Carpet"
    )
    html = render_to_string("emails/stock_inquiry_customer.html", context)
    return subject, text, html


def build_stock_inquiry_admin_email(inquiry):
    subject = f"Запит наявності: {inquiry.product_title} ({inquiry.size_label})"
    context = {
        "name": inquiry.name,
        "phone": inquiry.phone,
        "email": inquiry.email,
        "product_title": inquiry.product_title,
        "size_label": inquiry.size_label,
        "product_attr_id": inquiry.product_attr_id or "—",
    }
    text = (
        f"Новий запит про наявність\n\n"
        f"Ім'я: {inquiry.name}\n"
        f"Телефон: {inquiry.phone}\n"
        f"Email: {inquiry.email}\n"
        f"Товар: {inquiry.product_title}\n"
        f"Розмір: {inquiry.size_label}\n"
        f"ID варіації: {inquiry.product_attr_id or '—'}\n"
    )
    html = render_to_string("emails/stock_inquiry_admin.html", context)
    return subject, text, html
