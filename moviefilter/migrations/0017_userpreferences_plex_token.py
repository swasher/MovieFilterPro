# Generated by Django 5.0.2 on 2024-05-24 15:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('moviefilter', '0016_userpreferences_plex_address'),
    ]

    operations = [
        migrations.AddField(
            model_name='userpreferences',
            name='plex_token',
            field=models.CharField(blank=True, max_length=25, null=True),
        ),
    ]