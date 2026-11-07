(() => {
  const form = document.getElementById("translate-flow-form");
  if (!form) return;

  // Keep existing job links available without covering this page's controls.
  const activeNotice = document.querySelector(".active-job-banner");
  if (activeNotice) document.querySelector(".translate-flow__recent").before(activeNotice);

  const byId = (id) => document.getElementById(id);
  const fileInput = byId("translate-file");
  const dropZone = byId("translate-drop-zone");
  const source = byId("translate-source");
  const target = byId("translate-target");
  const swap = byId("translate-swap");
  const submit = byId("translate-start");
  const feedback = byId("translate-file-feedback");
  const actionHelp = byId("translate-action-help");
  const selected = byId("translate-selected");
  const uploadStage = byId("translate-upload-stage");
  const uploading = byId("translate-uploading");
  const errorStage = byId("translate-error-stage");
  const maxBytes = Number(form.dataset.maxFileBytes) || 50 * 1024 * 1024;
  const storageKey = `translation-upload:${form.dataset.workflowKey}`;
  let busy = false;
  let pending = null;
  let uploadController = null;
  const UPLOAD_TIMEOUT_MS = 120000;

  function remember(value) {
    pending = value;
    try {
      if (value) sessionStorage.setItem(storageKey, JSON.stringify(value));
      else sessionStorage.removeItem(storageKey);
    } catch (_) { /* The current page still guards duplicate submissions. */ }
  }

  function jobUrl(jobId) {
    return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(jobId || "")
      ? form.dataset.jobUrl.replace("00000000-0000-0000-0000-000000000000", jobId) : "";
  }

  function showPending() {
    const accepted = pending.state === "accepted";
    uploadStage.hidden = true;
    uploading.hidden = true;
    errorStage.hidden = false;
    errorStage.classList.remove("translate-flow__status--error");
    errorStage.classList.toggle("translate-flow__status--accepted", accepted);
    errorStage.setAttribute("role", "status");
    byId("translate-error-title").textContent = accepted ? "Your upload was accepted" : "Upload status could not be confirmed";
    byId("translate-error-description").textContent = accepted
      ? ""
      : "Your document may already have been accepted. Check this job or your history before submitting it again.";
    const review = byId("translate-review-upload");
    review.href = jobUrl(pending.job_id) || form.dataset.historyUrl;
    review.textContent = accepted && jobUrl(pending.job_id) ? "View translation"
      : jobUrl(pending.job_id) ? "Check this document" : "Check document history";
    review.hidden = false;
    byId("translate-try-again").hidden = false;
    byId("translate-try-again").textContent = accepted ? "Choose another document" : "I checked history — choose another document";
    submit.disabled = true;
    fileInput.disabled = true;
    submit.closest(".translate-flow__action").hidden = true;
    actionHelp.textContent = "Check the existing upload before starting another.";
    feedback.textContent = "";
    review.focus();
  }

  function syncSwap() {
    swap.disabled = busy || source.value === "auto";
    swap.title = swap.disabled ? "Choose a source language to swap" : "Swap source and target languages";
  }

  function showEmpty() {
    fileInput.value = "";
    selected.hidden = true;
    dropZone.hidden = false;
    uploadStage.hidden = false;
    uploading.hidden = true;
    errorStage.hidden = true;
    byId("translate-review-upload").hidden = true;
    feedback.textContent = "";
    actionHelp.textContent = "Choose a document to continue.";
    submit.closest(".translate-flow__action").hidden = false;
    submit.disabled = true;
  }

  function showError(message) {
    fileInput.value = "";
    selected.hidden = true;
    uploadStage.hidden = true;
    uploading.hidden = true;
    errorStage.hidden = false;
    errorStage.classList.add("translate-flow__status--error");
    errorStage.classList.remove("translate-flow__status--accepted");
    errorStage.setAttribute("role", "alert");
    byId("translate-error-title").textContent = "We couldn’t accept this document";
    byId("translate-review-upload").hidden = true;
    byId("translate-try-again").hidden = false;
    byId("translate-try-again").textContent = "Choose a document to try again";
    byId("translate-error-description").textContent = message;
    feedback.textContent = "";
    actionHelp.textContent = "Choose a document to try again.";
    submit.closest(".translate-flow__action").hidden = false;
    submit.disabled = true;
    byId("translate-try-again").focus();
  }

  function validateFile(file) {
    if (busy || pending) return false;
    if (!file) {
      showEmpty();
      return false;
    }
    const extension = file.name.toLowerCase().split(".").pop();
    if (!new Set(["pdf", "docx"]).has(extension)) {
      showError("Choose a PDF or DOCX document to continue.");
      return false;
    }
    if (file.size > maxBytes) {
      showError(`This file is larger than the ${Math.floor(maxBytes / 1048576)} MB upload limit.`);
      return false;
    }
    uploadStage.hidden = false;
    uploading.hidden = true;
    errorStage.hidden = true;
    selected.hidden = false;
    dropZone.hidden = true;
    byId("translate-file-type").textContent = extension.toUpperCase();
    byId("translate-file-name").textContent = file.name;
    byId("translate-file-size").textContent = `${extension.toUpperCase()} · ${file.size < 1048576 ? `${Math.max(1, Math.round(file.size / 1024))} KB` : `${(file.size / 1048576).toFixed(1)} MB`}`;
    feedback.textContent = "";
    actionHelp.textContent = "Ready to submit this document.";
    submit.disabled = false;
    if (document.activeElement === fileInput) byId("translate-remove-file").focus();
    return true;
  }

  function formatError(data) {
    if (!data) return "The upload failed. Please try again.";
    if (typeof data.detail === "string") return data.detail;
    if (data.detail && typeof data.detail === "object") {
      return Object.values(data.detail).flat().map((part) => part.message || String(part)).join(" ");
    }
    return data.error || "The upload failed. Please try again.";
  }

  fileInput.addEventListener("change", () => validateFile(fileInput.files[0]));
  for (const eventName of ["dragenter", "dragover"]) {
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropZone.classList.add("dragging");
    });
  }
  for (const eventName of ["dragleave", "drop"]) {
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropZone.classList.remove("dragging");
    });
  }
  dropZone.addEventListener("drop", (event) => {
    if (busy || pending) return;
    const file = event.dataTransfer.files[0];
    if (!file) return;
    fileInput.files = event.dataTransfer.files;
    validateFile(file);
  });
  byId("translate-remove-file").addEventListener("click", () => {
    if (busy || pending) return;
    showEmpty();
    fileInput.focus();
  });
  byId("translate-try-again").addEventListener("click", () => {
    if (busy) return;
    remember(null);
    fileInput.disabled = false;
    showEmpty();
    fileInput.focus();
    fileInput.click();
  });
  source.addEventListener("change", syncSwap);
  swap.addEventListener("click", () => {
    if (swap.disabled) return;
    const oldSource = source.value;
    source.value = target.value;
    target.value = oldSource;
    syncSwap();
  });

  const warnOnLeave = (event) => {
    if (!busy) return;
    event.preventDefault();
    event.returnValue = "";
  };
  byId("translate-stop-waiting").addEventListener("click", () => {
    if (uploadController) uploadController.abort();
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (busy || pending || !validateFile(fileInput.files[0])) return;
    const payload = new FormData(form);
    busy = true;
    form.setAttribute("aria-busy", "true");
    remember({state: "uncertain"});
    fileInput.disabled = true;
    source.disabled = true;
    target.disabled = true;
    syncSwap();
    submit.disabled = true;
    submit.setAttribute("aria-busy", "true");
    byId("translate-start-label").textContent = "Uploading...";
    uploadStage.hidden = true;
    errorStage.hidden = true;
    uploading.hidden = false;
    byId("translate-uploading-file").textContent = `Sending ${fileInput.files[0].name}.`;
    byId("translate-upload-announcement").textContent = `Uploading ${fileInput.files[0].name}. Translation begins after acceptance.`;
    uploading.focus();
    actionHelp.textContent = "Your upload is in progress.";
    window.addEventListener("beforeunload", warnOnLeave);
    uploadController = new AbortController();
    const deadline = window.setTimeout(() => uploadController.abort(), UPLOAD_TIMEOUT_MS);
    try {
      const response = await fetch(form.dataset.uploadUrl, {
        method: "POST",
        signal: uploadController.signal,
        body: payload,
        credentials: "same-origin",
        headers: {
          "X-CSRFToken": form.querySelector('[name="csrfmiddlewaretoken"]').value,
          "Accept": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
      });
      const contentType = response.headers.get("content-type") || "";
      if (!contentType.includes("application/json")) {
        throw new Error("Upload acceptance could not be confirmed.");
      }
      const data = await response.json();
      if (data.status_uncertain || (!response.ok && response.status >= 500 && data.status_uncertain !== false)) {
        remember({state: "uncertain", job_id: data.job_id});
        showPending();
      } else if (!response.ok) {
        remember(null);
        showError(formatError(data));
      } else if (jobUrl(data.job_id)) {
        remember({state: "accepted", job_id: data.job_id});
        window.removeEventListener("beforeunload", warnOnLeave);
        window.location.assign(jobUrl(data.job_id));
        return;
      } else {
        throw new Error("Upload acceptance could not be confirmed.");
      }
    } catch (_) {
      showPending();
    } finally {
      busy = false;
      window.clearTimeout(deadline);
      uploadController = null;
      form.setAttribute("aria-busy", "false");
      submit.removeAttribute("aria-busy");
      byId("translate-start-label").textContent = "Translate Document";
      byId("translate-upload-announcement").textContent = "";
      window.removeEventListener("beforeunload", warnOnLeave);
      fileInput.disabled = Boolean(pending);
      source.disabled = false;
      target.disabled = false;
      syncSwap();
    }
  });
  window.addEventListener("pageshow", () => {
    try {
      const saved = JSON.parse(sessionStorage.getItem(storageKey));
      if (saved && ["accepted", "uncertain"].includes(saved.state)) pending = saved;
    } catch (_) { /* Storage can be disabled by the browser. */ }
    if (pending) showPending();
  });
  syncSwap();
})();
