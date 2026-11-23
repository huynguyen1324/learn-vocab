import re
import sqlite3
import sys

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(ROOT))

from app import synonym_patterns

SOURCE = ROOT / "tools" / "synonymous_collocations.md"
DATABASE = ROOT / "instance" / "vocabulary.sqlite3"
ENTRY = re.compile(r"^\d+$")


def parse_synonymous_collocations(text):
    lines = text.splitlines()
    entries = []
    index = 0
    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue
        if not ENTRY.fullmatch(lines[index].strip()):
            raise ValueError(f"Dòng {index + 1}: cần số thứ tự entry.")
        entry_line = index + 1
        index += 1
        fields = []
        while index < len(lines) and not ENTRY.fullmatch(lines[index].strip()):
            if lines[index].strip():
                fields.append((lines[index].strip(), index + 1))
            index += 1
        if len(fields) < 2:
            raise ValueError(f"Entry tại dòng {entry_line}: thiếu english hoặc synonym.")
        english, synonym = fields[0][0].lower(), fields[1][0].lower()
        vietnamese = fields[2][0] if len(fields) > 2 else ""
        if not vietnamese.strip():
            raise ValueError(f"Entry tại dòng {entry_line}: thiếu nghĩa tiếng Việt.")
        entries.append((english, synonym, vietnamese.lower()))
    return entries


def import_synonymous_collocations(source=SOURCE, database=DATABASE):
    entries = parse_synonymous_collocations(Path(source).read_text(encoding="utf-8-sig"))
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("""CREATE TABLE IF NOT EXISTS synonymous_collocations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            english TEXT NOT NULL,
            synonym TEXT NOT NULL,
            vietnamese TEXT NOT NULL DEFAULT '',
            repetition_level INTEGER NOT NULL DEFAULT 0 CHECK (repetition_level BETWEEN 0 AND 8),
            practice_count INTEGER NOT NULL DEFAULT 0 CHECK (practice_count >= 0),
            next_review_at TEXT,
            english_pattern TEXT NOT NULL DEFAULT '',
            synonym_pattern TEXT NOT NULL DEFAULT '',
            UNIQUE (english COLLATE NOCASE, synonym COLLATE NOCASE)
        )""")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(synonymous_collocations)")}
        if "vietnamese" not in columns:
            connection.execute("ALTER TABLE synonymous_collocations ADD COLUMN vietnamese TEXT NOT NULL DEFAULT ''")
        if "english_pattern" not in columns:
            connection.execute("ALTER TABLE synonymous_collocations ADD COLUMN english_pattern TEXT NOT NULL DEFAULT ''")
        if "synonym_pattern" not in columns:
            connection.execute("ALTER TABLE synonymous_collocations ADD COLUMN synonym_pattern TEXT NOT NULL DEFAULT ''")
        for row in connection.execute("SELECT id, english, synonym FROM synonymous_collocations").fetchall():
            english_pattern, synonym_pattern = synonym_patterns(row["english"], row["synonym"])
            connection.execute("UPDATE synonymous_collocations SET english_pattern = ?, synonym_pattern = ? WHERE id = ?",
                               (english_pattern, synonym_pattern, row["id"]))
        before = connection.total_changes
        connection.executemany(
            "INSERT OR IGNORE INTO synonymous_collocations (english, synonym, vietnamese, english_pattern, synonym_pattern, repetition_level, practice_count) VALUES (?, ?, ?, ?, ?, 0, 0)",
            [(english, synonym, vietnamese, *synonym_patterns(english, synonym)) for english, synonym, vietnamese in entries],
        )
        imported = connection.total_changes - before
        connection.commit()
        return imported, len(entries) - imported
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    try:
        imported, skipped = import_synonymous_collocations()
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"Lỗi import: {error}", file=sys.stderr)
        sys.exit(1)
    print(f"Đã nhập {imported} cặp; bỏ qua {skipped} cặp trùng.")
