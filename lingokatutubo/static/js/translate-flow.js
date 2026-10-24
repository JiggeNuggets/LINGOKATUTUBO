(() => {
  const form = document.getElementById("translate-flow-form");
  if (!form) return;

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
  let busy = false;

  function syncSwap() {
    swap.disabled = busy || source.value === "auto";
    swap.title = swap.disabled ? "Choose a source language to swap" : "Swap source and target languages";
  }

  function showEmpty() {
    fileInput.value = "";
    selected.hidden = true;
    uploadStage.hidden = false;
    uploading.hidden = true;
    errorStage.hidden = true;
    feedback.textContent = "";
    actionHelp.textContent = "Choose a document to continue.";
    submit.disabled = true;
  }

  function showError(message) {
    fileInput.value = "";
    selected.hidden = true;
    uploadStage.hidden = true;
    uploading.hidden = true;
    errorStage.hidden = false;
    byId("translate-error-description").textContent = message;
    feedback.textContent = "";
    actionHelp.textContent = "Choose a document to try again.";
    submit.disabled = true;
    byId("translate-try-again").focus();
  }

  function validateFile(file) {
    if (!file) return false;
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
    byId("translate-file-type").textContent = extension.toUpperCase();
    byId("translate-file-name").textContent = file.name;
    byId("translate-file-size").textContent = `Selected file · ${file.size < 1048576 ? `${Math.max(1, Math.round(file.size / 1024))} KB` : `${(file.size / 1048576).toFixed(1)} MB`}`;
    feedback.textContent = "";
    actionHelp.textContent = "Ready to submit this document.";
    submit.disabled = false;
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
    const file = event.dataTransfer.files[0];
    if (!file) return;
    fileInput.files = event.dataTransfer.files;
    validateFile(file);
  });
  byId("translate-remove-file").addEventListener("click", () => {
    showEmpty();
    fileInput.focus();
  });
  byId("translate-try-again").addEventListener("click", () => {
    showEmpty();
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
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (busy || !validateFile(fileInput.files[0])) return;
    const payload = new FormData(form);
    busy = true;
    fileInput.disabled = true;
    source.disabled = true;
    target.disabled = true;
    syncSwap();
    submit.disabled = true;
    uploadStage.hidden = true;
    errorStage.hidden = true;
    uploading.hidden = false;
    byId("translate-uploading-file").textContent = `${fileInput.files[0].name} is being sent. Keep this page open until the upload finishes.`;
    actionHelp.textContent = "Your upload is in progress.";
    window.addEventListener("beforeunload", warnOnLeave);
    try {
      const response = await fetch(form.dataset.uploadUrl, {
        method: "POST",
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
        throw new Error("The server returned an unexpected response. Please refresh and try again.");
      }
      const data = await response.json();
      if (!response.ok) throw new Error(formatError(data));
      if (!data.job_id) throw new Error("The server did not create a translation job. Please try again.");
      busy = false;
      window.removeEventListener("beforeunload", warnOnLeave);
      window.location.assign(form.dataset.jobUrl.replace("00000000-0000-0000-0000-000000000000", data.job_id));
    } catch (error) {
      busy = false;
      window.removeEventListener("beforeunload", warnOnLeave);
      fileInput.disabled = false;
      source.disabled = false;
      target.disabled = false;
      syncSwap();
      showError(error.message || "The upload failed. Please try again.");
    }
  });
  syncSwap();
})();
