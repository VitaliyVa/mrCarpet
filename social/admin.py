"""Admin for social publishing."""

from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import path, reverse

from social.models import (
    SocialDelivery,
    SocialPost,
    SocialPostImage,
    SocialSettings,
    TikTokDailyPick,
    TikTokToken,
    VideoDelivery,
)
from social.services.publish import (
    enqueue_publish,
    ensure_deliveries,
    validate_post_for_publish,
)
from social.services.tg_isolation import isolation_issues
from social.services.wan_i2v import (
    WanBudgetError,
    WanConfigError,
    WanGenerateError,
    generate_draft_from_product,
)


class SocialSettingsForm(forms.ModelForm):
    class Meta:
        model = SocialSettings
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        issues = isolation_issues(
            channel_id=cleaned.get("products_channel_id") or "",
            discussion_id=cleaned.get("products_discussion_chat_id") or "",
            staff_comments_id=cleaned.get("staff_comments_chat_id") or "",
            staff_comments_thread_id=cleaned.get("staff_comments_thread_id")
            or "",
            video_comments_thread_id=cleaned.get("video_comments_thread_id")
            or "",
        )
        if issues:
            raise forms.ValidationError(issues)
        return cleaned


class SocialPostImageInline(admin.TabularInline):
    model = SocialPostImage
    extra = 2
    ordering = ("sort_order", "id")
    fields = ("sort_order", "image")


class SocialDeliveryInline(admin.TabularInline):
    model = SocialDelivery
    extra = 0
    readonly_fields = (
        "platform",
        "status",
        "external_id",
        "external_url",
        "attempts",
        "error",
        "finished_at",
        "created",
        "updated",
    )
    can_delete = False


class VideoDeliveryInline(admin.TabularInline):
    """Per-network outcome of one daily video, shown on the pick itself."""

    model = VideoDelivery
    extra = 0
    readonly_fields = (
        "platform",
        "status",
        "external_id",
        "external_url",
        "attempts",
        "error",
        "published_at",
    )
    fields = readonly_fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SocialPost)
class SocialPostAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "media_kind",
        "product",
        "status",
        "targets",
        "ai_generated",
        "created",
        "published_at",
    )
    list_filter = (
        "media_kind",
        "status",
        "ai_generated",
        "target_instagram",
        "target_facebook",
        "target_tiktok",
    )
    search_fields = ("caption", "product__title", "promo_code")
    autocomplete_fields = ("product",)
    readonly_fields = ("status", "published_at", "last_error", "ai_generated", "created", "updated")
    inlines = [SocialPostImageInline, SocialDeliveryInline]
    actions = ("action_publish", "action_generate_ai_draft")

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "media_kind",
                    "product",
                    "video",
                    "cover",
                    "status",
                    "published_at",
                    "last_error",
                ),
                "description": (
                    "video: завантаж MP4. photos: додай зображення в inline Gallery "
                    "(1 = single, 2–10 = carousel / slideshow)."
                ),
            },
        ),
        (
            "Captions",
            {
                "fields": (
                    "caption",
                    "caption_ig",
                    "caption_fb",
                    "caption_tt",
                    "promo_code",
                    "utm_campaign",
                )
            },
        ),
        (
            "Targets",
            {"fields": ("target_instagram", "target_facebook", "target_tiktok")},
        ),
        (
            "TikTok compliance (required for TT)",
            {
                "fields": (
                    "tt_privacy_level",
                    "tt_allow_comment",
                    "tt_allow_duet",
                    "tt_allow_stitch",
                    "tt_commercial_disclosure",
                    "tt_music_usage_confirmed",
                ),
                "description": (
                    "Privacy level must be chosen explicitly (no silent default). "
                    "Until TikTok app audit passes, posts are forced to SELF_ONLY. "
                    "Music usage must be confirmed (video + photo). See "
                    "https://developers.tiktok.com/doc/content-sharing-guidelines"
                ),
            },
        ),
        (
            "AI draft",
            {"fields": ("ai_generated", "ai_prompt")},
        ),
    )

    @admin.display(description="Targets")
    def targets(self, obj: SocialPost) -> str:
        bits = []
        if obj.target_instagram:
            bits.append("IG")
        if obj.target_facebook:
            bits.append("FB")
        if obj.target_tiktok:
            bits.append("TT")
        return ",".join(bits) or "—"

    @admin.action(description="Publish to selected platforms")
    def action_publish(self, request, queryset):
        n = 0
        for post in queryset:
            err = validate_post_for_publish(post)
            if err:
                self.message_user(
                    request, f"Post #{post.pk}: {err}", level=messages.ERROR
                )
                continue
            ensure_deliveries(post)
            post.status = SocialPost.Status.QUEUED
            post.save(update_fields=["status", "updated"])
            enqueue_publish(post.pk)
            n += 1
        self.message_user(request, f"Queued {n} post(s) for publish")

    @admin.action(description="Generate AI video draft (Wan I2V)")
    def action_generate_ai_draft(self, request, queryset):
        for post in queryset:
            if post.media_kind != SocialPost.MediaKind.VIDEO:
                self.message_user(
                    request,
                    f"Post #{post.pk}: AI draft only for media_kind=video",
                    level=messages.ERROR,
                )
                continue
            try:
                generate_draft_from_product(post)
                self.message_user(
                    request, f"Post #{post.pk}: AI draft generated — review before publish"
                )
            except (WanConfigError, WanBudgetError, WanGenerateError) as exc:
                self.message_user(
                    request, f"Post #{post.pk}: {exc}", level=messages.ERROR
                )

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<int:post_id>/publish/",
                self.admin_site.admin_view(self.publish_view),
                name="social_socialpost_publish",
            ),
            path(
                "<int:post_id>/ai-draft/",
                self.admin_site.admin_view(self.ai_draft_view),
                name="social_socialpost_ai_draft",
            ),
        ]
        return custom + urls

    def publish_view(self, request, post_id: int):
        post = SocialPost.objects.filter(pk=post_id).first()
        if not post:
            messages.error(request, "Post not found")
        else:
            self.action_publish(request, SocialPost.objects.filter(pk=post_id))
        return HttpResponseRedirect(
            reverse("admin:social_socialpost_change", args=[post_id])
        )

    def ai_draft_view(self, request, post_id: int):
        post = SocialPost.objects.filter(pk=post_id).first()
        if not post:
            messages.error(request, "Post not found")
        else:
            self.action_generate_ai_draft(
                request, SocialPost.objects.filter(pk=post_id)
            )
        return HttpResponseRedirect(
            reverse("admin:social_socialpost_change", args=[post_id])
        )

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        if object_id:
            extra_context["publish_url"] = reverse(
                "admin:social_socialpost_publish", args=[object_id]
            )
            extra_context["ai_draft_url"] = reverse(
                "admin:social_socialpost_ai_draft", args=[object_id]
            )
        return super().change_view(
            request, object_id, form_url, extra_context=extra_context
        )


@admin.register(SocialDelivery)
class SocialDeliveryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "post",
        "platform",
        "status",
        "external_id",
        "attempts",
        "finished_at",
    )
    list_filter = ("platform", "status")
    search_fields = ("external_id", "error", "post__caption")
    readonly_fields = (
        "post",
        "platform",
        "status",
        "external_id",
        "external_url",
        "error",
        "attempts",
        "finished_at",
        "created",
        "updated",
    )


@admin.register(SocialSettings)
class SocialSettingsAdmin(admin.ModelAdmin):
    form = SocialSettingsForm

    def has_add_permission(self, request):
        return not SocialSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    fieldsets = (
        (
            "Відео-мережі: щоденний ролик",
            {
                "fields": (
                    "tiktok_auto_enabled",
                    "tiktok_audit_passed",
                ),
                "description": (
                    "Один ролик на день розходиться по всіх увімкнених мережах. "
                    "Генерація о 04:00, публікація о 18:00 (Київ). "
                    "Мережа без токена не ламає прогін — вона позначається "
                    "«пропущено», решта постить далі."
                ),
            },
        ),
        (
            "Відео: генерація і бюджет",
            {
                "fields": (
                    "tiktok_video_model",
                    "tiktok_vertical_image_model",
                    "tiktok_video_seconds",
                    "tiktok_video_resolution",
                    "tiktok_video_draft",
                    "tiktok_monthly_budget_usd",
                ),
                "classes": ("collapse",),
                "description": (
                    "Вартість не залежить від кількості мереж: відео одне, "
                    "генерація одна. Стеля бюджету зупиняє генерацію, "
                    "не публікацію."
                ),
            },
        ),
        (
            "AI I2V (Wan)",
            {"fields": ("ai_i2v_enabled", "ai_i2v_daily_limit", "ai_i2v_model")},
        ),
        (
            "Meta (Instagram/Facebook) products",
            {
                "fields": ("auto_post_new_products_meta",),
                "description": (
                    "Авто-пост нових товарів у IG/FB (photos-пост). "
                    "Потребує META_* у прод .env (social_setup_check). "
                    "Ручний варіант: Catalog → Products → action "
                    "«Опублікувати в TG + Instagram + Facebook»."
                ),
            },
        ),
        (
            "Viber products channel",
            {
                "fields": (
                    "viber_posting_enabled",
                    "auto_post_new_products_viber",
                ),
                "description": (
                    "Канал «Меблі і Килими (Ланівці)», токен у .env "
                    "(VIBER_AUTH_TOKEN). Поки майстер-рубильник вимкнений — "
                    "у Viber не постить ніщо: ні авто, ні ручна дія."
                ),
            },
        ),
        (
            "Telegram products channel",
            {
                "fields": (
                    "auto_post_new_products_tg",
                    "products_channel_id",
                    "products_discussion_chat_id",
                    "products_bot_replies",
                ),
                "description": (
                    "IDs тут (Social settings), не в Telegram settings. "
                    "family orders ≠ staff comments ≠ channel ≠ discussion. "
                    "Див. social/README.md."
                ),
            },
        ),
        (
            "Staff comments inbox",
            {
                "fields": (
                    "staff_comments_enabled",
                    "staff_comments_chat_id",
                    "staff_comments_thread_id",
                    "video_comments_thread_id",
                ),
                "description": (
                    "Дубль коментарів (TG discussion → пізніше IG/FB) у forum-топік "
                    "сімейної групи «mr.Carpet comments». "
                    "chat_id порожньо = TelegramSettings.chat_id; "
                    "thread_id ≠ orders topic. Бот: can_manage_topics. "
                    "Video topic — окремий топік для відео-мереж; порожньо = "
                    "все падає сюди ж."
                ),
            },
        ),
    )


@admin.register(VideoDelivery)
class VideoDeliveryAdmin(admin.ModelAdmin):
    """Cross-pick view: which network is quietly failing every night."""

    list_display = (
        "pick",
        "platform",
        "status",
        "attempts",
        "published_at",
        "external_id",
    )
    list_filter = ("platform", "status")
    search_fields = ("external_id", "pick__product__title")
    date_hierarchy = "published_at"
    readonly_fields = tuple(
        f.name for f in VideoDelivery._meta.fields if f.name != "id"
    )

    def has_add_permission(self, request):
        return False


@admin.register(TikTokToken)
class TikTokTokenAdmin(admin.ModelAdmin):
    """Read-only view of the OAuth state plus a button to (re)authorize."""

    change_list_template = "admin/social/tiktoktoken/change_list.html"

    readonly_fields = (
        "open_id",
        "scope",
        "client_key",
        "expires_at",
        "refresh_expires_at",
        "last_refreshed_at",
        "refresh_fail_count",
        "last_error",
        "updated_at",
    )
    fields = readonly_fields
    list_display = ("__str__", "environment", "expires_at", "reauth_due")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Середовище")
    def environment(self, obj: TikTokToken) -> str:
        if not obj.client_key:
            return "—"
        return "Sandbox" if obj.client_key.startswith("sb") else "Production"

    @admin.display(description="Переавторизація до")
    def reauth_due(self, obj: TikTokToken) -> str:
        days = obj.days_until_reauth
        if days is None:
            return "—"
        return f"{obj.refresh_expires_at:%Y-%m-%d} ({days} дн.)"

    def get_urls(self):
        return [
            path(
                "refresh-now/",
                self.admin_site.admin_view(self.refresh_now),
                name="social_tiktoktoken_refresh",
            ),
            *super().get_urls(),
        ]

    def refresh_now(self, request):
        from social.services.tiktok_auth import TikTokAuthError
        from social.services.tiktok_auth import refresh_token as do_refresh

        try:
            token = do_refresh()
        except TikTokAuthError as exc:
            self.message_user(request, f"Рефреш не вдався: {exc}", messages.ERROR)
        else:
            self.message_user(
                request,
                f"Токен оновлено, діє до {token.expires_at:%Y-%m-%d %H:%M}.",
                messages.SUCCESS,
            )
        return HttpResponseRedirect(reverse("admin:social_tiktoktoken_changelist"))


@admin.register(TikTokDailyPick)
class TikTokDailyPickAdmin(admin.ModelAdmin):
    """
    Rotation history, plus the two manual steps of the daily pipeline.

    The scheduler does this unattended, but having both steps reachable from
    the admin gives an operator a way to re-run a failed night without SSH —
    and makes the integration demonstrable in a screen recording, which the
    TikTok app review asks for.
    """

    actions = ("action_generate", "action_publish")
    inlines = (VideoDeliveryInline,)

    list_display = (
        "picked_at",
        "cycle_number",
        "product",
        "status",
        "networks",
        "social_post",
    )
    list_filter = ("status", "cycle_number")
    search_fields = ("product__title",)
    date_hierarchy = "picked_at"
    readonly_fields = (
        "product",
        "cycle_number",
        "picked_at",
        "status",
        "social_post",
        "video_path",
        "montage_path",
        "error",
        "created",
        "updated",
    )
    fields = readonly_fields

    @admin.display(description="Мережі")
    def networks(self, obj):
        """Which networks took the video — the per-pick summary at a glance."""
        rows = obj.deliveries.all()
        if not rows:
            return "—"
        marks = {
            "published": "✅",
            "published_private": "🔒",
            "failed": "❌",
            "skipped": "–",
            "publishing": "⏳",
            "pending": "…",
        }
        return " ".join(
            f"{marks.get(r.status, '?')}{r.get_platform_display()}" for r in rows
        )

    def has_add_permission(self, request):
        return False

    @admin.action(description="1. Згенерувати відео для TikTok")
    def action_generate(self, request, queryset):
        from social.services.tiktok_publish import build_final_video

        for pick in queryset:
            if pick.product_id is None:
                self.message_user(
                    request, f"Пік #{pick.pk}: товар видалено", messages.WARNING
                )
                continue
            try:
                path = build_final_video(pick)
            except Exception as exc:
                self.message_user(
                    request, f"Пік #{pick.pk}: {exc}", messages.ERROR
                )
            else:
                self.message_user(
                    request,
                    f"Пік #{pick.pk} ({pick.product}): відео готове — {path}",
                    messages.SUCCESS,
                )

    @admin.action(description="2. Опублікувати в TikTok")
    def action_publish(self, request, queryset):
        from social.services.tiktok_publish import publish_pick

        for pick in queryset:
            try:
                # force: an operator clicking the button has already decided,
                # so the enabled toggle and the already-published guard stand
                # aside. Regeneration stays off — retrying must not re-buy the
                # video.
                result = publish_pick(pick, force=True)
            except Exception as exc:
                self.message_user(
                    request, f"Пік #{pick.pk}: {exc}", messages.ERROR
                )
            else:
                if result.get("already_published"):
                    self.message_user(
                        request,
                        f"Пік #{pick.pk}: вже опубліковано всюди",
                        messages.INFO,
                    )
                    continue
                published = ", ".join(result.get("published") or []) or "—"
                failed = result.get("failed") or []
                self.message_user(
                    request,
                    f"Пік #{pick.pk} ({pick.product}): {published}"
                    + (f" · не вийшло: {'; '.join(failed)}" if failed else ""),
                    messages.WARNING if failed else messages.SUCCESS,
                )

    def changelist_view(self, request, extra_context=None):
        from social.services.tiktok_rotation import rotation_status

        try:
            status = rotation_status()
            self.message_user(
                request,
                f"Цикл {status['cycle']}: опубліковано "
                f"{status['published_this_cycle']} з {status['pool_size']}, "
                f"лишилось {status['remaining']}.",
                messages.INFO,
            )
        except Exception:
            pass
        return super().changelist_view(request, extra_context=extra_context)
