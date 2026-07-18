import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_subscription_tokens(apps, schema_editor):
    Subscription = apps.get_model("project", "Subscription")
    for sub in Subscription.objects.all().iterator():
        if sub.unsubscribe_token:
            continue
        sub.unsubscribe_token = uuid.uuid4()
        sub.save(update_fields=["unsubscribe_token"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("project", "0012_shopsettings_novelty_days"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscription",
            name="is_active",
            field=models.BooleanField(
                db_index=True,
                default=True,
                verbose_name="Активна підписка",
            ),
        ),
        migrations.AddField(
            model_name="subscription",
            name="source",
            field=models.CharField(
                choices=[
                    ("footer", "Футер"),
                    ("profile", "Кабінет"),
                    ("import", "Імпорт"),
                ],
                db_index=True,
                default="footer",
                max_length=32,
                verbose_name="Джерело",
            ),
        ),
        migrations.AddField(
            model_name="subscription",
            name="subscribed_at",
            field=models.DateTimeField(
                auto_now_add=True,
                blank=True,
                null=True,
                verbose_name="Підписано",
            ),
        ),
        migrations.AddField(
            model_name="subscription",
            name="unsubscribed_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Відписано",
            ),
        ),
        migrations.AddField(
            model_name="subscription",
            name="unsubscribe_token",
            field=models.UUIDField(
                blank=True,
                editable=False,
                null=True,
                verbose_name="Токен відписки",
            ),
        ),
        migrations.AddField(
            model_name="subscription",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="subscriptions",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Користувач",
            ),
        ),
        migrations.AlterField(
            model_name="subscription",
            name="email",
            field=models.EmailField(
                max_length=254, unique=True, verbose_name="Email"
            ),
        ),
        migrations.AlterModelOptions(
            name="subscription",
            options={
                "ordering": ("-subscribed_at",),
                "verbose_name": "Підписаний користувач",
                "verbose_name_plural": "Підписані користувачі",
            },
        ),
        migrations.RunPython(backfill_subscription_tokens, noop_reverse),
        migrations.AlterField(
            model_name="subscription",
            name="unsubscribe_token",
            field=models.UUIDField(
                db_index=True,
                default=uuid.uuid4,
                editable=False,
                unique=True,
                verbose_name="Токен відписки",
            ),
        ),
    ]
