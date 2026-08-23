# FTS5 full-text index for Movie (case-insensitive Unicode search).
# Only created on SQLite. On Postgres, search falls back to ILIKE via FTSMovieSearchService.is_available().

from django.db import migrations


FTS_SQL = """
CREATE VIRTUAL TABLE movie_fts USING fts5(
    title,
    original_title,
    description,
    content='vault_movie',
    content_rowid='id',
    tokenize='unicode61'
);

CREATE TRIGGER movie_fts_ai AFTER INSERT ON vault_movie BEGIN
    INSERT INTO movie_fts(rowid, title, original_title, description)
    VALUES (new.id, new.title, new.original_title, new.description);
END;

CREATE TRIGGER movie_fts_ad AFTER DELETE ON vault_movie BEGIN
    INSERT INTO movie_fts(movie_fts, rowid, title, original_title, description)
    VALUES ('delete', old.id, old.title, old.original_title, old.description);
END;

CREATE TRIGGER movie_fts_au AFTER UPDATE ON vault_movie BEGIN
    INSERT INTO movie_fts(movie_fts, rowid, title, original_title, description)
    VALUES ('delete', old.id, old.title, old.original_title, old.description);
    INSERT INTO movie_fts(rowid, title, original_title, description)
    VALUES (new.id, new.title, new.original_title, new.description);
END;

INSERT INTO movie_fts(rowid, title, original_title, description)
    SELECT id, title, original_title, description FROM vault_movie;
"""

REVERSE_SQL = """
DROP TRIGGER IF EXISTS movie_fts_ai;
DROP TRIGGER IF EXISTS movie_fts_ad;
DROP TRIGGER IF EXISTS movie_fts_au;
DROP TABLE IF EXISTS movie_fts;
"""


def create_fts_sqlite(apps, schema_editor):
    """Create FTS5 virtual table and triggers only on SQLite."""
    if schema_editor.connection.vendor != 'sqlite':
        return
    with schema_editor.connection.cursor() as cursor:
        for statement in FTS_SQL.strip().split(';'):
            stmt = statement.strip()
            if stmt:
                cursor.execute(stmt)


def reverse_fts_sqlite(apps, schema_editor):
    """Drop FTS5 table and triggers only on SQLite."""
    if schema_editor.connection.vendor != 'sqlite':
        return
    with schema_editor.connection.cursor() as cursor:
        for statement in REVERSE_SQL.strip().split(';'):
            stmt = statement.strip()
            if stmt:
                cursor.execute(stmt)


class Migration(migrations.Migration):

    dependencies = [
        ('vault', '0025_sidebar_layout'),
    ]

    operations = [
        migrations.RunPython(
            code=create_fts_sqlite,
            reverse_code=reverse_fts_sqlite,
        ),
    ]