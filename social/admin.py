"""Admin for social publishing."""

from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import path, reverse

from social.models import SocialDelivery, SocialPost, SocialPostImage, SocialSettings
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
            "TikTok",
            {"fields": ("tiktok_audit_passed",)},
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
                    "Ручний варіант: Catalog → Products → actions "
                    "«Створити IG/FB пост» / «Опублікувати в IG/FB зараз»."
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
                ),
                "description": (
                    "Дубль коментарів (TG discussion → пізніше IG/FB) у forum-топік "
                    "сімейної групи «mr.Carpet comments». "
                    "chat_id порожньо = TelegramSettings.chat_id; "
                    "thread_id ≠ orders topic. Бот: can_manage_topics."
                ),
            },
        ),
    )
