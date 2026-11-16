import sqlite3
import sys
from pathlib import Path

from app import create_app


ROOT = Path(__file__).resolve().parent
DATABASE_PATH = ROOT / "instance" / "vocabulary.sqlite3"


def migrate_lowercase(database_path=DATABASE_PATH):
    # create_app applies the stage-to-repetition_count schema migration first.
    create_app({"DATABASE": str(database_path)})
    connection = sqlite3.connect(database_path)
    try:
        with connection:
            rows = connection.execute("SELECT id, english, vietnamese FROM vocabulary").fetchall()
            connection.executemany(
                "UPDATE vocabulary SET english = ?, vietnamese = ? WHERE id = ?",
                [(english.lower(), vietnamese.lower(), word_id) for word_id, english, vietnamese in rows],
            )
        return len(rows)
    finally:
        connection.close()


if __name__ == "__main__":
    try:
        print(f"Updated {migrate_lowercase()} vocabulary entries to lowercase.")
    except (OSError, sqlite3.Error, ValueError) as error:
        print(f"Migration failed: {ascii(error)}", file=sys.stderr)
        raise SystemExit(1)
