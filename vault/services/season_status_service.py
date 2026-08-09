from django.db import transaction

from vault.models import Season, UserSeason


STATUS_TO_WATCH_STATUS = {
    "watched": UserSeason.WatchStatus.WATCHED,
    "plan": UserSeason.WatchStatus.PLAN,
    "skip": UserSeason.WatchStatus.SKIP,
}

WATCH_STATUS_TO_KEY = {
    UserSeason.WatchStatus.WATCHED: "watched",
    UserSeason.WatchStatus.PLAN: "plan",
    UserSeason.WatchStatus.SKIP: "skip",
}


class _UnsetType:
    """Sentinel: поле не было прислано в PATCH-запросе."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self):
        return "UNSET"

    def __bool__(self):
        return False


UNSET = _UnsetType()


# ------------------------------------ #
#          APPLICATION LAYER           #
# ------------------------------------ #


class SeasonStatusService:
    """
    Service for managing per-user season watch status and ratings.
    Keeps Season/Episode models clean — user state lives only in UserSeason.
    """

    @staticmethod
    def get_season_state(user, season: Season) -> dict:
        obj = UserSeason.objects.filter(user=user, season=season).first()
        if not obj:
            return {"watch_status": None, "rating": None, "note": ""}
        return {
            "watch_status": WATCH_STATUS_TO_KEY.get(obj.watch_status),
            "rating": obj.rating,
            "note": obj.note,
        }

    @staticmethod
    @transaction.atomic
    def set_season_status(
        user,
        season: Season,
        watch_status: str | None | type(UNSET) = UNSET,
        rating: int | None | type(UNSET) = UNSET,
        note: str | None | type(UNSET) = UNSET,
    ) -> UserSeason:
        obj, _ = UserSeason.objects.get_or_create(user=user, season=season)
        if watch_status is not UNSET:
            if watch_status in (None, ""):
                obj.watch_status = None
            else:
                mapped = STATUS_TO_WATCH_STATUS.get(watch_status)
                if mapped is None:
                    raise ValueError(f"Неизвестный статус: {watch_status}")
                obj.watch_status = mapped
        if rating is not UNSET:
            if rating is None:
                obj.rating = None
            elif rating < 1 or rating > 10:
                raise ValueError("Оценка должна быть от 1 до 10")
            else:
                obj.rating = rating
        if note is not UNSET:
            obj.note = note
        obj.save(update_fields=["watch_status", "rating", "note"])
        return obj

    @staticmethod
    @transaction.atomic
    def sync_statuses_from_user_movie(user, movie, watch_status_key: str | None) -> int:
        """
        Create UserSeason rows for all seasons of *movie* based on the user's
        UserMovie watch_status. Called after TMDB sync loads seasons.
        Returns count of created UserSeason rows.
        """
        if not watch_status_key:
            return 0

        target_status = STATUS_TO_WATCH_STATUS.get(watch_status_key)
        if target_status is None:
            return 0

        seasons_qs = movie.seasons.all()
        created = 0
        for season in seasons_qs:
            obj, was_created = UserSeason.objects.get_or_create(
                user=user,
                season=season,
                defaults={"watch_status": target_status},
            )
            if was_created:
                created += 1
        return created
