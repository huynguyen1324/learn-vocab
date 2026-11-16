import sqlite3
import sys
from pathlib import Path

from app import create_app, local_now


ROOT = Path(__file__).resolve().parent
INPUT_PATH = ROOT / "input_vocab.txt"
DATABASE_PATH = ROOT / "instance" / "vocabulary.sqlite3"


def parse_vocabulary(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("File không có từ vựng.")
    if len(lines) % 2:
        raise ValueError("File phải có đủ cặp dòng tiếng Anh / nghĩa tiếng Việt.")
    return list(zip(lines[::2], lines[1::2]))


def import_vocabulary(input_path=INPUT_PATH, database_path=DATABASE_PATH):
    entries = parse_vocabulary(Path(input_path).read_text(encoding="utf-8-sig"))
    create_app({"DATABASE": str(database_path)})

    connection = sqlite3.connect(database_path)
    try:
        now = local_now().isoformat()
        with connection:
            connection.executemany(
                "INSERT INTO vocabulary "
                "(english, english_key, vietnamese, repetition_count, next_review_at) "
                "VALUES (?, ?, ?, 0, ?) "
                "ON CONFLICT(english_key) DO NOTHING",
                [(english.lower(), english.casefold(), vietnamese.lower(), now) for english, vietnamese in entries],
            )
            inserted = connection.total_changes
        return inserted, len(entries) - inserted
    finally:
        connection.close()


def main():
    try:
        inserted, skipped = import_vocabulary()
    except (OSError, UnicodeError, ValueError, sqlite3.Error) as error:
        print(f"Import failed: {ascii(error)}", file=sys.stderr)
        return 1
    print(f"Imported {inserted} words; skipped {skipped} existing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
