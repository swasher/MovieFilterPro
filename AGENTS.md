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

## Search Discipline
- Use `rg`/`rg --files` for codebase search so `.rgignore` is respected.
- Do not run repository-wide recursive listing commands like `Get-ChildItem -Recurse` from the repo root unless the user explicitly asks for it.

## Search Tools
- Use `fd` for fast file and directory discovery when it is a better fit than `rg --files`.
- Use `ast-grep` for syntax-aware search/refactoring when regex-based matching is fragile.
