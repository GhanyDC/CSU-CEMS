import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('elections', '0005_registrarimportbatch_candidate_photo_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='College',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255, unique=True)),
                ('code', models.CharField(blank=True, default='', help_text='Short code or abbreviation (optional).', max_length=20)),
                ('is_active', models.BooleanField(default=True, help_text='Inactive colleges are hidden from election creation dropdowns.')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'College',
                'verbose_name_plural': 'Colleges',
                'ordering': ['name'],
            },
        ),
    ]
