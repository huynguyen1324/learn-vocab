import calendar
import json
import math
import os
import random
import re
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
SQLITE_SCHEMA = """
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
    practice_day TEXT NOT NULL,
    round_id TEXT,
    round_kind TEXT,
    round_mode TEXT,
    daily_practice INTEGER NOT NULL DEFAULT 0,
    source_table TEXT DEFAULT 'collocations'
);
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
CREATE TABLE IF NOT EXISTS vocabulary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    english TEXT NOT NULL,
    vietnamese TEXT NOT NULL,
    repetition_level INTEGER NOT NULL DEFAULT 0 CHECK (repetition_level BETWEEN 0 AND 8),
    practice_count INTEGER NOT NULL DEFAULT 0 CHECK (practice_count >= 0),
    next_review_at TEXT
);
CREATE TABLE IF NOT EXISTS synonymous_collocations (
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
);
"""


def local_now():
    return datetime.now().replace(microsecond=0)


def load_server_config(path=SERVER_CONFIG):
    with Path(path).open(encoding="utf-8-sig") as config_file:
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


def synonym_patterns(english, synonym):
    def words(text):
        return [(match.group(), match.start(), match.end())
                for match in re.finditer(r"\w+", text, flags=re.UNICODE)]

    left, right = words(english), words(synonym)
    longest, matches = 0, []
    for li in range(len(left)):
        for ri in range(len(right)):
            size = 0
            while (li + size < len(left) and ri + size < len(right)
                   and left[li + size][0].casefold() == right[ri + size][0].casefold()):
                size += 1
            if size >= 2:
                if size > longest:
                    longest, matches = size, [(li, ri)]
                elif size == longest:
                    matches.append((li, ri))
    if not longest or len({tuple(left[li + i][0].casefold() for i in range(longest)) for li, _ in matches}) != 1:
        return english, synonym

    common = tuple(left[matches[0][0] + i][0].casefold() for i in range(longest))

    def replace_all(text, tokens):
        spans, index = [], 0
        while index + longest <= len(tokens):
            if tuple(tokens[index + i][0].casefold() for i in range(longest)) == common:
                spans.append((tokens[index][1], tokens[index + longest - 1][2]))
                index += longest
            else:
                index += 1
        for start, end in reversed(spans):
            text = text[:start] + "..." + text[end:]
        return text

    return replace_all(english, left), replace_all(synonym, right)


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


def normalize_meaning(value):
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


class DuplicateEnglishError(Exception):
    pass


def required_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} không được để trống.")
    value = value.strip()
    if len(value) > 500:
        raise ValueError(f"{label} không được dài quá 500 ký tự.")
    return value


def connect_database(database_path):
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    return connection


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(DATABASE=str(ROOT / "instance" / "vocabulary.sqlite3"), TESTING=False)
    if test_config:
        app.config.update(test_config)
    app.config["DATABASE"] = str(Path(app.config["DATABASE"]).resolve())
    connection = connect_database(app.config["DATABASE"])
    try:
        connection.executescript(SQLITE_SCHEMA)
        synonym_columns = {row[1] for row in connection.execute("PRAGMA table_info(synonymous_collocations)")}
        if "vietnamese" not in synonym_columns:
            connection.execute("ALTER TABLE synonymous_collocations ADD COLUMN vietnamese TEXT NOT NULL DEFAULT ''")
        if "english_pattern" not in synonym_columns:
            connection.execute("ALTER TABLE synonymous_collocations ADD COLUMN english_pattern TEXT NOT NULL DEFAULT ''")
        if "synonym_pattern" not in synonym_columns:
            connection.execute("ALTER TABLE synonymous_collocations ADD COLUMN synonym_pattern TEXT NOT NULL DEFAULT ''")
        for row in connection.execute("SELECT id, english, synonym FROM synonymous_collocations").fetchall():
            english_pattern, synonym_pattern = synonym_patterns(row["english"], row["synonym"])
            connection.execute("UPDATE synonymous_collocations SET english_pattern = ?, synonym_pattern = ? WHERE id = ?",
                               (english_pattern, synonym_pattern, row["id"]))
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS vocabulary_english_unique ON vocabulary (lower(english))")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(review_state)")}
        if "practice_day" not in columns and "batch_day" in columns:
            connection.execute("ALTER TABLE review_state RENAME COLUMN batch_day TO practice_day")
        if "daily_practice" not in columns:
            connection.execute("ALTER TABLE review_state ADD COLUMN daily_practice INTEGER NOT NULL DEFAULT 0")
        if "source_table" not in columns:
            connection.execute("ALTER TABLE review_state ADD COLUMN source_table TEXT DEFAULT 'collocations'")
        connection.execute("DROP TABLE IF EXISTS review_batch")
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

    def get_db():
        if "db" not in g:
            g.db = connect_database(current_app.config["DATABASE"])
        return g.db

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

    def get_table_from_request():
        """Lấy và validate tham số ?table= từ request. Bắt buộc phải có."""
        table = request.args.get("table")
        if table not in {"collocations", "vocabulary", "synonymous_collocations"}:
            raise ValueError("Thiếu hoặc không hợp lệ tham số table (collocations/vocabulary/synonymous_collocations).")
        return table

    def get_table_from_state(state):
        """Lấy bảng dữ liệu từ review_state, mặc định collocations."""
        table = state["source_table"] if state and state["source_table"] else "collocations"
        if table not in {"collocations", "vocabulary", "synonymous_collocations"}:
            table = "collocations"
        return table

    def reject_duplicate_english(table, english, synonym=None, word_id=None):
        meaning_field = "synonym" if table == "synonymous_collocations" else "vietnamese"
        for row in get_db().execute(f"SELECT id, english, {meaning_field} FROM {table}"):
            same_english = unicodedata.normalize("NFC", row["english"]).casefold() == english.casefold()
            same_meaning = synonym is None or unicodedata.normalize("NFC", row[meaning_field]).casefold() == synonym.casefold()
            if row["id"] != word_id and same_english and same_meaning:
                raise DuplicateEnglishError("Cặp cụm từ này đã có trong danh sách." if table == "synonymous_collocations" else "Từ tiếng Anh này đã có trong danh sách.")

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
            raise
        except Exception:
            db.rollback()
            raise

    def reset_daily_practice(db, now):
        day = now.date().isoformat()
        state = db.execute("SELECT practice_day FROM review_state WHERE singleton = 1").fetchone()
        if state is None:
            db.execute(
                "INSERT INTO review_state (singleton, practice_day, daily_practice) VALUES (1, ?, 0)",
                (day,),
            )
        elif state["practice_day"] != day:
            db.execute(
                "UPDATE review_state SET practice_day = ?, daily_practice = 0 WHERE singleton = 1",
                (day,),
            )

    def round_word(db, data, word_id, kind=None, shown=False):
        state = db.execute("SELECT * FROM review_state WHERE singleton = 1").fetchone()
        table = get_table_from_state(state)
        reset_daily_practice(db, local_now())
        round_id = data.get("round_id")
        if not isinstance(round_id, str) or not round_id:
            raise ValueError("Thiếu round_id hợp lệ.")
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
        word = db.execute(f"SELECT * FROM {table} WHERE id = ?", (word_id,)).fetchone()
        if word is None:
            raise NotFound("Không tìm thấy từ vựng.")
        due = ((word["repetition_level"] == 0 and word["practice_count"] == 0)
               or (word["next_review_at"] is not None and word["next_review_at"] <= local_now().isoformat())
               or (word["repetition_level"] == 0 and item["shown"]))
        if not due:
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

    def save_result(db, word, result, elapsed, table="collocations", first_review=None):
        answered_at = local_now()
        level = word["repetition_level"]
        if first_review is None:
            first_review = level == 0 and word["practice_count"] == 1
        if result == "known":
            level = 8
        elif first_review and result == "relative":
            level = 1
        elif first_review and result == "correct":
            level = 2 if elapsed <= 5000 else 1
        elif result != "relative":
            fail = result in {"wrong", "timeout"}
            if level > 0:
                change = -1 if fail else 1 if elapsed <= 5000 else 0
            elif fail:
                change = 0
            elif first_review:
                change = 2 if elapsed <= 5000 else 1
            else:
                change = 1
            level = min(8, max(0, level + change))
        next_at = next_review_for_count(level, answered_at)
        next_text = next_at.isoformat() if next_at else None
        db.execute(f"UPDATE {table} SET repetition_level = ?, next_review_at = ? WHERE id = ?",
                   (level, next_text, word["id"]))
        reset_daily_practice(db, answered_at)
        db.execute("UPDATE review_round_words SET answered = 1 WHERE word_id = ?", (word["id"],))
        return dict(repetition_level=level, next_review_at=next_text, completed=next_at is None)

    def receipt(db, word_id, data, result):
        db.execute("INSERT INTO review_receipts VALUES (?, ?, ?)",
                   (word_id, json.dumps({"path": request.path, "data": data}, sort_keys=True), json.dumps(result)))
        return result

    def hard_clause(hard):
        op = ">=" if hard else "<"
        return f"(practice_count - repetition_level {op} 3)"

    def begin_round(db, kind, mode, hard=False, table="collocations"):
        now = local_now()
        reset_daily_practice(db, now)
        now_text = now.isoformat()
        due = "(next_review_at <= ? OR (repetition_level = 0 AND practice_count = 0))"
        rows = db.execute(
            f"SELECT * FROM {table} WHERE repetition_level < 8 AND {due} AND {hard_clause(hard)} "
            "ORDER BY CASE WHEN practice_count > 0 THEN 0 ELSE 1 END, RANDOM()",
            (now_text,),
        ).fetchall()
        round_id = uuid.uuid4().hex
        db.execute("UPDATE review_state SET round_id = ?, round_kind = ?, round_mode = ?, source_table = ? WHERE singleton = 1",
                   (round_id, kind, mode, table))
        db.execute("DELETE FROM review_receipts")
        db.execute("DELETE FROM review_round_words")
        db.executemany("INSERT INTO review_round_words (word_id) VALUES (?)", [(row["id"],) for row in rows])
        return round_id, rows

    @app.post("/api/review/discard")
    def discard_review():
        try:
            data = payload()
            round_id = data.get("round_id")
            if not isinstance(round_id, str) or not round_id:
                raise ValueError("Thiếu round_id hợp lệ.")
            with transaction() as db:
                state = db.execute("SELECT round_id FROM review_state WHERE singleton = 1").fetchone()
                if state is None or state["round_id"] != round_id:
                    return jsonify(discarded=False)
                db.execute("DELETE FROM review_receipts")
                db.execute("DELETE FROM review_round_words")
                db.execute("UPDATE review_state SET round_id = NULL, round_kind = NULL, round_mode = NULL WHERE singleton = 1")
            return jsonify(discarded=True)
        except ValueError as error:
            return jsonify(error=str(error)), 400

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/words")
    def list_words():
        try:
            table = get_table_from_request()
        except ValueError as error:
            return jsonify(error=str(error)), 400
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
            order_clause = "lower(english)" + (" DESC" if descending else "")
        else:
            order_clause = sort_column + (" DESC" if descending else "")

        search = request.args.get("q", "").strip().casefold()
        now = local_now().isoformat()
        # shortcut: filters scan the full personal vocabulary; use indexed search if datasets grow large.
        meaning_field = "synonym" if table == "synonymous_collocations" else "vietnamese"
        rows = get_db().execute(
            f"SELECT id, english, {meaning_field}, {'vietnamese' if table == 'synonymous_collocations' else meaning_field}, repetition_level, practice_count, next_review_at "
            f"FROM {table} ORDER BY {order_clause}"
        ).fetchall()
        result = []
        for row in rows:
            if search and search not in row["english"].casefold() and search not in row[meaning_field].casefold():
                continue
            completed = row["repetition_level"] == 8 and row["next_review_at"] is None
            due = ((row["repetition_level"] == 0 and row["practice_count"] == 0)
                   or (row["next_review_at"] is not None and row["next_review_at"] <= now))
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
                meaning_field: row[meaning_field],
                **({"vietnamese": row["vietnamese"]} if table == "synonymous_collocations" else {}),
                "repetition_level": row["repetition_level"],
                "practice_count": row["practice_count"],
                "status": "Hoàn thành" if completed else f"{row['repetition_level']}/8",
                "next_review_at": row["next_review_at"],
            })
        reset_daily_practice(get_db(), local_now())
        today = get_db().execute("SELECT daily_practice FROM review_state WHERE singleton = 1").fetchone()
        return jsonify(words=result, today_practice=today["daily_practice"] if today else 0)

    def _compute_stats(db, now, now_text, table):
        rows = db.execute(
            f"SELECT repetition_level, practice_count, next_review_at FROM {table}"
        ).fetchall()
        total = len(rows)
        due = upcoming = done = hard = levels = practices = 0
        for row in rows:
            completed = row["repetition_level"] == 8 and row["next_review_at"] is None
            is_due = ((row["repetition_level"] == 0 and row["practice_count"] == 0)
                      or (row["next_review_at"] is not None and row["next_review_at"] <= now_text))
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
        return {
            "total": total,
            "due": due,
            "upcoming": upcoming,
            "completed": done,
            "hard": hard,
            "mastery": 0 if total == 0 else levels / (total * 8),
            "practice_count": practices,
        }

    @app.get("/api/stats")
    def stats():
        now = local_now()
        reset_daily_practice(get_db(), now)
        now_text = now.isoformat()
        today = get_db().execute("SELECT daily_practice FROM review_state WHERE singleton = 1").fetchone()
        return jsonify(
            collocations_stats=_compute_stats(get_db(), now, now_text, "collocations"),
            synonymous_collocations_stats=_compute_stats(get_db(), now, now_text, "synonymous_collocations"),
            vocabulary_stats=_compute_stats(get_db(), now, now_text, "vocabulary"),
            today_practice=today["daily_practice"] if today else 0,
        )

    @app.post("/api/words")
    def add_word():
        try:
            table = get_table_from_request()
        except ValueError as error:
            return jsonify(error=str(error)), 400
        try:
            data = payload()
            english = unicodedata.normalize("NFC", required_text(data.get("english"), "Từ tiếng Anh")).lower()
            meaning_field = "synonym" if table == "synonymous_collocations" else "vietnamese"
            meaning = unicodedata.normalize("NFC", required_text(data.get(meaning_field), "Cụm từ đồng nghĩa" if meaning_field == "synonym" else "Nghĩa tiếng Việt")).lower()
            vietnamese = unicodedata.normalize("NFC", required_text(data.get("vietnamese"), "Nghĩa tiếng Việt")) if meaning_field == "synonym" else meaning
            next_review_at = local_now().isoformat()
            with transaction() as db:
                reject_duplicate_english(table, english, meaning if meaning_field == "synonym" else None)
                if table == "synonymous_collocations":
                    english_pattern, synonym_pattern = synonym_patterns(english, meaning)
                    cursor = db.execute(
                        "INSERT INTO synonymous_collocations (english, synonym, vietnamese, english_pattern, synonym_pattern, repetition_level, next_review_at) "
                        "VALUES (?, ?, ?, ?, ?, 0, ?) RETURNING id",
                        (english, meaning, vietnamese, english_pattern, synonym_pattern, next_review_at),
                    ).fetchone()
                else:
                    cursor = db.execute(
                        f"INSERT INTO {table} (english, vietnamese, repetition_level, next_review_at) VALUES (?, ?, 0, ?) RETURNING id",
                        (english, meaning, next_review_at),
                    ).fetchone()
        except ValueError as error:
            return jsonify(error=str(error)), 400
        except DuplicateEnglishError as error:
            return jsonify(error=str(error)), 409
        except ValueError as error:
            return jsonify(error=str(error)), 400
        except Exception as error:
            if isinstance(error, sqlite3.IntegrityError) or error.__class__.__name__ == "UniqueViolation":
                return jsonify(error="Từ tiếng Anh này đã có trong danh sách."), 409
            raise
        return jsonify(id=cursor["id"]), 201

    @app.post("/api/words/<int:word_id>/practice")
    def practice_word(word_id):
        try:
            data = payload()
            with transaction() as db:
                state = db.execute("SELECT * FROM review_state WHERE singleton = 1").fetchone()
                table = get_table_from_state(state)
                word, item = round_word(db, data, word_id)
                if item["shown"]:
                    raise Conflict("Từ đã được hiển thị trong lượt này.")
                db.execute("UPDATE review_round_words SET shown = 1 WHERE word_id = ?", (word_id,))
                db.execute(f"UPDATE {table} SET practice_count = practice_count + 1 WHERE id = ?", (word_id,))
                db.execute("UPDATE review_state SET daily_practice = daily_practice + 1 WHERE singleton = 1")
            return jsonify(practice_count=word["practice_count"] + 1)
        except ValueError as error:
            return jsonify(error=str(error)), 400

    @app.post("/api/words/<int:word_id>/complete")
    def complete_word(word_id):
        try:
            data = payload()
            with transaction() as db:
                state = db.execute("SELECT * FROM review_state WHERE singleton = 1").fetchone()
                table = get_table_from_state(state)
                if state is not None and state["round_kind"] == "quiz":
                    if not isinstance(data.get("round_id"), str):
                        raise ValueError("Thiếu round_id hợp lệ.")
                    if state["round_id"] != data["round_id"]:
                        raise Conflict("Lượt ôn đã được thay thế.")
                    elapsed = data.get("response_time_ms")
                    if (isinstance(elapsed, bool) or not isinstance(elapsed, (int, float))
                            or not math.isfinite(elapsed) or not 0 <= elapsed <= 3000):
                        raise ValueError("Thời gian trả lời không hợp lệ.")
                    item = db.execute("SELECT shown, answered FROM review_round_words WHERE word_id = ?", (word_id,)).fetchone()
                    saved = db.execute("SELECT response_json FROM review_receipts WHERE word_id = ?", (word_id,)).fetchone()
                    if item is None or not item["shown"] or not item["answered"] or saved is None or not json.loads(saved["response_json"]).get("correct"):
                        raise Conflict("Chỉ có thể hoàn thành sau câu trả lời đúng.")
                    response_data = json.loads(saved["response_json"])
                    if elapsed + response_data.get("response_time_ms", 0) > 3000:
                        raise ValueError("Chỉ có thể đánh dấu đã biết trong 3 giây từ lúc hiện câu hỏi.")
                    db.execute(f"UPDATE {table} SET repetition_level = 8, next_review_at = NULL WHERE id = ?", (word_id,))
                    return jsonify(success=True, repetition_level=8, next_review_at=None, completed=True)
                elapsed = elapsed_time(data, "known")
                word, item = round_word(db, data, word_id, "flashcard", shown=True)
                if word is None:
                    return jsonify(**item)
                result = receipt(db, word_id, data, dict(success=True, **save_result(db, word, "known", elapsed, table)))
            return jsonify(**result)
        except ValueError as error:
            return jsonify(error=str(error)), 400

    @app.post("/api/words/<int:word_id>/restart")
    def restart_word(word_id):
        try:
            table = get_table_from_request()
        except ValueError as error:
            return jsonify(error=str(error)), 400
        db = get_db()
        word = db.execute(
            f"SELECT repetition_level, next_review_at FROM {table} WHERE id = ?",
            (word_id,),
        ).fetchone()
        if word is None:
            return jsonify(error="Không tìm thấy từ vựng."), 404
        if word["repetition_level"] != 8 or word["next_review_at"] is not None:
            return jsonify(error="Chỉ có thể học lại từ đã hoàn thành."), 409
        db.execute("DELETE FROM review_round_words WHERE word_id = ?", (word_id,))
        db.execute(
            f"UPDATE {table} SET repetition_level = 0, next_review_at = ? WHERE id = ?",
            (local_now().isoformat(), word_id),
        )
        return jsonify(success=True)

    @app.put("/api/words/<int:word_id>")
    def update_word(word_id):
        try:
            table = get_table_from_request()
        except ValueError as error:
            return jsonify(error=str(error)), 400
        db = get_db()
        if db.execute(f"SELECT 1 FROM {table} WHERE id = ?", (word_id,)).fetchone() is None:
            return jsonify(error="Không tìm thấy từ vựng."), 404
        try:
            data = payload()
            english = unicodedata.normalize("NFC", required_text(data.get("english"), "Từ tiếng Anh")).lower()
            meaning_field = "synonym" if table == "synonymous_collocations" else "vietnamese"
            meaning = unicodedata.normalize("NFC", required_text(data.get(meaning_field), "Cụm từ đồng nghĩa" if meaning_field == "synonym" else "Nghĩa tiếng Việt")).lower()
            vietnamese = unicodedata.normalize("NFC", required_text(data.get("vietnamese"), "Nghĩa tiếng Việt")) if meaning_field == "synonym" else meaning
            reject_duplicate_english(table, english, meaning if meaning_field == "synonym" else None, word_id)
            if table == "synonymous_collocations":
                english_pattern, synonym_pattern = synonym_patterns(english, meaning)
                db.execute(
                    "UPDATE synonymous_collocations SET english = ?, synonym = ?, vietnamese = ?, english_pattern = ?, synonym_pattern = ? WHERE id = ?",
                    (english, meaning, vietnamese, english_pattern, synonym_pattern, word_id),
                )
            else:
                db.execute(f"UPDATE {table} SET english = ?, vietnamese = ? WHERE id = ?",
                           (english, meaning, word_id))
        except ValueError as error:
            return jsonify(error=str(error)), 400
        except DuplicateEnglishError as error:
            return jsonify(error=str(error)), 409
        except ValueError as error:
            return jsonify(error=str(error)), 400
        except Exception as error:
            if isinstance(error, sqlite3.IntegrityError) or error.__class__.__name__ == "UniqueViolation":
                return jsonify(error="Từ tiếng Anh này đã có trong danh sách."), 409
            raise
        get_db().execute("DELETE FROM review_round_words WHERE word_id = ?", (word_id,))
        return jsonify(success=True)

    @app.delete("/api/words/<int:word_id>")
    def delete_word(word_id):
        try:
            table = get_table_from_request()
        except ValueError as error:
            return jsonify(error=str(error)), 400
        with transaction() as db:
            cursor = db.execute(f"DELETE FROM {table} WHERE id = ?", (word_id,))
            if cursor.rowcount == 0:
                raise NotFound("Không tìm thấy từ vựng.")
            db.execute("DELETE FROM review_round_words WHERE word_id = ?", (word_id,))
        return jsonify(success=True)

    @app.post("/api/quiz/start")
    def start_quiz():
        try:
            table = get_table_from_request()
        except ValueError as error:
            return jsonify(error=str(error)), 400
        mode = quiz_mode()
        if mode is None:
            return jsonify(error="Chế độ quiz không hợp lệ."), 400
        with transaction() as db:
            meaning_field = "synonym" if table == "synonymous_collocations" else "vietnamese"
            english_field = "english_pattern" if table == "synonymous_collocations" else "english"
            choice_field = "synonym_pattern" if table == "synonymous_collocations" else meaning_field
            words = db.execute(f"SELECT id, {english_field} AS english, {choice_field} AS {meaning_field}, repetition_level FROM {table} ORDER BY id").fetchall()
            if len(words) < 8:
                return jsonify(error=f"Cần ít nhất 8 mục trong bảng {table} để bắt đầu quiz."), 400
            round_id, due_words = begin_round(db, "quiz", mode, request.args.get("hard") == "1", table)
            questions = []
            for word in due_words:
                if table == "synonymous_collocations":
                    word = db.execute(
                        "SELECT id, english_pattern AS english, synonym_pattern AS synonym, repetition_level FROM synonymous_collocations WHERE id = ?",
                        (word["id"],),
                    ).fetchone()
                    group = ("leading" if word["english"].startswith("...") or word["synonym"].startswith("...")
                             else "trailing" if word["english"].endswith("...") or word["synonym"].endswith("...")
                             else "none")
                    matching = db.execute(
                        "SELECT id, english_pattern AS english, synonym_pattern AS synonym FROM synonymous_collocations "
                        "WHERE id != ? AND CASE WHEN english_pattern LIKE '...%' OR synonym_pattern LIKE '...%' THEN 'leading' "
                        "WHEN english_pattern LIKE '%...' OR synonym_pattern LIKE '%...' THEN 'trailing' ELSE 'none' END = ? "
                        "ORDER BY RANDOM() LIMIT 7",
                        (word["id"], group),
                    ).fetchall()
                    distractors = list(matching)
                    if len(distractors) < 7:
                        placeholders = ",".join("?" for _ in [word["id"], *[item["id"] for item in distractors]])
                        distractors.extend(db.execute(
                            f"SELECT id, english_pattern AS english, synonym_pattern AS synonym FROM synonymous_collocations "
                            f"WHERE id NOT IN ({placeholders}) ORDER BY RANDOM() LIMIT ?",
                            (word["id"], *[item["id"] for item in distractors], 7 - len(distractors)),
                        ).fetchall())
                else:
                    distractors = db.execute(
                        f"SELECT id, english, {meaning_field} FROM {table} WHERE id != ? ORDER BY RANDOM() LIMIT 7",
                        (word["id"],),
                    ).fetchall()
                choices = list(distractors) + [word]
                random.shuffle(choices)
                db.execute("UPDATE review_round_words SET choice_ids = ? WHERE word_id = ?",
                           (json.dumps([choice["id"] for choice in choices]), word["id"]))
                question = {
                    "word_id": word["id"], "prompt": word["english"] if mode == "av" else word[meaning_field],
                    "repetition_level_after_correct": min(word["repetition_level"] + 2, 8),
                    "choices": [{"id": choice["id"], "text": choice[meaning_field if mode == "av" else "english"]} for choice in choices],
                }
                if table == "synonymous_collocations":
                    correct_row = db.execute(
                        "SELECT english, synonym, vietnamese FROM synonymous_collocations WHERE id = ?", (word["id"],)
                    ).fetchone()
                    question["correct_english"] = correct_row["english"]
                    question["correct_synonym"] = correct_row["synonym"]
                    question["correct_vietnamese"] = correct_row["vietnamese"]
                questions.append(question)
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
                state = db.execute("SELECT * FROM review_state WHERE singleton = 1").fetchone()
                table = get_table_from_state(state)
                word, item = round_word(db, data, word_id, "quiz", shown=True)
                if word is None:
                    return jsonify(**item)
                if set(choice_ids) != set(json.loads(item["choice_ids"])):
                    raise Conflict("Các lựa chọn không thuộc câu hỏi.")
                placeholders = ",".join("?" for _ in choice_ids)
                meaning_field = "synonym" if table == "synonymous_collocations" else "vietnamese"
                query = f"SELECT id, {meaning_field} FROM {table} WHERE id IN ({placeholders})"
                rows = db.execute(query, choice_ids).fetchall()
                if len(rows) != 8:
                    raise Conflict("Một hoặc nhiều mục trong câu hỏi không còn tồn tại.")
                correct_ids = ([word_id] if table == "synonymous_collocations" else
                               [row["id"] for row in rows if normalize_meaning(row[meaning_field]) == normalize_meaning(word[meaning_field])])
                correct = not timeout and selected_id in correct_ids
                result = save_result(db, word, "timeout" if timeout else "correct" if correct else "wrong", elapsed, table)
                result = receipt(db, word_id, data, dict(correct=correct, correct_option_ids=correct_ids, response_time_ms=elapsed, **result))
            return jsonify(**result)
        except ValueError as error:
            return jsonify(error=str(error)), 400

    @app.post("/api/flashcard/start")
    def start_flashcards():
        try:
            table = get_table_from_request()
        except ValueError as error:
            return jsonify(error=str(error)), 400
        mode = quiz_mode()
        if mode is None:
            return jsonify(error="Chế độ ôn thẻ không hợp lệ."), 400
        with transaction() as db:
            round_id, rows = begin_round(db, "flashcard", mode, request.args.get("hard") == "1", table)
            meaning_field = "synonym" if table == "synonymous_collocations" else "vietnamese"
            cards = [{"word_id": row["id"], "front": row[meaning_field if mode == "va" else "english"],
                      "back": row["english" if mode == "va" else meaning_field],
                      **({"vietnamese": row["vietnamese"]} if table == "synonymous_collocations" else {}),
                      "repetition_level": row["repetition_level"],
                      "first_review": row["practice_count"] == 0 and row["repetition_level"] == 0} for row in rows]
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
                state = db.execute("SELECT * FROM review_state WHERE singleton = 1").fetchone()
                table = get_table_from_state(state)
                word, item = round_word(db, data, word_id, "flashcard", shown=True)
                if word is None:
                    return jsonify(**item)
                first_review = word["repetition_level"] == 0 and word["practice_count"] == 1
                result = receipt(db, word_id, data, save_result(db, word, result, elapsed, table, first_review))
            return jsonify(**result)
        except (ValueError, TypeError) as error:
            return jsonify(error=str(error)), 400

    return app


if __name__ == "__main__":
    host, port = load_server_config()
    create_app().run(host=host, port=port, debug=False)
