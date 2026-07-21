"""
The networks a daily video is sent to.

One montage goes out to several places. Each of them wants the same file but
a different caption, a different privacy vocabulary, and — for YouTube — the
bytes rather than a URL. This module hides all of that behind one contract so
the pipeline can loop over networks instead of naming them.

Adding a network means writing an adapter and appending it to REGISTRY. The
pipeline does not change.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from social.models import SocialSettings, VideoDelivery

logger = logging.getLogger(__name__)


class PublishResult(dict):
    """
    What an adapter returns.

    Keys: external_id, external_url, private (bool — posted but owner-only).
    A plain dict subclass rather than a dataclass so adapters can pass the
    network's own response through unchanged for debugging.
    """


class NetworkAdapter(Protocol):
    key: str
    label: str
    #: True when the network uploads bytes instead of fetching a URL, which
    #: means the montage must still exist on disk at publish time.
    needs_local_file: bool

    def is_configured(self) -> bool:
        """Credentials present. Missing ones mean SKIPPED, never FAILED."""

    def is_enabled(self, social: SocialSettings) -> bool:
        """Operator switched this network on."""

    def caption(self, pick, script: dict) -> str: ...

    def publish(
        self,
        *,
        pick,
        script: dict,
        caption: str,
        video_url: str,
        local_path: str,
    ) -> PublishResult: ...


class TikTokAdapter:
    key = VideoDelivery.Platform.TIKTOK
    label = "TikTok"
    needs_local_file = False

    def is_configured(self) -> bool:
        from social.services import tiktok

        return tiktok.tiktok_configured()

    def is_enabled(self, social: SocialSettings) -> bool:
        return bool(social.tiktok_auto_enabled)

    def caption(self, pick, script: dict) -> str:
        from social.services.tiktok_script import build_caption

        return build_caption(pick, script)

    def publish(
        self,
        *,
        pick,
        script: dict,
        caption: str,
        video_url: str,
        local_path: str,
    ) -> PublishResult:
        from social.services import tiktok
        from social.services.tiktok_publish import COVER_TIMESTAMP_MS

        # Unaudited apps may only post SELF_ONLY, and the account's own list is
        # narrower than the API's constant, so ask rather than assume.
        options = tiktok.creator_privacy_options()
        privacy = (
            "SELF_ONLY"
            if not tiktok.audit_passed()
            else ("PUBLIC_TO_EVERYONE" if "PUBLIC_TO_EVERYONE" in options else options[0])
        )

        result = tiktok.publish_video(
            video_url=video_url,
            caption=caption,
            privacy_level=privacy,
            allow_comment=True,
            # The music is ours and the visuals are generated, so both
            # declarations are honest and required.
            music_usage_confirmed=True,
            made_with_ai=True,
            cover_timestamp_ms=COVER_TIMESTAMP_MS,
        )
        return PublishResult(
            external_id=result.get("external_id", ""),
            external_url=result.get("external_url", ""),
            private=privacy == "SELF_ONLY",
        )


class InstagramReelsAdapter:
    key = VideoDelivery.Platform.INSTAGRAM
    label = "Instagram Reels"
    needs_local_file = False

    def is_configured(self) -> bool:
        from social.services import meta

        return meta.meta_configured(need_ig=True)

    def is_enabled(self, social: SocialSettings) -> bool:
        return bool(social.video_instagram_enabled)

    def caption(self, pick, script: dict) -> str:
        from social.services.video_caption import build_caption

        return build_caption(pick, script, platform=self.key)

    def publish(self, *, pick, script, caption, video_url, local_path) -> PublishResult:
        from social.services import meta

        result = meta.publish_instagram_reel(video_url=video_url, caption=caption)
        return PublishResult(
            external_id=result.get("external_id", ""),
            external_url=result.get("external_url", ""),
            private=False,
        )


class FacebookReelsAdapter:
    key = VideoDelivery.Platform.FACEBOOK
    label = "Facebook Reels"
    needs_local_file = False

    def is_configured(self) -> bool:
        from social.services import meta

        return meta.meta_configured(need_fb=True)

    def is_enabled(self, social: SocialSettings) -> bool:
        return bool(social.video_facebook_enabled)

    def caption(self, pick, script: dict) -> str:
        from social.services.video_caption import build_caption

        return build_caption(pick, script, platform=self.key)

    def publish(self, *, pick, script, caption, video_url, local_path) -> PublishResult:
        from social.services import meta

        # A real Reel, not a plain video post: /{page}/videos with file_url
        # still works but is undocumented and gets ordinary video distribution.
        #
        # The title shows above the video in the feed, so it carries the hook
        # rather than the product name — and never the price.
        result = meta.publish_facebook_reel(
            video_url=video_url,
            caption=caption,
            title=script.get("hook", "")[:255],
        )
        return PublishResult(
            external_id=result.get("external_id", ""),
            post_id=result.get("post_id", ""),
            external_url=result.get("external_url", ""),
            private=False,
        )


class ThreadsAdapter:
    key = VideoDelivery.Platform.THREADS
    label = "Threads"
    needs_local_file = False

    def is_configured(self) -> bool:
        from social.services import threads

        return threads.threads_configured()

    def is_enabled(self, social: SocialSettings) -> bool:
        return bool(social.video_threads_enabled)

    def caption(self, pick, script: dict) -> str:
        from social.services.video_caption import build_caption

        return build_caption(pick, script, platform=self.key)

    def publish(self, *, pick, script, caption, video_url, local_path) -> PublishResult:
        from social.services import threads
        from social.services.video_caption import threads_topic_tag

        result = threads.publish_video(
            video_url=video_url,
            text=caption,
            topic_tag=threads_topic_tag(pick.product),
        )
        return PublishResult(
            external_id=result.get("external_id", ""),
            external_url=result.get("external_url", ""),
            private=False,
        )


class YouTubeShortsAdapter:
    key = VideoDelivery.Platform.YOUTUBE
    label = "YouTube Shorts"
    #: The only network that wants the bytes rather than a URL — which is why
    #: the montage outlives the publish instead of being deleted on the first
    #: confirmation.
    needs_local_file = True

    def is_configured(self) -> bool:
        from social.services import youtube

        return youtube.youtube_configured()

    def is_enabled(self, social: SocialSettings) -> bool:
        return bool(social.video_youtube_enabled)

    def caption(self, pick, script: dict) -> str:
        from social.services.video_caption import build_caption

        return build_caption(pick, script, platform=self.key)

    def publish(self, *, pick, script, caption, video_url, local_path) -> PublishResult:
        from social.services import youtube
        from social.services.video_caption import build_youtube_title, hashtags_for

        tags = [
            t.lstrip("#")
            for t in hashtags_for(pick.product, self.key).split()
            if t.strip()
        ]
        result = youtube.upload_video(
            file_path=local_path,
            title=build_youtube_title(pick, script),
            description=caption,
            tags=tags,
            privacy="public",
        )
        # Before the compliance audit YouTube silently forces private. Recording
        # it as published_private keeps the daily report honest instead of
        # claiming an audience that cannot see the video.
        return PublishResult(
            external_id=result.get("external_id", ""),
            external_url=result.get("external_url", ""),
            private=bool(result.get("forced_private")),
        )


#: Order matters — it is the order posts go out in, and the order they are
#: reported in. TikTok stays first: it is the network the format was built for.
REGISTRY: list[NetworkAdapter] = [
    TikTokAdapter(),
    InstagramReelsAdapter(),
    FacebookReelsAdapter(),
    ThreadsAdapter(),
    YouTubeShortsAdapter(),
]


def all_adapters() -> list[NetworkAdapter]:
    return list(REGISTRY)


def adapter_for(key: str) -> NetworkAdapter | None:
    for adapter in REGISTRY:
        if adapter.key == key:
            return adapter
    return None


def needs_local_file(adapters: list[NetworkAdapter] | None = None) -> bool:
    """True when any target network uploads bytes rather than fetching a URL."""
    return any(a.needs_local_file for a in (adapters if adapters is not None else REGISTRY))


def plan_targets(social: SocialSettings | None = None) -> list[tuple[NetworkAdapter, str]]:
    """
    Decide what each network's delivery status should start as.

    Returns (adapter, initial_status). SKIPPED is not a failure: a network the
    operator never switched on must not show up as a red line in the daily
    report every single day.
    """
    social = social or SocialSettings.load()
    targets: list[tuple[NetworkAdapter, str]] = []
    for adapter in REGISTRY:
        if not adapter.is_enabled(social):
            targets.append((adapter, VideoDelivery.Status.SKIPPED))
        elif not adapter.is_configured():
            targets.append((adapter, VideoDelivery.Status.SKIPPED))
        else:
            targets.append((adapter, VideoDelivery.Status.PENDING))
    return targets


def is_video_post(*ids: str) -> bool:
    """
    True when any of these ids belongs to a daily video we published.

    Routing inbound comments by *platform* would not work: Instagram carries
    both the daily Reels and the product photo carousels, so only the post
    itself says which world a comment came from.

    Several ids are accepted because Facebook publishes against a video_id but
    reports comments against a post_id.
    """
    from django.db.models import Q

    wanted = [str(i).strip() for i in ids if str(i or "").strip()]
    if not wanted:
        return False
    return VideoDelivery.objects.filter(
        Q(external_id__in=wanted) | Q(post_id__in=wanted),
        status__in=VideoDelivery.SUCCESS_STATUSES,
    ).exists()


def skip_reason(adapter: NetworkAdapter, social: SocialSettings) -> str:
    if not adapter.is_enabled(social):
        return "вимкнено в налаштуваннях"
    if not adapter.is_configured():
        return "не налаштовано (немає токена)"
    return ""
