# FTS5 full-text index for Movie (case-insensitive Unicode search).

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


class Migration(migrations.Migration):

    dependencies = [
        ('vault', '0025_sidebar_layout'),
    ]

    operations = [
        migrations.RunSQL(
            sql=FTS_SQL,
            reverse_sql=REVERSE_SQL,
        ),
    ]