# Generated by Django 4.2.7 on 2023-11-29 19:27

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kinozal', '0009_alter_movierss_translate_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='movierss',
            name='translate',
            field=models.CharField(blank=True, max_length=300, null=True),
        ),
        migrations.AlterField(
            model_name='userpreferences',
            name='last_scan',
            field=models.DateField(default=datetime.datetime(2023, 6, 2, 21, 27, 37, 550026)),
        ),
    ]
