from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from vault.models import Collection, Movie, Person
from vault.services.image_service import ImageService


class ImageServiceUrlTests(SimpleTestCase):
    def test_relative_path_maps_to_internal_endpoint(self):
        self.assertEqual(
            ImageService.url("/poster.jpg"),
            "/api/vault/images/poster/w500/poster.jpg",
        )

    def test_path_without_leading_slash_is_normalized(self):
        self.assertEqual(
            ImageService.url("poster.jpg"),
            "/api/vault/images/poster/w500/poster.jpg",
        )

    def test_absolute_tmdb_url_is_unwrapped(self):
        self.assertEqual(
            ImageService.url("https://image.tmdb.org/t/p/w342/poster.jpg"),
            "/api/vault/images/poster/w500/poster.jpg",
        )

    def test_absolute_tmdb_url_respects_requested_size_and_kind(self):
        self.assertEqual(
            ImageService.url("https://image.tmdb.org/t/p/w500/profile.jpg", "original", kind="profile"),
            "/api/vault/images/profile/original/profile.jpg",
        )

    def test_foreign_absolute_url_is_not_proxied(self):
        self.assertEqual(
            ImageService.url("https://example.com/custom.jpg"),
            "https://example.com/custom.jpg",
        )

    def test_static_and_media_urls_are_returned_as_is(self):
        self.assertEqual(ImageService.url("/static/img/custom.jpg"), "/static/img/custom.jpg")
        self.assertEqual(ImageService.url("/media/posters/custom.jpg"), "/media/posters/custom.jpg")

    def test_empty_path_returns_none(self):
        self.assertIsNone(ImageService.url(None))
        self.assertIsNone(ImageService.url(""))
        self.assertIsNone(ImageService.url("   "))

    def test_unknown_size_falls_back_to_default(self):
        self.assertEqual(
            ImageService.url("/poster.jpg", "huge"),
            "/api/vault/images/poster/w500/poster.jpg",
        )

    def test_unknown_kind_falls_back_to_poster(self):
        self.assertEqual(
            ImageService.url("/poster.jpg", kind="unknown"),
            "/api/vault/images/poster/w500/poster.jpg",
        )

    def test_source_url_is_built_from_tmdb_base(self):
        self.assertEqual(
            ImageService.source_url("w500", "/poster.jpg"),
            "https://image.tmdb.org/t/p/w500/poster.jpg",
        )

    def test_placeholder_depends_on_kind(self):
        self.assertEqual(
            ImageService.placeholder_url("profile"),
            "/static/img/profile-placeholder.svg",
        )
        self.assertEqual(
            ImageService.placeholder_url("backdrop"),
            "/static/img/backdrop-placeholder.svg",
        )


class ImageServiceModelContractTests(SimpleTestCase):
    def test_movie_poster_property_uses_internal_endpoint(self):
        movie = Movie(poster="/poster.jpg")

        self.assertEqual(movie.poster_url, "/api/vault/images/poster/w500/poster.jpg")
        self.assertEqual(
            movie.get_poster_url("original"),
            "/api/vault/images/poster/original/poster.jpg",
        )
        self.assertEqual(
            movie.backdrop_url,
            None,
        )

    def test_person_photo_property_uses_profile_endpoint(self):
        person = Person(photo="/profile.jpg")

        self.assertEqual(person.photo_url, "/api/vault/images/profile/w500/profile.jpg")
        self.assertEqual(
            person.get_photo_url("original"),
            "/api/vault/images/profile/original/profile.jpg",
        )

    def test_collection_backdrop_uses_backdrop_endpoint(self):
        collection = Collection(backdrop_path="/backdrop.jpg")

        self.assertEqual(
            collection.backdrop_url,
            "/api/vault/images/backdrop/w1280/backdrop.jpg",
        )


class ImageServiceCacheLocationTests(SimpleTestCase):
    def test_cache_lives_under_cache_root_not_media_root(self):
        cache = ImageService._get_cache("poster", "w500")

        self.assertEqual(
            cache.root,
            Path(settings.CACHE_ROOT) / "vault" / "poster" / "w500",
        )
        self.assertTrue(cache.root.is_relative_to(settings.CACHE_ROOT))
        self.assertFalse(cache.root.is_relative_to(settings.MEDIA_ROOT))


class ImageServiceValidationTests(SimpleTestCase):
    def test_accepts_valid_request(self):
        self.assertTrue(ImageService.is_valid_request("poster", "w500", "poster.jpg"))
        self.assertTrue(ImageService.is_valid_request("profile", "original", "abc/def.jpg"))

    def test_rejects_unknown_kind_or_size(self):
        self.assertFalse(ImageService.is_valid_request("actor", "w500", "poster.jpg"))
        self.assertFalse(ImageService.is_valid_request("poster", "w999", "poster.jpg"))

    def test_rejects_path_traversal(self):
        self.assertFalse(ImageService.is_valid_request("poster", "w500", "../secret.jpg"))
        self.assertFalse(ImageService.is_valid_request("poster", "w500", "a/../../secret.jpg"))
        self.assertFalse(ImageService.is_valid_request("poster", "w500", "a/./b.jpg"))
        self.assertFalse(ImageService.is_valid_request("poster", "w500", "a//b.jpg"))

    def test_rejects_unsafe_characters(self):
        self.assertFalse(ImageService.is_valid_request("poster", "w500", "a\\b.jpg"))
        self.assertFalse(ImageService.is_valid_request("poster", "w500", "https://example.com/a.jpg"))
        self.assertFalse(ImageService.is_valid_request("poster", "w500", "a b.jpg"))

    def test_rejects_empty_and_too_long_paths(self):
        self.assertFalse(ImageService.is_valid_request("poster", "w500", ""))
        self.assertFalse(ImageService.is_valid_request("poster", "w500", "a" * 513))
