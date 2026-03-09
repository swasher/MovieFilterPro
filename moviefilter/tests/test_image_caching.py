from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from movie_filter_pro.settings import HIGH
from moviefilter.image_caching import (
    download_and_cache_image,
    get_cached_image_url,
    get_placeholder_image_url,
)


class ImageCachingTests(SimpleTestCase):
    def test_returns_placeholder_when_image_is_missing(self):
        with TemporaryDirectory() as temp_dir:
            cache_root = Path(temp_dir)
            response = Mock()
            response.raise_for_status.side_effect = __import__("requests").exceptions.HTTPError(
                response=Mock(status_code=404)
            )

            with override_settings(
                CACHE_ROOT=cache_root,
                CACHE_URL="/media/cached_images/",
                STATIC_URL="/static/",
            ):
                with patch("moviefilter.image_caching.requests.get", return_value=response):
                    download_and_cache_image("https://kinozal.guru/i/poster/9/5/1304395.jpg", 42, HIGH)

                poster_url = get_cached_image_url(
                    "https://kinozal.guru/i/poster/9/5/1304395.jpg",
                    42,
                    HIGH,
                )

        self.assertEqual(poster_url, get_placeholder_image_url())
