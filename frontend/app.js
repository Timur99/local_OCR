const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file");
const pick = document.getElementById("pick");
const statusBox = document.getElementById("status");
const resultBox = document.getElementById("result");
const meta = document.getElementById("meta");
const bar = document.getElementById("bar");
const message = document.getElementById("message");
const output = document.getElementById("output");

pick.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) submit(fileInput.files[0]);
});

["dragenter", "dragover"].forEach((eventName) => {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.add("drag");
  });
});
["dragleave", "drop"].forEach((eventName) => {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.remove("drag");
  });
});
dropzone.addEventListener("drop", (event) => {
  const file = event.dataTransfer.files[0];
  if (file) submit(file);
});

document.getElementById("copy").addEventListener("click", async () => {
  await navigator.clipboard.writeText(output.textContent);
});

function pill(text) {
  const span = document.createElement("span");
  span.className = "pill";
  span.textContent = text;
  return span;
}

function showStatus(job) {
  statusBox.hidden = false;
  meta.replaceChildren(
    pill(job.filename || "файл"),
    pill(job.path || job.engine),
    job.pdf_type ? pill(job.pdf_type) : "",
    job.page_count ? pill(`${job.page_count} стр.`) : "",
  );
  bar.style.width = `${job.progress || 0}%`;
  message.textContent = job.message || "";
}

async function waitForJob(jobId) {
  for (;;) {
    const response = await fetch(`/api/v1/jobs/${jobId}`);
    const job = await response.json();
    showStatus(job);
    if (job.status === "completed") return job;
    if (job.status === "failed") {
      throw new Error(job.error || "Ошибка обработки");
    }
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
}

async function submit(file) {
  resultBox.hidden = true;
  output.textContent = "";
  showStatus({ filename: file.name, engine: "auto", progress: 5, message: "Загрузка" });

  const body = new FormData();
  body.append("file", file);
  body.append("engine", document.getElementById("engine").value);
  body.append("language", document.getElementById("language").value);

  const response = await fetch("/api/v1/jobs", { method: "POST", body });
  const job = await response.json();
  if (!response.ok) {
    showStatus({ filename: file.name, progress: 100, message: job.detail || "Ошибка" });
    return;
  }
  showStatus(job);

  try {
    await waitForJob(job.id);
    const resultResponse = await fetch(`/api/v1/jobs/${job.id}/result`);
    const result = await resultResponse.json();
    if (!resultResponse.ok) {
      throw new Error(result.detail || "Нет результата");
    }
    resultBox.hidden = false;
    output.textContent = result.markdown || result.text || "";
    const blobMd = new Blob([result.markdown || result.text || ""], { type: "text/markdown" });
    const blobTxt = new Blob([result.text || ""], { type: "text/plain" });
    document.getElementById("download-md").href = URL.createObjectURL(blobMd);
    document.getElementById("download-txt").href = URL.createObjectURL(blobTxt);
  } catch (error) {
    showStatus({ filename: file.name, progress: 100, message: error.message });
  }
}
