// Run with: node tests/test_frontend.js (no browser or dependencies required).
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.join(__dirname, "..");
const html = fs.readFileSync(path.join(root, "templates/index.html"), "utf8");
const source = fs.readFileSync(path.join(root, "static/app.js"), "utf8");

class Element {
  constructor() {
    this.children = [];
    this.listeners = {};
    this.dataset = {};
    this.style = {};
    this.attributes = {};
    this.textContent = "";
    this.value = "";
    this.hidden = false;
    this.disabled = false;
    this.checked = false;
    const classes = new Set();
    this.classList = {
      add: (name) => classes.add(name),
      remove: (name) => classes.delete(name),
      contains: (name) => classes.has(name),
      toggle: (name, force) => force ? classes.add(name) : classes.delete(name),
    };
  }
  reset() {}
  focus() {}
  showModal() { this.hidden = false; }
  close() { this.hidden = true; }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(name, callback) { (this.listeners[name] ||= []).push(callback); }
  async fire(name) {
    if (name === "click" && this.disabled) return;
    for (const callback of this.listeners[name] || []) {
      await callback({ target: this, currentTarget: this, preventDefault() {} });
    }
  }
}

function setup() {
  const elements = new Map();
  for (const match of html.matchAll(/<[^>]*\bid="([^"]+)"[^>]*>/g)) {
    const element = new Element();
    element.hidden = /\shidden(?:\s|>)/.test(match[0]);
    element.disabled = /\sdisabled(?:\s|>)/.test(match[0]);
    elements.set(`#${match[1]}`, element);
  }
  const el = (id) => {
    assert.ok(elements.has(`#${id}`), `Missing HTML element: ${id}`);
    return elements.get(`#${id}`);
  };
  el("word-form").elements = { english: new Element(), vietnamese: new Element() };
  const headers = [...html.matchAll(/<th[^>]*data-sort="([^"]+)"/g)].map(match => { const header = new Element(); header.dataset.sort = match[1]; return header; });
  const requests = [];
  const timers = new Map();
  let now = 0;
  let timerId = 0;
  const context = vm.createContext({
    document: {
      querySelector: (selector) => {
        assert.ok(elements.has(selector), `Unknown selector: ${selector}`);
        return elements.get(selector);
      },
      querySelectorAll: (selector) => {
        if (selector === "th[data-sort]") return headers;
        assert.equal(selector, "#choices .choice");
        return el("choices").children;
      },
      createElement: () => new Element(),
    },
    window: { confirm: () => true },
    URLSearchParams,
    Intl,
    performance: { now: () => now },
    setInterval: (callback) => { timers.set(++timerId, callback); return timerId; },
    clearInterval: (id) => timers.delete(id),
    fetch: (url, options) => new Promise((resolve, reject) => {
      requests.push({
        url, options, reject,
        respond: (data, ok = true) => resolve({ ok, json: async () => data }),
      });
    }),
  });
  vm.runInContext(source, context);
  const run = (code) => vm.runInContext(code, context);
  const tick = (milliseconds) => {
    now += milliseconds;
    for (const callback of [...timers.values()]) callback();
  };
  return { el, run, requests, timers, tick, headers };
}

const flush = async () => { for (let i = 0; i < 10; i++) await Promise.resolve(); };
const cards = [
  { word_id: 1, front: "one", back: "một", repetition_level: 2 },
  { word_id: 2, front: "two", back: "hai", repetition_level: 3 },
];
const questions = [{
  word_id: 1, prompt: "một", repetition_level_after_correct: 3,
  choices: [{ id: 1, text: "one" }, { id: 2, text: "two" }],
}];

async function settleDisplay(h, promise, data) {
  h.requests.at(-1).respond({ round_id: "round-1", ...data });
  await flush();
  assert.match(h.requests.at(-1).url, /^\/api\/words\/\d+\/practice\?table=collocations$/);
  h.requests.at(-1).respond({ practice_count: 1 });
  await promise;
}

async function startFlash(h) {
  h.run('showView("flashcard")');
  const promise = h.run('startFlashcards("av")');
  await settleDisplay(h, promise, { cards });
}

const tests = [];
function test(name, body) { tests.push({ name, body }); }

test("leaving flashcards cancels timer and requires a fresh start", async () => {
  const h = setup();
  await startFlash(h);
  assert.equal(h.timers.size, 1);
  h.run('showView("quiz")');
  assert.equal(h.timers.size, 0);
  assert.equal(h.el("flashcard-panel").hidden, true);
  const count = h.requests.length;
  h.tick(21000);
  await flush();
  assert.equal(h.requests.length, count, "no hidden timeout penalty");
  h.run('showView("flashcard")');
  assert.equal(h.el("flashcard-panel").hidden, true);
  assert.equal(h.run("flashcards.cards.length"), 0);
  await startFlash(h);
  assert.equal(h.el("flashcard-panel").hidden, false);
});

test("restarting flashcards stops the old timer before the start response", async () => {
  const h = setup();
  await startFlash(h);
  const pending = h.run('startFlashcards("va")');
  assert.equal(h.timers.size, 0);
  assert.equal(h.el("flashcard-panel").hidden, true);
  const count = h.requests.length;
  h.tick(21000);
  assert.equal(h.requests.length, count);
  await settleDisplay(h, pending, { cards });
  assert.equal(h.timers.size, 1);
  assert.equal(h.run("flashcards.startedAt"), 21000);
});

test("timeout failure retries the same card/result through Next", async () => {
  const h = setup();
  await startFlash(h);
  h.tick(20050);
  assert.equal(h.timers.size, 0);
  assert.equal(h.el("flashcard-back").hidden, false);
  assert.equal(h.el("flashcard-known").disabled, true);
  const first = h.requests.at(-1);
  assert.deepEqual(JSON.parse(first.options.body), { word_id: 1, round_id: "round-1", result: "timeout", response_time_ms: 10000 });
  assert.equal(h.el("start-flashcard-av").disabled, true);
  first.respond({ error: "offline" }, false);
  await flush();
  assert.equal(h.el("flashcard-next").disabled, false);
  assert.equal(h.el("flashcard-next").textContent, "Thử lại");
  await h.el("flashcard-next").fire("click");
  assert.equal(h.requests.at(-1).options.body, first.options.body);
  assert.equal(h.run("flashcards.index"), 0);
  assert.equal(h.el("flashcard-next").disabled, true);
  h.requests.at(-1).respond({});
  await flush();
  assert.equal(h.el("flashcard-next").textContent, "Tiếp theo");
  assert.equal(h.requests.filter((request) => request.url.includes("/practice?")).length, 1, "timeout retry never recounts the front");
  await h.el("flashcard-next").fire("click");
  assert.equal(h.el("flashcard-front").textContent, "two");
  assert.equal(h.requests.at(-1).url, "/api/words/2/practice?table=collocations");
  h.requests.at(-1).respond({ practice_count: 1 });
  await flush();
});

for (const fail of [false, true]) {
  test(`pending flashcard start is locked and ignored after exit (${fail ? "failure" : "success"})`, async () => {
    const h = setup();
    h.run('showView("flashcard")');
    const promise = h.run('startFlashcards("av")');
    const request = h.requests.at(-1);
    const count = h.requests.length;
    await h.run('startFlashcards("va")');
    assert.equal(h.requests.length, count);
    assert.equal(h.el("start-flashcard-va").disabled, true);
    h.run('showView("quiz"); showView("flashcard")');
    await h.run('startFlashcards("va")');
    assert.equal(h.requests.length, count, "lock persists until old request settles");
    request.respond(fail ? { error: "stale error" } : { cards }, !fail);
    await promise;
    assert.equal(h.el("flashcard-panel").hidden, true);
    assert.equal(h.el("notice").textContent, "");
    assert.equal(h.timers.size, 0);
    assert.equal(h.el("start-flashcard-av").disabled, false);
    await startFlash(h);
    assert.equal(h.el("flashcard-front").textContent, "one");
  });

  test(`pending flashcard answer cannot update an exited round (${fail ? "failure" : "success"})`, async () => {
    const h = setup();
    await startFlash(h);
    h.tick(20050);
    const request = h.requests.at(-1);
    const count = h.requests.length;
    await h.run('startFlashcards("va")');
    assert.equal(h.requests.length, count);
    h.run('showView("quiz"); showView("flashcard")');
    request.respond(fail ? { error: "stale timeout" } : {}, !fail);
    await flush();
    assert.equal(h.el("flashcard-feedback").textContent, "");
    assert.equal(h.el("flashcard-panel").hidden, true);
    assert.equal(h.run("flashcards.retryTimeout"), false);
    assert.equal(h.el("start-flashcard-va").disabled, false);
    await startFlash(h);
    assert.equal(h.run("flashcards.answered"), false);
  });
}

test("fast-flip known threshold remains inclusive at three seconds", async () => {
  for (const [elapsed, disabled] of [[2999, false], [3000, false], [3001, true]]) {
    const h = setup();
    await startFlash(h);
    h.tick(elapsed);
    h.run("flipFlashcard()");
    assert.equal(h.el("flashcard-known").disabled, disabled, `${elapsed}ms`);
    assert.equal(h.run("flashcards.flippedAt"), elapsed);
    assert.equal(h.timers.size, 0);
    if (!disabled) {
      const promise = h.run('answerFlashcard("known")');
      assert.equal(h.requests.at(-1).url, "/api/words/1/complete?table=collocations");
      h.requests.at(-1).respond({});
      await promise;
    }
  }
});

test("manual correct retains flip latency and can retry a network failure", async () => {
  const h = setup();
  await startFlash(h);
  h.tick(1250);
  h.run("flipFlashcard()");
  const promise = h.run('answerFlashcard("correct", flashcards.flippedAt)');
  const first = h.requests.at(-1);
  assert.deepEqual(JSON.parse(first.options.body), { word_id: 1, round_id: "round-1", result: "correct", response_time_ms: 1250 });
  first.reject(new Error("network down"));
  await promise;
  assert.equal(h.el("flashcard-correct").disabled, false);
  const retry = h.run('answerFlashcard("correct", flashcards.flippedAt)');
  assert.equal(h.requests.at(-1).options.body, first.options.body);
  h.requests.at(-1).respond({});
  await retry;
});

test("quiz start, answer and completion lock mode/next and invalidate on exit", async () => {
  const h = setup();
  h.run('showView("quiz")');
  const start = h.run('startQuiz("av")');
  const count = h.requests.length;
  await h.run('startQuiz("va")');
  assert.equal(h.requests.length, count);
  assert.equal(h.el("start-quiz-va").disabled, true);
  await settleDisplay(h, start, { questions });
  const answer = h.run("submitAnswer(1)");
  await h.run('startQuiz("va")');
  assert.equal(h.requests.length, count + 2);
  h.requests.at(-1).respond({ correct: true, correct_option_ids: [1], completed: false });
  await answer;
  assert.equal(h.run("quiz.correct"), 1);
  const completion = h.el("mark-complete").fire("click");
  const request = h.requests.at(-1);
  assert.equal(h.el("start-quiz-av").disabled, true);
  await h.el("next-question").fire("click");
  assert.equal(h.run("quiz.index"), 0);
  h.run('showView("flashcard"); showView("quiz")');
  request.respond({ error: "old completion error" }, false);
  await completion;
  assert.equal(h.el("feedback").textContent.includes("old completion error"), false);
  assert.equal(h.el("quiz-panel").hidden, true);
  assert.equal(h.el("start-quiz-va").disabled, false);
});

for (const phase of ["start", "answer"]) {
  for (const fail of [false, true]) {
    test(`quiz ignores stale ${phase} ${fail ? "failure" : "success"}`, async () => {
      const h = setup();
      h.run('showView("quiz")');
      let pending = h.run('startQuiz("av")');
      if (phase === "answer") {
        await settleDisplay(h, pending, { questions });
        pending = h.run("submitAnswer(1)");
      }
      h.run('showView("flashcard"); showView("quiz")');
      h.requests.at(-1).respond(fail ? { error: "stale" } : phase === "start" ? { questions } : { correct: true, correct_option_ids: [1] }, !fail);
      await pending;
      assert.equal(h.el("quiz-panel").hidden, true);
      assert.equal(h.el("notice").textContent, "");
      assert.equal(h.el("feedback").textContent, "");
      assert.equal(h.run("quiz.correct"), 0);
      const fresh = h.run('startQuiz("va")');
      await settleDisplay(h, fresh, { questions });
      assert.equal(h.run("quiz.mode"), "va");
      assert.equal(h.el("quiz-panel").hidden, false);
    });
  }
}

test("latest search/filter response alone renders, including initial load", async () => {
  const h = setup();
  const initial = h.requests[0];
  h.el("search").value = "old";
  const old = h.run("loadWords()");
  const oldRequest = h.requests.at(-1);
  h.el("search").value = "new";
  h.el("status-filter").value = "due";
  const latest = h.run("loadWords()");
  assert.match(h.requests.at(-1).url, /q=new&status=due/);
  h.requests.at(-1).respond({ words: [{ id: 2, english: "new", vietnamese: "mới", status: "due" }] });
  await latest;
  oldRequest.respond({ words: [{ id: 1, english: "old", vietnamese: "cũ", status: "due" }] });
  await old;
  initial.respond({ words: [] });
  await flush();
  assert.equal(h.el("word-list").children[0].children[1].textContent, "new");
});

test("stale search errors are ignored; latest errors still surface", async () => {
  const h = setup();
  const old = h.el("search").fire("input");
  const oldRequest = h.requests.at(-1);
  const latest = h.el("status-filter").fire("change");
  h.requests.at(-1).respond({ words: [] });
  await latest;
  oldRequest.reject(new Error("stale error"));
  await old;
  await flush();
  assert.equal(h.el("notice").textContent, "");
  const failed = h.el("search").fire("input");
  h.requests.at(-1).respond({ error: "latest error" }, false);
  await failed;
  await flush();
  assert.equal(h.el("notice").textContent, "latest error");
});

const practiceRequests = (h) => h.requests.filter((request) => request.url.includes("/practice?"));

for (const type of ["quiz", "flashcard"]) {
  for (const fail of [false, true]) {
    test(`${type} practice is dispatched on display, locked, and stale ${fail ? "failure" : "success"} ignored after exit`, async () => {
      const h = setup();
      h.run(`showView("${type}")`);
      const pending = h.run(type === "quiz" ? 'startQuiz("av")' : 'startFlashcards("av")');
      assert.equal(practiceRequests(h).length, 0, "batch start does not count");
      h.requests.at(-1).respond(type === "quiz" ? { questions } : { cards });
      await flush();
      assert.equal(practiceRequests(h).length, 1);
      assert.equal(practiceRequests(h)[0].url, "/api/words/1/practice?table=collocations");
      assert.equal(practiceRequests(h)[0].options.method, "POST");
      assert.equal(h.el(`${type}-panel`).hidden, false, "front/question is visible before persistence");
      assert.equal(h.el(`start-${type}-av`).disabled, true);
      if (type === "quiz") {
        assert.equal(h.el("choices").children.every((choice) => choice.disabled), true);
        await h.run("submitAnswer(1)");
      } else {
        assert.equal(h.el("flashcard").disabled, true);
        assert.equal(h.timers.size, 0, "timer waits for practice acknowledgement");
        h.run("flipFlashcard()");
        await h.run('answerFlashcard("wrong")');
      }
      assert.equal(practiceRequests(h).length, 1);
      const practice = h.requests.at(-1);
      h.run('showView("list")');
      practice.respond(fail ? { error: "stale practice" } : { practice_count: 1 }, !fail);
      await pending;
      assert.equal(h.el(`${type}-panel`).hidden, true);
      assert.equal(h.el("notice").textContent, "");
      assert.equal(h.timers.size, 0);
      assert.equal(practiceRequests(h).length, 1, "exit still counts the shown unanswered item");
    });
  }

  test(`${type} failed practice requires restart without an automatic retry or answer`, async () => {
    const h = setup();
    h.run(`showView("${type}")`);
    const pending = h.run(type === "quiz" ? 'startQuiz("av")' : 'startFlashcards("av")');
    h.requests.at(-1).respond(type === "quiz" ? { questions } : { cards });
    await flush();
    h.requests.at(-1).reject(new Error("offline"));
    await pending;
    const count = h.requests.length;
    if (type === "quiz") {
      await h.run("submitAnswer(1)");
      await h.el("next-question").fire("click");
      assert.equal(h.el("choices").children.every((choice) => choice.disabled), true);
    } else {
      h.run("flipFlashcard()");
      await h.run('answerFlashcard("wrong")');
      await h.el("flashcard-next").fire("click");
      h.tick(21000);
      assert.equal(h.el("flashcard").disabled, true);
      assert.equal(h.timers.size, 0);
    }
    assert.equal(h.requests.length, count);
    assert.match(h.el(type === "quiz" ? "feedback" : "flashcard-feedback").textContent, /bắt đầu lại/);
    assert.equal(h.el(`start-${type}-av`).disabled, false);
  });
}

test("quiz counts only each shown question, never distractors or answers", async () => {
  const h = setup();
  h.run('showView("quiz")');
  const pending = h.run('startQuiz("av")');
  await settleDisplay(h, pending, { questions: [...questions, { ...questions[0], word_id: 3, prompt: "ba" }] });
  assert.equal(practiceRequests(h).length, 1);
  const answer = h.run("submitAnswer(1)");
  h.requests.at(-1).respond({ correct: true, correct_option_ids: [1], completed: false });
  await answer;
  assert.equal(practiceRequests(h).length, 1);
  await h.el("next-question").fire("click");
  assert.equal(practiceRequests(h).length, 2);
  assert.equal(practiceRequests(h)[1].url, "/api/words/3/practice?table=collocations");
  await h.el("next-question").fire("click");
  assert.equal(practiceRequests(h).length, 2, "pending next is locked");
  h.requests.at(-1).respond({ practice_count: 1 });
  await flush();
  h.run('showView("flashcard")');
  assert.equal(practiceRequests(h).length, 2);
});

test("flashcards count each shown front once, never flips, answers, retries or end screen", async () => {
  const h = setup();
  await startFlash(h);
  assert.equal(practiceRequests(h).length, 1);
  h.run("flipFlashcard(); flipFlashcard()");
  const answer = h.run('answerFlashcard("wrong")');
  h.requests.at(-1).respond({});
  await answer;
  assert.equal(practiceRequests(h).length, 1);
  await h.el("flashcard-next").fire("click");
  assert.equal(practiceRequests(h).length, 2);
  assert.equal(practiceRequests(h)[1].url, "/api/words/2/practice?table=collocations");
  h.requests.at(-1).respond({ practice_count: 1 });
  await flush();
  h.run("flipFlashcard()");
  const last = h.run('answerFlashcard("wrong")');
  h.requests.at(-1).respond({});
  await last;
  await h.el("flashcard-next").fire("click");
  assert.equal(practiceRequests(h).length, 2);
  assert.equal(h.timers.size, 0);
});

test("flashcard clock excludes delayed practice acknowledgement", async () => {
  const h = setup();
  const pending = h.run('startFlashcards("av")');
  h.requests.at(-1).respond({ cards, round_id: "round-1" }); await flush();
  h.tick(21000); assert.equal(h.timers.size, 0);
  h.requests.at(-1).respond({}); await pending;
  assert.equal(h.run("flashcards.startedAt"), 21000);
  h.tick(10000); assert.equal(h.requests.at(-1).url, "/api/words/1/practice?table=collocations");
  h.tick(1); assert.equal(h.requests.at(-1).url, "/api/flashcard/answer");
});

test("phrase list has filtered numbering, mastery, practice count, warning threshold and seven-column empty state", async () => {
  const h = setup();
  h.requests[0].respond({ words: [
    { id: 9, english: "nine", vietnamese: "chín", status: "2/8", repetition_level: 2, practice_count: 7 },
    { id: 12, english: "twelve", vietnamese: "mười hai", status: "5/8", repetition_level: 5, practice_count: 7 },
  ] });
  await flush();
  const rows = h.el("word-list").children;
  assert.equal(rows[0].children.length, 7);
  assert.equal(rows[0].children[0].textContent, 1);
  assert.equal(rows[1].children[0].textContent, 2);
  assert.equal(rows[0].children[3].textContent, "2/8");
  assert.equal(rows[0].children[4].textContent, 7);
  assert.equal(rows[0].classList.contains("needs-practice"), true);
  assert.equal(rows[1].classList.contains("needs-practice"), false);
  h.run("renderWords([])");
  assert.equal(h.el("word-list").children[0].children[0].colSpan, 7);
  assert.match(html, /Danh sách cụm từ/);
  assert.match(html, /Mức thông thạo/);
});

test("vocabulary list CRUD targets vocabulary and review selection/stats are wired", async () => {
  const h = setup();
  h.el("vocab-list-tab").fire("click");
  assert.match(h.requests.at(-1).url, /table=vocabulary/);
  h.requests.at(-1).respond({ words: [{ id: 4, english: "apple", vietnamese: "táo", status: "0/8", practice_count: 0, repetition_level: 0 }] });
  await flush();
  assert.equal(h.el("vocab-word-list").children[0].children[1].textContent, "apple");
  assert.equal(h.el("vocab-word-list").children[0].children.length, 7);
  await h.el("add-vocab-word").fire("click");
  assert.equal(h.el("dialog-title").textContent, "Thêm từ vựng");
  h.el("word-form").elements.english.value = "pear";
  h.el("word-form").elements.vietnamese.value = "lê";
  const save = h.el("word-form").fire("submit");
  assert.equal(h.requests.at(-1).url, "/api/words?table=vocabulary");
  h.requests.at(-1).respond({ id: 5 }); await flush();
  assert.match(h.requests.at(-1).url, /table=vocabulary/);
  h.requests.at(-1).respond({ words: [] }); await save;
  h.el("quiz-table").value = "vocabulary";
  const quiz = h.run('startQuiz("av")');
  assert.match(h.requests.at(-1).url, /table=vocabulary/);
  h.requests.at(-1).respond({ round_id: "v", questions: [] }); await quiz;
  h.el("flashcard-table").value = "vocabulary";
  const cards = h.run('startFlashcards("av")');
  assert.match(h.requests.at(-1).url, /table=vocabulary/);
  h.requests.at(-1).respond({ round_id: "v", cards: [] }); await cards;
});

test("rest notice and stats tab", async () => { 
  const h = setup();
  h.requests[0].respond({ words: [], today_practice: 201 });
  await flush();
  assert.equal(h.el("rest-notice").hidden, false);
  h.run('showView("stats")');
  assert.equal(h.el("stats-view").hidden, false);
  assert.equal(h.requests.at(-1).url, "/api/stats");
  h.requests.at(-1).respond({
    vocabulary_stats: { total: 8, due: 2, upcoming: 3, completed: 3, hard: 1, mastery: 0.5, practice_count: 20 },
  });
  await flush();
  assert.equal(h.el("stat-total").textContent, 8);
  assert.match(h.el("stat-mastery").textContent, /50/);
});

test("hard-review checkbox is sent only when ticked", async () => {
  const h = setup();
  h.requests[0].respond({ words: [] }); await flush();
  h.el("quiz-hard").checked = true;
  const pending = h.run('startQuiz("av")');
  assert.match(h.requests.at(-1).url, /hard=1/);
  h.requests.at(-1).respond({ round_id: "r", questions: [] }); await pending;
});

test("add and edit forms save without removed checkbox", async () => {
  for (const editing of [false, true]) {
    const h = setup();
    h.run(editing ? 'openWordDialog({id: 4, english: "one", vietnamese: "mot"})' : 'openWordDialog()');
    h.el("word-form").elements.english.value = "new";
    h.el("word-form").elements.vietnamese.value = "moi";
    const saving = h.el("word-form").fire("submit");
    const request = h.requests.at(-1);
    assert.equal(request.options.method, editing ? "PUT" : "POST");
    assert.deepEqual(JSON.parse(request.options.body), {english: "new", vietnamese: "moi"});
    request.respond({}); await flush();
    h.requests.at(-1).respond({words: []}); await saving;
    assert.equal(h.el("word-dialog").hidden, true);
  }
});

test("sortable headers dispatch selected sort", async () => {
  const h = setup(); await h.headers[0].fire("click");
  assert.match(h.requests.at(-1).url, /sort_by=english_desc/);
});

test("quiz boundaries retain time, exclude API wait, and safely retry frozen answers", async () => {
  for (const elapsed of [5000, 5001, 10000, 10001]) {
    const h = setup();
    const start = h.run('startQuiz("av")');
    h.requests.at(-1).respond({questions, round_id: "round-1"}); await flush();
    h.tick(20000); assert.equal(h.timers.size, 0);
    h.requests.at(-1).respond({}); await start;
    assert.equal(JSON.parse(h.requests.at(-1).options.body).round_id, "round-1");
    h.tick(elapsed);
    const pending = elapsed <= 10000 ? h.run("submitAnswer(1)") : null;
    const request = h.requests.at(-1);
    const payload = JSON.parse(request.options.body);
    assert.equal(payload.response_time_ms, Math.min(elapsed, 10000));
    assert.equal(payload.selected_id, elapsed > 10000 ? null : 1);
    assert.equal(payload.result, elapsed > 10000 ? "timeout" : undefined);
    assert.equal(h.el("choices").children.every(button => button.disabled), true);
    request.respond({error: "offline"}, false); if (pending) await pending; else await flush();
    assert.equal(h.run("quiz.saved"), false);
    await h.el("next-question").fire("click");
    assert.equal(h.requests.at(-1).options.body, request.options.body);
    h.requests.at(-1).respond({correct: false, correct_option_ids: [1]}); await flush();
    assert.equal(h.run("quiz.saved"), true);
    assert.equal(h.run("quiz.index"), 0);
  }
});

test("flashcard flip boundaries send retained times for all self ratings", async () => {
  for (const elapsed of [5000, 5001, 10000]) {
    for (const result of ["correct", "wrong", "relative"]) {
      const h = setup(); await startFlash(h); h.tick(elapsed); h.run("flipFlashcard()");
      const pending = h.run(`answerFlashcard("${result}")`);
      assert.equal(JSON.parse(h.requests.at(-1).options.body).response_time_ms, elapsed);
      h.requests.at(-1).respond({}); await pending;
    }
  }
});

(async () => {
  for (const { name, body } of tests) {
    await body();
    console.log(`ok - ${name}`);
  }
  console.log(`${tests.length} frontend regression tests passed`);
})().catch((error) => { console.error(error); process.exitCode = 1; });
