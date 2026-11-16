const notice = document.querySelector("#notice");
const wordList = document.querySelector("#word-list");
const wordDialog = document.querySelector("#word-dialog");
const wordForm = document.querySelector("#word-form");
const formError = document.querySelector("#form-error");
let words = [];
let editingId = null;

const quizState = {
  av: { questions: [], questionIndex: 0, correctCount: 0, answering: false },
  va: { questions: [], questionIndex: 0, correctCount: 0, answering: false },
};
let currentMode = null;

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
    cell.colSpan = 5;
    cell.className = "empty";
    cell.textContent = "Không có từ nào phù hợp.";
    row.append(cell);
    wordList.append(row);
    return;
  }

  for (const word of items) {
    const row = document.createElement("tr");
    addCell(row, word.english);
    addCell(row, word.vietnamese);
    addCell(row, word.status);
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
  const params = new URLSearchParams({
    q: document.querySelector("#search").value,
    status: document.querySelector("#status-filter").value,
  });
  const data = await api(`/api/words?${params}`);
  renderWords(data.words);
}

function openWordDialog(word = null) {
  editingId = word ? word.id : null;
  wordForm.reset();
  formError.textContent = "";
  document.querySelector("#dialog-title").textContent = word ? "Sửa từ" : "Thêm từ";
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
    showNotice(editingId ? "Đã cập nhật từ vựng." : "Đã thêm từ mới.");
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
      if (!window.confirm(`Xóa từ "${word.english}" vĩnh viễn?`)) return;
      await api(`/api/words/${word.id}`, { method: "DELETE" });
      showNotice("Đã xóa từ vựng.");
    } else {
      await api(`/api/words/${word.id}/${button.dataset.action}`, { method: "POST" });
      showNotice(button.dataset.action === "complete" ? "Đã đánh dấu hoàn thành." : "Từ đã được đặt lại mốc 1.");
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
};

function renderQuestion() {
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
  stage.textContent = `Lần ôn ${question.repetition_count_after_correct}/8`;
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
    button.textContent = choice.text;
    button.dataset.id = choice.id;
    button.addEventListener("click", () => submitAnswer(choice.id));
    choices.append(button);
  }
  panel.hidden = false;
}

async function submitAnswer(selectedId) {
  if (quiz.answering) return;
  quiz.answering = true;
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
    quiz.answering = false;
    feedback.textContent = error.message;
  }
}

async function startQuiz(mode) {
  quiz.mode = mode;
  showNotice();
  try {
    const data = await api(`/api/quiz/start?mode=${mode}`, { method: "POST" });
    quiz.questions = data.questions;
    quiz.index = 0;
    quiz.correct = 0;
    if (!quiz.questions.length) {
      document.querySelector("#quiz-panel").hidden = true;
      showNotice("Hiện không có từ nào đến hạn ôn.");
      return;
    }
    renderQuestion();
  } catch (error) {
    document.querySelector("#quiz-panel").hidden = true;
    showNotice(error.message, true);
  }
}

document.querySelector("#start-quiz-av").addEventListener("click", () => startQuiz("av"));
document.querySelector("#start-quiz-va").addEventListener("click", () => startQuiz("va"));
document.querySelector("#next-question").addEventListener("click", () => {
  quiz.index += 1;
  renderQuestion();
});
document.querySelector("#mark-complete").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const question = quiz.questions[quiz.index];
  button.disabled = true;
  try {
    await api(`/api/words/${question.word_id}/complete`, { method: "POST" });
    button.textContent = "Đã đánh dấu hoàn thành";
    document.querySelector("#feedback").textContent += " Từ đã được đánh dấu hoàn thành.";
  } catch (error) {
    button.disabled = false;
    document.querySelector("#feedback").textContent += ` ${error.message}`;
  }
});

const flashcards = { cards: [], index: 0, startedAt: 0, flippedAt: null, timer: null, answered: false };
const flashcardButton = document.querySelector("#flashcard");
const flashcardFill = document.querySelector("#flashcard-progress-fill");

function stopFlashcardTimer() {
  clearInterval(flashcards.timer);
  flashcards.timer = null;
}

function paintFlashcardProgress(elapsed) {
  const progress = Math.min(elapsed / 20, 1);
  flashcardFill.style.width = `${progress * 100}%`;
  document.querySelector("#flashcard-progress").setAttribute("aria-valuenow", String(Math.round(progress * 20000)));
  flashcardFill.dataset.band = elapsed <= 2 ? "fast" : elapsed <= 5 ? "medium" : elapsed <= 10 ? "slow" : "late";
}

async function answerFlashcard(result, elapsed = null) {
  if (flashcards.answered) return;
  flashcards.answered = true;
  stopFlashcardTimer();
  const card = flashcards.cards[flashcards.index];
  try {
    await api("/api/flashcard/answer", {
      method: "POST",
      body: JSON.stringify({
        word_id: card.word_id,
        result,
        ...(elapsed === null ? {} : { response_time_ms: elapsed }),
      }),
    });
    const messages = {
      timeout: "Quá 20 giây: đã tự lật thẻ và trừ 1 mốc ôn.",
      relative: "Đã lưu. Mốc ôn giữ nguyên, lịch ôn được dời theo mốc hiện tại.",
      correct: "Đã lưu kết quả nhớ đúng.",
      wrong: "Đã lưu kết quả nhớ sai.",
    };
    document.querySelector("#flashcard-feedback").textContent = messages[result];
    document.querySelector("#flashcard-correct").disabled = true;
    document.querySelector("#flashcard-wrong").disabled = true;
    document.querySelector("#flashcard-relative").disabled = true;
    document.querySelector("#flashcard-next").disabled = false;
  } catch (error) {
    flashcards.answered = false;
    document.querySelector("#flashcard-feedback").textContent = error.message;
  }
}

function flipFlashcard(automatic = false) {
  if (flashcards.flippedAt !== null) return;
  const elapsed = Math.round(performance.now() - flashcards.startedAt);
  automatic = automatic || elapsed > 20000;
  flashcards.flippedAt = automatic ? 20000 : elapsed;
  stopFlashcardTimer();
  flashcardButton.classList.add("flipped");
  document.querySelector("#flashcard-back").hidden = false;
  document.querySelector("#flashcard-correct").disabled = automatic;
  document.querySelector("#flashcard-wrong").disabled = automatic;
  document.querySelector("#flashcard-relative").disabled = automatic;
  if (automatic) answerFlashcard("timeout");
}

function renderFlashcard() {
  stopFlashcardTimer();
  flashcards.flippedAt = null;
  flashcards.answered = false;
  const panel = document.querySelector("#flashcard-panel");
  const feedback = document.querySelector("#flashcard-feedback");
  const correct = document.querySelector("#flashcard-correct");
  const wrong = document.querySelector("#flashcard-wrong");
  const next = document.querySelector("#flashcard-next");
  if (flashcards.index >= flashcards.cards.length) {
    document.querySelector("#flashcard-count").textContent = "Đã hoàn thành lượt ôn.";
    document.querySelector("#flashcard-front").textContent = "";
    document.querySelector("#flashcard-back").hidden = true;
    flashcardButton.disabled = true;
    correct.disabled = true;
    wrong.disabled = true;
    document.querySelector("#flashcard-relative").disabled = true;
    next.disabled = true;
    panel.hidden = false;
    return;
  }
  const card = flashcards.cards[flashcards.index];
  document.querySelector("#flashcard-count").textContent = `Câu ${flashcards.index + 1}/${flashcards.cards.length}`;
  document.querySelector("#flashcard-front").textContent = card.front;
  document.querySelector("#flashcard-back").textContent = card.back;
  document.querySelector("#flashcard-back").hidden = true;
  document.querySelector("#flashcard-progress-fill").style.width = "0%";
  document.querySelector("#flashcard-progress").setAttribute("aria-valuenow", "0");
  feedback.textContent = "";
  flashcardButton.disabled = false;
  flashcardButton.classList.remove("flipped");
  correct.disabled = true;
  wrong.disabled = true;
  document.querySelector("#flashcard-relative").disabled = true;
  next.disabled = true;
  flashcards.startedAt = performance.now();
  flashcards.timer = setInterval(() => {
    const elapsed = (performance.now() - flashcards.startedAt) / 1000;
    paintFlashcardProgress(elapsed);
    if (elapsed > 20) flipFlashcard(true);
  }, 50);
  panel.hidden = false;
}

async function startFlashcards(mode) {
  showNotice();
  try {
    const data = await api(`/api/flashcard/start?mode=${mode}`, { method: "POST" });
    flashcards.cards = data.cards;
    flashcards.index = 0;
    if (!flashcards.cards.length) {
      document.querySelector("#flashcard-panel").hidden = true;
      showNotice("Hiện không có từ nào đến hạn ôn.");
      return;
    }
    renderFlashcard();
  } catch (error) {
    document.querySelector("#flashcard-panel").hidden = true;
    showNotice(error.message, true);
  }
}

document.querySelector("#start-flashcard-av").addEventListener("click", () => startFlashcards("av"));
document.querySelector("#start-flashcard-va").addEventListener("click", () => startFlashcards("va"));
flashcardButton.addEventListener("click", () => flipFlashcard());
document.querySelector("#flashcard-correct").addEventListener("click", () => answerFlashcard("correct", flashcards.flippedAt));
document.querySelector("#flashcard-wrong").addEventListener("click", () => answerFlashcard("wrong"));
document.querySelector("#flashcard-relative").addEventListener("click", () => answerFlashcard("relative"));
document.querySelector("#flashcard-next").addEventListener("click", () => {
  flashcards.index += 1;
  renderFlashcard();
});

loadWords().catch((error) => showNotice(error.message, true));
