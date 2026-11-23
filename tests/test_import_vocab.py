import sqlite3
import tempfile
import unittest
from pathlib import Path

from tools.import_toeic_vocab import import_vocabulary, parse_toeic_vocab


class ImportVocabularyTests(unittest.TestCase):
    def test_parser_lowercases_and_keeps_first_english_duplicate(self):
        self.assertEqual(parse_toeic_vocab(
            "Category\nApple: Fruit\napple: Another fruit\nBook: Paper object"
        ), [("apple", "fruit"), ("book", "paper object")])

    def test_import_replaces_rows_and_resets_progress(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory:
            root = Path(directory)
            source = root / "vocab.md"
            database = root / "vocab.sqlite3"
            source.write_text("APPLE: Apple fruit\napple: Duplicate fruit\nBook: Paper object", encoding="utf-8")
            connection = sqlite3.connect(database)
            connection.execute("CREATE TABLE vocabulary (id INTEGER PRIMARY KEY, english TEXT NOT NULL, vietnamese TEXT NOT NULL, repetition_level INTEGER NOT NULL DEFAULT 0, practice_count INTEGER NOT NULL DEFAULT 0, next_review_at TEXT)")
            connection.execute("INSERT INTO vocabulary VALUES (1, 'old', 'old', 6, 12, '2030-01-01')")
            connection.commit()
            connection.close()
            self.assertEqual(import_vocabulary(source, database), (2, 0))
            connection = sqlite3.connect(database)
            rows = connection.execute("SELECT english, vietnamese, repetition_level, practice_count, next_review_at FROM vocabulary ORDER BY id").fetchall()
            self.assertEqual([(row[0], row[1], row[2], row[3]) for row in rows], [("apple", "apple fruit", 0, 0), ("book", "paper object", 0, 0)])
            self.assertTrue(all(row[4] for row in rows))
            connection.close()

    def test_invalid_source_does_not_clear_existing_data(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory:
            root = Path(directory)
            source = root / "vocab.md"
            database = root / "vocab.sqlite3"
            source.write_text("Only headings", encoding="utf-8")
            connection = sqlite3.connect(database)
            connection.execute("CREATE TABLE vocabulary (id INTEGER PRIMARY KEY, english TEXT, vietnamese TEXT, repetition_level INTEGER DEFAULT 0, practice_count INTEGER DEFAULT 0, next_review_at TEXT)")
            connection.execute("INSERT INTO vocabulary (english, vietnamese) VALUES ('keep', 'keep')")
            connection.commit()
            connection.close()
            with self.assertRaises(ValueError):
                import_vocabulary(source, database)
            connection = sqlite3.connect(database)
            self.assertEqual(connection.execute("SELECT english FROM vocabulary").fetchall(), [("keep",)])
            connection.close()


if __name__ == "__main__":
    unittest.main()
