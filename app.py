import calendar
import json
import math
import random
import sqlite3
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, current_app, g, jsonify, render_template, request
from werkzeug.exceptions import HTTPException


ROOT = Path(__file__).resolve().parent
SERVER_CONFIG = ROOT / "config.json"
SCHEMA = """
CREATE TABLE IF NOT EXISTS collocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    english TEXT NOT NULL UNIQUE COLLATE NOCASE,
    vietnamese TEXT NOT NULL,
    repetition_level INTEGER NOT NULL CHECK (repetition_level BETWEEN 0 AND 8),
    practice_count INTEGER NOT NULL DEFAULT 0 CHECK (practice_count >= 0),
    next_review_at TEXT,
    CHECK (next_review_at IS NOT NULL OR repetition_level = 8)
);
"""


def local_now():
    return datetime.now().replace(microsecond=0)


def load_server_config(path=SERVER_CONFIG):
    with Path(path).open(encoding="utf-8") as config_file:
        config = json.load(config_file)
    if not isinstance(config, dict):
        raise ValueError("config.json must contain a JSON object.")

    host = config.get("VOCAB_HOST")
    port = config.get("VOCAB_PORT")
    if not isinstance(host, str) or not host.strip():
        raise ValueError('config.json "VOCAB_HOST" must be a non-empty string.')
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError('config.json "VOCAB_PORT" must be an integer from 1 to 65535.')
    return host.strip(), port


def add_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def next_review_for_count(count, answered_at):
    if count == 0:
        return answered_at
    intervals = {
        1: timedelta(hours=1),
        2: timedelta(days=1),
        3: timedelta(days=3),
        4: timedelta(days=7),
    }
    if count in intervals:
        return answered_at + intervals[count]
    if count == 5:
        return add_months(answered_at, 1)
    if count == 6:
        return add_months(answered_at, 3)
    if count == 7:
        return add_months(answered_at, 12)
    raise ValueError("Mốc repetition không hợp lệ.")


def normalize_meaning(value):
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def required_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} không được để trống.")
    value = value.strip()
    if len(value) > 500:
        raise ValueError(f"{label} không được dài quá 500 ký tự.")
    return value


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            isolation_level=None,
        )
        g.db.row_factory = sqlite3.Row
    return g.db


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(DATABASE=str(ROOT / "instance" / "vocabulary.sqlite3"))
    if test_config:
        app.config.update(test_config)

    database_path = Path(app.config["DATABASE"])
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    try:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'vocabulary'"
        ).fetchone()
        if table:
            raise sqlite3.DatabaseError(
                "Legacy vocabulary table exists. Run export_db_vocab.py and the explicit database reset "
                "before starting the app; startup will not convert or delete your data."
            )
        connection.executescript(SCHEMA)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    @app.teardown_appcontext
    def close_db(_error=None):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        if request.path.startswith("/api/"):
            return jsonify(error=error.description), error.code
        return error

    def payload():
        data = request.get_json()
        if not isinstance(data, dict):
            raise ValueError("Dữ liệu gửi lên không hợp lệ.")
        return data

    def quiz_mode():
        mode = request.args.get("mode", "va")
        if mode not in {"va", "av"}:
            return None
        return mode

    def reject_duplicate_english(english, word_id=None):
        # SQLite NOCASE handles ASCII; casefold also catches Unicode equivalents.
        for row in get_db().execute("SELECT id, english FROM collocations"):
            if row["id"] != word_id and unicodedata.normalize("NFC", row["english"]).casefold() == english.casefold():
                raise sqlite3.IntegrityError("Duplicate English text.")

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/words")
    def list_words():
        status_filter = request.args.get("status", "all")
        if status_filter not in {"all", "due", "upcoming"}:
            return jsonify(error="Bộ lọc không hợp lệ."), 400

        search = request.args.get("q", "").strip().casefold()
        now = local_now().isoformat()
        # shortcut: filters scan the full personal vocabulary; use indexed search if datasets grow large.
        rows = get_db().execute(
            "SELECT id, english, vietnamese, repetition_level, practice_count, next_review_at "
            "FROM collocations ORDER BY english COLLATE NOCASE"
        ).fetchall()
        result = []
        for row in rows:
            if search and search not in row["english"].casefold() and search not in row["vietnamese"].casefold():
                continue
            completed = row["repetition_level"] == 8 and row["next_review_at"] is None
            due = row["next_review_at"] is not None and row["next_review_at"] <= now
            if status_filter == "due" and not due:
                continue
            if status_filter == "upcoming" and (due or completed):
                continue
            result.append({
                "id": row["id"],
                "english": row["english"],
                "vietnamese": row["vietnamese"],
                "repetition_level": row["repetition_level"],
                "practice_count": row["practice_count"],
                "status": "Hoàn thành" if completed else f"{row['repetition_level']}/8",
                "next_review_at": row["next_review_at"],
            })
        return jsonify(words=result)

    @app.post("/api/words")
    def add_word():
        try:
            data = payload()
            english = unicodedata.normalize("NFC", required_text(data.get("english"), "Từ tiếng Anh")).lower()
            vietnamese = required_text(data.get("vietnamese"), "Nghĩa tiếng Việt")
            complete = data.get("complete", False)
            if not isinstance(complete, bool):
                raise ValueError("Trạng thái hoàn thành không hợp lệ.")
            repetition_level = 8 if complete else 0
            next_review_at = None if complete else local_now().isoformat()
            reject_duplicate_english(english)
            cursor = get_db().execute(
                "INSERT INTO collocations (english, vietnamese, repetition_level, next_review_at) "
                "VALUES (?, ?, ?, ?)",
                (english, vietnamese.lower(), repetition_level, next_review_at),
            )
        except ValueError as error:
            return jsonify(error=str(error)), 400
        except sqlite3.IntegrityError:
            return jsonify(error="Từ tiếng Anh này đã có trong danh sách."), 409
        return jsonify(id=cursor.lastrowid), 201

    @app.post("/api/words/<int:word_id>/practice")
    def practice_word(word_id):
        db = get_db()
        cursor = db.execute(
            "UPDATE collocations SET practice_count = practice_count + 1 "
            "WHERE id = ? AND next_review_at IS NOT NULL AND next_review_at <= ? "
            "RETURNING practice_count",
            (word_id, local_now().isoformat()),
        )
        row = cursor.fetchone()
        cursor.close()
        if row is not None:
            return jsonify(practice_count=row["practice_count"])
        if db.execute("SELECT 1 FROM collocations WHERE id = ?", (word_id,)).fetchone() is None:
            return jsonify(error="Không tìm thấy từ vựng."), 404
        return jsonify(error="Từ này không còn đến hạn ôn."), 409

    @app.post("/api/words/<int:word_id>/complete")
    def complete_word(word_id):
        cursor = get_db().execute(
            "UPDATE collocations SET repetition_level = 8, next_review_at = NULL WHERE id = ?",
            (word_id,),
        )
        if cursor.rowcount == 0:
            return jsonify(error="Không tìm thấy từ vựng."), 404
        return jsonify(success=True)

    @app.post("/api/words/<int:word_id>/restart")
    def restart_word(word_id):
        db = get_db()
        word = db.execute(
            "SELECT repetition_level, next_review_at FROM collocations WHERE id = ?",
            (word_id,),
        ).fetchone()
        if word is None:
            return jsonify(error="Không tìm thấy từ vựng."), 404
        if word["repetition_level"] != 8 or word["next_review_at"] is not None:
            return jsonify(error="Chỉ có thể học lại từ đã hoàn thành."), 409
        db.execute(
            "UPDATE collocations SET repetition_level = 0, next_review_at = ? WHERE id = ?",
            (local_now().isoformat(), word_id),
        )
        return jsonify(success=True)

    @app.put("/api/words/<int:word_id>")
    def update_word(word_id):
        db = get_db()
        if db.execute("SELECT 1 FROM collocations WHERE id = ?", (word_id,)).fetchone() is None:
            return jsonify(error="Không tìm thấy từ vựng."), 404
        try:
            data = payload()
            english = unicodedata.normalize("NFC", required_text(data.get("english"), "Từ tiếng Anh")).lower()
            vietnamese = required_text(data.get("vietnamese"), "Nghĩa tiếng Việt")
            reject_duplicate_english(english, word_id)
            db.execute(
                "UPDATE collocations SET english = ?, vietnamese = ? WHERE id = ?",
                (english, vietnamese.lower(), word_id),
            )
        except ValueError as error:
            return jsonify(error=str(error)), 400
        except sqlite3.IntegrityError:
            return jsonify(error="Từ tiếng Anh này đã có trong danh sách."), 409
        return jsonify(success=True)

    @app.delete("/api/words/<int:word_id>")
    def delete_word(word_id):
        cursor = get_db().execute("DELETE FROM collocations WHERE id = ?", (word_id,))
        if cursor.rowcount == 0:
            return jsonify(error="Không tìm thấy từ vựng."), 404
        return jsonify(success=True)

    @app.post("/api/quiz/start")
    def start_quiz():
        mode = quiz_mode()
        if mode is None:
            return jsonify(error="Chế độ quiz không hợp lệ."), 400
        db = get_db()
        words = db.execute(
            "SELECT id, english, vietnamese FROM collocations ORDER BY id"
        ).fetchall()
        if len(words) < 8:
            return jsonify(error="Cần ít nhất 8 từ tiếng Anh trong danh sách để bắt đầu quiz."), 400

        now = local_now().isoformat()
        due_words = db.execute(
            "SELECT id, english, vietnamese, repetition_level FROM collocations "
            "WHERE next_review_at IS NOT NULL AND next_review_at <= ? ORDER BY id",
            (now,),
        ).fetchall()
        questions = []
        for word in due_words:
            choices = random.sample([other for other in words if other["id"] != word["id"]], 7)
            choices.append(word)
            random.shuffle(choices)
            if mode == "av":
                prompt = word["english"]
                choice_key = "vietnamese"
            else:
                prompt = word["vietnamese"]
                choice_key = "english"
            questions.append({
                "word_id": word["id"],
                "prompt": prompt,
                "repetition_level_after_correct": min(word["repetition_level"] + 1, 8),
                "choices": [{"id": choice["id"], "text": choice[choice_key]} for choice in choices],
            })
        random.shuffle(questions)
        return jsonify(questions=questions)

    @app.post("/api/quiz/answer")
    def answer_quiz():
        mode = quiz_mode()
        if mode is None:
            return jsonify(error="Chế độ quiz không hợp lệ."), 400
        try:
            data = payload()
            word_id = data.get("word_id")
            selected_id = data.get("selected_id")
            choice_ids = data.get("choice_ids")
            if (
                not isinstance(word_id, int)
                or isinstance(word_id, bool)
                or not isinstance(selected_id, int)
                or isinstance(selected_id, bool)
                or not isinstance(choice_ids, list)
                or len(choice_ids) != 8
                or any(not isinstance(choice_id, int) or isinstance(choice_id, bool) for choice_id in choice_ids)
                or len(set(choice_ids)) != 8
                or word_id not in choice_ids
                or selected_id not in choice_ids
            ):
                raise ValueError("Câu trả lời không hợp lệ.")
        except ValueError as error:
            return jsonify(error=str(error)), 400

        db = get_db()
        placeholders = ",".join("?" for _ in choice_ids)
        rows = db.execute(
            f"SELECT id, vietnamese, repetition_level, next_review_at FROM collocations WHERE id IN ({placeholders})",
            choice_ids,
        ).fetchall()
        by_id = {row["id"]: row for row in rows}
        if len(by_id) != 8 or word_id not in by_id:
            return jsonify(error="Một hoặc nhiều từ trong câu hỏi không còn tồn tại."), 409

        target = by_id[word_id]
        answered_at = local_now()
        if target["next_review_at"] is None or target["next_review_at"] > answered_at.isoformat():
            return jsonify(error="Từ này không còn đến hạn ôn."), 409

        correct_ids = [
            choice_id for choice_id in choice_ids
            if normalize_meaning(by_id[choice_id]["vietnamese"]) == normalize_meaning(target["vietnamese"])
        ]
        is_correct = selected_id in correct_ids
        if is_correct and target["repetition_level"] == 7:
            new_count = 8
            next_review_at = None
        elif is_correct:
            new_count = target["repetition_level"] + 1
            next_review_at = next_review_for_count(new_count, answered_at).isoformat()
        else:
            new_count = max(target["repetition_level"] - 2, 0)
            next_review_at = (answered_at + timedelta(hours=1)).isoformat()

        db.execute(
            "UPDATE collocations SET repetition_level = ?, next_review_at = ? WHERE id = ?",
            (new_count, next_review_at, word_id),
        )
        return jsonify(
            correct=is_correct,
            correct_option_ids=correct_ids,
            repetition_level=new_count,
            next_review_at=next_review_at,
            completed=next_review_at is None,
        )

    @app.post("/api/flashcard/start")
    def start_flashcards():
        mode = quiz_mode()
        if mode is None:
            return jsonify(error="Chế độ ôn thẻ không hợp lệ."), 400
        rows = get_db().execute(
            "SELECT id, english, vietnamese, repetition_level FROM collocations "
            "WHERE next_review_at IS NOT NULL AND next_review_at <= ? ORDER BY RANDOM()",
            (local_now().isoformat(),),
        ).fetchall()
        if mode == "va":
            cards = [
                {"word_id": row["id"], "front": row["vietnamese"], "back": row["english"], "repetition_level": row["repetition_level"]}
                for row in rows
            ]
        else:
            cards = [
                {"word_id": row["id"], "front": row["english"], "back": row["vietnamese"], "repetition_level": row["repetition_level"]}
                for row in rows
            ]
        return jsonify(cards=cards)

    @app.post("/api/flashcard/answer")
    def answer_flashcard():
        try:
            data = payload()
            word_id = data.get("word_id")
            result = data.get("result")
            response_time_ms = data.get("response_time_ms")
            if (
                not isinstance(word_id, int)
                or isinstance(word_id, bool)
                or not isinstance(result, str)
                or result not in {"correct", "wrong", "relative", "timeout"}
            ):
                raise ValueError("Kết quả ôn thẻ không hợp lệ.")
            if result == "correct" and (
                isinstance(response_time_ms, bool)
                or not isinstance(response_time_ms, (int, float))
                or not 0 <= response_time_ms <= 20000
                or not math.isfinite(response_time_ms)
            ):
                raise ValueError("Thời gian trả lời không hợp lệ.")
        except ValueError as error:
            return jsonify(error=str(error)), 400

        db = get_db()
        word = db.execute(
            "SELECT repetition_level, next_review_at FROM collocations WHERE id = ?",
            (word_id,),
        ).fetchone()
        if word is None:
            return jsonify(error="Không tìm thấy từ vựng."), 404
        answered_at = local_now()
        if word["next_review_at"] is None or word["next_review_at"] > answered_at.isoformat():
            return jsonify(error="Từ này không còn đến hạn ôn."), 409

        if result == "wrong":
            new_count = max(word["repetition_level"] - 2, 0)
            next_review_at = (answered_at + timedelta(hours=1)).isoformat()
        elif result == "relative":
            new_count = word["repetition_level"]
            if new_count == 8:
                next_review_at = None
            elif new_count == 0:
                next_review_at = (answered_at + timedelta(hours=1)).isoformat()
            else:
                next_review_at = next_review_for_count(new_count, answered_at).isoformat()
        elif result == "timeout":
            new_count = max(word["repetition_level"] - 1, 0)
            next_review_at = (answered_at + timedelta(hours=1)).isoformat()
        else:
            elapsed = response_time_ms / 1000
            change = 2 if elapsed <= 2 else 1 if elapsed <= 5 else 0 if elapsed <= 10 else -1
            new_count = min(max(word["repetition_level"] + change, 0), 8)
            if new_count == 8:
                next_review_at = None
            elif new_count == 0:
                next_review_at = (answered_at + timedelta(hours=1)).isoformat()
            else:
                next_review_at = next_review_for_count(new_count, answered_at).isoformat()

        db.execute(
            "UPDATE collocations SET repetition_level = ?, next_review_at = ? WHERE id = ?",
            (new_count, next_review_at, word_id),
        )
        return jsonify(
            repetition_level=new_count,
            next_review_at=next_review_at,
            completed=next_review_at is None,
        )

    return app


if __name__ == "__main__":
    host, port = load_server_config()
    create_app().run(host=host, port=port, debug=False)
