import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(ROOT))

from app import connect_database, create_app, sql


def migrate_lowercase(database_path=None):
    app = create_app()
    configured_url = app.config["DATABASE_URL"]
    database_url = f"sqlite:///{Path(database_path).resolve().as_posix()}" if database_path is not None and (configured_url.startswith("sqlite:///") or Path(database_path).exists()) else configured_url
    connection = connect_database(database_url)
    try:
        rows = connection.execute("SELECT id, english, vietnamese FROM vocabulary").fetchall()
        connection.executemany(
            sql("UPDATE vocabulary SET english = %s, vietnamese = %s WHERE id = %s"),
            [(row["english"].lower(), row["vietnamese"].lower(), row["id"]) for row in rows],
        )
        connection.commit()
        return len(rows)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    try:
        print(f"Updated {migrate_lowercase()} vocabulary entries to lowercase.")
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Migration failed: {ascii(error)}", file=sys.stderr)
        raise SystemExit(1)
