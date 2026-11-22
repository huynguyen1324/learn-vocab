import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(ROOT))

from app import connect_database, local_now, required_text, sql

INPUT_PATH = ROOT / "tools" / "toeic_vocab.md"
DATABASE_PATH = ROOT / "instance" / "vocabulary.sqlite3"


def parse_toeic_vocab(text):
    """Parse toeic_vocab.md.

    Lines containing ':' are word entries:  English (with part-of-speech) : Vietnamese.
    Lines without ':' are category headers and are skipped.
    """
    entries = []
    seen = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        english, vietnamese = line.split(":", 1)
        english = required_text(english.strip(), "Từ tiếng Anh").lower()
        vietnamese = required_text(vietnamese.strip(), "Nghĩa tiếng Việt").lower()
        key = english.casefold()
        if key not in seen:
            seen.add(key)
            entries.append((english, vietnamese))
    if not entries:
        raise ValueError("File không có từ vựng nào hợp lệ.")
    return entries


SCHEMA_VOCABULARY = """
CREATE TABLE IF NOT EXISTS vocabulary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    english TEXT NOT NULL,
    vietnamese TEXT NOT NULL,
    repetition_level INTEGER NOT NULL DEFAULT 0 CHECK (repetition_level BETWEEN 0 AND 8),
    practice_count INTEGER NOT NULL DEFAULT 0 CHECK (practice_count >= 0),
    next_review_at TEXT
);
"""


def import_vocabulary(input_path=INPUT_PATH, database_path=None):
    entries = parse_toeic_vocab(Path(input_path).read_text(encoding="utf-8-sig"))

    if database_path is None:
        from app import create_app
        app = create_app()
        database_url = app.config["DATABASE_URL"]
    else:
        database_url = f"sqlite:///{Path(database_path).resolve().as_posix()}"

    connection = connect_database(database_url)
    try:
        now = local_now().isoformat()
        if database_url.startswith("sqlite:///"):
            connection.executescript(SCHEMA_VOCABULARY)
            connection.execute("BEGIN IMMEDIATE")
        else:
            connection.execute("BEGIN")
        try:
            connection.execute("DELETE FROM vocabulary")
            if database_url.startswith("sqlite:///"):
                connection.executescript("CREATE TABLE IF NOT EXISTS review_receipts (word_id INTEGER PRIMARY KEY, request_json TEXT NOT NULL, response_json TEXT NOT NULL); CREATE TABLE IF NOT EXISTS review_round_words (word_id INTEGER PRIMARY KEY, choice_ids TEXT, shown INTEGER NOT NULL DEFAULT 0, answered INTEGER NOT NULL DEFAULT 0);")
            connection.execute("DELETE FROM review_receipts")
            connection.execute("DELETE FROM review_round_words")
            if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='review_state'").fetchone():
                connection.execute("UPDATE review_state SET round_id = NULL, round_kind = NULL, round_mode = NULL WHERE singleton = 1")
            connection.executemany(
                "INSERT INTO vocabulary "
                "(english, vietnamese, repetition_level, practice_count, next_review_at) "
                "VALUES (%s, %s, 0, 0, %s)" if not database_url.startswith("sqlite:///") else
                "INSERT INTO vocabulary (english, vietnamese, repetition_level, practice_count, next_review_at) VALUES (?, ?, 0, 0, ?)",
                [(english, vietnamese, now) for english, vietnamese in entries],
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        return len(entries), 0
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
