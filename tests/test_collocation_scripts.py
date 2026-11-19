import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from tools.export_db_vocab import export_vocabulary
from tools.import_collocations import import_collocations, parse_collocations
from tools.transform_input_vocab_into_collocations import generate_collocations, waiting_for_ai


class CollocationScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "db.sqlite3"
        self.input = self.root / "input.txt"
        self.output = self.root / "output.txt"
        self.config = self.root / "config.json"
        self.config.write_text(json.dumps({"BASE_URL": "https://example.invalid/v1/", "API_KEY": "secret", "MODEL": "test"}))

    def test_defaults_follow_repository_layout_not_current_directory(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(export_vocabulary.__defaults__, (root / "instance" / "vocabulary.sqlite3", root / "tools" / "input_vocab.txt"))
        self.assertEqual(import_collocations.__defaults__, (root / "tools" / "output_collocations.txt", root / "instance" / "vocabulary.sqlite3"))
        self.assertEqual(generate_collocations.__defaults__, (root / "tools" / "input_vocab.txt", root / "tools" / "output_collocations.txt", root / "config.json", root / "USER_DESCRIPTION.md"))

    def test_waiting_log_reports_elapsed_and_stops_on_success_or_error(self):
        for fail in (False, True):
            stopped = Mock()
            stopped.wait.side_effect = [False, True]
            output = io.StringIO()
            with patch("tools.transform_input_vocab_into_collocations.Event", return_value=stopped), patch("tools.transform_input_vocab_into_collocations.time.perf_counter", return_value=25), redirect_stdout(output):
                try:
                    with waiting_for_ai(5):
                        if fail:
                            raise ValueError("test")
                except ValueError:
                    pass
            self.assertIn("[20s] Still waiting for AI response", output.getvalue())
            self.assertIn("not token progress", output.getvalue())
            stopped.set.assert_called_once()
            self.assertEqual(stopped.wait.call_args_list[0].args, (10,))

    def test_export_matches_pairs_and_does_not_change_db(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("CREATE TABLE vocabulary (id INTEGER PRIMARY KEY, english TEXT, vietnamese TEXT)")
            db.executemany("INSERT INTO vocabulary VALUES (?, ?, ?)", [(1, "lease", "thuê"), (2, "book", "sách")])
            db.commit()
        before = self.db.read_bytes()
        self.input.write_text("old input")
        self.assertEqual(export_vocabulary(self.db, self.input), 2)
        self.assertEqual(parse_collocations(self.input.read_text(encoding="utf-8")), [("lease", "thuê"), ("book", "sách")])
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(next(self.root.glob("input.txt.before-export-*")).read_text(), "old input")

    def test_export_cannot_overwrite_database(self):
        self.db.write_bytes(b"preserve")
        with self.assertRaises(ValueError):
            export_vocabulary(self.db, self.db)
        self.assertEqual(self.db.read_bytes(), b"preserve")

    def test_import_idempotent_keeps_progress_and_has_exact_fields(self):
        self.output.write_text("Sign a lease\nKý hợp đồng thuê\n\nlease property\ncho thuê bất động sản\n", encoding="utf-8")
        self.assertEqual(import_collocations(self.output, self.db), (2, 0))
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual([r[1] for r in db.execute("PRAGMA table_info(collocations)")],
                             ["id", "english", "vietnamese", "repetition_level", "practice_count", "next_review_at"])
            self.assertEqual(db.execute("SELECT repetition_level, practice_count FROM collocations").fetchall(), [(0, 0), (0, 0)])
            db.execute("UPDATE collocations SET repetition_level=4, practice_count=9")
            db.commit()
        self.assertEqual(import_collocations(self.output, self.db), (0, 2))
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute("SELECT repetition_level, practice_count FROM collocations").fetchall(), [(4, 9), (4, 9)])

    def test_invalid_later_pair_writes_nothing(self):
        for content in ("one\nmột\nmissing", "one\nmột\n" + "a" * 501 + "\nnghĩa"):
            self.output.write_text(content, encoding="utf-8")
            with self.assertRaises(ValueError):
                import_collocations(self.output, self.db)
            self.assertFalse(self.db.exists())

    def test_import_rolls_back_when_later_insert_fails(self):
        from app import create_app
        create_app({"DATABASE": str(self.db)})
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("CREATE TRIGGER reject_bad BEFORE INSERT ON collocations WHEN NEW.english = 'bad' BEGIN SELECT RAISE(ABORT, 'test failure'); END")
            db.commit()
        self.output.write_text("good\ntốt\nbad\nxấu\n", encoding="utf-8")
        with self.assertRaises(sqlite3.IntegrityError):
            import_collocations(self.output, self.db)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM collocations").fetchone()[0], 0)

    def test_export_multiline_rejected_without_overwriting_input(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("CREATE TABLE vocabulary (id INTEGER PRIMARY KEY, english TEXT, vietnamese TEXT)")
            db.execute("INSERT INTO vocabulary VALUES (1, 'line one' || char(10) || 'line two', 'nghĩa')")
            db.commit()
        self.input.write_text("preserve")
        with self.assertRaises(ValueError):
            export_vocabulary(self.db, self.input)
        self.assertEqual(self.input.read_text(), "preserve")

    def test_generate_text_pairs_no_database_and_custom_endpoint(self):
        self.input.write_text("lease\nhợp đồng thuê / cho thuê\n", encoding="utf-8")
        self.output.write_text("sample", encoding="utf-8")
        answer = [{"source_id": 1, "english": "sign a lease", "vietnamese": "ký hợp đồng thuê"},
                  {"source_id": 1, "english": "lease property", "vietnamese": "cho thuê bất động sản"}]
        response = {"choices": [{"message": {"content": json.dumps(answer)}}]}
        log = io.StringIO()
        with patch("tools.transform_input_vocab_into_collocations.urlopen", return_value=io.BytesIO(json.dumps(response).encode())) as mock, redirect_stdout(log):
            self.assertEqual(generate_collocations(self.input, self.output, self.config), 2)
        self.assertIn("Response received", log.getvalue())
        self.assertIn("Saved 2 collocations", log.getvalue())
        self.assertNotIn("sign a lease", log.getvalue())
        self.assertEqual(parse_collocations(self.output.read_text(encoding="utf-8")), [(p["english"], p["vietnamese"]) for p in answer])
        request = mock.call_args.args[0]
        mock.assert_called_once()
        self.assertEqual(request.full_url, "https://example.invalid/v1/chat/completions")
        self.assertEqual(request.get_header("User-agent"), "learn-vocab/1.0")
        self.assertEqual(next(self.root.glob("output.txt.before-generate-*")).read_text(), "sample")
        self.assertFalse(self.db.exists())

    def test_all_835_entries_sent_in_one_request(self):
        self.input.write_text("".join(f"word-{i}\nnghĩa {i}\n" for i in range(835)), encoding="utf-8")
        answer = [{"source_id": i, "english": f"use word {i}", "vietnamese": f"dùng từ {i}"} for i in range(1, 836)]
        response = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(answer)}}]}
        with patch("tools.transform_input_vocab_into_collocations.urlopen", return_value=io.BytesIO(json.dumps(response).encode())) as mock, redirect_stdout(io.StringIO()):
            self.assertEqual(generate_collocations(self.input, self.output, self.config), 835)
        mock.assert_called_once()
        payload = json.loads(mock.call_args.args[0].data)
        supplied = json.loads(payload["messages"][1]["content"])
        self.assertEqual(len(supplied), 835)
        self.assertEqual(supplied[0]["source_id"], 1)
        self.assertEqual(supplied[-1]["english"], "word-834")
        self.assertEqual(len(parse_collocations(self.output.read_text(encoding="utf-8"))), 835)

    def test_missing_invalid_ids_and_truncation_preserve_output(self):
        self.input.write_text("one\nmột\ntwo\nhai\n", encoding="utf-8")
        self.output.write_text("preserve", encoding="utf-8")
        for source_id, finish in ((1, "stop"), (True, "stop"), (3, "stop"), (1, "length")):
            answer = [{"source_id": source_id, "english": "one item", "vietnamese": "một mục"}]
            response = {"choices": [{"finish_reason": finish, "message": {"content": json.dumps(answer)}}]}
            with patch("tools.transform_input_vocab_into_collocations.urlopen", return_value=io.BytesIO(json.dumps(response).encode())), redirect_stdout(io.StringIO()):
                with self.assertRaises(ValueError):
                    generate_collocations(self.input, self.output, self.config)
            self.assertEqual(self.output.read_text(encoding="utf-8"), "preserve")

    def test_generate_rejects_malformed_or_multiline_output(self):
        self.input.write_text("lease\nthuê\n", encoding="utf-8")
        self.output.write_text("preserve", encoding="utf-8")
        for content in ("not json", "[]", '[{"source_id":1,"english":"a\\nb","vietnamese":"nghĩa"}]'):
            response = {"choices": [{"message": {"content": content}}]}
            with patch("tools.transform_input_vocab_into_collocations.urlopen", return_value=io.BytesIO(json.dumps(response).encode())):
                with self.assertRaises(ValueError):
                    generate_collocations(self.input, self.output, self.config)
            self.assertEqual(self.output.read_text(encoding="utf-8"), "preserve")


if __name__ == "__main__":
    unittest.main()
