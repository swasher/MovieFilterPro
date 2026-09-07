# Generated for OMDB API key move from env to UserPreferences

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('moviefilter', '0041_add_tmdb_watched_list_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='userpreferences',
            name='omdb_api_key',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
    ]
