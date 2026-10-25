from datetime import datetime, time

from django.db import migrations, models
from django.utils import timezone


def backfill_scanned_at(apps, schema_editor):
    MovieRSS = apps.get_model('moviefilter', 'MovieRSS')
    # order_by('id') переопределяет Meta.ordering, который на этом шаге
    # миграции ещё ссылается на старое имя поля date_added.
    for movie in MovieRSS.objects.order_by('id').filter(scanned_at__isnull=True).only('id', 'tracker_date'):
        naive = datetime.combine(movie.tracker_date, time.min)
        movie.scanned_at = timezone.make_aware(naive)
        movie.save(update_fields=['scanned_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('moviefilter', '0049_userpreferences_last_scan_kinozal_id'),
    ]

    operations = [
        migrations.RenameField(
            model_name='movierss',
            old_name='date_added',
            new_name='tracker_date',
        ),
        migrations.AddField(
            model_name='movierss',
            name='scanned_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_scanned_at, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='movierss',
            name='scanned_at',
            field=models.DateTimeField(default=timezone.now, db_index=True, help_text='Дата и время попадания записи в базу при сканировании'),
        ),
        migrations.AlterField(
            model_name='movierss',
            name='tracker_date',
            field=models.DateField(help_text='Дата создания раздачи на трекере Kinozal'),
        ),
        migrations.AlterModelOptions(
            name='movierss',
            options={'ordering': ['scanned_at', 'id']},
        ),
    ]
