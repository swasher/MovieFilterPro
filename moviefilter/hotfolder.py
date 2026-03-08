import os
from pathlib import Path


def resolve_torrents_hotfolder_path(configured_path: str) -> Path:
    raw_path = (configured_path or "").strip()
    if not raw_path:
        raise ValueError("Hotfolder path is empty.")

    expanded_path = os.path.expandvars(os.path.expanduser(raw_path))

    if os.name == "nt" and expanded_path.startswith("/") and not expanded_path.startswith("//"):
        current_dir = Path.cwd()
        drive_root = Path(current_dir.anchor or f"{current_dir.drive}\\")
        windows_relative_path = expanded_path.lstrip("/").replace("/", os.sep)
        return drive_root / windows_relative_path

    return Path(expanded_path)
