# Redesign the elections app schema:
#  1. Drop the old flat Candidate model (Vote FK already removed in voting/0002).
#  2. Create Election.
#  3. Create Position (FK → Election).
#  4. Create new Candidate (FK → Position, adds college field).

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("elections", "0001_initial"),
        # Ensure Vote (which FK'd to old Candidate) is deleted first.
        ("voting", "0002_delete_vote"),
    ]

    operations = [
        # ── 1. Remove the old flat Candidate ─────────────────────────────────
        migrations.DeleteModel(
            name="Candidate",
        ),

        # ── 2. Election ───────────────────────────────────────────────────────
        migrations.CreateModel(
            name="Election",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                ("start_time", models.DateTimeField()),
                ("end_time", models.DateTimeField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("active", "Active"),
                            ("closed", "Closed"),
                            ("published", "Published"),
                        ],
                        db_index=True,
                        default="draft",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Election",
                "verbose_name_plural": "Elections",
                "ordering": ["-start_time"],
            },
        ),

        # ── 3. Position ───────────────────────────────────────────────────────
        migrations.CreateModel(
            name="Position",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "election",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="positions",
                        to="elections.election",
                    ),
                ),
                ("title", models.CharField(max_length=100)),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("executive", "Executive"),
                            ("senate", "Senate"),
                            ("house_college", "House \u2013 College Representative"),
                            (
                                "house_party",
                                "House \u2013 Party-List Representative",
                            ),
                        ],
                        db_index=True,
                        max_length=20,
                    ),
                ),
                (
                    "max_selections",
                    models.PositiveSmallIntegerField(
                        default=1,
                        help_text=(
                            "Maximum number of candidates a voter may select "
                            "for this position."
                        ),
                    ),
                ),
                (
                    "order",
                    models.PositiveSmallIntegerField(
                        default=0,
                        help_text="Ascending display order on the ballot.",
                    ),
                ),
            ],
            options={
                "verbose_name": "Position",
                "verbose_name_plural": "Positions",
                "ordering": ["order", "title"],
            },
        ),
        migrations.AddConstraint(
            model_name="position",
            constraint=models.UniqueConstraint(
                fields=["election", "title"],
                name="unique_position_title_per_election",
            ),
        ),

        # ── 4. New Candidate (FK → Position) ──────────────────────────────────
        migrations.CreateModel(
            name="Candidate",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "position",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="candidates",
                        to="elections.position",
                    ),
                ),
                ("full_name", models.CharField(max_length=255)),
                ("party", models.CharField(blank=True, default="", max_length=100)),
                (
                    "college",
                    models.CharField(
                        blank=True,
                        help_text=(
                            "College affiliation — required for House College "
                            "Representatives."
                        ),
                        max_length=255,
                        null=True,
                    ),
                ),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Candidate",
                "verbose_name_plural": "Candidates",
                "ordering": ["position__order", "full_name"],
            },
        ),
    ]
