class ScanCancelled(Exception):
    """Custom exception raised when scanning cancelling task is called by user from browser (clicked Cancel button)"""
    pass


class DetailsFetchError(Exception):
    """Custom exception for critical errors during movie details fetching."""
    pass
