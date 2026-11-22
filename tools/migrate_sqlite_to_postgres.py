"""Copy the selected SQLite dataset and learning progress into the configured PostgreSQL database."""
import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(ROOT))

from app import POSTGRES_SCHEMA, create_app


def migrate(source=ROOT / "instance" / "vocabulary.sqlite3", replace=False):
    source = Path(source)
    app = create_app()
    connection = sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"collocations", "vocabulary", "review_state", "review_receipts", "review_round_words"}
        if not required <= tables:
            raise ValueError(f"SQLite source missing tables: {', '.join(sorted(required - tables))}")
        payload = {table: [dict(row) for row in connection.execute(f"SELECT * FROM {table}")] for table in required}
        sqlite_counts = {table: len(payload[table]) for table in required}
    finally:
        connection.close()

    if app.config["DATABASE_URL"].startswith("sqlite:///"):
        raise ValueError("Configured database URL points to SQLite, not PostgreSQL.")
    import psycopg
    with psycopg.connect(app.config["DATABASE_URL"]) as db:
        for statement in POSTGRES_SCHEMA.strip().split(";"):
            if statement.strip():
                db.execute(statement)
        counts = {table: db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                  for table in ("collocations", "vocabulary", "review_state", "review_receipts", "review_round_words")}
        data_tables = ("collocations", "vocabulary")
        if not replace and any(counts[table] for table in data_tables):
            raise ValueError("Postgres vocabulary tables are not empty; inspect them before migrating.")
        if counts["review_state"] and not replace:
            raise ValueError("Postgres review state exists; use --replace only if overwriting is intended.")
        if counts["review_receipts"] or counts["review_round_words"]:
            raise ValueError("Postgres has active review session records; clear/finish that session before migration.")
        with db.transaction():
            for table in ("review_round_words", "review_receipts", "review_state", "vocabulary", "collocations"):
                if replace:
                    db.execute(f"DELETE FROM {table}")
            for table in ("collocations", "vocabulary", "review_state", "review_receipts", "review_round_words"):
                rows = payload[table]
                if not rows:
                    continue
                columns = list(rows[0])
                placeholders = ",".join("%s" for _ in columns)
                col_sql = ",".join(columns)
                db.cursor().executemany(
                    f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders})",
                    [tuple(row[column] for column in columns) for row in rows],
                )
            for table in ("collocations", "vocabulary"):
                db.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE((SELECT MAX(id) FROM {table}), 1), EXISTS (SELECT 1 FROM {table}))")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS collocations_english_unique ON collocations (lower(english))")
        final_counts = {table: db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in ("collocations", "vocabulary", "review_state")}
        if final_counts["collocations"] != sqlite_counts["collocations"] or final_counts["vocabulary"] != sqlite_counts["vocabulary"]:
            raise ValueError(f"Post-migration verification mismatch: source={sqlite_counts}, target={final_counts}")
    return {**final_counts, "source_receipts": sqlite_counts["review_receipts"], "source_round_words": sqlite_counts["review_round_words"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "instance" / "vocabulary.sqlite3")
    parser.add_argument("--replace", action="store_true", help="Replace existing vocabulary/state tables (destructive).")
    args = parser.parse_args(argv)
    try:
        print(migrate(args.source, args.replace))
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"Migration failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
