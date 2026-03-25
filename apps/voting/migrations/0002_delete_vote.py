# Delete the old Vote model before the Candidate it references is removed.
# This migration must run before elections/0002 which drops the old Candidate table.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("voting", "0001_initial"),
    ]

    operations = [
        migrations.DeleteModel(
            name="Vote",
        ),
    ]
