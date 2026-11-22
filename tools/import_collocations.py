"""Import reviewed English/Vietnamese pairs; no AI calls."""
import argparse
import sqlite3
import sys
import unicodedata
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
if __package__ in {None, ""}:
    sys.path.insert(0, str(ROOT))

from app import connect_database, create_app, local_now, required_text


def parse_collocations(content):
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines or len(lines) % 2:
        raise ValueError("File phải có đủ cặp dòng cụm tiếng Anh / nghĩa tiếng Việt.")
    return [(required_text(english, "Cụm tiếng Anh"), required_text(vietnamese, "Nghĩa tiếng Việt"))
            for english, vietnamese in zip(lines[::2], lines[1::2])]


def import_collocations(input_path=TOOLS / "output_collocations.txt", database_path=ROOT / "instance" / "vocabulary.sqlite3"):
    entries = parse_collocations(Path(input_path).read_text(encoding="utf-8-sig"))
    create_app({"TESTING": True, "DATABASE": database_path})
    db = connect_database(database_path)
    try:
        existing = {unicodedata.normalize("NFC", row["english"]).casefold()
                    for row in db.execute("SELECT english FROM collocations")}
        db.execute("BEGIN IMMEDIATE")
        inserted = 0
        now = local_now().isoformat()
        for english, vietnamese in entries:
            english = unicodedata.normalize("NFC", english)
            if english.casefold() in existing:
                continue
            db.execute("INSERT INTO collocations (english, vietnamese, repetition_level, practice_count, next_review_at) VALUES (%s, %s, 0, 0, %s)",
                       (english.lower(), vietnamese.lower(), now))
            existing.add(english.casefold())
            inserted += 1
        db.commit()
        return inserted, len(entries) - inserted
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=TOOLS / "output_collocations.txt")
    parser.add_argument("--database", type=Path, default=ROOT / "instance" / "vocabulary.sqlite3")
    args = parser.parse_args(argv)
    try:
        inserted, skipped = import_collocations(args.input, args.database)
        print(f"Imported {inserted} collocations; skipped {skipped} existing.")
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"Import failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
