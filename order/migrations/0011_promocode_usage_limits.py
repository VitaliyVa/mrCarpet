import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0044_promocode_usage_limits"),
        ("order", "0010_order_free_shipping"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="promocode_code",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Знімок коду на момент замовлення (навіть якщо промокод видалять).",
                max_length=115,
                verbose_name="Промокод (код)",
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="promocode_discount",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Знімок знижки % на момент замовлення.",
                null=True,
                verbose_name="Промокод (знижка %)",
            ),
        ),
        migrations.AlterField(
            model_name="order",
            name="promocode",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="orders",
                to="catalog.promocode",
                verbose_name="Промокод",
            ),
        ),
        migrations.CreateModel(
            name="PromoCodeRedemption",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created",
                    models.DateTimeField(
                        auto_now_add=True, null=True, verbose_name="Створено"
                    ),
                ),
                (
                    "updated",
                    models.DateTimeField(
                        auto_now=True, null=True, verbose_name="Оновлено"
                    ),
                ),
                (
                    "email",
                    models.EmailField(
                        blank=True,
                        db_index=True,
                        default="",
                        max_length=254,
                        verbose_name="Email",
                    ),
                ),
                (
                    "order",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="promo_redemption",
                        to="order.order",
                        verbose_name="Замовлення",
                    ),
                ),
                (
                    "promocode",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="redemptions",
                        to="catalog.promocode",
                        verbose_name="Промокод",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="promo_redemptions",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Користувач",
                    ),
                ),
            ],
            options={
                "verbose_name": "Використання промокоду",
                "verbose_name_plural": "Використання промокодів",
            },
        ),
        migrations.AddIndex(
            model_name="promocoderedemption",
            index=models.Index(
                fields=["promocode", "email"],
                name="order_promo_promoco_idx",
            ),
        ),
    ]
