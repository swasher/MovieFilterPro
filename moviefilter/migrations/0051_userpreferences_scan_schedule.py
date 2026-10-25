from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('moviefilter', '0050_rename_date_added_tracker_date_add_scanned_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='userpreferences',
            name='scan_interval_minutes',
            field=models.PositiveIntegerField(blank=True, null=True, default=None, help_text='Интервал автоматического сканирования Kinozal в минутах. NULL — автозапуск выключен.'),
        ),
        migrations.AddField(
            model_name='userpreferences',
            name='scan_in_progress',
            field=models.BooleanField(default=False, help_text='Сейчас идёт сканирование (ручное или по расписанию). Взаимное исключение.'),
        ),
        migrations.AddField(
            model_name='userpreferences',
            name='scan_cancel_requested',
            field=models.BooleanField(default=False, help_text='Запрос отмены текущего сканирования. Используется для сканов по расписанию в HUEY-воркере.'),
        ),
        migrations.AddField(
            model_name='userpreferences',
            name='last_scheduled_run_at',
            field=models.DateTimeField(blank=True, null=True, help_text='Время завершения последнего сканирования по расписанию.'),
        ),
        migrations.AddField(
            model_name='userpreferences',
            name='last_scheduled_status',
            field=models.CharField(max_length=20, blank=True, null=True, help_text='Результат последнего сканирования по расписанию: success/error/cancelled.'),
        ),
    ]
