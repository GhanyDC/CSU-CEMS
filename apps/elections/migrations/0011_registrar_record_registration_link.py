import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_admin_profile_model"),
        ("elections", "0010_school_year_web_registration"),
    ]

    operations = [
        migrations.CreateModel(
            name="RegistrarRecord",
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
                ("batch", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="records", to="elections.registrarimportbatch")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="registrar_records", to="accounts.student")),
            ],
            options={
                "verbose_name": "Registrar Record",
                "verbose_name_plural": "Registrar Records",
                "ordering": ["batch", "student_identifier"],
            },
        ),
        migrations.AlterField(
            model_name="voterregistration",
            name="enrollment_record",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="voter_registrations", to="elections.enrollmentrecord"),
        ),
        migrations.AddField(
            model_name="voterregistration",
            name="registrar_record",
            field=models.ForeignKey(blank=True, help_text="Registrar batch record used for batch-backed web registration.", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="voter_registrations", to="elections.registrarrecord"),
        ),
        migrations.AddConstraint(
            model_name="registrarrecord",
            constraint=models.UniqueConstraint(fields=("batch", "student_identifier"), name="unique_registrar_record_per_batch_student_identifier"),
        ),
    ]
