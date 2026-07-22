"""Generate the TikTok background music library. Run once, by hand."""

from django.core.management.base import BaseCommand

from social.services.tiktok_music import (
    MusicError,
    PROMPTS,
    generate_library,
    library_paths,
)


class Command(BaseCommand):
    help = (
        "Generate royalty-free background tracks for the TikTok montage. "
        "One-off: the daily job only picks from what is already stored."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=20,
            help=(
                f"How many tracks to generate. Above {len(PROMPTS)} the prompts "
                "repeat with a different seed, giving a new melody per track."
            ),
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Regenerate even if the library already has tracks.",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help=(
                "Delete every stored track and stop. For switching to a "
                "hand-picked library: clear, then upload files into "
                "media/social/tiktok/music/."
            ),
        )

    def handle(self, *args, **options):
        existing = library_paths()
        self.stdout.write(f"library now: {len(existing)} track(s)")
        if options["clear"]:
            from django.core.files.storage import default_storage

            for path in existing:
                default_storage.delete(path)
                self.stdout.write(f"  - {path}")
            self.stdout.write(self.style.SUCCESS(f"cleared: {len(existing)} track(s)"))
            return
        if existing and not options["overwrite"]:
            for path in existing:
                self.stdout.write(f"  {path}")
            self.stdout.write(
                self.style.WARNING("nothing to do — pass --overwrite to regenerate")
            )
            return

        try:
            created = generate_library(
                count=options["count"], overwrite=options["overwrite"]
            )
        except MusicError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            return

        for path in created:
            self.stdout.write(self.style.SUCCESS(f"  + {path}"))
        self.stdout.write(self.style.SUCCESS(f"done: {len(created)} track(s)"))
