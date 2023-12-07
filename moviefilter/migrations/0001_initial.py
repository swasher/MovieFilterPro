# Generated by Django 5.0 on 2023-12-07 19:51

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Country',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=60, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='Genre',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=30)),
            ],
        ),
        migrations.CreateModel(
            name='KinoriumMovie',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=50)),
                ('original_title', models.CharField(blank=True, max_length=50)),
                ('year', models.PositiveSmallIntegerField()),
                ('status', models.PositiveSmallIntegerField(choices=[(0, 'Новый'), (1, 'Просмотрен'), (2, 'Буду смотреть'), (3, 'Не буду смотреть')], default=0, verbose_name='Статус')),
            ],
        ),
        migrations.CreateModel(
            name='MovieRSS',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ignored', models.BooleanField(default=False, help_text='Пользователь не хочет видеть этот фильм.')),
                ('low_priority', models.BooleanField(default=False)),
                ('kinozal_id', models.PositiveSmallIntegerField()),
                ('title', models.CharField(max_length=70)),
                ('original_title', models.CharField(max_length=70)),
                ('year', models.CharField(help_text='Год может быть представлен как диапазон: 1982-1994', max_length=9)),
                ('date_added', models.DateField()),
                ('imdb_id', models.CharField(blank=True, max_length=9, null=True)),
                ('imdb_rating', models.FloatField(blank=True, null=True)),
                ('kinopoisk_id', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('kinopoisk_rating', models.FloatField(blank=True, null=True)),
                ('genres', models.CharField(max_length=300)),
                ('countries', models.CharField(max_length=300)),
                ('director', models.CharField(max_length=300)),
                ('actors', models.CharField(max_length=300)),
                ('plot', models.CharField(max_length=300)),
                ('translate', models.CharField(blank=True, max_length=300, null=True)),
                ('poster', models.CharField(max_length=300)),
                ('kinorium_id', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('kinorium_partial_match', models.BooleanField(blank=True, default=False, null=True)),
            ],
            options={
                'ordering': ['-id'],
            },
        ),
        migrations.CreateModel(
            name='UserPreferences',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('last_scan', models.DateField(blank=True, null=True)),
                ('countries', models.CharField(blank=True, default=None, max_length=300, null=True)),
                ('genres', models.CharField(blank=True, default=None, max_length=300, null=True)),
                ('max_year', models.PositiveSmallIntegerField(default=1900)),
                ('min_rating', models.FloatField(default=1.0)),
                ('low_countries', models.CharField(blank=True, default=None, max_length=300, null=True)),
                ('low_genres', models.CharField(blank=True, default=None, max_length=300, null=True)),
                ('low_max_year', models.PositiveSmallIntegerField(default=1900)),
                ('low_min_rating', models.FloatField(default=1.0)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='preferences', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
