# Generated manually: index for TMDB-sync queue lookups
# (Movie.objects.filter(source=KINORIUM, tmdb_id__isnull=True)).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vault', '0041_alter_usermovie_watch_status_and_more'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='movie',
            index=models.Index(fields=['source', 'tmdb_id'], name='movie_source_tmdb_idx'),
        ),
    ]
