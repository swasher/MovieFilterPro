import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('moviefilter', '0051_userpreferences_scan_schedule'),
    ]

    operations = [
        migrations.CreateModel(
            name='ScanRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('trigger', models.CharField(choices=[('manual', 'Manual'), ('scheduled', 'Scheduled')], db_index=True, max_length=20, verbose_name='Триггер')),
                ('status', models.CharField(choices=[('running', 'Running'), ('success', 'Success'), ('error', 'Error'), ('cancelled', 'Cancelled'), ('rate_limited', 'Rate limited'), ('cloudflare_blocked', 'Cloudflare blocked')], db_index=True, default='running', max_length=30, verbose_name='Статус')),
                ('started_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Начало')),
                ('finished_at', models.DateTimeField(blank=True, null=True, verbose_name='Завершение')),
                ('scan_to_date', models.DateField(blank=True, null=True, verbose_name='Сканировать до даты')),
                ('new_movies_count', models.PositiveIntegerField(default=0, verbose_name='Новых фильмов')),
                ('error_type', models.CharField(blank=True, max_length=50, null=True, verbose_name='Тип ошибки')),
                ('error_message', models.TextField(blank=True, verbose_name='Сообщение об ошибке')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='scan_runs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Запуск сканирования',
                'verbose_name_plural': 'Запуски сканирования',
                'ordering': ['-started_at', '-id'],
            },
        ),
        migrations.CreateModel(
            name='ScanLogEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('level', models.CharField(choices=[('info', 'Info'), ('error', 'Error')], db_index=True, default='info', max_length=10, verbose_name='Уровень')),
                ('message', models.TextField(verbose_name='Сообщение')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Создано')),
                ('run', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='entries', to='moviefilter.scanrun')),
            ],
            options={
                'verbose_name': 'Запись лога сканирования',
                'verbose_name_plural': 'Записи лога сканирования',
                'ordering': ['created_at', 'id'],
                'indexes': [
                    models.Index(fields=['run', 'created_at'], name='mf_scanlog_run_created_idx'),
                ],
            },
        ),
    ]
