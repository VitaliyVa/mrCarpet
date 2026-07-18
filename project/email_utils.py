from project.email_branding import render_branded_email, with_plain_footer


def build_stock_inquiry_customer_email(inquiry):
    subject = "mr.Carpet — ми отримали ваш запит про наявність"
    context = {
        "name": inquiry.name,
        "product_title": inquiry.product_title,
        "size_label": inquiry.size_label,
    }
    text = with_plain_footer(
        f"Дякуємо, {inquiry.name}!\n\n"
        f"Ми отримали запит щодо товару «{inquiry.product_title}», "
        f"розмір {inquiry.size_label}.\n"
        f"Менеджер зв’яжеться з вами найближчим часом.\n\n"
        f"— mr.Carpet"
    )
    html = render_branded_email(
        "emails/stock_inquiry_customer_body.html",
        context,
        eyebrow="Запит про наявність",
        preheader=f"Запит щодо {inquiry.product_title}, розмір {inquiry.size_label}",
    )
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
    text = with_plain_footer(
        f"Новий запит про наявність\n\n"
        f"Ім'я: {inquiry.name}\n"
        f"Телефон: {inquiry.phone}\n"
        f"Email: {inquiry.email}\n"
        f"Товар: {inquiry.product_title}\n"
        f"Розмір: {inquiry.size_label}\n"
        f"ID варіації: {inquiry.product_attr_id or '—'}\n"
    )
    html = render_branded_email(
        "emails/stock_inquiry_admin_body.html",
        context,
        eyebrow="Адмін-сповіщення",
        preheader=subject,
    )
    return subject, text, html


def build_contact_received_email(contact):
    subject = "mr.Carpet — ми отримали ваше повідомлення"
    context = {
        "name": contact.name,
        "text": contact.text or "",
    }
    plain = with_plain_footer(
        f"Дякуємо, {contact.name}!\n\n"
        f"Ми отримали ваше повідомлення і відповімо найближчим часом.\n\n"
        f"— mr.Carpet"
    )
    html = render_branded_email(
        "emails/contact_received.html",
        context,
        eyebrow="Зворотний звʼязок",
        preheader="Ми отримали ваше повідомлення",
    )
    return subject, plain, html
