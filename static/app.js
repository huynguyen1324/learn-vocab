const notice = document.querySelector("#notice");
const wordList = document.querySelector("#word-list");
const vocabWordList = document.querySelector("#vocab-word-list");
const synonymWordList = document.querySelector("#synonym-word-list");
const wordDialog = document.querySelector("#word-dialog");
const wordForm = document.querySelector("#word-form");
const formError = document.querySelector("#form-error");
let words = [];
let editingId = null;
let currentSortBy = "english";
let activeListTable = "collocations";
let activeWords = words;

let wordRequest = 0;

function setRoundPending(round, type, pending) {
  round.pending = pending;
  document.querySelector(`#start-${type}-av`).disabled = pending;
  document.querySelector(`#start-${type}-va`).disabled = pending;
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Đã xảy ra lỗi.");
  return data;
}

function showNotice(message = "", isError = false) {
  notice.textContent = message;
  notice.classList.toggle("error", isError);
  notice.hidden = !message;
}

function formatDate(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function addCell(row, text) {
  const cell = document.createElement("td");
  cell.textContent = text;
  row.append(cell);
  return cell;
}

function renderWords(items) {
  activeWords = items;
  const list = activeListTable === "collocations" ? wordList : activeListTable === "vocabulary" ? vocabWordList : synonymWordList;
  list.replaceChildren();
  if (!items.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = activeListTable === "synonymous_collocations" ? 8 : 7;
    cell.className = "empty";
    cell.textContent = activeListTable === "vocabulary" ? "Không có từ vựng nào phù hợp." : activeListTable === "synonymous_collocations" ? "Không có cụm từ đồng nghĩa nào phù hợp." : "Không có cụm từ nào phù hợp.";
    row.append(cell);
    list.append(row);
    return;
  }

  for (const [index, word] of items.entries()) {
    const row = document.createElement("tr");
    row.classList.toggle("needs-practice", word.practice_count - word.repetition_level >= 3);
    addCell(row, index + 1);
    addCell(row, word.english);
    addCell(row, word[activeListTable === "synonymous_collocations" ? "synonym" : "vietnamese"]);
    if (activeListTable === "synonymous_collocations") addCell(row, word.vietnamese);
    addCell(row, word.status);
    addCell(row, word.practice_count);
    addCell(row, word.next_review_at ? formatDate(word.next_review_at) : "—");

    const actions = document.createElement("td");
    actions.className = "actions";
    const edit = document.createElement("button");
    edit.type = "button";
    edit.textContent = "Sửa";
    edit.dataset.action = "edit";
    edit.dataset.id = word.id;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "Xóa";
    remove.dataset.action = "delete";
    remove.dataset.id = word.id;
    if (word.status === "Hoàn thành") {
      const restart = document.createElement("button");
      restart.type = "button";
      restart.textContent = "Học lại";
      restart.dataset.action = "restart";
      restart.dataset.id = word.id;
      actions.append(edit, remove, restart);
    } else {
      actions.append(edit, remove);
    }
    row.append(actions);
    list.append(row);
  }
}

async function loadWords() {
  const request = ++wordRequest;
  const isVocab = activeListTable === "vocabulary";
  const isSynonym = activeListTable === "synonymous_collocations";
  const params = new URLSearchParams({
    table: activeListTable,
    q: document.querySelector(isVocab ? "#vocab-search" : isSynonym ? "#synonym-search" : "#search").value,
    status: document.querySelector(isVocab ? "#vocab-status-filter" : isSynonym ? "#synonym-status-filter" : "#status-filter").value,
    sort_by: currentSortBy,
  });
  try {
    const data = await api(`/api/words?${params}`);
    if (request === wordRequest) {
      renderWords(data.words);
      const rest = document.querySelector("#rest-notice");
      rest.hidden = !(data.today_practice > 200);
    }
  } catch (error) {
    if (request === wordRequest) throw error;
  }
}

function openWordDialog(word = null) {
  editingId = word ? word.id : null;
  wordForm.reset();
  formError.textContent = "";
  const isSynonym = activeListTable === "synonymous_collocations";
  const noun = activeListTable === "collocations" ? "cụm từ" : isSynonym ? "cụm từ đồng nghĩa" : "từ vựng";
  document.querySelector("#dialog-title").textContent = word ? `Sửa ${noun}` : `Thêm ${noun}`;
  document.querySelector("#dialog-type-label").textContent = isSynonym ? "Cụm tiếng Anh và cụm đồng nghĩa" : `${noun[0].toUpperCase()}${noun.slice(1)} tiếng Anh`;
  wordForm.elements.english.value = word ? word.english : "";
  wordForm.elements.vietnamese.value = word ? (isSynonym ? word.synonym : word.vietnamese) : "";
  wordForm.elements.gloss.value = word ? (word.vietnamese || "") : "";
  document.querySelector("#gloss-label").hidden = !isSynonym;
  document.querySelector("#meaning-label").textContent = isSynonym ? "Cụm từ đồng nghĩa" : "Nghĩa tiếng Việt";
  wordDialog.showModal();
  wordForm.elements.english.focus();
}

document.querySelector("#add-word").addEventListener("click", () => openWordDialog());
document.querySelector("#add-vocab-word").addEventListener("click", () => openWordDialog());
document.querySelector("#add-synonym-word").addEventListener("click", () => openWordDialog());
document.querySelector("#cancel-word").addEventListener("click", () => wordDialog.close());

wordForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  formError.textContent = "";
  const data = {
    english: wordForm.elements.english.value,
    [activeListTable === "synonymous_collocations" ? "synonym" : "vietnamese"]: wordForm.elements.vietnamese.value,
    ...(activeListTable === "synonymous_collocations" ? { vietnamese: wordForm.elements.gloss.value } : {}),
  };
  try {
    const table = activeListTable;
    await api(`${editingId ? `/api/words/${editingId}` : "/api/words"}?table=${table}`, {
      method: editingId ? "PUT" : "POST",
      body: JSON.stringify(data),
    });
    wordDialog.close();
    showNotice(editingId ? "Đã cập nhật." : "Đã thêm mới.");
    await loadWords();
  } catch (error) {
    formError.textContent = error.message;
  }
});

for (const listElement of [wordList, vocabWordList, synonymWordList]) listElement.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const word = activeWords.find((item) => item.id === Number(button.dataset.id));
  if (!word) return;
  if (button.dataset.action === "edit") {
    openWordDialog(word);
    return;
  }
  const noun = activeListTable === "collocations" ? "cụm từ" : activeListTable === "synonymous_collocations" ? "cụm từ đồng nghĩa" : "từ vựng";
  if (button.dataset.action === "restart" && !window.confirm(`Học lại "${word.english}" từ mốc 1? Tiến độ cũ sẽ bị xóa.`)) return;
  try {
    if (button.dataset.action === "delete") {
      if (!window.confirm(`Xóa ${noun} "${word.english}" vĩnh viễn?`)) return;
      await api(`/api/words/${word.id}?table=${activeListTable}`, { method: "DELETE" });
      showNotice("Đã xóa.");
    } else {
      await api(`/api/words/${word.id}/${button.dataset.action}?table=${activeListTable}`, { method: "POST" });
      showNotice(button.dataset.action === "complete" ? "Đã đánh dấu hoàn thành." : "Từ đã được đặt lại mốc 1.");
    }
    await loadWords();
  } catch (error) {
    showNotice(error.message, true);
  }
});

for (const selector of ["#search", "#vocab-search", "#synonym-search"] ) {
  document.querySelector(selector).addEventListener("input", () => loadWords().catch((error) => showNotice(error.message, true)));
}
for (const selector of ["#status-filter", "#vocab-status-filter", "#synonym-status-filter"]) {
  document.querySelector(selector).addEventListener("change", () => loadWords().catch((error) => showNotice(error.message, true)));
}

// Add click handlers for sortable table headers
const tableHeaders = document.querySelectorAll("th[data-sort]");
tableHeaders.forEach(header => {
  header.addEventListener("click", () => {
    const sortBy = header.dataset.sort;

    // Extract the base column name (remove _desc if present)
    const currentBase = currentSortBy.replace("_desc", "");

    if (currentBase === sortBy) {
      // Same column, toggle descending
      if (currentSortBy.endsWith("_desc")) {
        currentSortBy = sortBy;
      } else {
        currentSortBy = sortBy + "_desc";
      }
    } else {
      // Different column, start with ascending
      currentSortBy = sortBy;
    }

    loadWords().catch((error) => showNotice(error.message, true));
  });
});

async function loadStats() {
  const data = await api("/api/stats");
  for (const [prefix, key] of [["collocation-", "collocations_stats"], ["synonym-", "synonymous_collocations_stats"], ["", "vocabulary_stats"]]) {
    const stats = data[key];
    for (const field of ["total", "due", "upcoming", "completed", "hard", "practice_count"]) {
      const target = document.querySelector(`#${prefix}stat-${field === "practice_count" ? "practice" : field}`);
      if (target) target.textContent = stats[field];
    }
    const mastery = document.querySelector(`#${prefix}stat-mastery`);
    if (mastery) mastery.textContent = stats.total ? stats.mastery.toLocaleString("vi-VN", { style: "percent", maximumFractionDigits: 1 }) : "0%";
  }
}

function showView(view) {
  const isList = view === "list";
  const isVocabList = view === "vocab-list";
  const isSynonymList = view === "synonym-list";
  const isQuiz = view === "quiz";
  const isFlashcard = view === "flashcard";
  const isStats = view === "stats";
  if (!isQuiz) {
    stopQuizTimer();
    const roundId = quiz.roundId;
    quiz.generation += 1;
    quiz.questions = [];
    quiz.roundId = null;
    document.querySelector("#quiz-panel").hidden = true;
    if (roundId) api("/api/review/discard", { method: "POST", body: JSON.stringify({ round_id: roundId }) }).catch(() => {});
  }
  if (!isFlashcard) {
    const roundId = flashcards.roundId;
    resetFlashcards();
    flashcards.roundId = null;
    if (roundId) api("/api/review/discard", { method: "POST", body: JSON.stringify({ round_id: roundId }) }).catch(() => {});
  }
  document.querySelector("#list-view").hidden = !isList;
  document.querySelector("#vocab-list-view").hidden = !isVocabList;
  document.querySelector("#synonym-list-view").hidden = !isSynonymList;
  document.querySelector("#quiz-view").hidden = !isQuiz;
  document.querySelector("#flashcard-view").hidden = !isFlashcard;
  document.querySelector("#stats-view").hidden = !isStats;
  document.querySelector("#list-tab").classList.toggle("active", isList);
  document.querySelector("#vocab-list-tab").classList.toggle("active", isVocabList);
  document.querySelector("#synonym-list-tab").classList.toggle("active", isSynonymList);
  document.querySelector("#quiz-tab").classList.toggle("active", isQuiz);
  document.querySelector("#flashcard-tab").classList.toggle("active", isFlashcard);
  document.querySelector("#stats-tab").classList.toggle("active", isStats);
  showNotice();
  if (isList || isVocabList || isSynonymList) {
    activeListTable = isVocabList ? "vocabulary" : isSynonymList ? "synonymous_collocations" : "collocations";
    loadWords().catch((error) => showNotice(error.message, true));
  }
  if (isStats) loadStats().catch((error) => showNotice(error.message, true));
}

document.querySelector("#list-tab").addEventListener("click", () => showView("list"));
document.querySelector("#vocab-list-tab").addEventListener("click", () => showView("vocab-list"));
document.querySelector("#synonym-list-tab").addEventListener("click", () => showView("synonym-list"));
document.querySelector("#quiz-tab").addEventListener("click", () => showView("quiz"));
document.querySelector("#flashcard-tab").addEventListener("click", () => showView("flashcard"));
document.querySelector("#stats-tab").addEventListener("click", () => showView("stats"));

const quiz = {
  mode: "va",
  table: "collocations",
  questions: [],
  index: 0,
  correct: 0,
  answering: false,
  pending: false,
  generation: 0,
  displayReady: false,
  timer: null, startedAt: 0, saved: false, retryAnswer: null, roundId: null,
};

function stopQuizTimer() {
  clearInterval(quiz.timer);
  quiz.timer = null;
}

function paintProgress(id, elapsed) {
  const progress = Math.min(elapsed / 10000, 1);
  document.querySelector(`#${id}-progress-fill`).style.width = `${progress * 100}%`;
  document.querySelector(`#${id}-progress`).setAttribute("aria-valuenow", String(Math.round(progress * 10000)));
  document.querySelector(`#${id}-progress-fill`).dataset.band = elapsed <= 5000 ? "fast" : elapsed <= 10000 ? "medium" : "slow";
}

async function renderQuestion() {
  stopQuizTimer();
  quiz.saved = false;
  quiz.retryAnswer = null;
  paintProgress("quiz", 0);
  const panel = document.querySelector("#quiz-panel");
  const count = document.querySelector("#question-count");
  const prompt = document.querySelector("#question-prompt");
  const stage = document.querySelector("#question-stage");
  const choices = document.querySelector("#choices");
  const feedback = document.querySelector("#feedback");
  const markComplete = document.querySelector("#mark-complete");
  const next = document.querySelector("#next-question");

  if (quiz.index >= quiz.questions.length) {
    count.textContent = "";
    prompt.textContent = `Đã hoàn thành lượt ôn. Số câu đúng: ${quiz.correct}/${quiz.questions.length}.`;
    stage.textContent = "";
    choices.replaceChildren();
    feedback.textContent = "";
    markComplete.hidden = true;
    next.hidden = true;
    panel.hidden = false;
    return;
  }

  const question = quiz.questions[quiz.index];
  count.textContent = `Câu ${quiz.index + 1}/${quiz.questions.length}`;
  prompt.textContent = question.prompt;
  stage.textContent = "Đúng ≤5 giây / ≤10 giây theo mức từ. Hết 10 giây hoặc sai: trừ hoặc giữ mức.";
  choices.replaceChildren();
  feedback.textContent = "";
  markComplete.hidden = true;
  markComplete.disabled = false;
  markComplete.textContent = "Đã biết";
  next.hidden = true;
  next.textContent = "Tiếp theo";
  quiz.answering = false;
  for (const choice of question.choices) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "choice";
    button.disabled = true;
    button.textContent = choice.text;
    button.dataset.id = choice.id;
    button.addEventListener("click", () => submitAnswer(choice.id));
    choices.append(button);
  }
  panel.hidden = false;
  quiz.displayReady = false;
  const generation = quiz.generation;
  setRoundPending(quiz, "quiz", true);
  try {
    await api(`/api/words/${question.word_id}/practice?table=${quiz.table}`, { method: "POST", body: JSON.stringify({ round_id: quiz.roundId }) });
    if (generation !== quiz.generation) return;
    quiz.displayReady = true;
    for (const button of choices.children) button.disabled = false;
    quiz.startedAt = performance.now();
    quiz.timer = setInterval(() => {
      const elapsed = performance.now() - quiz.startedAt;
      paintProgress("quiz", elapsed);
      if (elapsed > 10000) submitAnswer(null);
    }, 50);
  } catch (error) {
    if (generation !== quiz.generation) return;
    feedback.textContent = `${error.message} Không thể xác nhận số lần ôn. Hãy bắt đầu lại lượt ôn; yêu cầu này sẽ không tự thử lại.`;
  } finally {
    setRoundPending(quiz, "quiz", false);
  }
}

async function submitAnswer(selectedId) {
  if (quiz.pending || !quiz.displayReady || quiz.answering || !quiz.questions[quiz.index]) return;
  const elapsed = performance.now() - quiz.startedAt;
  const timeout = selectedId === null || elapsed > 10000;
  const payload = quiz.retryAnswer || { word_id: quiz.questions[quiz.index].word_id, round_id: quiz.roundId, selected_id: timeout ? null : selectedId, response_time_ms: timeout ? 10000 : Math.min(Math.round(elapsed), 10000), choice_ids: quiz.questions[quiz.index].choices.map(choice => choice.id), ...(timeout ? { result: "timeout" } : {}) };
  quiz.retryAnswer = payload;
  quiz.answering = true;
  stopQuizTimer();
  for (const button of document.querySelectorAll("#choices .choice")) button.disabled = true;
  setRoundPending(quiz, "quiz", true);
  const generation = quiz.generation;
  const question = quiz.questions[quiz.index];
  const feedback = document.querySelector("#feedback");
  const markComplete = document.querySelector("#mark-complete");
  const next = document.querySelector("#next-question");
  try {
    const result = await api(`/api/quiz/answer?mode=${quiz.mode}&table=${quiz.table}`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (generation !== quiz.generation) return;
    quiz.saved = true;
    quiz.answerStartedAt = performance.now();
    quiz.retryAnswer = null;
    if (result.correct) quiz.correct += 1;
    for (const button of document.querySelectorAll("#choices .choice")) {
      const id = Number(button.dataset.id);
      if (result.correct_option_ids.includes(id)) button.classList.add("correct");
      else if (id === selectedId) button.classList.add("incorrect");
      button.disabled = true;
    }
    const correctWords = question.choices
      .filter((choice) => result.correct_option_ids.includes(choice.id))
      .map((choice) => choice.text);
    feedback.textContent = result.correct
      ? `Chính xác. Đáp án đúng: ${correctWords.join(", ")}.`
      : `Chưa chính xác. Đáp án đúng: ${correctWords.join(", ")}.`;
    if (quiz.table === "synonymous_collocations") {
      for (const [label, value] of [["Tiếng Anh", question.correct_english], ["Đồng nghĩa", question.correct_synonym], ["Nghĩa tiếng Việt", question.correct_vietnamese]]) {
        const detail = document.createElement("span");
        detail.className = "quiz-vietnamese-meaning";
        detail.textContent = `${label}: ${value || "—"}`;
        feedback.append(document.createElement("br"), detail);
      }
    }
    markComplete.hidden = !result.correct || result.completed || performance.now() - quiz.startedAt > 3000;
    next.hidden = false;
    next.textContent = "Tiếp theo";
  } catch (error) {
    if (generation !== quiz.generation) return;
    quiz.answering = false;
    feedback.textContent = `${error.message} Kết quả chưa lưu. Thử lại để tiếp tục.`;
    next.hidden = false;
    next.textContent = "Thử lại";
  } finally {
    setRoundPending(quiz, "quiz", false);
  }
}

async function startQuiz(mode) {
  if (quiz.pending) return;
  if (quiz.roundId) api("/api/review/discard", { method: "POST", body: JSON.stringify({ round_id: quiz.roundId }) }).catch(() => {});
  quiz.roundId = null;
  resetFlashcards();
  stopQuizTimer();
  setRoundPending(quiz, "quiz", true);
  const generation = ++quiz.generation;
  document.querySelector("#quiz-panel").hidden = true;
  quiz.mode = mode;
  showNotice();
  try {
    const hard = document.querySelector("#quiz-hard").checked ? "&hard=1" : "";
    const table = document.querySelector("#quiz-table").value || "collocations";
    quiz.table = table || "collocations";
    const data = await api(`/api/quiz/start?mode=${mode}${hard}&table=${table}`, { method: "POST" });
    if (generation !== quiz.generation) {
      api("/api/review/discard", { method: "POST", body: JSON.stringify({ round_id: data.round_id }) }).catch(() => {});
      return;
    }
    quiz.roundId = data.round_id;
    quiz.questions = data.questions;
    quiz.index = 0;
    quiz.correct = 0;
    if (!quiz.questions.length) {
      document.querySelector("#quiz-panel").hidden = true;
      showNotice(`Hiện không có ${table === "vocabulary" ? "từ vựng" : table === "synonymous_collocations" ? "cụm từ đồng nghĩa" : "cụm từ"} nào đến hạn ôn.`);
      return;
    }
    await renderQuestion();
  } catch (error) {
    if (generation !== quiz.generation) return;
    document.querySelector("#quiz-panel").hidden = true;
    showNotice(error.message, true);
  } finally {
    setRoundPending(quiz, "quiz", false);
  }
}

document.querySelector("#start-quiz-av").addEventListener("click", () => startQuiz("av"));
document.querySelector("#start-quiz-va").addEventListener("click", () => startQuiz("va"));
document.querySelector("#next-question").addEventListener("click", () => {
  if (quiz.pending || !quiz.displayReady || !quiz.questions.length) return;
  if (quiz.retryAnswer) { submitAnswer(quiz.retryAnswer.selected_id); return; }
  if (!quiz.saved) return;
  quiz.index += 1;
  renderQuestion();
});
document.querySelector("#mark-complete").addEventListener("click", async (event) => {
  if (quiz.pending || !quiz.saved || !quiz.questions[quiz.index]) return;
  const button = event.currentTarget;
  const question = quiz.questions[quiz.index];
  const generation = quiz.generation;
  setRoundPending(quiz, "quiz", true);
  button.disabled = true;
  try {
    await api(`/api/words/${question.word_id}/complete?table=${quiz.table}`, { method: "POST", body: JSON.stringify({ round_id: quiz.roundId, response_time_ms: Math.round(performance.now() - quiz.startedAt) }) });
    if (generation !== quiz.generation) return;
    button.textContent = "Đã biết";
    document.querySelector("#feedback").textContent += " Đã biết.";
  } catch (error) {
    if (generation !== quiz.generation) return;
    button.disabled = false;
    document.querySelector("#feedback").textContent += ` ${error.message}`;
  } finally {
    setRoundPending(quiz, "quiz", false);
  }
});

const flashcards = { displayReady: false, table: "collocations", cards: [], index: 0, startedAt: 0, flippedAt: null, timer: null, answered: false, pending: false, generation: 0, retryTimeout: false };
const flashcardButton = document.querySelector("#flashcard");
const flashcardFill = document.querySelector("#flashcard-progress-fill");

function stopFlashcardTimer() {
  clearInterval(flashcards.timer);
  flashcards.timer = null;
}

function resetFlashcards() {
  stopFlashcardTimer();
  flashcards.generation += 1;
  flashcards.cards = [];
  flashcards.index = 0;
  flashcards.flippedAt = null;
  flashcards.answered = false;
  flashcards.retryTimeout = false;
  document.querySelector("#flashcard-panel").hidden = true;
  document.querySelector("#flashcard-back").hidden = true;
  document.querySelector("#flashcard-gloss").hidden = true;
  flashcardButton.classList.remove("flipped");
}

function paintFlashcardProgress(elapsed) {
  paintProgress("flashcard", elapsed * 1000);
}

async function answerFlashcard(result, elapsed = null) {
  if (flashcards.pending || !flashcards.displayReady || flashcards.answered || !flashcards.cards[flashcards.index]) return;
  if ((!flashcards.cards[flashcards.index].first_review && flashcards.flippedAt === null) || (result === "known" && performance.now() - flashcards.startedAt > 3000) || (flashcards.retryTimeout && result !== "timeout")) return;
  elapsed = result === "timeout" ? 10000 : Math.min(Math.round(flashcards.firstReview ? performance.now() - flashcards.startedAt : flashcards.flippedAt), 10000);
  flashcards.answered = true;
  setRoundPending(flashcards, "flashcard", true);
  const generation = flashcards.generation;
  document.querySelector("#flashcard-next").disabled = true;
  stopFlashcardTimer();
  const card = flashcards.cards[flashcards.index];
  try {
    if (result === "known") {
      await api(`/api/words/${card.word_id}/complete?table=${flashcards.table}`, { method: "POST", body: JSON.stringify({ round_id: flashcards.roundId, response_time_ms: elapsed }) });
    } else {
      await api("/api/flashcard/answer", {
        method: "POST",
        body: JSON.stringify({
          word_id: card.word_id,
          round_id: flashcards.roundId,
          result,
          ...(elapsed === null ? {} : { response_time_ms: elapsed }),
        }),
      });
    }
    if (generation !== flashcards.generation) return;
    flashcards.retryTimeout = false;
    document.querySelector("#flashcard-next").textContent = "Tiếp theo";
    const messages = {
      timeout: "Quá 10 giây: đã tự lật thẻ.",
      relative: "Đã lưu. Mốc ôn giữ nguyên, lịch ôn được dời theo mốc hiện tại.",
      correct: "Đã lưu kết quả nhớ đúng.",
      wrong: "Đã lưu kết quả nhớ sai.",
      known: "Đã đánh dấu cụm từ này hoàn thành.",
    };
    document.querySelector("#flashcard-feedback").textContent = messages[result];
    document.querySelector("#flashcard-correct").disabled = true;
    document.querySelector("#flashcard-wrong").disabled = true;
    document.querySelector("#flashcard-relative").disabled = true;
    document.querySelector("#flashcard-known").disabled = true;
    document.querySelector("#flashcard-next").disabled = false;
  } catch (error) {
    if (generation !== flashcards.generation) return;
    flashcards.answered = false;
    document.querySelector("#flashcard-feedback").textContent = error.message;
    if (result === "timeout") {
      flashcards.retryTimeout = true;
      document.querySelector("#flashcard-next").textContent = "Thử lại";
      document.querySelector("#flashcard-next").disabled = false;
    }
  } finally {
    setRoundPending(flashcards, "flashcard", false);
  }
}

function flipFlashcard(automatic = false) {
  if (flashcards.pending || !flashcards.displayReady || !flashcards.cards[flashcards.index] || flashcards.flippedAt !== null || flashcards.cards[flashcards.index].first_review) return;
  const elapsed = performance.now() - flashcards.startedAt;
  automatic = automatic || elapsed > 10000;
  flashcards.flippedAt = automatic ? 10000 : elapsed;
  stopFlashcardTimer();
  flashcardButton.classList.add("flipped");
  document.querySelector("#flashcard-back").hidden = false;
  const gloss = document.querySelector("#flashcard-gloss");
  gloss.hidden = !flashcards.cards[flashcards.index].vietnamese;
  document.querySelector("#flashcard-correct").disabled = automatic;
  document.querySelector("#flashcard-wrong").disabled = automatic;
  document.querySelector("#flashcard-relative").disabled = automatic;
  document.querySelector("#flashcard-known").disabled = automatic || elapsed > 3000;
  paintProgress("flashcard", flashcards.flippedAt);
  if (automatic) { flashcards.retryTimeout = true; answerFlashcard("timeout"); }
}

async function renderFlashcard() {
  stopFlashcardTimer();
  flashcards.flippedAt = null;
  flashcards.answered = false;
  flashcards.retryTimeout = false;
  document.querySelector("#flashcard-next").textContent = "Tiếp theo";
  const panel = document.querySelector("#flashcard-panel");
  const feedback = document.querySelector("#flashcard-feedback");
  const correct = document.querySelector("#flashcard-correct");
  const wrong = document.querySelector("#flashcard-wrong");
  const next = document.querySelector("#flashcard-next");
  if (flashcards.index >= flashcards.cards.length) {
    document.querySelector("#flashcard-count").textContent = "Đã hoàn thành lượt ôn.";
    document.querySelector("#flashcard-stage").textContent = "";
    document.querySelector("#flashcard-front").textContent = "";
    document.querySelector("#flashcard-back").hidden = true;
    document.querySelector("#flashcard-gloss").hidden = true;
    flashcardButton.disabled = true;
    correct.disabled = true;
    wrong.disabled = true;
    document.querySelector("#flashcard-relative").disabled = true;
    document.querySelector("#flashcard-known").disabled = true;
    next.disabled = true;
    panel.hidden = false;
    return;
  }
  const card = flashcards.cards[flashcards.index];
  document.querySelector("#flashcard-count").textContent = `Câu ${flashcards.index + 1}/${flashcards.cards.length}`;
  document.querySelector("#flashcard-stage").textContent = `Mức thông thạo: ${card.repetition_level}/8`;
  document.querySelector("#flashcard-front").textContent = card.front;
  document.querySelector("#flashcard-back").textContent = card.back;
  document.querySelector("#flashcard-back").hidden = !card.first_review;
  const gloss = document.querySelector("#flashcard-gloss");
  gloss.textContent = card.vietnamese || "";
  gloss.hidden = !card.first_review || !card.vietnamese;
  document.querySelector("#flashcard-progress-fill").style.width = "0%";
  document.querySelector("#flashcard-progress").setAttribute("aria-valuenow", "0");
  feedback.textContent = "";
  flashcardButton.disabled = true;
  flashcardButton.classList.remove("flipped");
  correct.disabled = true;
  wrong.disabled = true;
  document.querySelector("#flashcard-relative").disabled = true;
  document.querySelector("#flashcard-known").disabled = true;
  next.disabled = true;
  flashcards.displayReady = false;
  const generation = flashcards.generation;
  setRoundPending(flashcards, "flashcard", true);
  panel.hidden = false;
  try {
    await api(`/api/words/${card.word_id}/practice?table=${flashcards.table}`, { method: "POST", body: JSON.stringify({ round_id: flashcards.roundId }) });
    if (generation !== flashcards.generation) return;
    flashcards.displayReady = true;
    flashcards.startedAt = performance.now();
    if (card.first_review) {
      for (const id of ["flashcard-correct", "flashcard-wrong", "flashcard-relative", "flashcard-known"]) document.querySelector(`#${id}`).disabled = false;
      return;
    }
    flashcardButton.disabled = false;
    flashcards.timer = setInterval(() => {
      const elapsed = (performance.now() - flashcards.startedAt) / 1000;
      paintFlashcardProgress(elapsed);
      if (elapsed > 10) flipFlashcard(true);
    }, 50);
  } catch (error) {
    if (generation !== flashcards.generation) return;
    stopFlashcardTimer();
    feedback.textContent = `${error.message} Không thể xác nhận số lần ôn. Hãy bắt đầu lại lượt ôn; yêu cầu này sẽ không tự thử lại.`;
  } finally {
    setRoundPending(flashcards, "flashcard", false);
  }
}

async function startFlashcards(mode) {
  if (flashcards.pending) return;
  if (flashcards.roundId) api("/api/review/discard", { method: "POST", body: JSON.stringify({ round_id: flashcards.roundId }) }).catch(() => {});
  flashcards.roundId = null;
  stopQuizTimer();
  quiz.generation += 1;
  quiz.questions = [];
  document.querySelector("#quiz-panel").hidden = true;
  resetFlashcards();
  setRoundPending(flashcards, "flashcard", true);
  const generation = flashcards.generation;
  showNotice();
  try {
    const hard = document.querySelector("#flashcard-hard").checked ? "&hard=1" : "";
    const table = document.querySelector("#flashcard-table").value || "collocations";
    flashcards.table = table;
    const data = await api(`/api/flashcard/start?mode=${mode}${hard}&table=${table}`, { method: "POST" });
    if (generation !== flashcards.generation) {
      api("/api/review/discard", { method: "POST", body: JSON.stringify({ round_id: data.round_id }) }).catch(() => {});
      return;
    }
    flashcards.roundId = data.round_id;
    flashcards.cards = data.cards;
    flashcards.index = 0;
    if (!flashcards.cards.length) {
      document.querySelector("#flashcard-panel").hidden = true;
      showNotice(`Hiện không có ${table === "vocabulary" ? "từ vựng" : table === "synonymous_collocations" ? "cụm từ đồng nghĩa" : "cụm từ"} nào đến hạn ôn.`);
      return;
    }
    await renderFlashcard();
  } catch (error) {
    if (generation !== flashcards.generation) return;
    document.querySelector("#flashcard-panel").hidden = true;
    showNotice(error.message, true);
  } finally {
    setRoundPending(flashcards, "flashcard", false);
  }
}

document.querySelector("#start-flashcard-av").addEventListener("click", () => startFlashcards("av"));
document.querySelector("#start-flashcard-va").addEventListener("click", () => startFlashcards("va"));
flashcardButton.addEventListener("click", () => flipFlashcard());
document.querySelector("#flashcard-correct").addEventListener("click", () => answerFlashcard("correct", flashcards.flippedAt));
document.querySelector("#flashcard-wrong").addEventListener("click", () => answerFlashcard("wrong"));
document.querySelector("#flashcard-relative").addEventListener("click", () => answerFlashcard("relative"));
document.querySelector("#flashcard-known").addEventListener("click", () => answerFlashcard("known"));
document.querySelector("#flashcard-next").addEventListener("click", () => {
  if (flashcards.pending || !flashcards.cards.length) return;
  if (flashcards.retryTimeout) {
    answerFlashcard("timeout");
    return;
  }
  if (!flashcards.answered) return;
  flashcards.index += 1;
  renderFlashcard();
});

loadWords().catch((error) => showNotice(error.message, true));
