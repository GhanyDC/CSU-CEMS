import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('elections', '0006_college'),
    ]

    operations = [
        migrations.AddField(
            model_name='election',
            name='banner',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to='election_banners/',
                validators=[django.core.validators.FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp'])],
                help_text='Optional banner image (JPG, PNG, or WebP, max 5 MB).',
            ),
        ),
    ]
