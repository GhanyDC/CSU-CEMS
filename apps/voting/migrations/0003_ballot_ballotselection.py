# Create Ballot and BallotSelection models.
# Depends on elections/0002 so that Election, Position, and Candidate exist.

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("voting", "0002_delete_vote"),
        ("elections", "0002_election_position_candidate_redesign"),
    ]

    operations = [
        # ── Ballot ────────────────────────────────────────────────────────────
        migrations.CreateModel(
            name="Ballot",
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
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="ballots",
                        to="elections.election",
                    ),
                ),
                (
                    "hashed_student_id",
                    models.CharField(
                        db_index=True,
                        help_text="SHA-256 hash of (student_id + SECRET_KEY salt).",
                        max_length=64,
                    ),
                ),
                ("timestamp", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Ballot",
                "verbose_name_plural": "Ballots",
                "ordering": ["-timestamp"],
            },
        ),
        migrations.AddConstraint(
            model_name="ballot",
            constraint=models.UniqueConstraint(
                fields=["election", "hashed_student_id"],
                name="unique_ballot_per_voter_per_election",
            ),
        ),

        # ── BallotSelection ───────────────────────────────────────────────────
        migrations.CreateModel(
            name="BallotSelection",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "ballot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="selections",
                        to="voting.ballot",
                    ),
                ),
                (
                    "position",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="ballot_selections",
                        to="elections.position",
                    ),
                ),
                (
                    "candidate",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="ballot_selections",
                        to="elections.candidate",
                    ),
                ),
            ],
            options={
                "verbose_name": "Ballot Selection",
                "verbose_name_plural": "Ballot Selections",
            },
        ),
        migrations.AddConstraint(
            model_name="ballotselection",
            constraint=models.UniqueConstraint(
                fields=["ballot", "position", "candidate"],
                name="unique_selection_per_ballot_position_candidate",
            ),
        ),
    ]
