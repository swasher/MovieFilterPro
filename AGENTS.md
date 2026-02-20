# Project Agreements

## Vault Data Import
- Assume Vault tables are empty before import.
- No data transfer between legacy Vault schemas is required.

## Deployment Model
- The app is single-user and self-hosted.
- Authentication stays enabled.
- Keep user-related logic and models simple.
- Do not add multi-user collaboration complexity (for example, per-user comment threads is out of scope).

## Management Commands
- Run Django management commands via `uv run python manage.py <command>`.
