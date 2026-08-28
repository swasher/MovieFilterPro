# Generated for OMDB imdbVotes

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vault', '0037_add_popularity'),
    ]

    operations = [
        migrations.AddField(
            model_name='movie',
            name='omdb_imdb_votes',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='OMDB IMDb голосов'),
        ),
    ]
