import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(ROOT))

from app import connect_database, create_app


def migrate_lowercase(database_path=None):
    app = create_app()
    database = Path(database_path) if database_path is not None else Path(app.config["DATABASE"])
    connection = connect_database(database)
    try:
        rows = connection.execute("SELECT id, english, vietnamese FROM vocabulary").fetchall()
        connection.executemany(
            "UPDATE vocabulary SET english = %s, vietnamese = %s WHERE id = %s",
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
