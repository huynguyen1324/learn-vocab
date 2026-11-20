import calendar
import json
import math
import random
import sqlite3
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, current_app, g, jsonify, render_template, request
from werkzeug.exceptions import HTTPException, Conflict, NotFound


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
CREATE TABLE IF NOT EXISTS review_state (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    batch_day TEXT NOT NULL,
    round_id TEXT,
    round_kind TEXT,
    round_mode TEXT,
    daily_practice INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS review_batch (word_id INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS review_receipts (
    word_id INTEGER PRIMARY KEY,
    request_json TEXT NOT NULL,
    response_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS review_round_words (
    word_id INTEGER PRIMARY KEY,
    choice_ids TEXT,
    shown INTEGER NOT NULL DEFAULT 0,
    answered INTEGER NOT NULL DEFAULT 0
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
    if count == 8:
        return None
    if count == 0:
        return answered_at + timedelta(hours=1)
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


# Interest keywords for personalized quiz distractors
INTEREST_KEYWORDS = {
    "gaming": ["game", "play", "winner", "score", "match", "team", "player", "champion", "win", "defeat"],
    "swimming": ["swim", "water", "pool", "dive", "float", "stroke", "underwater"],
    "badminton": ["badminton", "racket", "shuttle", "serve", "net", "court"],
    "sports": ["sport", "athlete", "coach", "training", "competition", "exercise", "fitness"],
    "history": ["history", "war", "battle", "king", "empire", "century", "ancient", "historical", "period"],
    "economics": ["economy", "market", "price", "trade", "business", "profit", "cost", "economic", "commerce"],
    "finance": ["finance", "bank", "investment", "stock", "debt", "loan", "capital", "money", "financial"],
    "it": ["computer", "software", "program", "code", "internet", "technology", "data", "digital", "system"],
}


def score_word_by_interests(word_english, word_vietnamese):
    """Score a word based on relevance to user's interests"""
    score = 0
    combined_text = f"{word_english} {word_vietnamese}".lower()

    for category, keywords in INTEREST_KEYWORDS.items():
        for keyword in keywords:
            if keyword in combined_text:
                score += 1

    return score


def select_distractors_with_interests(target_word_id, all_words, count=7):
    """Select distractor words, prioritizing those related to user interests"""
    candidates = [w for w in all_words if w["id"] != target_word_id]

    # Score and sort by interest relevance
    scored = [
        (w, score_word_by_interests(w["english"], w["vietnamese"]))
        for w in candidates
    ]
    scored.sort(key=lambda x: x[1], reverse=True)

    # Return top scoring words, or all if not enough candidates
    result_count = min(count, len(scored))
    return [w[0] for w in scored[:result_count]]


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
        columns = {row[1] for row in connection.execute("PRAGMA table_info(review_state)")}
        if "daily_practice" not in columns:
            connection.execute("ALTER TABLE review_state ADD COLUMN daily_practice INTEGER NOT NULL DEFAULT 0")
            connection.commit()
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

    @contextmanager
    def transaction():
        db = get_db()
        db.execute("BEGIN IMMEDIATE")
        try:
            yield db
            db.commit()
        except HTTPException:
            db.rollback()
            db.execute("BEGIN IMMEDIATE")
            refresh_batch(db, local_now())
            db.commit()
            raise
        except Exception:
            db.rollback()
            raise

    def refresh_batch(db, now):
        day = now.date().isoformat()
        state = db.execute("SELECT * FROM review_state WHERE singleton = 1").fetchone()
        if state is None or state["batch_day"] != day:
            db.execute("DELETE FROM review_receipts")
            db.execute("DELETE FROM review_batch")
            db.execute("DELETE FROM review_round_words")
            db.execute(
                "INSERT OR REPLACE INTO review_state (singleton, batch_day, daily_practice) VALUES (1, ?, 0)",
                (day,),
            )
        db.execute("DELETE FROM review_batch WHERE word_id NOT IN "
                   "(SELECT id FROM collocations WHERE repetition_level < 8 AND next_review_at IS NOT NULL)")

    def round_word(db, data, word_id, kind=None, shown=False):
        refresh_batch(db, local_now())
        round_id = data.get("round_id")
        if not isinstance(round_id, str) or not round_id:
            raise ValueError("Thiếu round_id hợp lệ.")
        state = db.execute("SELECT * FROM review_state WHERE singleton = 1").fetchone()
        if state is None or state["round_id"] != round_id:
            raise Conflict("Lượt ôn đã được thay thế.")
        if kind and (state["round_kind"] != kind or (kind == "quiz" and state["round_mode"] != quiz_mode())):
            raise Conflict("Lượt ôn không phù hợp.")
        receipt = db.execute("SELECT * FROM review_receipts WHERE word_id = ?", (word_id,)).fetchone()
        if receipt is not None and shown:
            key = json.dumps({"path": request.path, "data": data}, sort_keys=True)
            if receipt["request_json"] == key:
                return None, json.loads(receipt["response_json"])
            raise Conflict("Từ đã được trả lời với kết quả khác.")
        item = db.execute("SELECT * FROM review_round_words WHERE word_id = ?", (word_id,)).fetchone()
        if item is None or item["answered"] or (shown and not item["shown"]):
            raise Conflict("Từ không thuộc lượt ôn hoặc đã được trả lời.")
        word = db.execute("SELECT * FROM collocations WHERE id = ?", (word_id,)).fetchone()
        if word is None:
            raise NotFound("Không tìm thấy từ vựng.")
        if word["next_review_at"] is None or (word["next_review_at"] > local_now().isoformat()
                and not (word["repetition_level"] == 0 and (word["practice_count"] == 0 or item["shown"]))):
            raise Conflict("Từ này không còn đến hạn ôn.")
        return word, item

    def elapsed_time(data, result):
        elapsed = data.get("response_time_ms")
        if (isinstance(elapsed, bool) or not isinstance(elapsed, (int, float))
                or not math.isfinite(elapsed) or not 0 <= elapsed <= 10000
                or (result == "timeout" and elapsed != 10000)
                or (result == "known" and elapsed > 3000)):
            raise ValueError("Thời gian trả lời không hợp lệ.")
        return elapsed

    def save_result(db, word, result, elapsed):
        answered_at = local_now()
        level = word["repetition_level"]
        prior = max(word["practice_count"] - 1, 0)
        if result == "known":
            level = 8
        elif result != "relative":
            fail = result in {"wrong", "timeout"}
            if level > 0:
                change = -1 if fail else 1 if elapsed <= 5000 else 0
            elif fail:
                change = 0
            elif prior == 0:
                change = 2 if elapsed <= 5000 else 1
            else:
                change = 1
            level = min(8, max(0, level + change))
        next_at = next_review_for_count(level, answered_at)
        next_text = next_at.isoformat() if next_at else None
        db.execute("UPDATE collocations SET repetition_level = ?, next_review_at = ? WHERE id = ?",
                   (level, next_text, word["id"]))
        refresh_batch(db, answered_at)
        hard = word["practice_count"] - level >= 3
        if next_at is not None and next_at.date() == answered_at.date() and not hard:
            db.execute("INSERT OR IGNORE INTO review_batch (word_id) SELECT ? "
                       "WHERE (SELECT COUNT(*) FROM review_batch) < 100", (word["id"],))
        else:
            db.execute("DELETE FROM review_batch WHERE word_id = ?", (word["id"],))
        db.execute("UPDATE review_round_words SET answered = 1 WHERE word_id = ?", (word["id"],))
        return dict(repetition_level=level, next_review_at=next_text, completed=next_at is None)

    def receipt(db, word_id, data, result):
        db.execute("INSERT INTO review_receipts VALUES (?, ?, ?)",
                   (word_id, json.dumps({"path": request.path, "data": data}, sort_keys=True), json.dumps(result)))
        return result

    def hard_clause(hard):
        op = ">=" if hard else "<"
        return f"(practice_count - repetition_level {op} 3)"

    def begin_round(db, kind, mode, hard=False):
        now = local_now()
        refresh_batch(db, now)
        db.execute(
            "DELETE FROM review_batch WHERE word_id IN "
            "(SELECT id FROM collocations WHERE practice_count - repetition_level >= 3)"
        )
        now_text = now.isoformat()
        due = "(next_review_at <= ? OR (repetition_level = 0 AND practice_count = 0))"
        if hard:
            rows = db.execute(
                f"SELECT * FROM collocations WHERE repetition_level < 8 AND {due} AND {hard_clause(True)} "
                "ORDER BY CASE WHEN practice_count > 0 THEN 0 ELSE 1 END, id LIMIT 100",
                (now_text,),
            ).fetchall()
        else:
            count = db.execute("SELECT COUNT(*) FROM review_batch").fetchone()[0]
            rows = db.execute(
                "SELECT * FROM collocations WHERE id IN (SELECT word_id FROM review_batch) "
                f"AND {due} AND {hard_clause(False)} ORDER BY id", (now_text,)).fetchall()
            slots = 100 - count
            outside = (
                "id NOT IN (SELECT word_id FROM review_batch) AND repetition_level < 8 AND "
                f"{due} AND {hard_clause(False)}"
            )
            practiced = db.execute(
                f"SELECT * FROM collocations WHERE {outside} AND practice_count > 0 ORDER BY id LIMIT ?",
                (now_text, slots)).fetchall() if slots else []
            remain = slots - len(practiced)
            fresh = db.execute(
                f"SELECT * FROM collocations WHERE {outside} AND practice_count = 0 ORDER BY id LIMIT ?",
                (now_text, remain)).fetchall() if remain else []
            rows += practiced + fresh
        round_id = uuid.uuid4().hex
        db.execute("UPDATE review_state SET round_id = ?, round_kind = ?, round_mode = ? WHERE singleton = 1",
                   (round_id, kind, mode))
        db.execute("DELETE FROM review_receipts")
        db.execute("DELETE FROM review_round_words")
        db.executemany("INSERT INTO review_round_words (word_id) VALUES (?)", [(row["id"],) for row in rows])
        return round_id, rows

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/words")
    def list_words():
        status_filter = request.args.get("status", "all")
        if status_filter not in {"all", "due", "upcoming", "completed", "hard"}:
            return jsonify(error="Bộ lọc không hợp lệ."), 400

        # Handle sorting
        sort_by = request.args.get("sort_by", "english")
        valid_sorts = {"english", "repetition_level", "practice_count", "next_review_at"}
        sort_column = sort_by.replace("_desc", "")
        if sort_column not in valid_sorts:
            sort_column = "english"
        descending = sort_by.endswith("_desc")

        # Build ORDER BY clause
        if sort_column == "english":
            order_clause = "english COLLATE NOCASE" + (" DESC" if descending else "")
        else:
            order_clause = sort_column + (" DESC" if descending else "")

        search = request.args.get("q", "").strip().casefold()
        now = local_now().isoformat()
        # shortcut: filters scan the full personal vocabulary; use indexed search if datasets grow large.
        rows = get_db().execute(
            f"SELECT id, english, vietnamese, repetition_level, practice_count, next_review_at "
            f"FROM collocations ORDER BY {order_clause}"
        ).fetchall()
        result = []
        for row in rows:
            if search and search not in row["english"].casefold() and search not in row["vietnamese"].casefold():
                continue
            completed = row["repetition_level"] == 8 and row["next_review_at"] is None
            due = row["next_review_at"] is not None and (row["next_review_at"] <= now
                    or (row["repetition_level"] == 0 and row["practice_count"] == 0))
            hard = row["practice_count"] - row["repetition_level"] >= 3
            if status_filter == "due" and not due:
                continue
            if status_filter == "upcoming" and (due or completed):
                continue
            if status_filter == "completed" and not completed:
                continue
            if status_filter == "hard" and not hard:
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
        refresh_batch(get_db(), local_now())
        today = get_db().execute("SELECT daily_practice FROM review_state WHERE singleton = 1").fetchone()
        return jsonify(words=result, today_practice=today["daily_practice"] if today else 0)

    @app.get("/api/stats")
    def stats():
        now = local_now()
        refresh_batch(get_db(), now)
        now_text = now.isoformat()
        rows = get_db().execute(
            "SELECT repetition_level, practice_count, next_review_at FROM collocations"
        ).fetchall()
        total = len(rows)
        due = upcoming = done = hard = levels = practices = 0
        for row in rows:
            completed = row["repetition_level"] == 8 and row["next_review_at"] is None
            is_due = row["next_review_at"] is not None and (
                row["next_review_at"] <= now_text
                or (row["repetition_level"] == 0 and row["practice_count"] == 0)
            )
            if completed:
                done += 1
            elif is_due:
                due += 1
            else:
                upcoming += 1
            if row["practice_count"] - row["repetition_level"] >= 3:
                hard += 1
            levels += row["repetition_level"]
            practices += row["practice_count"]
        today = get_db().execute("SELECT daily_practice FROM review_state WHERE singleton = 1").fetchone()
        return jsonify(
            total=total,
            due=due,
            upcoming=upcoming,
            completed=done,
            hard=hard,
            mastery=0 if total == 0 else levels / (total * 8),
            practice_count=practices,
            today_practice=today["daily_practice"] if today else 0,
        )

    @app.post("/api/words")
    def add_word():
        try:
            data = payload()
            english = unicodedata.normalize("NFC", required_text(data.get("english"), "Từ tiếng Anh")).lower()
            vietnamese = required_text(data.get("vietnamese"), "Nghĩa tiếng Việt")
            repetition_level = 0
            next_review_at = local_now().isoformat()
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
        try:
            data = payload()
            with transaction() as db:
                word, item = round_word(db, data, word_id)
                if item["shown"]:
                    raise Conflict("Từ đã được hiển thị trong lượt này.")
                db.execute("UPDATE review_round_words SET shown = 1 WHERE word_id = ?", (word_id,))
                db.execute("UPDATE collocations SET practice_count = practice_count + 1 WHERE id = ?", (word_id,))
                db.execute("UPDATE review_state SET daily_practice = daily_practice + 1 WHERE singleton = 1")
            return jsonify(practice_count=word["practice_count"] + 1)
        except ValueError as error:
            return jsonify(error=str(error)), 400

    @app.post("/api/words/<int:word_id>/complete")
    def complete_word(word_id):
        try:
            data = payload()
            with transaction() as db:
                refresh_batch(db, local_now())
                state = db.execute("SELECT * FROM review_state WHERE singleton = 1").fetchone()
                if state is not None and state["round_kind"] == "quiz":
                    if not isinstance(data.get("round_id"), str):
                        raise ValueError("Thiếu round_id hợp lệ.")
                    if state["round_id"] != data["round_id"]:
                        raise Conflict("Lượt ôn đã được thay thế.")
                    saved = db.execute("SELECT response_json FROM review_receipts WHERE word_id = ?", (word_id,)).fetchone()
                    if saved is None or not json.loads(saved["response_json"]).get("correct"):
                        raise Conflict("Chỉ có thể hoàn thành sau câu trả lời đúng.")
                    db.execute("UPDATE collocations SET repetition_level = 8, next_review_at = NULL WHERE id = ?", (word_id,))
                    db.execute("DELETE FROM review_batch WHERE word_id = ?", (word_id,))
                    return jsonify(success=True, repetition_level=8, next_review_at=None, completed=True)
                elapsed = elapsed_time(data, "known")
                word, item = round_word(db, data, word_id, "flashcard", shown=True)
                if word is None:
                    return jsonify(**item)
                result = receipt(db, word_id, data, dict(success=True, **save_result(db, word, "known", elapsed)))
            return jsonify(**result)
        except ValueError as error:
            return jsonify(error=str(error)), 400

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
        with transaction() as db:
            cursor = db.execute("DELETE FROM collocations WHERE id = ?", (word_id,))
            if cursor.rowcount == 0:
                raise NotFound("Không tìm thấy từ vựng.")
            db.execute("DELETE FROM review_batch WHERE word_id = ?", (word_id,))
            db.execute("DELETE FROM review_round_words WHERE word_id = ?", (word_id,))
        return jsonify(success=True)

    @app.post("/api/quiz/start")
    def start_quiz():
        mode = quiz_mode()
        if mode is None:
            return jsonify(error="Chế độ quiz không hợp lệ."), 400
        with transaction() as db:
            words = db.execute("SELECT id, english, vietnamese FROM collocations ORDER BY id").fetchall()
            if len(words) < 8:
                return jsonify(error="Cần ít nhất 8 từ tiếng Anh trong danh sách để bắt đầu quiz."), 400
            round_id, due_words = begin_round(db, "quiz", mode, request.args.get("hard") == "1")
            questions = []
            for word in due_words:
                choices = select_distractors_with_interests(word["id"], words, 7) + [word]
                random.shuffle(choices)
                db.execute("UPDATE review_round_words SET choice_ids = ? WHERE word_id = ?",
                           (json.dumps([choice["id"] for choice in choices]), word["id"]))
                questions.append({
                    "word_id": word["id"], "prompt": word["english"] if mode == "av" else word["vietnamese"],
                    "repetition_level_after_correct": min(word["repetition_level"] + 2, 8),
                    "choices": [{"id": choice["id"], "text": choice["vietnamese" if mode == "av" else "english"]} for choice in choices],
                })
        return jsonify(round_id=round_id, questions=questions)

    @app.post("/api/quiz/answer")
    def answer_quiz():
        if quiz_mode() is None:
            return jsonify(error="Chế độ quiz không hợp lệ."), 400
        try:
            data = payload()
            word_id, selected_id, choice_ids = data.get("word_id"), data.get("selected_id"), data.get("choice_ids")
            timeout = data.get("result") == "timeout"
            elapsed = elapsed_time(data, "timeout" if timeout else "correct")
            if (type(word_id) is not int or not isinstance(choice_ids, list) or len(choice_ids) != 8
                    or any(type(value) is not int for value in choice_ids) or len(set(choice_ids)) != 8
                    or word_id not in choice_ids or (selected_id is not None if timeout else
                        type(selected_id) is not int or selected_id not in choice_ids)):
                raise ValueError("Câu trả lời không hợp lệ.")
            with transaction() as db:
                word, item = round_word(db, data, word_id, "quiz", shown=True)
                if word is None:
                    return jsonify(**item)
                if set(choice_ids) != set(json.loads(item["choice_ids"])):
                    raise Conflict("Các lựa chọn không thuộc câu hỏi.")
                rows = db.execute("SELECT id, vietnamese FROM collocations WHERE id IN (%s)" % ",".join("?" for _ in choice_ids), choice_ids).fetchall()
                if len(rows) != 8:
                    raise Conflict("Một hoặc nhiều từ trong câu hỏi không còn tồn tại.")
                correct_ids = [row["id"] for row in rows if normalize_meaning(row["vietnamese"]) == normalize_meaning(word["vietnamese"])]
                correct = not timeout and selected_id in correct_ids
                result = save_result(db, word, "timeout" if timeout else "correct" if correct else "wrong", elapsed)
                result = receipt(db, word_id, data, dict(correct=correct, correct_option_ids=correct_ids, **result))
            return jsonify(**result)
        except ValueError as error:
            return jsonify(error=str(error)), 400

    @app.post("/api/flashcard/start")
    def start_flashcards():
        mode = quiz_mode()
        if mode is None:
            return jsonify(error="Chế độ ôn thẻ không hợp lệ."), 400
        with transaction() as db:
            round_id, rows = begin_round(db, "flashcard", mode, request.args.get("hard") == "1")
            cards = [{"word_id": row["id"], "front": row["vietnamese" if mode == "va" else "english"],
                      "back": row["english" if mode == "va" else "vietnamese"],
                      "repetition_level": row["repetition_level"]} for row in rows]
        return jsonify(round_id=round_id, cards=cards)

    @app.post("/api/flashcard/answer")
    def answer_flashcard():
        try:
            data = payload()
            word_id, result = data.get("word_id"), data.get("result")
            if type(word_id) is not int or result not in {"correct", "wrong", "relative", "timeout", "known"}:
                raise ValueError("Kết quả ôn thẻ không hợp lệ.")
            elapsed = elapsed_time(data, result)
            with transaction() as db:
                word, item = round_word(db, data, word_id, "flashcard", shown=True)
                if word is None:
                    return jsonify(**item)
                result = receipt(db, word_id, data, save_result(db, word, result, elapsed))
            return jsonify(**result)
        except (ValueError, TypeError) as error:
            return jsonify(error=str(error)), 400

    return app


if __name__ == "__main__":
    host, port = load_server_config()
    create_app().run(host=host, port=port, debug=False)
