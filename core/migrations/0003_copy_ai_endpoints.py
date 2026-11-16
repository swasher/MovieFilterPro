# Перенос AI endpoints из ai_predict (фича) в core (инфраструктура).
# Таблицы создаются/удаляются обычными миграциями; копирование строк с
# сохранением ID — только здесь, чтобы не потерять активный endpoint в
# UserPreferences.ai_endpoint.

from django.db import migrations

FIELDS = ("id", "name", "base_url", "model", "api_key", "created_at", "updated_at")


def _copy_rows(apps, source_label: str, target_label: str, table: str, schema_editor) -> None:
    source = apps.get_model(*source_label.split("."))
    target = apps.get_model(*target_label.split("."))

    rows = list(source.objects.order_by("id").values(*FIELDS))
    for row in rows:
        target.objects.create(**row)

    # Явные ID не сдвигают sequence — иначе следующая вставка упадёт на конфликте pk.
    max_id = max((row["id"] for row in rows), default=0)
    if max_id:
        schema_editor.execute(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), %s, true)",
            [max_id],
        )
    else:
        schema_editor.execute(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), 1, false)"
        )


def copy_to_core(apps, schema_editor):
    _copy_rows(apps, "ai_predict.AiEndpoint", "core.AiEndpoint", "core_aiendpoint", schema_editor)


def copy_to_ai_predict(apps, schema_editor):
    _copy_rows(
        apps,
        "core.AiEndpoint",
        "ai_predict.AiEndpoint",
        "ai_predict_aiendpoint",
        schema_editor,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_aiendpoint"),
        ("ai_predict", "0004_aiendpoint"),
    ]

    operations = [
        migrations.RunPython(copy_to_core, copy_to_ai_predict),
    ]
