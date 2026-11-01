import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from tmdb_adapter.client_singleton import get_person_basic, get_tmdb_client
from vault.models import Person
from vault.services.tmdb_movie_sync_service import TMDBMovieSyncService
from vault.services.tmdb_rate_limiter import TmdbRateLimiter


logger = logging.getLogger("vault.backfill.person_details")


class Command(BaseCommand):
    help = (
        "Backfill недостающих деталей персон из TMDB: место рождения, "
        "known_for_department, gender, also_known_as и другие пустые поля."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Сколько персон обработать за запуск (по умолчанию 100).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Показать, что было бы обновлено, но не сохранять изменения.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Обрабатывать и уже синхронизированные персоны (person_details_synced_at не null).",
        )
        parser.add_argument(
            "--person-id",
            type=int,
            default=None,
            help="Обработать только одну персону по локальному Person.id.",
        )
        parser.add_argument(
            "--after-id",
            type=int,
            default=None,
            help="Начать с персон с id больше указанного (удобно для --force батчей).",
        )

    def handle(self, *args, **options):
        person_id = options["person_id"]
        after_id = options["after_id"]
        limit = max(1, options["limit"])
        dry_run = options["dry_run"]
        force = options["force"]

        if person_id is not None:
            qs = Person.objects.filter(pk=person_id)
            limit = 1
        elif force:
            qs = Person.objects.all().order_by("id")
        else:
            qs = Person.objects.filter(person_details_synced_at__isnull=True).order_by("id")

        if after_id is not None and person_id is None:
            qs = qs.filter(id__gt=after_id)

        if person_id is None:
            # Синтетические k.../t... ID не существуют в TMDB.
            qs = qs.filter(tmdb_id__regex=r"^\d+$")

        persons = list(qs[:limit])
        if not persons:
            self.stdout.write(self.style.WARNING("Нет персон для обработки."))
            return

        try:
            tmdb = get_tmdb_client()
        except Exception as exc:
            raise CommandError(f"Не удалось создать TMDB-клиент: {exc}") from exc

        processed = 0
        updated = 0
        unchanged = 0
        skipped = 0
        failed = 0

        for person in persons:
            tmdb_id_text = (person.tmdb_id or "").strip()
            if not tmdb_id_text.isdigit():
                skipped += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"SKIP person_id={person.id}: нечисловой tmdb_id={person.tmdb_id!r}"
                    )
                )
                continue

            processed += 1
            try:
                TmdbRateLimiter.wait()
                details = get_person_basic(tmdb, int(tmdb_id_text))
            except Exception:
                failed += 1
                logger.exception(
                    "Person details backfill failed for person_id=%s tmdb_id=%s",
                    person.id,
                    person.tmdb_id,
                )
                self.stderr.write(
                    self.style.ERROR(
                        f"FAIL person_id={person.id} tmdb_id={person.tmdb_id}: ошибка запроса TMDB"
                    )
                )
                continue

            if details is None:
                failed += 1
                logger.warning(
                    "Person details backfill returned no data for person_id=%s tmdb_id=%s",
                    person.id,
                    person.tmdb_id,
                )
                self.stderr.write(
                    self.style.ERROR(
                        f"FAIL person_id={person.id} tmdb_id={person.tmdb_id}: пустой ответ TMDB"
                    )
                )
                continue

            updates = self._collect_updates(person, details)
            aliases = TMDBMovieSyncService._clean_aliases(
                details.also_known_as,
                person.name,
                person.original_name,
            )
            existing_tmdb_aliases = set(
                person.aliases.filter(source="tmdb").values_list("name", flat=True)
            )
            aliases_changed = existing_tmdb_aliases != set(aliases)
            would_update = bool(updates) or aliases_changed

            if dry_run:
                if would_update:
                    updated += 1
                    self.stdout.write(
                        f"DRY-RUN person_id={person.id} {person.name}: "
                        f"{', '.join(updates) if updates else 'только aliases'}"
                    )
                else:
                    unchanged += 1
                continue

            synced_at = timezone.now()
            person.person_details_synced_at = synced_at
            updates["person_details_synced_at"] = synced_at

            with transaction.atomic():
                person.save(update_fields=list(updates.keys()))
                TMDBMovieSyncService._sync_person_aliases(
                    person,
                    aliases,
                    clear_empty=True,
                )

            if would_update:
                updated += 1
                if options["verbosity"] >= 2:
                    self.stdout.write(
                        f"OK person_id={person.id} {person.name}: "
                        f"{', '.join(updates.keys())}"
                    )
            else:
                unchanged += 1

        mode = "DRY-RUN" if dry_run else "Готово"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode}: selected={len(persons)} processed={processed} "
                f"updated={updated} unchanged={unchanged} "
                f"skipped={skipped} failed={failed}"
            )
        )

    @staticmethod
    def _collect_updates(person: Person, details) -> dict:
        """Собирает только заполнение пустых полей, не затирая существующие данные."""
        updates = {}

        if not person.place_of_birth and details.place_of_birth:
            person.place_of_birth = details.place_of_birth
            updates["place_of_birth"] = details.place_of_birth

        if not person.known_for_department and details.known_for_department:
            person.known_for_department = details.known_for_department
            updates["known_for_department"] = details.known_for_department

        mapped_gender = TMDBMovieSyncService._map_person_gender(details.gender)
        if mapped_gender and person.gender != mapped_gender:
            person.gender = mapped_gender
            updates["gender"] = mapped_gender

        if person.birth_date is None and details.birthday:
            person.birth_date = details.birthday
            updates["birth_date"] = details.birthday

        if person.death_date is None and details.deathday:
            person.death_date = details.deathday
            updates["death_date"] = details.deathday

        if not person.biography and details.biography:
            person.biography = details.biography
            updates["biography"] = details.biography

        if not person.photo and details.profile_path:
            person.photo = details.profile_path
            updates["photo"] = details.profile_path

        if person.popularity is None and details.popularity is not None:
            person.popularity = details.popularity
            updates["popularity"] = details.popularity

        return updates
