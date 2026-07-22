"""Singleton OAuth token stores for the social publishing networks."""

from __future__ import annotations

from django.db import models
from django.utils import timezone


class TikTokToken(models.Model):
    """
    Singleton OAuth token store for the TikTok Content Posting API.

    TikTok has no never-expiring token: access_token lives 24h and
    refresh_token 365 days from the *initial* grant (not rolling). So the
    access token is refreshed in the background and the OAuth flow has to be
    repeated by a human roughly once a year — see refresh_expires_at.

    client_key is stored alongside the tokens because sandbox and production
    credentials are separate: a token minted for one client_key returns 401
    for the other, and that failure is otherwise indistinguishable from an
    expired token.
    """

    REFRESH_MARGIN_SECONDS = 600
    REAUTH_WARNING_DAYS = 30

    access_token = models.TextField(blank=True, default="")
    refresh_token = models.TextField(blank=True, default="")
    open_id = models.CharField(max_length=128, blank=True, default="")
    scope = models.CharField(max_length=255, blank=True, default="")
    client_key = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="client_key the tokens were issued for (sandbox keys start with 'sb').",
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    refresh_expires_at = models.DateTimeField(null=True, blank=True)
    last_refreshed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    refresh_fail_count = models.PositiveIntegerField(default=0)
    reauth_warned_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "TikTok token"
        verbose_name_plural = "TikTok token"

    def __str__(self) -> str:
        if not self.access_token:
            return "TikTok token (not authorized)"
        return f"TikTok token open_id={self.open_id or '?'}"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "TikTokToken":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def is_authorized(self) -> bool:
        return bool(self.access_token and self.refresh_token)

    @property
    def needs_refresh(self) -> bool:
        """True when the access token is missing or within the safety margin."""
        if not self.access_token or self.expires_at is None:
            return True
        margin = timezone.timedelta(seconds=self.REFRESH_MARGIN_SECONDS)
        return self.expires_at - timezone.now() <= margin

    @property
    def refresh_expired(self) -> bool:
        if self.refresh_expires_at is None:
            return False
        return timezone.now() >= self.refresh_expires_at

    @property
    def days_until_reauth(self) -> int | None:
        if self.refresh_expires_at is None:
            return None
        return (self.refresh_expires_at - timezone.now()).days


class ThreadsToken(models.Model):
    """
    Singleton OAuth token store for Threads.

    Threads works unlike TikTok: there is no refresh_token. One long-lived
    access_token lives 60 days and is exchanged for a fresh 60 days using
    itself. Two rules follow, and both bite if ignored:

    * A token may only be refreshed once it is **at least 24 hours old**. The
      obvious "refresh every night at 03:00" fails on day one.
    * A token left unrefreshed past 60 days is dead, and only a human
      repeating the OAuth flow in a browser brings it back.

    user_id is stored because every publishing call is addressed to it, and
    because a token minted for a different account fails in a way that looks
    like an expiry.
    """

    #: Refresh once the remaining life drops below this.
    REFRESH_MARGIN_DAYS = 30
    #: Meta rejects a refresh before the token is this old.
    MIN_AGE_HOURS = 24
    REAUTH_WARNING_DAYS = 7

    access_token = models.TextField(blank=True, default="")
    user_id = models.CharField(max_length=128, blank=True, default="")
    username = models.CharField(max_length=190, blank=True, default="")
    scope = models.CharField(max_length=255, blank=True, default="")
    issued_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_refreshed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    refresh_fail_count = models.PositiveIntegerField(default=0)
    reauth_warned_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Threads token"
        verbose_name_plural = "Threads token"

    def __str__(self) -> str:
        if not self.access_token:
            return "Threads token (not authorized)"
        return f"Threads token @{self.username or self.user_id or '?'}"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "ThreadsToken":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def is_authorized(self) -> bool:
        return bool(self.access_token and self.user_id)

    @property
    def expired(self) -> bool:
        if self.expires_at is None:
            return False
        return timezone.now() >= self.expires_at

    @property
    def old_enough_to_refresh(self) -> bool:
        """Meta refuses a refresh within 24 hours of the token being issued."""
        stamp = self.last_refreshed_at or self.issued_at
        if stamp is None:
            return False
        return timezone.now() - stamp >= timezone.timedelta(hours=self.MIN_AGE_HOURS)

    @property
    def needs_refresh(self) -> bool:
        if not self.access_token or self.expires_at is None:
            return False
        remaining = self.expires_at - timezone.now()
        return remaining <= timezone.timedelta(days=self.REFRESH_MARGIN_DAYS)

    @property
    def days_until_expiry(self) -> int | None:
        if self.expires_at is None:
            return None
        return (self.expires_at - timezone.now()).days


class YouTubeToken(models.Model):
    """
    Singleton OAuth token store for the YouTube Data API.

    Google's model is the classic one: a one-hour access_token plus a
    refresh_token that does not expire on a schedule. Two things still kill it,
    and both are worth naming because neither looks like what it is:

    * **Testing mode.** While the Cloud app's publishing status is `Testing`,
      Google expires the refresh_token after **seven days**. The scheduler
      then fails weekly with an auth error that reads like bad credentials.
      The app must be published — see social/YOUTUBE_SETUP.md.

    * **Six months idle.** A refresh_token unused for six months is revoked.
      Not our case at one upload a day, but it explains a dead token on a
      project that was paused.

    channel_id is stored so a misdirected authorization is visible rather than
    silently uploading to somebody else's channel.
    """

    REFRESH_MARGIN_SECONDS = 300

    access_token = models.TextField(blank=True, default="")
    refresh_token = models.TextField(blank=True, default="")
    scope = models.CharField(max_length=255, blank=True, default="")
    channel_id = models.CharField(max_length=128, blank=True, default="")
    channel_title = models.CharField(max_length=190, blank=True, default="")
    expires_at = models.DateTimeField(null=True, blank=True)
    authorized_at = models.DateTimeField(null=True, blank=True)
    last_refreshed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    refresh_fail_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "YouTube token"
        verbose_name_plural = "YouTube token"

    def __str__(self) -> str:
        if not self.access_token and not self.refresh_token:
            return "YouTube token (not authorized)"
        return f"YouTube token · {self.channel_title or self.channel_id or '?'}"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "YouTubeToken":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def is_authorized(self) -> bool:
        # The refresh_token is what matters: the access_token is disposable.
        return bool(self.refresh_token)

    @property
    def needs_refresh(self) -> bool:
        if not self.access_token or self.expires_at is None:
            return True
        margin = timezone.timedelta(seconds=self.REFRESH_MARGIN_SECONDS)
        return self.expires_at - timezone.now() <= margin
