from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def create_stars_for_favorites(apps, schema_editor):
    """Все персоны с включенным «сердцем» получают «звезду».

    FavoritePerson при этом не меняется: статусы независимы, миграция только
    добавляет недостающие StarPerson.
    """
    FavoritePerson = apps.get_model("vault", "FavoritePerson")
    StarPerson = apps.get_model("vault", "StarPerson")

    existing = set(StarPerson.objects.values_list("user_id", "person_id"))
    batch = []
    for user_id, person_id in FavoritePerson.objects.values_list(
        "user_id", "person_id"
    ).iterator(chunk_size=1000):
        key = (user_id, person_id)
        if key in existing:
            continue
        batch.append(StarPerson(user_id=user_id, person_id=person_id))
        if len(batch) >= 1000:
            StarPerson.objects.bulk_create(batch, ignore_conflicts=True)
            batch.clear()
    if batch:
        StarPerson.objects.bulk_create(batch, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("vault", "0049_person_details_synced_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="StarPerson",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Добавлено")),
                (
                    "person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="starred_by",
                        to="vault.person",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="star_persons",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Персона-звезда",
                "verbose_name_plural": "Персоны-звезды",
                "ordering": ["-created_at"],
                "unique_together": {("user", "person")},
            },
        ),
        migrations.RunPython(create_stars_for_favorites, migrations.RunPython.noop),
    ]
