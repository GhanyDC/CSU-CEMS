import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_admin_profile_model"),
        ("elections", "0009_position_scope_college"),
    ]

    operations = [
        migrations.CreateModel(
            name="SchoolYear",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(help_text="Display name, e.g. 'AY 2026-2027'.", max_length=255)),
                ("academic_year", models.CharField(db_index=True, help_text="Academic year label, e.g. '2026-2027'.", max_length=50)),
                ("status", models.CharField(choices=[("active", "Active"), ("archived", "Archived")], db_index=True, default="archived", max_length=10)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "School Year",
                "verbose_name_plural": "School Years",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddField(
            model_name="election",
            name="registration_closes_at",
            field=models.DateTimeField(blank=True, help_text="Optional deadline for web voter registration.", null=True),
        ),
        migrations.AddField(
            model_name="election",
            name="registration_enabled",
            field=models.BooleanField(default=False, help_text="Allow enrolled students to register themselves for this election."),
        ),
        migrations.AddField(
            model_name="election",
            name="school_year",
            field=models.ForeignKey(blank=True, help_text="School-year enrollment roster used for web voter registration.", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="elections", to="elections.schoolyear"),
        ),
        migrations.CreateModel(
            name="EnrollmentRecord",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("student_identifier", models.CharField(db_index=True, max_length=50)),
                ("full_name", models.CharField(max_length=255)),
                ("date_of_birth", models.DateField()),
                ("college", models.CharField(db_index=True, max_length=255)),
                ("course", models.CharField(max_length=255)),
                ("year_level", models.PositiveSmallIntegerField(default=1)),
                ("status", models.CharField(choices=[("active", "Active"), ("inactive", "Inactive")], db_index=True, default="active", max_length=10)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("school_year", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="enrollments", to="elections.schoolyear")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="enrollments", to="accounts.student")),
            ],
            options={
                "verbose_name": "Enrollment Record",
                "verbose_name_plural": "Enrollment Records",
                "ordering": ["school_year", "student_identifier"],
            },
        ),
        migrations.CreateModel(
            name="VoterRegistration",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(choices=[("approved", "Approved"), ("rejected", "Rejected")], db_index=True, default="approved", max_length=10)),
                ("source", models.CharField(choices=[("web", "Web")], db_index=True, default="web", max_length=10)),
                ("college_snapshot", models.CharField(max_length=255)),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.TextField(blank=True, default="")),
                ("election", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="voter_registrations", to="elections.election")),
                ("eligible_voter", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="registration", to="elections.eligiblevoter")),
                ("enrollment_record", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="voter_registrations", to="elections.enrollmentrecord")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="voter_registrations", to="accounts.student")),
            ],
            options={
                "verbose_name": "Voter Registration",
                "verbose_name_plural": "Voter Registrations",
                "ordering": ["-requested_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="schoolyear",
            constraint=models.UniqueConstraint(fields=("academic_year",), name="unique_school_year_academic_year"),
        ),
        migrations.AddConstraint(
            model_name="schoolyear",
            constraint=models.UniqueConstraint(condition=models.Q(("status", "active")), fields=("status",), name="single_active_school_year"),
        ),
        migrations.AddConstraint(
            model_name="enrollmentrecord",
            constraint=models.UniqueConstraint(fields=("school_year", "student_identifier"), name="unique_enrollment_per_school_year_student_identifier"),
        ),
        migrations.AddConstraint(
            model_name="voterregistration",
            constraint=models.UniqueConstraint(fields=("election", "student"), name="unique_voter_registration_per_election_student"),
        ),
    ]
