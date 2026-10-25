import hashlib

import bencodepy
from django.test import SimpleTestCase

from qbittorrent.services.metadata import TorrentMetadataError, parse_torrent_metadata


class TorrentMetadataTests(SimpleTestCase):
    def _build_torrent(self, name=b'Test Movie', comment=b'https://kinozal.tv/details.php?id=1'):
        info = {
            b'name': name,
            b'length': 1,
            b'piece length': 1,
            b'pieces': b'0' * 20,
        }
        return bencodepy.encode({b'info': info, b'comment': comment})

    def test_parses_infohash_name_and_comment(self):
        data = self._build_torrent()

        metadata = parse_torrent_metadata(data)

        expected_hash = hashlib.sha1(
            bencodepy.encode(
                {
                    b'name': b'Test Movie',
                    b'length': 1,
                    b'piece length': 1,
                    b'pieces': b'0' * 20,
                }
            )
        ).hexdigest()
        self.assertEqual(metadata.info_hash, expected_hash)
        self.assertEqual(metadata.name, 'Test Movie')
        self.assertEqual(metadata.comment, 'https://kinozal.tv/details.php?id=1')

    def test_rejects_invalid_torrent(self):
        with self.assertRaises(TorrentMetadataError):
            parse_torrent_metadata(b'not-a-torrent')
