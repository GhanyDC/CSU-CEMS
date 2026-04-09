"""
Management command to seed the College table from OFFICIAL_COLLEGES constants.

Run once after initial setup:
    python manage.py seed_colleges
"""
from django.core.management.base import BaseCommand

from apps.elections.constants import OFFICIAL_COLLEGES
from apps.elections.models import College


class Command(BaseCommand):
    help = "Seed the College table from the OFFICIAL_COLLEGES constant."

    def handle(self, *args, **options):
        created = 0
        skipped = 0
        for name in OFFICIAL_COLLEGES:
            _, was_created = College.objects.get_or_create(name=name)
            if was_created:
                created += 1
            else:
                skipped += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {created} college(s) created, {skipped} already existed."
            )
        )
