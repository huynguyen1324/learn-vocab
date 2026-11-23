import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from app import create_app


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / 'review.sqlite3')
        self.app = create_app({'TESTING': True, 'DATABASE': self.path})
        self.client = self.app.test_client()
        self.now = datetime(2026, 11, 19, 10)
        self.clock = patch('app.local_now', side_effect=lambda: self.now)
        self.clock.start()

    def tearDown(self):
        self.clock.stop()
        self.temp.cleanup()

    def seed(self, count=1, level=0, table='collocations'):
        with closing(sqlite3.connect(self.path)) as db, db:
            start = db.execute(f'SELECT COALESCE(MAX(id),0) FROM {table}').fetchone()[0]
            db.executemany(f'INSERT INTO {table} (english,vietnamese,repetition_level,next_review_at) VALUES (?,?,?,?)',
                           [(f'word-{start+i}', f'meaning-{start+i}', level, self.now.isoformat()) for i in range(count)])
        return start + 1

    def start(self, kind='flashcard'):
        result = self.client.post(f'/api/{kind}/start?table=collocations').json
        self.assertIn('round_id', result)
        return result

    def show(self, word, round_id):
        return self.client.post(f'/api/words/{word}/practice?table=collocations', json={'round_id': round_id})

    def answer(self, word, round_id, result='correct', elapsed=3000):
        return self.client.post('/api/flashcard/answer', json=dict(word_id=word, round_id=round_id, result=result, response_time_ms=elapsed))

    def test_grading_boundaries_shared_and_schedules(self):
        for kind in ('quiz', 'flashcard'):
            for elapsed, delta in ((0,1),(5000,1),(5001,0),(10000,0)):
                with self.subTest(kind=kind, elapsed=elapsed):
                    word = self.seed(8 if kind == 'quiz' else 1, 3)
                    round_data = self.start(kind)
                    rid = round_data['round_id']
                    self.assertEqual(self.show(word,rid).status_code,200)
                    if kind == 'flashcard':
                        response = self.answer(word,rid,elapsed=elapsed)
                    else:
                        question = next(q for q in round_data['questions'] if q['word_id']==word)
                        response = self.client.post('/api/quiz/answer',json=dict(round_id=rid,word_id=word,selected_id=word,response_time_ms=elapsed,choice_ids=[c['id'] for c in question['choices']]))
                    self.assertEqual(response.status_code,200,response.json)
                    self.assertEqual(response.json['repetition_level'],3+delta)
        for result in ('wrong','timeout','relative'):
            word=self.seed(level=5);rid=self.start()['round_id'];self.show(word,rid)
            response=self.answer(word,rid,result,10000 if result=='timeout' else 5000)
            self.assertEqual(response.json['repetition_level'],5 if result=='relative' else 4)
            expected=datetime(2026,12,19,10) if result=='relative' else self.now+timedelta(days=7)
            self.assertEqual(response.json['next_review_at'],expected.isoformat())

    def test_protocol_stale_unshown_duplicates_and_known(self):
        word=self.seed();rid=self.start()['round_id']
        self.assertEqual(self.client.post(f'/api/words/{word}/practice?table=collocations').status_code,415)
        self.assertEqual(self.answer(word,rid).status_code,409)
        self.assertEqual(self.show(word,rid).status_code,200)
        self.assertEqual(self.show(word,rid).status_code,409)
        self.assertEqual(self.client.post(f'/api/words/{word}/complete?table=collocations').status_code,415)
        self.assertEqual(self.answer(word,rid,'known',3001).status_code,400)
        newer=self.start()['round_id']
        self.assertEqual(self.answer(word,rid).status_code,409)
        self.assertEqual(self.show(word,rid).status_code,409)
        self.show(word,newer)
        self.assertEqual(self.client.post(f'/api/words/{word}/complete?table=collocations',json={'round_id':newer,'response_time_ms':3001}).status_code,400)
        self.assertEqual(self.answer(word,newer,'known',3000).json['repetition_level'],8)
        self.assertEqual(self.answer(word,newer).status_code,409)

    def test_quiz_timeout_choices_and_synonyms(self):
        word=self.seed(8,3)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE collocations SET vietnamese = ? WHERE id IN (?,?)',('  QUẢ   TÁO ',word,word+1))
        data=self.start('quiz');rid=data['round_id'];q=next(q for q in data['questions'] if q['word_id']==word)
        self.show(word,rid)
        payload=dict(round_id=rid,word_id=word,selected_id=None,result='timeout',response_time_ms=10000,choice_ids=[c['id'] for c in q['choices']])
        self.assertEqual(self.client.post('/api/quiz/answer',json={**payload,'response_time_ms':9999}).status_code,400)
        response=self.client.post('/api/quiz/answer',json=payload)
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.client.post('/api/quiz/answer',json=payload).json,response.json)
        self.assertFalse(response.json['correct'])
        self.assertEqual(response.json['repetition_level'],2)
        self.assertCountEqual(response.json['correct_option_ids'],[word,word+1])

    def test_rounds_randomize_within_practiced_then_fresh_priority(self):
        self.seed(80)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE collocations SET practice_count = 1 WHERE id <= 40")
        seen = set()
        for _ in range(12):
            data = self.start()
            ids = [card['word_id'] for card in data['cards']]
            self.assertEqual(len(ids), 80)
            self.assertTrue(all(word_id <= 40 for word_id in ids[:40]))
            self.assertTrue(all(word_id > 40 for word_id in ids[40:]))
            seen.add(tuple(ids[:40]))
        self.assertGreater(len(seen), 1)

    def test_hard_rounds_are_unlimited_and_randomized(self):
        self.seed(80)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE collocations SET practice_count = 5")
        seen = set()
        for _ in range(12):
            data = self.client.post('/api/flashcard/start?hard=1&table=collocations').json
            ids = [card['word_id'] for card in data['cards']]
            self.assertEqual(len(ids), 80)
            seen.add(tuple(ids))
        self.assertGreater(len(seen), 1)

    def test_priority_and_randomization_apply_to_vocabulary_too(self):
        self.seed(80, table='vocabulary')
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE vocabulary SET practice_count = 1 WHERE id <= 40")
        seen = set()
        for _ in range(12):
            data = self.client.post('/api/flashcard/start?table=vocabulary').json
            ids = [card['word_id'] for card in data['cards']]
            self.assertEqual(len(ids), 80)
            self.assertTrue(all(word_id <= 40 for word_id in ids[:40]))
            self.assertTrue(all(word_id > 40 for word_id in ids[40:]))
            seen.add(tuple(ids[:40]))
        self.assertGreater(len(seen), 1)

    def test_delete_round_word_and_new_words_ignore_complete(self):
        word=self.seed();rid=self.start()['round_id'];self.show(word,rid);self.answer(word,rid,'relative')
        self.assertEqual(self.client.delete(f'/api/words/{word}?table=collocations').status_code,200)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertIsNone(db.execute('SELECT 1 FROM review_round_words WHERE word_id = ?', (word,)).fetchone())
        created=self.client.post('/api/words?table=collocations',json={'english':'new','vietnamese':'mới','complete':True})
        record=self.client.get('/api/words?table=collocations').json['words'][0]
        self.assertEqual((record['repetition_level'],record['practice_count']),(0,0))
        self.assertEqual(record['next_review_at'],self.now.isoformat())

    def test_atomic_concurrent_answer_and_practice(self):
        word=self.seed();rid=self.start()['round_id']
        def show(_):
            return self.app.test_client().post(f'/api/words/{word}/practice?table=collocations',json={'round_id':rid}).status_code
        with ThreadPoolExecutor(2) as pool:
            self.assertCountEqual(list(pool.map(show,range(2))),[200,409])
        def answer(_):
            return self.app.test_client().post('/api/flashcard/answer',json=dict(word_id=word,round_id=rid,result='correct',response_time_ms=3000)).status_code
        with ThreadPoolExecutor(2) as pool:
            self.assertCountEqual(list(pool.map(answer,range(2))),[200,200])
        record=self.client.get('/api/words?table=collocations').json['words'][0]
        self.assertEqual((record['practice_count'],record['repetition_level']),(1,2))

    def test_grading_depends_on_level_and_prior_practice(self):
        cases = (
            (0, 0, 'correct', 5000, 2),
            (0, 0, 'correct', 5001, 1),
            (0, 0, 'wrong', 1000, 0),
            (0, 1, 'correct', 10000, 1),
            (0, 1, 'timeout', 10000, 0),
            (3, 4, 'correct', 5000, 4),
            (3, 4, 'correct', 5001, 3),
            (3, 4, 'wrong', 1000, 2),
        )
        for level, practice, result, elapsed, expected in cases:
            with self.subTest(level=level, practice=practice, result=result, elapsed=elapsed):
                word = self.seed(level=level)
                with closing(sqlite3.connect(self.path)) as db, db:
                    db.execute('UPDATE collocations SET practice_count = ? WHERE id = ?', (practice, word))
                rid = self.start()['round_id']
                self.show(word, rid)
                response = self.answer(word, rid, result, elapsed)
                self.assertEqual(response.status_code, 200, response.json)
                self.assertEqual(response.json['repetition_level'], expected)

    def test_never_practiced_zero_level_is_due_even_with_future_schedule(self):
        word = self.seed()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE collocations SET next_review_at = ? WHERE id = ?',
                       ((self.now + timedelta(days=5)).isoformat(), word))
        self.assertEqual(self.client.get('/api/words?table=collocations&status=due').json['words'][0]['id'], word)
        rid = self.start()['round_id']
        self.assertEqual(self.show(word, rid).status_code, 200)
        # Once shown, the old future timestamp must not invalidate this allowed item.
        self.assertEqual(self.answer(word, rid, 'relative').status_code, 200)

    def test_quiz_completion_needs_correct_answer_for_same_shown_word_and_within_three_seconds(self):
        target = self.seed(8, 0)
        data = self.client.post('/api/quiz/start?table=collocations').json
        question = next(q for q in data['questions'] if q['word_id'] == target)
        self.show(target, data['round_id'])
        other = target + 1
        response = self.client.post(f'/api/words/{other}/complete?table=collocations',
                                    json={'round_id': data['round_id'], 'response_time_ms': 0})
        self.assertEqual(response.status_code, 409)
        answered = self.client.post('/api/quiz/answer', json=dict(
            round_id=data['round_id'], word_id=target, selected_id=target,
            response_time_ms=2000, choice_ids=[choice['id'] for choice in question['choices']]))
        self.assertEqual(answered.status_code, 200)
        too_slow = self.client.post(f'/api/words/{target}/complete?table=collocations',
                                    json={'round_id': data['round_id'], 'response_time_ms': 1001})
        self.assertEqual(too_slow.status_code, 400)
        allowed = self.client.post(f'/api/words/{target}/complete?table=collocations',
                                   json={'round_id': data['round_id'], 'response_time_ms': 1000})
        self.assertEqual(allowed.status_code, 200)

    def test_discard_round_clears_session_without_changing_word_schedule(self):
        word = self.seed()
        data = self.start()
        original = self.client.get('/api/words?table=collocations').json['words'][0]['next_review_at']
        self.show(word, data['round_id'])
        discarded = self.client.post('/api/review/discard', json={'round_id': data['round_id']})
        self.assertEqual(discarded.status_code, 200)
        self.assertTrue(discarded.json['discarded'])
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM review_round_words').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM review_receipts').fetchone()[0], 0)
        current = self.client.get('/api/words?table=collocations').json['words'][0]
        self.assertEqual(current['next_review_at'], original)
        self.assertEqual(self.client.post('/api/flashcard/answer', json=dict(
            word_id=word, round_id=data['round_id'], result='correct', response_time_ms=1000
        )).status_code, 409)

    def test_quiz_normalized_synonyms_both_modes_count_and_completion(self):
        import unicodedata
        for mode in ('va', 'av'):
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute('DELETE FROM collocations')
                db.execute("DELETE FROM sqlite_sequence WHERE name = 'collocations'")
            word = self.seed(8, 7)
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute('UPDATE collocations SET vietnamese = ? WHERE id = ?', ('quả táo', word))
                db.execute('UPDATE collocations SET vietnamese = ? WHERE id = ?',
                           (unicodedata.normalize('NFD', '  QUẢ   TÁO '), word + 1))
            data = self.client.post(f'/api/quiz/start?mode={mode}&table=collocations').json
            question = next(q for q in data['questions'] if q['word_id'] == word)
            record = next(w for w in self.client.get('/api/words?table=collocations').json['words'] if w['id'] == word)
            self.assertEqual(record['practice_count'], 0)
            self.show(word, data['round_id'])
            response = self.client.post(f'/api/quiz/answer?mode={mode}', json=dict(
                round_id=data['round_id'], word_id=word, selected_id=word+1, response_time_ms=3000,
                choice_ids=[c['id'] for c in question['choices']]))
            self.assertTrue(response.json['correct'])
            self.assertEqual(response.json['repetition_level'], 8)
            record = next(w for w in self.client.get('/api/words?table=collocations').json['words'] if w['id'] == word)
            self.assertEqual(record['practice_count'], 1)
            self.assertEqual(self.client.post(f'/api/words/{word}/complete?table=collocations',
                json={'round_id':data['round_id'], 'response_time_ms': 0}).status_code, 200)
            self.assertEqual(self.client.post(f'/api/words/{word}/complete?table=collocations',
                json={'round_id':data['round_id'], 'response_time_ms': 0}).status_code, 200)

    def test_invalid_times_and_zero_floor(self):
        word=self.seed();rid=self.start()['round_id'];self.show(word,rid)
        for value in (None,True,-1,10001,float('inf')):
            self.assertEqual(self.answer(word,rid,'correct',value).status_code,400)
        response=self.answer(word,rid,'wrong',0)
        self.assertEqual(response.json['repetition_level'],0)
        self.assertEqual(response.json['next_review_at'],(self.now+timedelta(hours=1)).isoformat())

    def test_stats_and_daily_practice_reset(self):
        self.seed(2, 0)
        self.seed(1, 8)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE collocations SET next_review_at = NULL WHERE repetition_level = 8")
            db.execute("UPDATE collocations SET practice_count = 5, repetition_level = 1 WHERE id = 2")
            db.execute("UPDATE collocations SET next_review_at = ? WHERE id = 2",
                       ((self.now + timedelta(days=2)).isoformat(),))
        empty = self.client.get('/api/stats').json
        cs = empty['collocations_stats']
        self.assertEqual((cs['total'], cs['due'], cs['upcoming'], cs['completed'], cs['hard']), (3, 1, 1, 1, 1))
        self.assertEqual(cs['practice_count'], 5)
        self.assertAlmostEqual(cs['mastery'], 9 / 24)
        rid = self.start()['round_id']
        self.assertEqual(self.client.get('/api/words?table=collocations').json['today_practice'], 0)
        self.show(1, rid)
        self.assertEqual(self.client.get('/api/words?table=collocations').json['today_practice'], 1)
        self.now += timedelta(days=1)
        self.assertEqual(self.client.get('/api/stats').json['today_practice'], 0)

    def test_list_filters_and_hard_review_sessions(self):
        easy = self.seed()
        hard = self.seed()
        done = self.seed(level=8)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE collocations SET practice_count = 5, next_review_at = ? WHERE id = ?',
                       (self.now.isoformat(), hard))
            db.execute('UPDATE collocations SET next_review_at = NULL WHERE id = ?', (done,))
        listed = {word['id'] for word in self.client.get('/api/words?table=collocations&status=hard').json['words']}
        self.assertEqual(listed, {hard})
        self.assertEqual({w['id'] for w in self.client.get('/api/words?table=collocations&status=completed').json['words']}, {done})
        normal = self.start()
        self.assertEqual({c['word_id'] for c in normal['cards']}, {easy})
        focused = self.client.post('/api/flashcard/start?hard=1&table=collocations').json
        self.assertEqual({c['word_id'] for c in focused['cards']}, {hard})


if __name__ == '__main__':
    unittest.main()
