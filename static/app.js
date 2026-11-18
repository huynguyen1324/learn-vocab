const notice = document.querySelector("#notice");
const wordList = document.querySelector("#word-list");
const wordDialog = document.querySelector("#word-dialog");
const wordForm = document.querySelector("#word-form");
const formError = document.querySelector("#form-error");
let words = [];
let editingId = null;

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
  words = items;
  wordList.replaceChildren();
  if (!items.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 7;
    cell.className = "empty";
    cell.textContent = "Không có cụm từ nào phù hợp.";
    row.append(cell);
    wordList.append(row);
    return;
  }

  for (const [index, word] of items.entries()) {
    const row = document.createElement("tr");
    row.classList.toggle("needs-practice", word.practice_count - word.repetition_level > 4);
    addCell(row, index + 1);
    addCell(row, word.english);
    addCell(row, word.vietnamese);
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
    wordList.append(row);
  }
}

async function loadWords() {
  const request = ++wordRequest;
  const params = new URLSearchParams({
    q: document.querySelector("#search").value,
    status: document.querySelector("#status-filter").value,
  });
  try {
    const data = await api(`/api/words?${params}`);
    if (request === wordRequest) renderWords(data.words);
  } catch (error) {
    if (request === wordRequest) throw error;
  }
}

function openWordDialog(word = null) {
  editingId = word ? word.id : null;
  wordForm.reset();
  formError.textContent = "";
  document.querySelector("#dialog-title").textContent = word ? "Sửa cụm từ" : "Thêm cụm từ";
  document.querySelector("#complete-option-label").hidden = Boolean(word);
  document.querySelector("#complete-option").checked = false;
  wordForm.elements.english.value = word ? word.english : "";
  wordForm.elements.vietnamese.value = word ? word.vietnamese : "";
  wordDialog.showModal();
  wordForm.elements.english.focus();
}

document.querySelector("#add-word").addEventListener("click", () => openWordDialog());
document.querySelector("#cancel-word").addEventListener("click", () => wordDialog.close());

wordForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  formError.textContent = "";
  const data = {
    english: wordForm.elements.english.value,
    vietnamese: wordForm.elements.vietnamese.value,
  };
  if (!editingId) data.complete = document.querySelector("#complete-option").checked;
  try {
    await api(editingId ? `/api/words/${editingId}` : "/api/words", {
      method: editingId ? "PUT" : "POST",
      body: JSON.stringify(data),
    });
    wordDialog.close();
    showNotice(editingId ? "Đã cập nhật cụm từ." : "Đã thêm cụm từ mới.");
    await loadWords();
  } catch (error) {
    formError.textContent = error.message;
  }
});

wordList.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const word = words.find((item) => item.id === Number(button.dataset.id));
  if (!word) return;
  if (button.dataset.action === "edit") {
    openWordDialog(word);
    return;
  }
  if (button.dataset.action === "restart" && !window.confirm(`Học lại "${word.english}" từ mốc 1? Tiến độ cũ sẽ bị xóa.`)) return;
  try {
    if (button.dataset.action === "delete") {
      if (!window.confirm(`Xóa cụm từ "${word.english}" vĩnh viễn?`)) return;
      await api(`/api/words/${word.id}`, { method: "DELETE" });
      showNotice("Đã xóa cụm từ.");
    } else {
      await api(`/api/words/${word.id}/${button.dataset.action}`, { method: "POST" });
      showNotice(button.dataset.action === "complete" ? "Đã đánh dấu hoàn thành." : "Cụm từ đã được đặt lại mốc 1.");
    }
    await loadWords();
  } catch (error) {
    showNotice(error.message, true);
  }
});

document.querySelector("#search").addEventListener("input", () => {
  loadWords().catch((error) => showNotice(error.message, true));
});
document.querySelector("#status-filter").addEventListener("change", () => {
  loadWords().catch((error) => showNotice(error.message, true));
});

function showView(view) {
  const isList = view === "list";
  const isQuiz = view === "quiz";
  const isFlashcard = view === "flashcard";
  if (!isQuiz) {
    quiz.generation += 1;
    quiz.questions = [];
    document.querySelector("#quiz-panel").hidden = true;
  }
  if (!isFlashcard) resetFlashcards();
  document.querySelector("#list-view").hidden = !isList;
  document.querySelector("#quiz-view").hidden = !isQuiz;
  document.querySelector("#flashcard-view").hidden = !isFlashcard;
  document.querySelector("#list-tab").classList.toggle("active", isList);
  document.querySelector("#quiz-tab").classList.toggle("active", isQuiz);
  document.querySelector("#flashcard-tab").classList.toggle("active", isFlashcard);
  showNotice();
  if (isList) loadWords().catch((error) => showNotice(error.message, true));
}

document.querySelector("#list-tab").addEventListener("click", () => showView("list"));
document.querySelector("#quiz-tab").addEventListener("click", () => showView("quiz"));
document.querySelector("#flashcard-tab").addEventListener("click", () => showView("flashcard"));

const quiz = {
  mode: "va",
  questions: [],
  index: 0,
  correct: 0,
  answering: false,
  pending: false,
  generation: 0,
  displayReady: false,
};

async function renderQuestion() {
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
  stage.textContent = `Mức thông thạo sau khi trả lời đúng: ${question.repetition_level_after_correct}/8`;
  choices.replaceChildren();
  feedback.textContent = "";
  markComplete.hidden = true;
  markComplete.disabled = false;
  markComplete.textContent = "Đánh dấu hoàn thành";
  next.hidden = true;
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
    await api(`/api/words/${question.word_id}/practice`, { method: "POST" });
    if (generation !== quiz.generation) return;
    quiz.displayReady = true;
    for (const button of choices.children) button.disabled = false;
  } catch (error) {
    if (generation !== quiz.generation) return;
    feedback.textContent = `${error.message} Không thể xác nhận số lần ôn. Hãy bắt đầu lại lượt ôn; yêu cầu này sẽ không tự thử lại.`;
  } finally {
    setRoundPending(quiz, "quiz", false);
  }
}

async function submitAnswer(selectedId) {
  if (quiz.pending || !quiz.displayReady || quiz.answering || !quiz.questions[quiz.index]) return;
  quiz.answering = true;
  setRoundPending(quiz, "quiz", true);
  const generation = quiz.generation;
  const question = quiz.questions[quiz.index];
  const choiceIds = question.choices.map((choice) => choice.id);
  const feedback = document.querySelector("#feedback");
  const markComplete = document.querySelector("#mark-complete");
  const next = document.querySelector("#next-question");
  try {
    const result = await api(`/api/quiz/answer?mode=${quiz.mode}`, {
      method: "POST",
      body: JSON.stringify({ word_id: question.word_id, selected_id: selectedId, choice_ids: choiceIds }),
    });
    if (generation !== quiz.generation) return;
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
    markComplete.hidden = !result.correct || result.completed;
    next.hidden = false;
  } catch (error) {
    if (generation !== quiz.generation) return;
    quiz.answering = false;
    feedback.textContent = error.message;
  } finally {
    setRoundPending(quiz, "quiz", false);
  }
}

async function startQuiz(mode) {
  if (quiz.pending) return;
  setRoundPending(quiz, "quiz", true);
  const generation = ++quiz.generation;
  document.querySelector("#quiz-panel").hidden = true;
  quiz.mode = mode;
  showNotice();
  try {
    const data = await api(`/api/quiz/start?mode=${mode}`, { method: "POST" });
    if (generation !== quiz.generation) return;
    quiz.questions = data.questions;
    quiz.index = 0;
    quiz.correct = 0;
    if (!quiz.questions.length) {
      document.querySelector("#quiz-panel").hidden = true;
      showNotice("Hiện không có cụm từ nào đến hạn ôn.");
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
  if (quiz.pending || !quiz.displayReady || !quiz.answering || !quiz.questions.length) return;
  quiz.index += 1;
  renderQuestion();
});
document.querySelector("#mark-complete").addEventListener("click", async (event) => {
  if (quiz.pending || !quiz.questions[quiz.index]) return;
  const button = event.currentTarget;
  const question = quiz.questions[quiz.index];
  const generation = quiz.generation;
  setRoundPending(quiz, "quiz", true);
  button.disabled = true;
  try {
    await api(`/api/words/${question.word_id}/complete`, { method: "POST" });
    if (generation !== quiz.generation) return;
    button.textContent = "Đã đánh dấu hoàn thành";
    document.querySelector("#feedback").textContent += " Cụm từ đã được đánh dấu hoàn thành.";
  } catch (error) {
    if (generation !== quiz.generation) return;
    button.disabled = false;
    document.querySelector("#feedback").textContent += ` ${error.message}`;
  } finally {
    setRoundPending(quiz, "quiz", false);
  }
});

const flashcards = { displayReady: false, cards: [], index: 0, startedAt: 0, flippedAt: null, timer: null, answered: false, pending: false, generation: 0, retryTimeout: false };
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
  flashcardButton.classList.remove("flipped");
}

function paintFlashcardProgress(elapsed) {
  const progress = Math.min(elapsed / 20, 1);
  flashcardFill.style.width = `${progress * 100}%`;
  document.querySelector("#flashcard-progress").setAttribute("aria-valuenow", String(Math.round(progress * 20000)));
  flashcardFill.dataset.band = elapsed <= 2 ? "fast" : elapsed <= 5 ? "medium" : elapsed <= 10 ? "slow" : "late";
}

async function answerFlashcard(result, elapsed = null) {
  if (flashcards.pending || !flashcards.displayReady || flashcards.answered || !flashcards.cards[flashcards.index]) return;
  flashcards.answered = true;
  setRoundPending(flashcards, "flashcard", true);
  const generation = flashcards.generation;
  document.querySelector("#flashcard-next").disabled = true;
  stopFlashcardTimer();
  const card = flashcards.cards[flashcards.index];
  try {
    if (result === "known") {
      await api(`/api/words/${card.word_id}/complete`, { method: "POST" });
    } else {
      await api("/api/flashcard/answer", {
        method: "POST",
        body: JSON.stringify({
          word_id: card.word_id,
          result,
          ...(elapsed === null ? {} : { response_time_ms: elapsed }),
        }),
      });
    }
    if (generation !== flashcards.generation) return;
    flashcards.retryTimeout = false;
    document.querySelector("#flashcard-next").textContent = "Tiếp theo";
    const messages = {
      timeout: "Quá 20 giây: đã tự lật thẻ và trừ 1 mốc ôn.",
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
  if (flashcards.pending || !flashcards.displayReady || !flashcards.cards[flashcards.index] || flashcards.flippedAt !== null) return;
  const elapsed = performance.now() - flashcards.startedAt;
  automatic = automatic || elapsed > 20000;
  flashcards.flippedAt = automatic ? 20000 : elapsed;
  stopFlashcardTimer();
  flashcardButton.classList.add("flipped");
  document.querySelector("#flashcard-back").hidden = false;
  document.querySelector("#flashcard-correct").disabled = automatic;
  document.querySelector("#flashcard-wrong").disabled = automatic;
  document.querySelector("#flashcard-relative").disabled = automatic;
  document.querySelector("#flashcard-known").disabled = automatic || elapsed > 2000;
  if (automatic) answerFlashcard("timeout");
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
  document.querySelector("#flashcard-back").hidden = true;
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
  flashcards.startedAt = performance.now();
  const practice = api(`/api/words/${card.word_id}/practice`, { method: "POST" });
  flashcards.timer = setInterval(() => {
    const elapsed = (performance.now() - flashcards.startedAt) / 1000;
    paintFlashcardProgress(elapsed);
    if (elapsed > 20) flipFlashcard(true);
  }, 50);
  try {
    await practice;
    if (generation !== flashcards.generation) return;
    flashcards.displayReady = true;
    flashcardButton.disabled = false;
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
  resetFlashcards();
  setRoundPending(flashcards, "flashcard", true);
  const generation = flashcards.generation;
  showNotice();
  try {
    const data = await api(`/api/flashcard/start?mode=${mode}`, { method: "POST" });
    if (generation !== flashcards.generation) return;
    flashcards.cards = data.cards;
    flashcards.index = 0;
    if (!flashcards.cards.length) {
      document.querySelector("#flashcard-panel").hidden = true;
      showNotice("Hiện không có cụm từ nào đến hạn ôn.");
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
