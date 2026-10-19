from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('moviefilter', '0048_userpreferences_kinozal_mirrors'),
    ]

    operations = [
        migrations.AddField(
            model_name='userpreferences',
            name='last_scan_kinozal_id',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
