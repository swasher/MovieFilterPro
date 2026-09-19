# Generated for local AI settings in UserPreferences

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('moviefilter', '0042_userpreferences_omdb_api_key'),
    ]

    operations = [
        migrations.AddField(
            model_name='userpreferences',
            name='ai_enabled',
            field=models.BooleanField(
                default=False,
                help_text='Использовать локальный AI для будущих фич',
                verbose_name='Локальный AI включен',
            ),
        ),
        migrations.AddField(
            model_name='userpreferences',
            name='ai_base_url',
            field=models.CharField(
                blank=True,
                help_text='Base URL OpenAI-совместимого сервера, например http://localhost:11434/v1',
                max_length=300,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='userpreferences',
            name='ai_api_key',
            field=models.CharField(
                blank=True,
                help_text='API-ключ, если сервер его требует (для локальных обычно не нужен)',
                max_length=200,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='userpreferences',
            name='ai_model',
            field=models.CharField(
                blank=True,
                help_text='Имя модели, например qwen2.5:7b',
                max_length=100,
                null=True,
            ),
        ),
    ]
