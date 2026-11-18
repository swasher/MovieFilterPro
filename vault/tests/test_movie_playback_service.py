"""Запуск фильма во внешнем плеере: маппинг путей Plex → UNC и токены mfp://."""

from urllib.parse import parse_qs, urlparse

from django.core import signing
from django.test import Client, SimpleTestCase, TestCase
from django.utils import timezone

from core.models import UserPreferences
from plex.models import PlexLibraryItem
from vault.models import Movie
from vault.services.movie_playback_service import (
    REASON_DISABLED,
    REASON_NO_PATH_RULES,
    REASON_NOT_IN_PLEX,
    TOKEN_SALT,
    MoviePlaybackService,
    map_path,
    parse_path_rules,
    read_launch_token,
    sign_launch_token,
)

RULES_RAW = r"""
# комментарий и пустая строка ниже игнорируются
/share/Movies => \\qnap\Movies
/share/CACHEDEV3_DATA/Review => \\qnap\Review
"""


class PathRuleParsingTests(SimpleTestCase):
    def test_ignores_comments_and_blank_lines(self):
        rules = parse_path_rules(RULES_RAW)

        self.assertEqual(len(rules), 2)
        self.assertEqual(rules[0].source, "/share/CACHEDEV3_DATA/Review")

    def test_lines_without_arrow_are_skipped(self):
        self.assertEqual(parse_path_rules("/share/Movies без стрелки"), [])

    def test_longest_prefix_wins_regardless_of_order(self):
        rules = parse_path_rules(
            "/share => \\\\qnap\\share\n"
            "/share/CACHEDEV3_DATA/Review => \\\\qnap\\Review"
        )

        self.assertEqual(
            map_path("/share/CACHEDEV3_DATA/Review/Film.mkv", rules),
            r"\\qnap\Review\Film.mkv",
        )


class MapPathTests(SimpleTestCase):
    def setUp(self):
        self.rules = parse_path_rules(RULES_RAW)

    def test_maps_file_inside_share(self):
        self.assertEqual(
            map_path("/share/Movies/Two.Words.2020.mkv", self.rules),
            r"\\qnap\Movies\Two.Words.2020.mkv",
        )

    def test_keeps_unicode_and_spaces(self):
        self.assertEqual(
            map_path("/share/Movies/Альпы (2011) BDRemux 1080p.mkv", self.rules),
            r"\\qnap\Movies\Альпы (2011) BDRemux 1080p.mkv",
        )

    def test_maps_nested_directories(self):
        self.assertEqual(
            map_path("/share/CACHEDEV3_DATA/Review/2026/Film.mkv", self.rules),
            r"\\qnap\Review\2026\Film.mkv",
        )

    def test_unknown_prefix_returns_none(self):
        self.assertIsNone(map_path("/share/TVShow/Show/S01E01.mkv", self.rules))

    def test_prefix_equal_to_directory_is_not_a_file(self):
        self.assertIsNone(map_path("/share/Movies", self.rules))
        self.assertIsNone(map_path("/share/Movies/", self.rules))


class LaunchTokenTests(SimpleTestCase):
    def test_roundtrip(self):
        token = sign_launch_token("some-movie-2020")

        self.assertEqual(read_launch_token(token), "some-movie-2020")

    def test_expired_token_is_rejected(self):
        token = sign_launch_token("some-movie-2020")

        self.assertIsNone(read_launch_token(token, max_age=-1))

    def test_tampered_token_is_rejected(self):
        token = sign_launch_token("some-movie-2020")
        tampered = token.replace("some-movie-2020", "another-movie")

        self.assertIsNone(read_launch_token(tampered))

    def test_salt_is_required(self):
        foreign = signing.TimestampSigner(salt="other.salt").sign("some-movie-2020")

        self.assertIsNone(read_launch_token(foreign))
        self.assertNotEqual(TOKEN_SALT, "other.salt")


class PlaybackSeedingMixin:
    def seed_preferences(self, *, enabled: bool = True, path_map: str = RULES_RAW):
        preferences = UserPreferences.get()
        preferences.player_enabled = enabled
        preferences.player_path_map = path_map
        preferences.save()
        return preferences

    def seed_movie(self, *, title: str = "Play Test", plex_path: str | None = None) -> Movie:
        movie = Movie.objects.create(title=title, year=2020)
        if plex_path is not None:
            PlexLibraryItem.objects.create(
                rating_key=f"rk-{movie.pk}",
                media_type=PlexLibraryItem.MediaType.MOVIE,
                section="Movies",
                title=title,
                file_path=plex_path,
                file_name=plex_path.rsplit("/", 1)[-1],
                last_seen_at=timezone.now(),
                vault_movie=movie,
            )
        return movie


class PlaybackResolveTests(PlaybackSeedingMixin, TestCase):
    def test_resolves_unc_path_from_plex(self):
        self.seed_preferences()
        movie = self.seed_movie(plex_path="/share/Movies/Play.Test.2020.mkv")

        resolution = MoviePlaybackService.resolve(movie)

        self.assertTrue(resolution.available)
        self.assertEqual(resolution.target.unc_path, r"\\qnap\Movies\Play.Test.2020.mkv")
        self.assertEqual(resolution.target.file_name, "Play.Test.2020.mkv")

    def test_disabled_flag_reports_reason(self):
        self.seed_preferences(enabled=False)
        movie = self.seed_movie(plex_path="/share/Movies/Play.Test.2020.mkv")

        resolution = MoviePlaybackService.resolve(movie)

        self.assertFalse(resolution.available)
        self.assertEqual(resolution.reason, REASON_DISABLED)

    def test_empty_mapping_reports_reason(self):
        self.seed_preferences(path_map="")
        movie = self.seed_movie(plex_path="/share/Movies/Play.Test.2020.mkv")

        resolution = MoviePlaybackService.resolve(movie)

        self.assertFalse(resolution.available)
        self.assertEqual(resolution.reason, REASON_NO_PATH_RULES)

    def test_movie_without_plex_reports_reason(self):
        self.seed_preferences()
        movie = self.seed_movie()

        resolution = MoviePlaybackService.resolve(movie)

        self.assertFalse(resolution.available)
        self.assertEqual(resolution.reason, REASON_NOT_IN_PLEX)

    def test_unmapped_path_shows_path_in_reason(self):
        self.seed_preferences()
        movie = self.seed_movie(plex_path="/share/Unknown/Film.mkv")

        resolution = MoviePlaybackService.resolve(movie)

        self.assertFalse(resolution.available)
        self.assertIn("/share/Unknown/Film.mkv", resolution.reason)

    def test_show_item_is_ignored(self):
        self.seed_preferences()
        movie = self.seed_movie()
        PlexLibraryItem.objects.create(
            rating_key="show-1",
            media_type=PlexLibraryItem.MediaType.SHOW,
            section="TVShow",
            title="Show",
            file_path="/share/TVShow/Show",
            last_seen_at=timezone.now(),
            vault_movie=movie,
        )

        self.assertFalse(MoviePlaybackService.resolve(movie).available)

    def test_launch_url_uses_scheme_and_signed_token(self):
        url = MoviePlaybackService.build_launch_url("play-test-2020")

        self.assertTrue(url.startswith("mfp://play-test-2020?t="))
        # Токен в ссылке percent-encoded — сервер получает его уже раскодированным.
        query = parse_qs(urlparse(url).query)
        self.assertEqual(read_launch_token(query["t"][0]), "play-test-2020")


class PlaybackTargetEndpointTests(PlaybackSeedingMixin, TestCase):
    def setUp(self):
        self.client = Client()
        self.seed_preferences()
        self.movie = self.seed_movie(plex_path="/share/Movies/Play.Test.2020.mkv")
        self.url = f"/api/vault/playback-target/{self.movie.slug}"

    def _token(self, slug: str | None = None) -> str:
        return sign_launch_token(slug or self.movie.slug)

    def test_valid_token_returns_unc_path(self):
        response = self.client.get(self.url, {"t": self._token()})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["unc_path"], r"\\qnap\Movies\Play.Test.2020.mkv")
        self.assertEqual(payload["movie_slug"], self.movie.slug)
        self.assertEqual(payload["source_path"], "/share/Movies/Play.Test.2020.mkv")

    def test_missing_token_is_forbidden(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_token_of_another_movie_is_forbidden(self):
        other = self.seed_movie(title="Other Movie", plex_path="/share/Movies/Other.mkv")

        response = self.client.get(self.url, {"t": self._token(other.slug)})

        self.assertEqual(response.status_code, 403)

    def test_unknown_movie_is_not_found(self):
        response = self.client.get("/api/vault/playback-target/ghost-movie", {"t": self._token("ghost-movie")})

        self.assertEqual(response.status_code, 404)

    def test_movie_without_playable_path_conflicts(self):
        movie = self.seed_movie(title="No Plex Movie")

        response = self.client.get(
            f"/api/vault/playback-target/{movie.slug}",
            {"t": self._token(movie.slug)},
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("Plex", response.json()["detail"])

    def test_movie_detail_exposes_playback(self):
        response = self.client.get(f"/api/vault/movies/{self.movie.slug}")

        self.assertEqual(response.status_code, 200)
        playback = response.json()["playback"]
        self.assertTrue(playback["available"])
        self.assertTrue(playback["url"].startswith(f"mfp://{self.movie.slug}?t="))
