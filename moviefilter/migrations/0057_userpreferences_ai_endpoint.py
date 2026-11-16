# Generated manually: AI settings moved from UserPreferences to ai_predict.AiEndpoint.

import django.db.models.deletion
from django.db import migrations, models


def _migrate_ai_settings(apps, schema_editor):
    """
    Старые плоские поля (ai_base_url / ai_model / ai_api_key) превращаем в
    первый AI endpoint «Default». Groq-поля не переносим — они просто удаляются.
    """
    UserPreferences = apps.get_model('moviefilter', 'UserPreferences')
    AiEndpoint = apps.get_model('ai_predict', 'AiEndpoint')

    preferences = UserPreferences.objects.filter(pk=1).first()
    if preferences is None:
        return

    base_url = (preferences.ai_base_url or '').strip().rstrip('/')
    model = (preferences.ai_model or '').strip()
    if not base_url or not model:
        return

    endpoint = AiEndpoint.objects.create(
        name='Default',
        base_url=base_url,
        model=model,
        api_key=(preferences.ai_api_key or '').strip(),
    )
    preferences.ai_endpoint = endpoint
    preferences.save(update_fields=['ai_endpoint'])


def _restore_ai_settings(apps, schema_editor):
    """Обратная миграция: возвращаем значения активного endpoint в плоские поля."""
    UserPreferences = apps.get_model('moviefilter', 'UserPreferences')

    preferences = UserPreferences.objects.filter(pk=1).first()
    if preferences is None:
        return

    endpoint = preferences.ai_endpoint
    if endpoint is None:
        return

    preferences.ai_base_url = endpoint.base_url
    preferences.ai_model = endpoint.model
    preferences.ai_api_key = endpoint.api_key or None
    preferences.save(update_fields=['ai_base_url', 'ai_model', 'ai_api_key'])


class Migration(migrations.Migration):

    dependencies = [
        ('ai_predict', '0004_aiendpoint'),
        ('moviefilter', '0056_userpreferences_qbt_api_key_qbt_skip_cert_verify'),
    ]

    operations = [
        migrations.AddField(
            model_name='userpreferences',
            name='ai_endpoint',
            field=models.ForeignKey(
                blank=True,
                help_text='Шаблон подключения, который используют все AI-фичи',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='+',
                to='ai_predict.aiendpoint',
                verbose_name='Активный AI endpoint',
            ),
        ),
        migrations.RunPython(_migrate_ai_settings, _restore_ai_settings),
        migrations.RemoveField(
            model_name='userpreferences',
            name='ai_api_key',
        ),
        migrations.RemoveField(
            model_name='userpreferences',
            name='ai_base_url',
        ),
        migrations.RemoveField(
            model_name='userpreferences',
            name='ai_model',
        ),
        migrations.RemoveField(
            model_name='userpreferences',
            name='groq_api_key',
        ),
        migrations.RemoveField(
            model_name='userpreferences',
            name='groq_model',
        ),
        migrations.AlterField(
            model_name='userpreferences',
            name='ai_enabled',
            field=models.BooleanField(
                default=False,
                help_text='Использовать AI (активный AI endpoint) в фичах скана и Vault',
                verbose_name='AI включен',
            ),
        ),
    ]
