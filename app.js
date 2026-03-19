(function () {
  const dataset = window.TEST_APP_DATA;

  if (!dataset || !Array.isArray(dataset.exams) || dataset.exams.length === 0) {
    document.body.innerHTML =
      '<main style="padding:2rem;font-family:sans-serif">No hay exámenes cargados.</main>';
    return;
  }

  const STORAGE_PREFIX = "test-oposicion-progress";

  const elements = {
    examSelect: document.querySelector("#exam-select"),
    randomOrder: document.querySelector("#random-order"),
    resetProgress: document.querySelector("#reset-progress"),
    examTitle: document.querySelector("#exam-title"),
    statCurrent: document.querySelector("#stat-current"),
    statCorrect: document.querySelector("#stat-correct"),
    statIncorrect: document.querySelector("#stat-incorrect"),
    statPending: document.querySelector("#stat-pending"),
    progressLabel: document.querySelector("#progress-label"),
    progressFill: document.querySelector("#progress-fill"),
    questionMap: document.querySelector("#question-map"),
    questionCounter: document.querySelector("#question-counter"),
    questionText: document.querySelector("#question-text"),
    options: document.querySelector("#options"),
    feedback: document.querySelector("#feedback"),
    feedbackLabel: document.querySelector("#feedback-label"),
    feedbackText: document.querySelector("#feedback-text"),
    prevQuestion: document.querySelector("#prev-question"),
    nextQuestion: document.querySelector("#next-question"),
  };

  const state = {
    examId: dataset.exams[0].id,
    order: [],
    answers: {},
    currentQuestionIndex: 0,
    randomOrder: false,
  };

  function storageKey(examId) {
    return `${STORAGE_PREFIX}:${examId}`;
  }

  function getExam(examId) {
    return dataset.exams.find((exam) => exam.id === examId);
  }

  function getQuestionByOrderIndex(index) {
    const exam = getExam(state.examId);
    const questionId = state.order[index];
    return exam.questions.find((question) => question.id === questionId);
  }

  function saveProgress() {
    const payload = {
      answers: state.answers,
      currentQuestionIndex: state.currentQuestionIndex,
      randomOrder: state.randomOrder,
      order: state.order,
    };

    window.localStorage.setItem(storageKey(state.examId), JSON.stringify(payload));
  }

  function loadProgress(examId) {
    const exam = getExam(examId);
    const fallbackOrder = exam.questions.map((question) => question.id);
    const raw = window.localStorage.getItem(storageKey(examId));

    if (!raw) {
      return {
        answers: {},
        currentQuestionIndex: 0,
        randomOrder: false,
        order: fallbackOrder,
      };
    }

    try {
      const parsed = JSON.parse(raw);
      const storedOrder = Array.isArray(parsed.order) ? parsed.order : fallbackOrder;
      return {
        answers: parsed.answers || {},
        currentQuestionIndex: Number.isInteger(parsed.currentQuestionIndex)
          ? Math.min(Math.max(parsed.currentQuestionIndex, 0), exam.questions.length - 1)
          : 0,
        randomOrder: Boolean(parsed.randomOrder),
        order:
          storedOrder.length === exam.questions.length
            ? storedOrder
            : parsed.randomOrder
              ? shuffle([...fallbackOrder])
              : fallbackOrder,
      };
    } catch (error) {
      return {
        answers: {},
        currentQuestionIndex: 0,
        randomOrder: false,
        order: fallbackOrder,
      };
    }
  }

  function shuffle(items) {
    for (let i = items.length - 1; i > 0; i -= 1) {
      const swapIndex = Math.floor(Math.random() * (i + 1));
      [items[i], items[swapIndex]] = [items[swapIndex], items[i]];
    }
    return items;
  }

  function getCounts() {
    const exam = getExam(state.examId);
    let correct = 0;
    let incorrect = 0;

    exam.questions.forEach((question) => {
      const answer = state.answers[question.id];
      if (!answer) {
        return;
      }

      if (answer.isCorrect) {
        correct += 1;
      } else {
        incorrect += 1;
      }
    });

    return {
      correct,
      incorrect,
      pending: exam.questions.length - correct - incorrect,
    };
  }

  function setFeedback(question, answer) {
    if (!answer) {
      elements.feedback.hidden = true;
      elements.feedback.className = "feedback";
      elements.feedbackLabel.textContent = "";
      elements.feedbackText.textContent = "";
      return;
    }

    const correctOption = question.options.find((option) => option.id === question.correctOption);
    const isCorrect = answer.isCorrect;

    elements.feedback.hidden = false;
    elements.feedback.className = `feedback ${isCorrect ? "is-correct" : "is-incorrect"}`;
    elements.feedbackLabel.textContent = isCorrect ? "Respuesta correcta" : "Respuesta incorrecta";
    elements.feedbackText.textContent = isCorrect
      ? `La opción ${question.correctOption.toUpperCase()} es la válida.`
      : `La correcta es la ${question.correctOption.toUpperCase()}: ${correctOption.text}`;
  }

  function renderQuestionMap() {
    const exam = getExam(state.examId);
    elements.questionMap.innerHTML = "";

    state.order.forEach((questionId, orderIndex) => {
      const originalIndex = exam.questions.findIndex((question) => question.id === questionId);
      const question = exam.questions[originalIndex];
      const answer = state.answers[question.id];
      const button = document.createElement("button");

      button.type = "button";
      button.className = "question-dot";
      button.textContent = question.number;
      button.setAttribute("aria-label", `Ir a la pregunta ${question.number}`);

      if (orderIndex === state.currentQuestionIndex) {
        button.classList.add("is-active");
      }

      if (answer) {
        button.classList.add(answer.isCorrect ? "is-correct" : "is-incorrect");
      }

      button.addEventListener("click", () => {
        state.currentQuestionIndex = orderIndex;
        saveProgress();
        render();
      });

      elements.questionMap.appendChild(button);
    });
  }

  function renderOptions(question) {
    const savedAnswer = state.answers[question.id];
    elements.options.innerHTML = "";

    question.options.forEach((option) => {
      const button = document.createElement("button");
      const optionSelected = savedAnswer && savedAnswer.selectedOption === option.id;
      const isCorrectOption = option.id === question.correctOption;

      button.type = "button";
      button.className = "option";
      button.innerHTML = `
        <span class="option__letter">${option.id.toUpperCase()}</span>
        <span class="option__text">${option.text}</span>
      `;

      if (savedAnswer) {
        button.disabled = true;
        if (optionSelected) {
          button.classList.add("is-selected");
        }
        if (isCorrectOption) {
          button.classList.add("is-correct");
        } else if (optionSelected && !savedAnswer.isCorrect) {
          button.classList.add("is-incorrect");
        }
      }

      button.addEventListener("click", () => {
        if (state.answers[question.id]) {
          return;
        }

        state.answers[question.id] = {
          selectedOption: option.id,
          isCorrect: option.id === question.correctOption,
          answeredAt: new Date().toISOString(),
        };
        saveProgress();
        render();
      });

      elements.options.appendChild(button);
    });
  }

  function renderStats() {
    const exam = getExam(state.examId);
    const counts = getCounts();
    const answered = counts.correct + counts.incorrect;
    const progress = Math.round((answered / exam.questions.length) * 100) || 0;

    elements.statCurrent.textContent = `${state.currentQuestionIndex + 1} / ${exam.questions.length}`;
    elements.statCorrect.textContent = counts.correct;
    elements.statIncorrect.textContent = counts.incorrect;
    elements.statPending.textContent = counts.pending;
    elements.progressLabel.textContent = `${progress}%`;
    elements.progressFill.style.width = `${progress}%`;
  }

  function renderExamSelector() {
    elements.examSelect.innerHTML = "";

    dataset.exams.forEach((exam) => {
      const option = document.createElement("option");
      option.value = exam.id;
      option.textContent = exam.title;
      elements.examSelect.appendChild(option);
    });

    elements.examSelect.value = state.examId;
    elements.randomOrder.checked = state.randomOrder;
  }

  function render() {
    const exam = getExam(state.examId);
    const question = getQuestionByOrderIndex(state.currentQuestionIndex);
    const answer = state.answers[question.id];

    elements.examTitle.textContent = exam.title;
    elements.questionCounter.textContent = `Pregunta ${question.number}`;
    elements.questionText.textContent = question.text;
    elements.prevQuestion.disabled = state.currentQuestionIndex === 0;
    elements.nextQuestion.disabled = state.currentQuestionIndex === state.order.length - 1;

    renderExamSelector();
    renderStats();
    renderQuestionMap();
    renderOptions(question);
    setFeedback(question, answer);
  }

  function resetExamProgress() {
    const exam = getExam(state.examId);
    state.answers = {};
    state.currentQuestionIndex = 0;
    state.order = state.randomOrder
      ? shuffle(exam.questions.map((question) => question.id))
      : exam.questions.map((question) => question.id);
    saveProgress();
    render();
  }

  function hydrateExam(examId) {
    state.examId = examId;
    const progress = loadProgress(examId);
    state.answers = progress.answers;
    state.currentQuestionIndex = progress.currentQuestionIndex;
    state.randomOrder = progress.randomOrder;
    state.order = progress.order;
    render();
  }

  elements.examSelect.addEventListener("change", (event) => {
    hydrateExam(event.target.value);
  });

  elements.randomOrder.addEventListener("change", (event) => {
    const exam = getExam(state.examId);
    state.randomOrder = event.target.checked;
    state.currentQuestionIndex = 0;
    state.order = state.randomOrder
      ? shuffle(exam.questions.map((question) => question.id))
      : exam.questions.map((question) => question.id);
    saveProgress();
    render();
  });

  elements.resetProgress.addEventListener("click", () => {
    window.localStorage.removeItem(storageKey(state.examId));
    resetExamProgress();
  });

  elements.prevQuestion.addEventListener("click", () => {
    if (state.currentQuestionIndex === 0) {
      return;
    }

    state.currentQuestionIndex -= 1;
    saveProgress();
    render();
  });

  elements.nextQuestion.addEventListener("click", () => {
    if (state.currentQuestionIndex >= state.order.length - 1) {
      return;
    }

    state.currentQuestionIndex += 1;
    saveProgress();
    render();
  });

  hydrateExam(state.examId);
})();
