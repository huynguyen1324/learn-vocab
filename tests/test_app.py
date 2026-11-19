import json
import sqlite3
import tempfile
import unittest
import unicodedata
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

from app import add_months, create_app, load_server_config, next_review_for_count


class ServerConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "config.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_config(self, value):
        self.config_path.write_text(json.dumps(value), encoding="utf-8")

    def test_loads_host_and_port(self):
        self.write_config({"VOCAB_HOST": " 0.0.0.0 ", "VOCAB_PORT": 8080})
        self.assertEqual(load_server_config(self.config_path), ("0.0.0.0", 8080))

    def test_missing_or_malformed_config_file_fails(self):
        with self.assertRaises(FileNotFoundError):
            load_server_config(self.config_path)
        self.config_path.write_text("{", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            load_server_config(self.config_path)

    def test_rejects_missing_or_invalid_host_and_port(self):
        invalid_configs = (
            {},
            {"VOCAB_HOST": "", "VOCAB_PORT": 5000},
            {"VOCAB_HOST": "127.0.0.1"},
            {"VOCAB_HOST": "127.0.0.1", "VOCAB_PORT": "5000"},
            {"VOCAB_HOST": "127.0.0.1", "VOCAB_PORT": True},
            {"VOCAB_HOST": "127.0.0.1", "VOCAB_PORT": 65536},
            [],
        )
        for config in invalid_configs:
            with self.subTest(config=config):
                self.write_config(config)
                with self.assertRaises(ValueError):
                    load_server_config(self.config_path)


class VocabularyAppTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database = Path(self.temp_dir.name) / "test.sqlite3"
        self.app = create_app({"TESTING": True, "DATABASE": str(database)})
        self.client = self.app.test_client()
        self.database = database

    def tearDown(self):
        self.temp_dir.cleanup()

    def insert_word(self, english, vietnamese, repetition_level=0, due=True):
        due_at = datetime.now().replace(microsecond=0)
        if not due:
            due_at += timedelta(days=10)
        with closing(sqlite3.connect(self.database)) as connection:
            cursor = connection.execute(
                "INSERT INTO collocations (english, vietnamese, repetition_level, next_review_at, practice_count) "
                "VALUES (?, ?, ?, ?, ?)",
                (english.lower(), vietnamese, repetition_level, due_at.isoformat(), 0 if due else 1),
            )
            connection.commit()
            return cursor.lastrowid

    def test_legacy_database_fails_without_modifying_data(self):
        for progress_column in ("stage", "repetition_level"):
            with self.subTest(progress_column=progress_column), tempfile.TemporaryDirectory() as directory:
                database = Path(directory) / "legacy.sqlite3"
                with closing(sqlite3.connect(database)) as connection:
                    connection.execute(
                        f"CREATE TABLE vocabulary (id INTEGER PRIMARY KEY, english TEXT, "
                        f"english_key TEXT UNIQUE, vietnamese TEXT, {progress_column} INTEGER, next_review_at TEXT)"
                    )
                    connection.execute(
                        "INSERT INTO vocabulary VALUES (1, 'Apple', 'apple', 'Quả táo', 4, '2030-01-01T00:00:00')"
                    )
                    connection.commit()
                before = database.read_bytes()
                with self.assertRaisesRegex(sqlite3.DatabaseError, "export.*reset"):
                    create_app({"TESTING": True, "DATABASE": str(database)})
                self.assertEqual(database.read_bytes(), before)
                with closing(sqlite3.connect(database)) as connection:
                    self.assertIsNone(connection.execute(
                        "SELECT name FROM sqlite_master WHERE name = 'collocations'"
                    ).fetchone())

    def test_collocations_schema_defaults_and_constraints(self):
        with closing(sqlite3.connect(self.database)) as connection:
            columns = [row[1] for row in connection.execute("PRAGMA table_info(collocations)")]
            self.assertEqual(columns, [
                "id", "english", "vietnamese", "repetition_level", "practice_count", "next_review_at",
            ])
            self.assertIsNone(connection.execute(
                "SELECT name FROM sqlite_master WHERE name = 'vocabulary'"
            ).fetchone())
        word_id = self.insert_word("example", "ví dụ")
        word = self.client.get("/api/words").json["words"][0]
        self.assertEqual(word["practice_count"], 0)
        self.assertEqual(word["repetition_level"], 0)
        with closing(sqlite3.connect(self.database)) as connection:
            for column, value in (("repetition_level", -1), ("repetition_level", 9), ("practice_count", -1)):
                with self.subTest(column=column, value=value), self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(f"UPDATE collocations SET {column} = ? WHERE id = ?", (value, word_id))
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO collocations (english, vietnamese, repetition_level, next_review_at) "
                    "VALUES ('EXAMPLE', 'trùng', 0, '2020-01-01T00:00:00')"
                )




    def test_english_unicode_duplicates_are_normalized_without_english_key(self):
        for english, duplicate in (("Straße", "STRASSE"), ("Café", "Cafe\u0301")):
            created = self.client.post("/api/words", json={"english": english, "vietnamese": "nghĩa"})
            self.assertEqual(created.status_code, 201)
            self.assertEqual(self.client.post(
                "/api/words", json={"english": duplicate, "vietnamese": "trùng"}
            ).status_code, 409)
            other_id = self.insert_word(f"other-{created.json['id']}", "khác")
            self.assertEqual(self.client.put(
                f"/api/words/{other_id}", json={"english": duplicate, "vietnamese": "trùng"}
            ).status_code, 409)

    def test_word_text_length_limits_on_create_and_update(self):
        labels = {"english": "Từ tiếng Anh", "vietnamese": "Nghĩa tiếng Việt"}
        for field, label in labels.items():
            with self.subTest(field=field):
                character = "a" if field == "english" else "ế"
                data = {"english": f"word-{field}", "vietnamese": "nghĩa"}
                data[field] = f"  {character * 500}  "
                created = self.client.post("/api/words", json=data)
                self.assertEqual(created.status_code, 201)
                word_id = created.json["id"]
                updated = self.client.put(f"/api/words/{word_id}", json=data)
                self.assertEqual(updated.status_code, 200)

                data[field] = character * 501
                for response in (
                    self.client.post("/api/words", json=data),
                    self.client.put(f"/api/words/{word_id}", json=data),
                ):
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response.json["error"], f"{label} không được dài quá 500 ký tự.")
                word = next(word for word in self.client.get("/api/words").json["words"] if word["id"] == word_id)
                self.assertEqual(word[field], character * 500)

    def test_words_are_lowercase_when_added(self):
        created = self.client.post(
            "/api/words", json={"english": "Apple", "vietnamese": "Quả Táo"}
        )
        self.assertEqual(created.status_code, 201)
        word = self.client.get("/api/words").json["words"][0]
        self.assertEqual((word["english"], word["vietnamese"]), ("apple", "quả táo"))

    def test_create_rejects_casefold_duplicate_and_edit_preserves_progress(self):
        created = self.client.post(
            "/api/words",
            json={"english": "Apple", "vietnamese": "quả táo"},
        )
        self.assertEqual(created.status_code, 201)
        word_id = created.json["id"]

        duplicate = self.client.post(
            "/api/words",
            json={"english": "APPLE", "vietnamese": "trái táo"},
        )
        self.assertEqual(duplicate.status_code, 409)

        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(
                "UPDATE collocations SET repetition_level = 4, next_review_at = '2030-01-01T12:00:00' WHERE id = ?",
                (word_id,),
            )
            connection.commit()
        updated = self.client.put(
            f"/api/words/{word_id}",
            json={"english": "Red apple", "vietnamese": "quả táo đỏ"},
        )
        self.assertEqual(updated.status_code, 200)
        with closing(sqlite3.connect(self.database)) as connection:
            row = connection.execute(
                "SELECT repetition_level, next_review_at FROM collocations WHERE id = ?",
                (word_id,),
            ).fetchone()
        self.assertEqual(row, (4, "2030-01-01T12:00:00"))


    def test_existing_word_can_be_completed_and_restarted(self):
        word_id = self.insert_word("known", "đã biết", repetition_level=4)
        round_id = self.client.post("/api/flashcard/start").json["round_id"]
        self.client.post(f"/api/words/{word_id}/practice", json={"round_id": round_id})
        completed = self.client.post(f"/api/words/{word_id}/complete", json={"round_id": round_id, "response_time_ms": 2000})
        self.assertEqual(completed.status_code, 200)
        word = self.client.get("/api/words").json["words"][0]
        self.assertEqual(word["status"], "Hoàn thành")
        self.assertIsNone(word["next_review_at"])

        restarted = self.client.post(f"/api/words/{word_id}/restart")
        self.assertEqual(restarted.status_code, 200)
        word = self.client.get("/api/words?status=due").json["words"][0]
        self.assertEqual(word["id"], word_id)
        self.assertEqual(word["repetition_level"], 0)
        self.assertIsNotNone(word["next_review_at"])

        self.assertEqual(self.client.post(f"/api/words/{word_id}/restart").status_code, 409)

    def test_delete_removes_word(self):
        created = self.client.post(
            "/api/words",
            json={"english": "temporary", "vietnamese": "tạm thời"},
        )
        word_id = created.json["id"]

        deleted = self.client.delete(f"/api/words/{word_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get("/api/words").json["words"], [])
        self.assertEqual(self.client.delete(f"/api/words/{word_id}").status_code, 404)

    def test_search_is_unicode_case_insensitive_and_completed_are_not_due(self):
        word_id = self.insert_word("Học", "học tập")
        response = self.client.get("/api/words?q=HỌC")
        self.assertEqual([word["id"] for word in response.json["words"]], [word_id])

        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(
                "UPDATE collocations SET repetition_level = 8, next_review_at = NULL WHERE id = ?",
                (word_id,),
            )
            connection.commit()
        listed = self.client.get("/api/words")
        self.assertEqual(listed.json["words"][0]["status"], "Hoàn thành")
        self.assertEqual(self.client.get("/api/words?status=due").json["words"], [])



    def test_quiz_repetition_level_after_correct_is_capped_at_eight(self):
        target_id = self.insert_word("final-repetition-count", "nghĩa cuối", repetition_level=7)
        for index in range(7):
            self.insert_word(f"other-{index}", f"nghĩa {index}", due=False)

        quiz = self.client.post("/api/quiz/start")
        question = next(
            question for question in quiz.json["questions"]
            if question["word_id"] == target_id
        )
        self.assertEqual(question["repetition_level_after_correct"], 8)


    def test_quiz_requires_eight_words_and_month_arithmetic_clamps_day(self):
        for index in range(7):
            self.insert_word(f"word-{index}", f"nghĩa {index}")
        response = self.client.post("/api/quiz/start")
        self.assertEqual(response.status_code, 400)
        self.assertIn("ít nhất 8 từ", response.json["error"])
        self.assertEqual(
            add_months(datetime(2024, 1, 31, 9), 1),
            datetime(2024, 2, 29, 9),
        )

    def test_repetition_intervals_match_the_schedule(self):
        answered_at = datetime(2024, 1, 31, 9)
        expected = {
            0: datetime(2024, 1, 31, 10),
            1: datetime(2024, 1, 31, 10),
            2: datetime(2024, 2, 1, 9),
            3: datetime(2024, 2, 3, 9),
            4: datetime(2024, 2, 7, 9),
            5: datetime(2024, 2, 29, 9),
            6: datetime(2024, 4, 30, 9),
            7: datetime(2025, 1, 31, 9),
        }
        for repetition_level, next_review in expected.items():
            with self.subTest(repetition_level=repetition_level):
                self.assertEqual(next_review_for_count(repetition_level, answered_at), next_review)

    def test_quiz_av_mode_prompt_is_english_and_choices_are_vietnamese(self):
        target_id = self.insert_word("apple", "quả táo", repetition_level=0)
        for index in range(7):
            self.insert_word(f"word-{index}", f"nghĩa {index}", due=False)

        quiz = self.client.post("/api/quiz/start?mode=av")
        self.assertEqual(quiz.status_code, 200)
        question = next(
            q for q in quiz.json["questions"] if q["word_id"] == target_id
        )
        self.assertEqual(question["prompt"], "apple")
        for choice in question["choices"]:
            self.assertIn("text", choice)
            self.assertNotIn("english", choice)


    def test_quiz_rejects_invalid_mode(self):
        response = self.client.post("/api/quiz/start?mode=invalid")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Chế độ quiz không hợp lệ", response.json["error"])

    def test_flashcard_modes_return_only_due_words(self):
        target_id = self.insert_word("apple", "quả táo")
        self.insert_word("book", "quyển sách", due=False)
        av = self.client.post("/api/flashcard/start?mode=av")
        va = self.client.post("/api/flashcard/start?mode=va")
        self.assertEqual(av.json["cards"], [{
            "word_id": target_id, "front": "apple", "back": "quả táo", "repetition_level": 0,
        }])
        self.assertEqual(va.json["cards"][0]["front"], "quả táo")
        self.assertEqual(va.json["cards"][0]["back"], "apple")




if __name__ == "__main__":
    unittest.main()
