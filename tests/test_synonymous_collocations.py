import sqlite3
import tempfile
import unittest
from pathlib import Path

from app import create_app
from tools.import_synonymous_collocations import import_synonymous_collocations, parse_synonymous_collocations


class SynonymousCollocationTests(unittest.TestCase):
    def test_parser_reads_all_three_fields_and_lowercases_them(self):
        self.assertEqual(parse_synonymous_collocations("1\n\nTAKE A BUS\n\nCatch a Bus\n\nBẮT XE BUS\n"),
                         [("take a bus", "catch a bus", "bắt xe bus")])

    def test_parser_reports_missing_field(self):
        with self.assertRaisesRegex(ValueError, "dòng 1"):
            parse_synonymous_collocations("1\n\nonly one\n")
        with self.assertRaisesRegex(ValueError, "nghĩa tiếng Việt"):
            parse_synonymous_collocations("1\n\nphrase\n\nsynonym\n")

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

    def test_quiz_and_flashcard_use_english_pair_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app({"TESTING": True, "DATABASE": str(Path(tmp) / "db.sqlite3")})
            client = app.test_client()
            db = sqlite3.connect(app.config["DATABASE"])
            db.executemany("INSERT INTO synonymous_collocations (english, synonym, vietnamese, next_review_at) VALUES (?, ?, ?, datetime('now','-1 day'))", [(f"phrase {i}", f"equivalent {i}", f"meaning {i}") for i in range(8)])
            db.commit()
            db.close()
            quiz = client.post("/api/quiz/start?table=synonymous_collocations&mode=av")
            self.assertEqual(quiz.status_code, 200)
            question = quiz.json["questions"][0]
            self.assertTrue(question["prompt"].startswith("phrase "))
            self.assertEqual(len(question["choices"]), 8)
            card = client.post("/api/flashcard/start?table=synonymous_collocations&mode=av")
            self.assertEqual(card.status_code, 200)
            self.assertEqual(card.json["cards"][0]["front"].split()[0], "phrase")
            self.assertEqual(card.json["cards"][0]["back"].split()[0], "equivalent")
