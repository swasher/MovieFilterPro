from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('moviefilter', '0046_userpreferences_searxng_url'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='movierss',
            constraint=models.UniqueConstraint(
                fields=('title', 'original_title', 'year'),
                name='unique_movierss_movie_identity',
            ),
        ),
    ]
