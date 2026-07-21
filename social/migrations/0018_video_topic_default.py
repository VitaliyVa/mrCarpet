"""
Point the daily video reports at the topic created for them.

The id is hard-coded because SocialSettings is deployment configuration for a
single store, not a shared default — the same is already true of the channel,
discussion and comments ids next to it. Filling it here saves an operator
from having to find the number by hand after the deploy.

Only fills a blank value, so a deliberately different id survives, and the
reverse leaves the field alone rather than guessing what it used to be.
"""

from django.db import migrations

# Forum topic «mr.Carpet video» in the family group.
VIDEO_TOPIC_THREAD_ID = "1040"


def set_video_topic(apps, schema_editor):
    SocialSettings = apps.get_model("social", "SocialSettings")
    row = SocialSettings.objects.filter(pk=1).first()
    if row is None:
        return
    if (row.video_comments_thread_id or "").strip():
        return
    row.video_comments_thread_id = VIDEO_TOPIC_THREAD_ID
    row.save(update_fields=["video_comments_thread_id"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("social", "0017_threadstoken"),
    ]

    operations = [
        migrations.RunPython(set_video_topic, noop),
    ]
