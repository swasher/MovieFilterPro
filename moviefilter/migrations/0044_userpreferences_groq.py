# Generated for Groq settings in UserPreferences

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('moviefilter', '0043_userpreferences_local_ai'),
    ]

    operations = [
        migrations.AddField(
            model_name='userpreferences',
            name='groq_api_key',
            field=models.CharField(
                blank=True,
                help_text='API-ключ Groq для облачных LLM',
                max_length=200,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='userpreferences',
            name='groq_model',
            field=models.CharField(
                blank=True,
                help_text='Имя Groq-модели, например llama-3.3-70b-versatile',
                max_length=100,
                null=True,
            ),
        ),
    ]
