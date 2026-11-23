import sqlite3
import tempfile
import unittest
from pathlib import Path
from datetime import datetime

from app import create_app, synonym_patterns
from tools.import_synonymous_collocations import import_synonymous_collocations, parse_synonymous_collocations


class SynonymousCollocationTests(unittest.TestCase):
    def test_patterns_replace_unique_longest_common_phrase(self):
        self.assertEqual(synonym_patterns("Have a problem with a credit card", "A credit card is not working"),
                         ("Have a problem with ...", "... is not working"))
        self.assertEqual(synonym_patterns("Take a bus", "Catch a bus"), ("Take ...", "Catch ..."))
        self.assertEqual(synonym_patterns("Have a large amount of work to complete", "Have many tasks to finish"),
                         ("Have a large amount of work to complete", "Have many tasks to finish"))
        self.assertEqual(synonym_patterns("The bus arrived", "The train departed"),
                         ("The bus arrived", "The train departed"))
        self.assertEqual(synonym_patterns("a bus, a bus", "a bus"), ("..., ...", "..."))
        self.assertEqual(synonym_patterns("display the award-winning products", "exhibit the award-winning products"),
                         ("display ...", "exhibit ..."))

    def test_parser_reads_all_three_fields_and_lowercases_them(self):
        self.assertEqual(parse_synonymous_collocations("1\n\nTAKE A BUS\n\nCatch a Bus\n\nBẮT XE BUS\n"),
                         [("take a bus", "catch a bus", "bắt xe bus")])

    def test_parser_reports_missing_field(self):
        with self.assertRaisesRegex(ValueError, "dòng 1"):
            parse_synonymous_collocations("1\n\nonly one\n")
        with self.assertRaisesRegex(ValueError, "nghĩa tiếng Việt"):
            parse_synonymous_collocations("1\n\nphrase\n\nsynonym\n")

    def test_import_recalculates_patterns_for_existing_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.md"
            database = Path(tmp) / "db.sqlite3"
            source.write_text("1\n\ndisplay the award-winning products\n\nexhibit the award-winning products\n\ntrưng bày sản phẩm\n", encoding="utf-8")
            self.assertEqual(import_synonymous_collocations(source, database), (1, 0))
            db = sqlite3.connect(database)
            db.execute("UPDATE synonymous_collocations SET english_pattern = english, synonym_pattern = synonym")
            db.commit()
            db.close()
            self.assertEqual(import_synonymous_collocations(source, database), (0, 1))
            db = sqlite3.connect(database)
            try:
                self.assertEqual(db.execute("SELECT english_pattern, synonym_pattern FROM synonymous_collocations").fetchone(),
                                 ("display ...", "exhibit ..."))
            finally:
                db.close()

    def test_import_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.md"
            database = Path(tmp) / "db.sqlite3"
            source.write_text("1\n\nTake a bus\n\nCatch a bus\n\nbắt xe bus\n", encoding="utf-8")
            self.assertEqual(import_synonymous_collocations(source, database), (1, 0))
            self.assertEqual(import_synonymous_collocations(source, database), (0, 1))
            db = sqlite3.connect(database)
            try:
                self.assertEqual(db.execute("SELECT english, synonym, vietnamese FROM synonymous_collocations").fetchall(), [("take a bus", "catch a bus", "bắt xe bus")])
            finally:
                db.close()

    def test_api_crud_and_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app({"TESTING": True, "DATABASE": str(Path(tmp) / "db.sqlite3")})
            client = app.test_client()
            created = client.post("/api/words?table=synonymous_collocations", json={"english": "Take a bus", "synonym": "Catch a bus", "vietnamese": "bắt xe bus"})
            self.assertEqual(created.status_code, 201)
            word_id = created.json["id"]
            self.assertEqual(client.get("/api/words?table=synonymous_collocations").json["words"][0]["synonym"], "catch a bus")
            duplicate = client.post("/api/words?table=synonymous_collocations", json={"english": "TAKE A BUS", "synonym": "CATCH A BUS", "vietnamese": "bắt xe bus"})
            self.assertEqual(duplicate.status_code, 409)
            self.assertEqual(client.get("/api/stats").json["synonymous_collocations_stats"]["total"], 1)
            round_id = client.post("/api/flashcard/start?table=synonymous_collocations").json["round_id"]
            shown = client.post(f"/api/words/{word_id}/practice?table=synonymous_collocations", json={"round_id": round_id})
            self.assertEqual(shown.status_code, 200, shown.json)
            self.assertEqual(client.delete(f"/api/words/{word_id}?table=synonymous_collocations").status_code, 200)

    def test_quiz_distractors_prioritize_same_pattern_group_then_fill_remaining(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app({"TESTING": True, "DATABASE": str(Path(tmp) / "db.sqlite3")})
            client = app.test_client()
            rows = []
            # Target is trailing; four other trailing patterns and four non-trailing patterns.
            for i in range(9):
                english, synonym = f"take a bus {i}", f"catch a bus {i}"
                english_pattern, synonym_pattern = ("take ...", "catch ...") if i < 5 else (english, synonym)
                rows.append((english, synonym, "nghĩa", english_pattern, synonym_pattern, "2000-01-01T00:00:00"))
            db = sqlite3.connect(app.config["DATABASE"])
            db.executemany("INSERT INTO synonymous_collocations (english, synonym, vietnamese, english_pattern, synonym_pattern, next_review_at) VALUES (?, ?, ?, ?, ?, ?)", rows)
            db.commit()
            db.close()
            quiz = client.post("/api/quiz/start?table=synonymous_collocations&mode=av")
            question = next(q for q in quiz.json["questions"] if q["word_id"] == 1)
            choices = {choice["id"]: choice["text"] for choice in question["choices"]}
            same_group_wrong = [text for option_id, text in choices.items() if option_id != 1]
            self.assertEqual(len(choices), 8)
            self.assertEqual(sum(text.startswith("take ...") or text.startswith("catch ...") for text in same_group_wrong), 4)
            self.assertEqual(len(same_group_wrong), 7)

    def test_quiz_uses_stored_patterns_for_prompt_and_all_choices(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app({"TESTING": True, "DATABASE": str(Path(tmp) / "db.sqlite3")})
            client = app.test_client()
            db = sqlite3.connect(app.config["DATABASE"])
            rows = [(f"have {i} common phrase", f"use {i} common phrase", "nghĩa") for i in range(8)]
            db.executemany("INSERT INTO synonymous_collocations (english, synonym, vietnamese, english_pattern, synonym_pattern, next_review_at) VALUES (?, ?, ?, ?, ?, datetime('now','-1 day'))", [(e, s, vi, *synonym_patterns(e, s)) for e, s, vi in rows])
            db.commit()
            db.close()
            quiz = client.post("/api/quiz/start?table=synonymous_collocations&mode=av")
            self.assertEqual(quiz.status_code, 200)
            question = quiz.json["questions"][0]
            self.assertTrue(question["prompt"].startswith("have "))
            self.assertIn("...", question["prompt"])
            self.assertTrue(all("..." in choice["text"] for choice in question["choices"]))
            self.assertEqual(question["correct_vietnamese"], "nghĩa")

    def test_quiz_and_flashcard_use_english_pair_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app({"TESTING": True, "DATABASE": str(Path(tmp) / "db.sqlite3")})
            client = app.test_client()
            db = sqlite3.connect(app.config["DATABASE"])
            entries = [(f"take a bus {i}", f"catch a bus {i}", f"meaning {i}") for i in range(8)]
            db.executemany("INSERT INTO synonymous_collocations (english, synonym, vietnamese, english_pattern, synonym_pattern, next_review_at) VALUES (?, ?, ?, ?, ?, datetime('now','-1 day'))", [(e, s, vi, *synonym_patterns(e, s)) for e, s, vi in entries])
            db.commit()
            db.close()
            quiz = client.post("/api/quiz/start?table=synonymous_collocations&mode=av")
            self.assertEqual(quiz.status_code, 200)
            question = next(q for q in quiz.json["questions"] if q["word_id"] == 1)
            self.assertEqual(question["prompt"], "take ...")
            self.assertEqual(len(question["choices"]), 8)
            self.assertTrue(all("..." in choice["text"] for choice in question["choices"]))
            card = client.post("/api/flashcard/start?table=synonymous_collocations&mode=av")
            self.assertEqual(card.status_code, 200)
            self.assertTrue(card.json["cards"][0]["front"].startswith("take a bus"))
            self.assertTrue(card.json["cards"][0]["back"].startswith("catch a bus"))
