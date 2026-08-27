# Generated for OMDB ratings integration

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vault', '0034_add_collection'),
    ]

    operations = [
        migrations.AddField(
            model_name='movie',
            name='omdb_imdb_rating',
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=3, null=True, verbose_name='OMDB IMDb рейтинг'),
        ),
        migrations.AddField(
            model_name='movie',
            name='omdb_rotten_tomatoes',
            field=models.PositiveSmallIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)], verbose_name='OMDB Rotten Tomatoes %'),
        ),
        migrations.AddField(
            model_name='movie',
            name='omdb_metacritic',
            field=models.PositiveSmallIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)], verbose_name='OMDB Metacritic /100'),
        ),
        migrations.AddField(
            model_name='movie',
            name='omdb_last_synced_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Последняя синхронизация OMDB'),
        ),
    ]
