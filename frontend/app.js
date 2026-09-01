const PDF_TYPES = {
  text_based: "Текстовый",
  scanned: "Скан",
  image_based: "Изображения",
  mixed: "Смешанный",
  not_pdf: "Не PDF",
};

const PATHS = {
  native: "Напрямую, без OCR",
  ocr: "Через OCR",
  hybrid: "Гибридный",
};

const BUSY = new Set(["queued", "preparing", "triaging", "running", "postprocessing"]);
const POLL_MS = 400;

const state = {
  engine: "auto",
  engines: [],
  selectedId: null,
  result: null,
  job: null,
  pageFilter: null,
  copyText: "",
  lastFile: null,
  pollToken: 0,
  objectUrls: [],
};

const $ = (id) => document.getElementById(id);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function plural(n, forms) {
  const abs = Math.abs(n) % 100;
  const last = abs % 10;
  if (abs > 10 && abs < 20) return forms[2];
  if (last > 1 && last < 5) return forms[1];
  if (last === 1) return forms[0];
  return forms[2];
}

function formatDuration(ms) {
  if (!Number.isFinite(ms) || ms < 0) return null;
  if (ms < 1000) return `${Math.round(ms)} мс`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1).replace(".", ",")} с`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes} ${plural(minutes, ["минуту", "минуты", "минут"])} ${Math.round(seconds % 60)} с`;
}

function extensionOf(filename) {
  const dot = filename.lastIndexOf(".");
  return dot === -1 ? "Файл" : filename.slice(dot + 1).toUpperCase();
}

/* --- api --- */

async function getJSON(url) {
  const response = await fetch(url);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `Ошибка запроса ${response.status}`);
  return data;
}

/* --- engines --- */

async function loadEngines() {
  const data = await getJSON("/api/v1/engines");
  state.engines = data.engines || [];
  state.engine = data.default || "auto";
  renderEngines();
}

function renderEngines() {
  const box = $("engines");
  box.replaceChildren();
  for (const engine of state.engines) {
    const button = el("button", engine.available ? null : "unavailable", engine.label);
    button.type = "button";
    button.setAttribute("role", "radio");
    button.setAttribute("aria-checked", String(engine.id === state.engine));
    button.setAttribute("aria-label", engine.available ? engine.label : `${engine.label} — недоступен`);
    button.title = engine.description || "";
    button.addEventListener("click", () => selectEngine(engine));
    box.append(button);
  }
}

function selectEngine(engine) {
  if (!engine.available) {
    showEngineUnavailable(engine);
    return;
  }
  state.engine = engine.id;
  renderEngines();
}

function showEngineUnavailable(engine) {
  showPane("result-pane");
  $("doc-title").textContent = engine.label;
  $("doc-meta").textContent = "Движок недоступен";
  $("facts").replaceChildren();
  $("pagestrip").replaceChildren();
  $("legend").hidden = true;
  document.querySelector(".result-head").hidden = true;
  $("page-confidence").hidden = true;
  $("output").textContent = "";
  $("notices").replaceChildren(
    buildNotice("error", `${engine.description || "Движок не установлен."} Установите зависимости и перезапустите приложение.`, {
      code: "pip install '.[ocr]'",
    }),
  );
}

/* --- sidebar --- */

function dayBucket(iso) {
  const created = new Date(iso);
  if (Number.isNaN(created.getTime())) return "Ранее";
  const today = new Date();
  const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const startOfCreated = new Date(created.getFullYear(), created.getMonth(), created.getDate());
  const diffDays = Math.round((startOfToday - startOfCreated) / 86400000);
  if (diffDays <= 0) return "Сегодня";
  if (diffDays === 1) return "Вчера";
  return "Ранее";
}

async function loadJobs() {
  const list = $("job-list");
  let jobs = [];
  try {
    const data = await getJSON("/api/v1/jobs");
    jobs = data.jobs || [];
  } catch {
    list.replaceChildren(el("p", "sidebar-empty", "Не удалось загрузить историю"));
    return;
  }

  jobs.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  list.replaceChildren();

  if (jobs.length === 0) {
    list.append(el("p", "sidebar-empty", "Пока ничего не обработано"));
    return;
  }

  let currentBucket = null;
  for (const job of jobs) {
    const bucket = dayBucket(job.created_at);
    if (bucket !== currentBucket) {
      currentBucket = bucket;
      list.append(el("div", "sidebar-group", bucket));
    }

    const row = el("button", "sidebar-row");
    row.type = "button";
    row.setAttribute("aria-current", String(job.id === state.selectedId));

    const status = job.status === "completed" ? "completed" : job.status === "failed" ? "failed" : "busy";
    const statusLabel = { completed: "готово", failed: "ошибка", busy: "в работе" }[status];
    row.setAttribute("aria-label", `${job.filename} — ${statusLabel}`);
    row.append(el("span", `dot ${status}`));
    row.append(el("span", "name", job.filename));
    row.addEventListener("click", () => openJob(job.id));
    list.append(row);
  }
}

/* --- panes --- */

function showPane(id) {
  for (const pane of ["empty-pane", "progress-pane", "result-pane"]) {
    $(pane).hidden = pane !== id;
  }
}

function showEmpty() {
  state.selectedId = null;
  state.job = null;
  state.result = null;
  state.pageFilter = null;
  $("toolbar-title").textContent = "PDF2Text";
  showPane("empty-pane");
  loadJobs();
}

/* --- notices --- */

function buildNotice(kind, text, options = {}) {
  const notice = el("div", `notice ${kind}`);
  const body = el("div", "notice-body");
  body.append(el("span", null, text));

  if (options.code) {
    const line = el("p", null);
    line.style.margin = "8px 0 0";
    line.append(el("code", null, options.code));
    body.append(line);
  }

  const actions = el("div", "notice-actions");
  if (options.code) {
    const copyCode = el("button", "btn", "Скопировать команду");
    copyCode.type = "button";
    copyCode.addEventListener("click", () => navigator.clipboard.writeText(options.code));
    actions.append(copyCode);
  }
  if (options.retry) {
    const retry = el("button", "btn", "Повторить в режиме Авто");
    retry.type = "button";
    retry.addEventListener("click", () => {
      state.engine = "auto";
      renderEngines();
      submit(options.retry);
    });
    actions.append(retry);
  }
  if (actions.childElementCount > 0) body.append(actions);

  notice.append(body);
  return notice;
}

function needsAutoRetry(message) {
  return message.includes("Выберите Авто");
}

function needsOcrInstall(message) {
  return message.includes("PaddleOCR не установлен");
}

/* --- job flow --- */

async function openJob(jobId) {
  state.selectedId = jobId;
  state.pageFilter = null;
  await loadJobs();

  let job;
  try {
    job = await getJSON(`/api/v1/jobs/${jobId}`);
  } catch (error) {
    renderFailure({ id: jobId, filename: "Задача", error: error.message });
    return;
  }

  if (BUSY.has(job.status)) {
    renderProgress(job);
    pollJob(jobId);
    return;
  }
  await renderFinished(job);
}

function pollJob(jobId) {
  const token = ++state.pollToken;
  const tick = async () => {
    if (token !== state.pollToken || state.selectedId !== jobId) return;
    let job;
    try {
      job = await getJSON(`/api/v1/jobs/${jobId}`);
    } catch (error) {
      renderFailure({ id: jobId, filename: "Задача", error: error.message });
      return;
    }
    if (token !== state.pollToken || state.selectedId !== jobId) return;

    if (BUSY.has(job.status)) {
      renderProgress(job);
      setTimeout(tick, POLL_MS);
      return;
    }
    await renderFinished(job);
    loadJobs();
  };
  setTimeout(tick, POLL_MS);
}

async function renderFinished(job) {
  if (job.status === "failed") {
    renderFailure(job);
    return;
  }
  try {
    const result = await getJSON(`/api/v1/jobs/${job.id}/result`);
    renderResult(job, result);
  } catch (error) {
    renderFailure({ ...job, error: error.message });
  }
}

/* --- rendering --- */

function renderProgress(job) {
  state.job = job;
  showPane("progress-pane");
  $("toolbar-title").textContent = job.filename;
  $("progress-title").textContent = job.filename;
  $("progress-meta").textContent = `${extensionOf(job.filename)} · обрабатывается`;
  $("progress-fill").style.width = `${job.progress || 0}%`;
  $("progress-message").textContent = job.message || "";
}

function renderFailure(job) {
  state.job = job;
  state.result = null;
  showPane("result-pane");
  $("toolbar-title").textContent = job.filename || "Ошибка";
  $("doc-title").textContent = job.filename || "Ошибка";
  $("doc-meta").textContent = "Обработка не завершилась";
  $("facts").replaceChildren();
  $("pagestrip").replaceChildren();
  $("legend").hidden = true;
  $("page-confidence").hidden = true;
  $("output").textContent = "";
  document.querySelector(".result-head").hidden = true;

  const message = job.error || "Неизвестная ошибка";
  const options = {};
  if (needsOcrInstall(message)) options.code = "pip install '.[ocr]'";
  if (needsAutoRetry(message) && state.lastFile && state.lastFile.name === job.filename) {
    options.retry = state.lastFile;
  }
  $("notices").replaceChildren(buildNotice("error", message, options));
}

function renderResult(job, result) {
  state.job = job;
  state.result = result;
  showPane("result-pane");
  document.querySelector(".result-head").hidden = false;

  $("toolbar-title").textContent = job.filename;
  $("doc-title").textContent = job.filename;

  const pageCount = result.metadata?.page_count ?? result.pages.length;
  const duration = formatDuration(new Date(job.updated_at) - new Date(job.created_at));
  const metaParts = [extensionOf(job.filename), `${pageCount} ${plural(pageCount, ["страница", "страницы", "страниц"])}`];
  if (duration) metaParts.push(`обработано за ${duration}`);
  $("doc-meta").textContent = metaParts.join(" · ");

  renderFacts(result, pageCount);
  renderPages(result);
  renderNotices(result);
  prepareDownloads(result);
  renderText();
}

function renderFacts(result, pageCount) {
  const facts = $("facts");
  facts.replaceChildren();

  const addRow = (key, value, badge) => {
    const row = el("div", "grouped-row");
    row.append(el("span", "key", key));
    row.append(el("span", badge ? "value value-badge" : "value", value));
    facts.append(row);
  };

  const triage = result.triage;
  if (triage) {
    addRow("Тип документа", PDF_TYPES[triage.pdf_type] || triage.pdf_type);
    if (triage.confidence < 0.9) {
      addRow("Уверенность triage", `${Math.round(triage.confidence * 100)}%`);
    }
  }

  addRow("Путь обработки", PATHS[result.path] || result.path);
  addRow("Движок", result.engine);

  const ocrPages = result.metadata?.ocr_pages || [];
  addRow("Страниц через OCR", ocrPages.length === 0 ? "ни одной" : `${ocrPages.length} из ${pageCount}`, true);

  if (triage && triage.processing_time_ms > 0) {
    addRow("Triage занял", formatDuration(triage.processing_time_ms));
  }
}

/* Причины из backend/domain/models.py: PageResult.skipped_reason. */
const SKIP_REASONS = {
  limit: "сработал лимит авто-режима",
  failed: "движок не вернул результат",
};

function pageScopeLabel(page) {
  if (!page) return "напрямую";
  if (page.skipped_reason) return "OCR не выполнен";
  return page.source === "ocr" ? "OCR" : "напрямую";
}

function renderPages(result) {
  const strip = $("pagestrip");
  const legend = $("legend");
  strip.replaceChildren();
  strip.classList.toggle("dense", result.pages.length > 120);

  if (result.pages.length <= 1) {
    legend.hidden = true;
    return;
  }

  let hasOcr = false;
  let hasSkipped = false;
  for (const page of result.pages) {
    /* Три состояния, а не два: страница, которой был нужен OCR, но он не
       состоялся, не должна выглядеть как взятая напрямую. */
    const isSkipped = Boolean(page.skipped_reason);
    const isOcr = page.source === "ocr" && !isSkipped;
    if (isOcr) hasOcr = true;
    if (isSkipped) hasSkipped = true;
    const modifier = isSkipped ? " skipped" : isOcr ? " ocr" : "";
    const cell = el("button", `page-cell${modifier}`, String(page.page));
    cell.type = "button";
    cell.title = isSkipped
      ? `Страница ${page.page} — нужен был OCR, но он не выполнен: ${SKIP_REASONS[page.skipped_reason] || page.skipped_reason}`
      : isOcr
        ? `Страница ${page.page} — распознана OCR`
        : `Страница ${page.page} — взята напрямую`;
    cell.setAttribute("aria-pressed", String(state.pageFilter === page.page));
    cell.addEventListener("click", () => {
      state.pageFilter = state.pageFilter === page.page ? null : page.page;
      renderPages(result);
      renderText();
    });
    strip.append(cell);
  }

  legend.hidden = false;
  const parts = [];
  if (hasOcr) parts.push("Синим — страницы, где текст не читался и потребовался OCR.");
  if (hasSkipped) parts.push("Жёлтым — страницы, которым нужен был OCR, но он не выполнен: они пустые.");
  if (!parts.length) parts.push("Все страницы разобраны напрямую, OCR не запускался.");
  parts.push("Нажмите на страницу, чтобы открыть её отдельно.");
  legend.textContent = parts.join(" ");
}

function renderNotices(result) {
  const notices = $("notices");
  notices.replaceChildren();
  for (const warning of result.warnings || []) {
    notices.append(buildNotice("warn", warning));
  }
}

/* Минимальный Markdown → DOM. Только createElement и createTextNode:
   содержимое приходит из документа пользователя и не является доверенным,
   поэтому innerHTML здесь недопустим. */

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g;

function appendInline(parent, text) {
  for (const part of text.split(INLINE)) {
    if (!part) continue;
    if (part.length > 4 && part.startsWith("**") && part.endsWith("**")) {
      parent.append(el("strong", null, part.slice(2, -2)));
    } else if (part.length > 2 && part.startsWith("`") && part.endsWith("`")) {
      parent.append(el("code", null, part.slice(1, -1)));
    } else if (part.length > 2 && part.startsWith("*") && part.endsWith("*")) {
      parent.append(el("em", null, part.slice(1, -1)));
    } else {
      parent.append(document.createTextNode(part));
    }
  }
}

function renderMarkdownInto(container, source) {
  container.replaceChildren();
  let list = null;
  let paragraph = null;

  const flushParagraph = () => {
    if (paragraph) container.append(paragraph);
    paragraph = null;
  };
  const flushList = () => {
    if (list) container.append(list);
    list = null;
  };

  for (const raw of source.split("\n")) {
    const line = raw.trim();
    if (!line) {
      flushParagraph();
      flushList();
      continue;
    }

    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      flushParagraph();
      flushList();
      const node = el(`h${Math.min(heading[1].length, 4)}`);
      appendInline(node, heading[2]);
      container.append(node);
      continue;
    }

    if (/^(-{3,}|\*{3,}|_{3,})$/.test(line)) {
      flushParagraph();
      flushList();
      container.append(el("hr"));
      continue;
    }

    const bullet = /^[-*+]\s+(.*)$/.exec(line);
    if (bullet) {
      flushParagraph();
      if (!list || list.tagName !== "UL") {
        flushList();
        list = el("ul");
      }
      const item = el("li");
      appendInline(item, bullet[1]);
      list.append(item);
      continue;
    }

    const ordered = /^\d+[.)]\s+(.*)$/.exec(line);
    if (ordered) {
      flushParagraph();
      if (!list || list.tagName !== "OL") {
        flushList();
        list = el("ol");
      }
      const item = el("li");
      appendInline(item, ordered[1]);
      list.append(item);
      continue;
    }

    const quote = /^>\s?(.*)$/.exec(line);
    if (quote) {
      flushParagraph();
      flushList();
      const node = el("blockquote");
      appendInline(node, quote[1]);
      container.append(node);
      continue;
    }

    flushList();
    if (!paragraph) {
      paragraph = el("p");
    } else {
      paragraph.append(document.createTextNode(" "));
    }
    appendInline(paragraph, line);
  }

  flushParagraph();
  flushList();
}

function showText(output, text, fallback) {
  if (text) {
    output.className = "doc-text";
    renderMarkdownInto(output, text);
  } else {
    output.className = "doc-empty";
    output.replaceChildren(document.createTextNode(fallback));
  }
}

function renderText() {
  const result = state.result;
  if (!result) return;

  const output = $("output");
  const scope = $("result-scope");
  const confidence = $("page-confidence");

  if (state.pageFilter === null) {
    const text = result.markdown || result.text || "";
    state.copyText = text;
    showText(output, text, "Текст не извлечён.");
    scope.textContent = "";
    confidence.hidden = true;
    return;
  }

  const page = result.pages.find((item) => item.page === state.pageFilter);
  const text = page ? page.markdown || page.text : "";
  state.copyText = text;
  showText(output, text, "На этой странице текст не извлечён.");
  scope.textContent = `страница ${state.pageFilter} · ${pageScopeLabel(page)}`;

  if (page && page.confidence !== null && page.confidence !== undefined) {
    confidence.hidden = false;
    confidence.textContent = `confidence ${page.confidence.toFixed(2)}`;
  } else {
    confidence.hidden = true;
  }
}

function prepareDownloads(result) {
  for (const url of state.objectUrls) URL.revokeObjectURL(url);
  state.objectUrls = [];

  const markdown = result.markdown || result.text || "";
  const text = result.text || "";
  const mdUrl = URL.createObjectURL(new Blob([markdown], { type: "text/markdown" }));
  const txtUrl = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
  state.objectUrls.push(mdUrl, txtUrl);

  $("download-md").href = mdUrl;
  $("download-txt").href = txtUrl;
}

/* --- upload --- */

async function submit(file) {
  state.lastFile = file;
  state.pageFilter = null;
  state.selectedId = null;

  showPane("progress-pane");
  $("toolbar-title").textContent = file.name;
  $("progress-title").textContent = file.name;
  $("progress-meta").textContent = `${extensionOf(file.name)} · загрузка`;
  $("progress-fill").style.width = "3%";
  $("progress-message").textContent = "Отправка файла";

  const body = new FormData();
  body.append("file", file);
  body.append("engine", state.engine);
  body.append("language", $("language").value);

  let job;
  try {
    const response = await fetch("/api/v1/jobs", { method: "POST", body });
    job = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(job.detail || `Ошибка загрузки ${response.status}`);
  } catch (error) {
    renderFailure({ id: null, filename: file.name, error: error.message });
    return;
  }

  state.selectedId = job.id;
  renderProgress(job);
  loadJobs();
  pollJob(job.id);
}

/* --- wiring --- */

$("pick").addEventListener("click", () => $("file").click());
$("new-file").addEventListener("click", () => $("file").click());

$("file").addEventListener("change", () => {
  const file = $("file").files[0];
  if (file) submit(file);
  $("file").value = "";
});

const content = $("content");
["dragenter", "dragover"].forEach((name) => {
  content.addEventListener(name, (event) => {
    event.preventDefault();
    content.classList.add("dragging");
  });
});
["dragleave", "drop"].forEach((name) => {
  content.addEventListener(name, (event) => {
    event.preventDefault();
    content.classList.remove("dragging");
  });
});
content.addEventListener("drop", (event) => {
  const file = event.dataTransfer.files[0];
  if (file) submit(file);
});

$("copy").addEventListener("click", async () => {
  const button = $("copy");
  await navigator.clipboard.writeText(state.copyText || "");
  button.textContent = "Скопировано";
  setTimeout(() => {
    button.textContent = "Копировать";
  }, 1200);
});

$("delete").addEventListener("click", async () => {
  const job = state.job;
  if (!job || !job.id) return;
  if (!confirm(`Удалить «${job.filename}» вместе с исходником и результатами?`)) return;
  try {
    await fetch(`/api/v1/jobs/${job.id}`, { method: "DELETE" });
  } catch {
    /* задача уже могла быть удалена */
  }
  showEmpty();
});

loadEngines().catch(() => {
  state.engines = [{ id: "auto", label: "Авто", available: true, description: "" }];
  renderEngines();
});
loadJobs();
