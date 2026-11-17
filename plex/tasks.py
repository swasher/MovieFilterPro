from django.db import close_old_connections
from movie_filter_pro.huey import HUEY

from plex.services.plex_link_sync_service import PlexLinkSyncService


@HUEY.task()
def sync_plex_link():
    """Фоновая синхронизация кэша связи Vault <-> Plex."""
    close_old_connections()
    return PlexLinkSyncService.sync()
