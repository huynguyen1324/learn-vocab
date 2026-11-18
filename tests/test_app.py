import json
import sqlite3
import tempfile
import unittest
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

    def insert_word(self, english, vietnamese, repetition_count=0, due=True):
        due_at = datetime.now().replace(microsecond=0)
        if not due:
            due_at += timedelta(days=10)
        with closing(sqlite3.connect(self.database)) as connection:
            cursor = connection.execute(
                "INSERT INTO vocabulary (english, english_key, vietnamese, repetition_count, next_review_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (english, english.casefold(), vietnamese, repetition_count, due_at.isoformat()),
            )
            connection.commit()
            return cursor.lastrowid

    def test_legacy_database_migrates_progress_without_changing_review_dates(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "legacy.sqlite3"
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "CREATE TABLE vocabulary (id INTEGER PRIMARY KEY, english TEXT NOT NULL, "
                    "english_key TEXT NOT NULL UNIQUE, vietnamese TEXT NOT NULL, "
                    "stage INTEGER NOT NULL, next_review_at TEXT)"
                )
                connection.executemany(
                    "INSERT INTO vocabulary VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        (1, "Apple", "apple", "Quả táo", 1, "2025-01-01T00:00:00"),
                        (2, "Book", "book", "Quyển sách", 4, "2025-02-01T00:00:00"),
                        (3, "Known", "known", "Đã biết", 8, None),
                        (4, "Due", "due", "Đến hạn", 8, "2025-03-01T00:00:00"),
                    ],
                )
                connection.commit()
            create_app({"DATABASE": str(database)})
            create_app({"DATABASE": str(database)})
            with closing(sqlite3.connect(database)) as connection:
                rows = connection.execute(
                    "SELECT repetition_count, next_review_at FROM vocabulary ORDER BY id"
                ).fetchall()
            self.assertEqual(rows, [
                (0, "2025-01-01T00:00:00"),
                (3, "2025-02-01T00:00:00"),
                (8, None),
                (7, "2025-03-01T00:00:00"),
            ])

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
                "UPDATE vocabulary SET repetition_count = 4, next_review_at = '2030-01-01T12:00:00' WHERE id = ?",
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
                "SELECT repetition_count, next_review_at FROM vocabulary WHERE id = ?",
                (word_id,),
            ).fetchone()
        self.assertEqual(row, (4, "2030-01-01T12:00:00"))

    def test_create_as_completed_and_reject_invalid_completion_value(self):
        created = self.client.post(
            "/api/words",
            json={"english": "known", "vietnamese": "đã biết", "complete": True},
        )
        self.assertEqual(created.status_code, 201)
        word_id = created.json["id"]
        for index in range(7):
            self.insert_word(f"other-{index}", f"nghĩa {index}", due=False)

        word = next(word for word in self.client.get("/api/words").json["words"] if word["id"] == word_id)
        self.assertEqual(word["status"], "Hoàn thành")
        self.assertIsNone(word["next_review_at"])
        self.assertEqual(self.client.post("/api/quiz/start").json["questions"], [])

        invalid = self.client.post(
            "/api/words",
            json={"english": "invalid", "vietnamese": "không hợp lệ", "complete": "yes"},
        )
        self.assertEqual(invalid.status_code, 400)

    def test_existing_word_can_be_completed_and_restarted(self):
        word_id = self.insert_word("known", "đã biết", repetition_count=4)
        completed = self.client.post(f"/api/words/{word_id}/complete")
        self.assertEqual(completed.status_code, 200)
        word = self.client.get("/api/words").json["words"][0]
        self.assertEqual(word["status"], "Hoàn thành")
        self.assertIsNone(word["next_review_at"])

        restarted = self.client.post(f"/api/words/{word_id}/restart")
        self.assertEqual(restarted.status_code, 200)
        word = self.client.get("/api/words?status=due").json["words"][0]
        self.assertEqual(word["id"], word_id)
        self.assertEqual(word["repetition_count"], 0)
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
                "UPDATE vocabulary SET repetition_count = 8, next_review_at = NULL WHERE id = ?",
                (word_id,),
            )
            connection.commit()
        listed = self.client.get("/api/words")
        self.assertEqual(listed.json["words"][0]["status"], "Hoàn thành")
        self.assertEqual(self.client.get("/api/words?status=due").json["words"], [])

    def test_quiz_accepts_all_choices_with_matching_vietnamese_meaning(self):
        target_id = self.insert_word("apple", "quả táo")
        synonym_id = self.insert_word("pomme", "quả táo", due=False)
        other_ids = [
            self.insert_word("book", "quyển sách", due=False),
            self.insert_word("chair", "cái ghế", due=False),
        ]
        self.insert_word("water", "nước", due=False)
        for index in range(3):
            self.insert_word(f"extra-{index}", f"nghĩa thêm {index}", due=False)

        quiz = self.client.post("/api/quiz/start")
        self.assertEqual(quiz.status_code, 200)
        self.assertEqual(len(quiz.json["questions"]), 1)
        question = quiz.json["questions"][0]
        self.assertEqual(question["word_id"], target_id)
        self.assertEqual(question["repetition_count_after_correct"], 1)
        self.assertEqual(len(question["choices"]), 8)
        self.assertEqual(len({choice["id"] for choice in question["choices"]}), 8)

        choice_ids = [choice["id"] for choice in question["choices"]]
        self.assertIn(synonym_id, choice_ids)
        answer = self.client.post(
            "/api/quiz/answer",
            json={
                "word_id": target_id,
                "selected_id": synonym_id,
                "choice_ids": choice_ids,
            },
        )
        self.assertEqual(answer.status_code, 200)
        self.assertTrue(answer.json["correct"])
        self.assertCountEqual(answer.json["correct_option_ids"], [target_id, synonym_id])
        self.assertEqual(answer.json["repetition_count"], 1)

    def test_quiz_repetition_count_after_correct_is_capped_at_eight(self):
        target_id = self.insert_word("final-repetition-count", "nghĩa cuối", repetition_count=7)
        for index in range(7):
            self.insert_word(f"other-{index}", f"nghĩa {index}", due=False)

        quiz = self.client.post("/api/quiz/start")
        question = next(
            question for question in quiz.json["questions"]
            if question["word_id"] == target_id
        )
        self.assertEqual(question["repetition_count_after_correct"], 8)

    def test_wrong_answer_resets_repetition_count_and_completed_word_can_restart(self):
        target_id = self.insert_word("target", "mục tiêu", repetition_count=5)
        other_ids = [self.insert_word(f"word-{index}", f"nghĩa {index}", due=False) for index in range(7)]
        choice_ids = [target_id, *other_ids]
        wrong = self.client.post(
            "/api/quiz/answer",
            json={"word_id": target_id, "selected_id": other_ids[0], "choice_ids": choice_ids},
        )
        self.assertEqual(wrong.status_code, 200)
        self.assertEqual(wrong.json["repetition_count"], 0)
        delay = datetime.fromisoformat(wrong.json["next_review_at"]) - datetime.now().replace(microsecond=0)
        self.assertGreaterEqual(delay, timedelta(seconds=3599))
        self.assertLessEqual(delay, timedelta(hours=1))

        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(
                "UPDATE vocabulary SET repetition_count = 7, next_review_at = ? WHERE id = ?",
                (datetime.now().replace(microsecond=0).isoformat(), target_id),
            )
            connection.commit()
        completed = self.client.post(
            "/api/quiz/answer",
            json={"word_id": target_id, "selected_id": target_id, "choice_ids": choice_ids},
        )
        self.assertEqual(completed.status_code, 200)
        self.assertTrue(completed.json["completed"])
        self.assertIsNone(completed.json["next_review_at"])
        self.assertEqual(self.client.get("/api/words?status=due").json["words"], [])

        restarted = self.client.post(f"/api/words/{target_id}/restart")
        self.assertEqual(restarted.status_code, 200)
        due_word = next(
            word for word in self.client.get("/api/words?status=due").json["words"]
            if word["id"] == target_id
        )
        self.assertEqual(due_word["repetition_count"], 0)

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
            0: datetime(2024, 1, 31, 9),
            1: datetime(2024, 1, 31, 10),
            2: datetime(2024, 2, 1, 9),
            3: datetime(2024, 2, 3, 9),
            4: datetime(2024, 2, 7, 9),
            5: datetime(2024, 2, 29, 9),
            6: datetime(2024, 4, 30, 9),
            7: datetime(2025, 1, 31, 9),
        }
        for repetition_count, next_review in expected.items():
            with self.subTest(repetition_count=repetition_count):
                self.assertEqual(next_review_for_count(repetition_count, answered_at), next_review)

    def test_quiz_av_mode_prompt_is_english_and_choices_are_vietnamese(self):
        target_id = self.insert_word("apple", "quả táo", repetition_count=0)
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

    def test_quiz_av_answer_updates_repetition_count(self):
        target_id = self.insert_word("apple", "quả táo", repetition_count=0)
        other_ids = [
            self.insert_word(f"word-{index}", f"nghĩa {index}", due=False)
            for index in range(7)
        ]
        choice_ids = [target_id, *other_ids]
        result = self.client.post(
            "/api/quiz/answer?mode=av",
            json={
                "word_id": target_id,
                "selected_id": target_id,
                "choice_ids": choice_ids,
            },
        )
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.json["correct"])
        self.assertEqual(result.json["repetition_count"], 1)

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
            "word_id": target_id, "front": "apple", "back": "quả táo", "repetition_count": 0,
        }])
        self.assertEqual(va.json["cards"][0]["front"], "quả táo")
        self.assertEqual(va.json["cards"][0]["back"], "apple")

    def test_flashcard_correct_thresholds_wrong_timeout_and_completion(self):
        cases = [
            (1500, 3, 5), (2000, 3, 5), (2001, 3, 4),
            (5000, 3, 4), (5001, 3, 3), (10000, 3, 3),
            (10001, 3, 2), (20000, 3, 2),
        ]
        for elapsed, starting_count, expected_count in cases:
            word_id = self.insert_word(f"word-{elapsed}-{starting_count}", "nghĩa", repetition_count=starting_count)
            response = self.client.post(
                "/api/flashcard/answer",
                json={"word_id": word_id, "result": "correct", "response_time_ms": elapsed},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["repetition_count"], expected_count)
        wrong_id = self.insert_word("wrong", "sai", repetition_count=5)
        wrong = self.client.post(
            "/api/flashcard/answer", json={"word_id": wrong_id, "result": "wrong"}
        )
        self.assertEqual(wrong.json["repetition_count"], 0)
        timeout_id = self.insert_word("timeout", "chậm", repetition_count=3)
        timeout = self.client.post(
            "/api/flashcard/answer", json={"word_id": timeout_id, "result": "timeout"}
        )
        self.assertEqual(timeout.json["repetition_count"], 2)
        final_id = self.insert_word("final", "cuối", repetition_count=7)
        final = self.client.post(
            "/api/flashcard/answer",
            json={"word_id": final_id, "result": "correct", "response_time_ms": 1000},
        )
        self.assertEqual(final.json["repetition_count"], 8)
        self.assertTrue(final.json["completed"])
        self.assertIsNone(final.json["next_review_at"])

    def test_flashcard_relative_preserves_count_and_reschedules_at_current_level(self):
        word_id = self.insert_word("relative", "tương đối", repetition_count=3)
        response = self.client.post(
            "/api/flashcard/answer", json={"word_id": word_id, "result": "relative"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["repetition_count"], 3)
        delay = datetime.fromisoformat(response.json["next_review_at"]) - datetime.now().replace(microsecond=0)
        self.assertGreaterEqual(delay, timedelta(days=2, seconds=86399))
        self.assertLessEqual(delay, timedelta(days=3))

        new_word_id = self.insert_word("relative-new", "mới", repetition_count=0)
        new_response = self.client.post(
            "/api/flashcard/answer", json={"word_id": new_word_id, "result": "relative"}
        )
        new_delay = datetime.fromisoformat(new_response.json["next_review_at"]) - datetime.now().replace(microsecond=0)
        self.assertGreaterEqual(new_delay, timedelta(seconds=3599))
        self.assertLessEqual(new_delay, timedelta(hours=1))


if __name__ == "__main__":
    unittest.main()
