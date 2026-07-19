"""Admin for social publishing."""

from __future__ import annotations

from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import path, reverse

from social.models import SocialDelivery, SocialPost, SocialSettings
from social.services.publish import enqueue_publish, ensure_deliveries
from social.services.wan_i2v import (
    WanBudgetError,
    WanConfigError,
    WanGenerateError,
    generate_draft_from_product,
)


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
        "product",
        "status",
        "targets",
        "ai_generated",
        "created",
        "published_at",
    )
    list_filter = ("status", "ai_generated", "target_instagram", "target_facebook", "target_tiktok")
    search_fields = ("caption", "product__title", "promo_code")
    autocomplete_fields = ("product",)
    readonly_fields = ("status", "published_at", "last_error", "ai_generated", "created", "updated")
    inlines = [SocialDeliveryInline]
    actions = ("action_publish", "action_generate_ai_draft")

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "product",
                    "video",
                    "cover",
                    "status",
                    "published_at",
                    "last_error",
                )
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
                    "Music usage must be confirmed. See "
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
            if not post.video:
                self.message_user(
                    request, f"Post #{post.pk}: no video", level=messages.ERROR
                )
                continue
            if post.target_tiktok:
                if not (post.tt_privacy_level or "").strip():
                    self.message_user(
                        request,
                        f"Post #{post.pk}: set TikTok privacy level",
                        level=messages.ERROR,
                    )
                    continue
                if not post.tt_music_usage_confirmed:
                    self.message_user(
                        request,
                        f"Post #{post.pk}: confirm TikTok music usage",
                        level=messages.ERROR,
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
            "Telegram products channel",
            {
                "fields": (
                    "auto_post_new_products_tg",
                    "products_channel_id",
                    "products_discussion_chat_id",
                    "products_bot_replies",
                ),
                "description": "See social/README.md for channel setup.",
            },
        ),
    )
