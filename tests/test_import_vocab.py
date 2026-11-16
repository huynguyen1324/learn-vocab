import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from import_vocab import import_vocabulary, parse_vocabulary
from migrate_lowercase import migrate_lowercase


class VocabularyImportTests(unittest.TestCase):
    def test_parse_pairs_and_preserves_english_line(self):
        entries = parse_vocabulary(
            "According to\n\nTheo như\n\n"
            "Advancement / Advance (n)\n\nSự tiến bộ, bước tiến\n\n"
            "Alert (n)\n\nSự báo động, thông báo\n"
        )
        self.assertEqual(
            entries,
            [
                ("According to", "Theo như"),
                ("Advancement / Advance (n)", "Sự tiến bộ, bước tiến"),
                ("Alert (n)", "Sự báo động, thông báo"),
            ],
        )

    def test_parse_rejects_unpaired_line(self):
        with self.assertRaisesRegex(ValueError, "đủ cặp dòng"):
            parse_vocabulary("word")

    def test_import_is_repeatable_and_preserves_existing_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "words.txt"
            database = Path(directory) / "vocabulary.sqlite3"
            source.write_text("Apple\n\nQuả Táo\n\nBook\n\nQuyển Sách\n", encoding="utf-8")

            self.assertEqual(import_vocabulary(source, database), (2, 0))
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "UPDATE vocabulary SET repetition_count = 4, next_review_at = '2030-01-01T12:00:00' "
                    "WHERE english_key = 'apple'"
                )
                connection.commit()

            self.assertEqual(import_vocabulary(source, database), (0, 2))
            with closing(sqlite3.connect(database)) as connection:
                rows = connection.execute(
                    "SELECT english, repetition_count, next_review_at FROM vocabulary ORDER BY english"
                ).fetchall()
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0], ("apple", 4, "2030-01-01T12:00:00"))
            self.assertEqual(rows[1][0], "book")

    def test_migration_lowercases_existing_unicode_text_and_preserves_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "legacy.sqlite3"
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "CREATE TABLE vocabulary (id INTEGER PRIMARY KEY, english TEXT NOT NULL, "
                    "english_key TEXT NOT NULL UNIQUE, vietnamese TEXT NOT NULL, "
                    "stage INTEGER NOT NULL, next_review_at TEXT)"
                )
                connection.execute(
                    "INSERT INTO vocabulary VALUES (1, 'Apple', 'apple', 'TRÁI TÁO', 4, '2030-01-01T12:00:00')"
                )
                connection.commit()
            self.assertEqual(migrate_lowercase(database), 1)
            with closing(sqlite3.connect(database)) as connection:
                row = connection.execute(
                    "SELECT english, vietnamese, repetition_count, next_review_at FROM vocabulary"
                ).fetchone()
            self.assertEqual(row, ("apple", "trái táo", 3, "2030-01-01T12:00:00"))


if __name__ == "__main__":
    unittest.main()
