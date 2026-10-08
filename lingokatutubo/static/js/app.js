(function () {
  const activeStatuses = new Set(["queued", "processing", "retrying"]);
  const terminalStatuses = new Set(["completed", "failed"]);

  const phaseLabels = {
    uploading: "Uploading",
    queued: "Queued for processing",
    retrying: "Retrying",
    detecting: "Detecting document",
    extracting: "Extracting text and layout",
    ocr: "Running OCR",
    translating: "Translating",
    reconstructing: "Reconstructing document",
    preview_generation: "Creating preview",
    bilingual_output: "Preparing bilingual output",
    completed: "Completed",
    failed: "Failed",
  };

  const phaseProgress = {
    uploading: 3,
    queued: 5,
    retrying: 5,
    detecting: 15,
    extracting: 30,
    ocr: 45,
    translating: 65,
    reconstructing: 80,
    preview_generation: 90,
    bilingual_output: 95,
    completed: 100,
  };

  const controllers = new Map();

  function text(value) {
    return value == null ? "" : String(value);
  }

  function csrfToken() {
    const input = document.querySelector("input[name='csrfmiddlewaretoken']");
    if (input) return input.value;
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function normalizeStatus(value) {
    return text(value).trim().toLowerCase();
  }

  function statusLabel(value) {
    const status = normalizeStatus(value);
    if (status === "queued") return "Pending";
    return phaseLabels[status] || (status ? status.charAt(0).toUpperCase() + status.slice(1) : "Unknown");
  }

  function progressFor(data) {
    const phase = normalizeStatus(data.current_phase || data.status);
    const raw = data.progress_percent != null ? data.progress_percent : data.progress;
    const numeric = Number(raw);
    if (Number.isFinite(numeric)) return Math.max(0, Math.min(100, Math.round(numeric)));
    return phaseProgress[phase] || 0;
  }

  function languageName(value) {
    const names = {
      english: "English",
      filipino: "Filipino",
      cebuano: "Cebuano",
      tagabawa: "Bagobo-Tagabawa",
    };
    const key = normalizeStatus(value);
    return names[key] || text(value);
  }

  function formatDateTime(value) {
    if (!value) return "Not available";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return text(value);
    return date.toLocaleString([], {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  }

  function nowLabel() {
    return new Date().toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  }

  function setHidden(element, hidden) {
    if (element) element.hidden = hidden;
  }

  function setText(element, value) {
    if (element) element.textContent = value;
  }

  function setError(errorBox, message) {
    if (!errorBox) return;
    errorBox.hidden = !message;
    errorBox.textContent = message || "";
  }

  // Django can hand back an HTML page instead of JSON (login redirect, CSRF
  // failure, 404/500 error page) whenever something between the browser and
  // the view doesn't go as planned. Parsing that as JSON throws a raw
  // "Unexpected token '<'" SyntaxError — never call response.json() without
  // checking Content-Type first, or that raw parser error reaches the user.
  function parseJsonResponse(response) {
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      return response.text().then((bodyText) => {
        console.error(
          "Expected JSON but received:",
          response.status,
          contentType,
          bodyText.slice(0, 300)
        );
        throw new Error("The server returned an unexpected response. Please refresh and try again.");
      });
    }
    return response.json().then((data) => ({ response, data }));
  }

  class PollingController {
    constructor(key, statusUrl, handlers) {
      this.key = key;
      this.statusUrl = statusUrl;
      this.handlers = handlers || {};
      this.timer = null;
      this.inFlight = false;
      this.stopped = false;
      this.failureCount = 0;
      this.lastData = null;
      this.boundVisibilityHandler = () => this.handleVisibilityChange();
      document.addEventListener("visibilitychange", this.boundVisibilityHandler);
    }

    static start(key, statusUrl, handlers) {
      if (controllers.has(key)) {
        return controllers.get(key);
      }
      const controller = new PollingController(key, statusUrl, handlers);
      controllers.set(key, controller);
      controller.poll(0);
      return controller;
    }

    stop() {
      this.stopped = true;
      if (this.timer) {
        window.clearTimeout(this.timer);
        this.timer = null;
      }
      document.removeEventListener("visibilitychange", this.boundVisibilityHandler);
      controllers.delete(this.key);
    }

    handleVisibilityChange() {
      if (this.stopped) return;
      if (!document.hidden && this.lastData && activeStatuses.has(normalizeStatus(this.lastData.status))) {
        this.schedule(0);
      }
    }

    schedule(delay) {
      if (this.stopped) return;
      if (this.timer) window.clearTimeout(this.timer);
      this.timer = window.setTimeout(() => this.poll(), delay);
    }

    nextDelay() {
      const visibleDelay = this.failureCount ? 3000 : 1500;
      const hiddenDelay = this.failureCount ? 15000 : 10000;
      return document.hidden ? hiddenDelay : visibleDelay;
    }

    poll(delayOverride) {
      if (this.stopped || this.inFlight) return;
      if (typeof delayOverride === "number" && delayOverride > 0) {
        this.schedule(delayOverride);
        return;
      }
      this.inFlight = true;
      fetch(this.statusUrl, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      })
        .then(parseJsonResponse)
        .then(({ response, data }) => {
          if (!response.ok) throw new Error(data.error || `Status check failed (${response.status}).`);
          this.failureCount = 0;
          this.lastData = data;
          if (this.handlers.onUpdate) this.handlers.onUpdate(data);
          if (this.handlers.onNetworkState) this.handlers.onNetworkState("", data);
          const status = normalizeStatus(data.status);
          if (terminalStatuses.has(status) || !activeStatuses.has(status)) {
            if (this.handlers.onTerminal) this.handlers.onTerminal(data);
            this.stop();
            return;
          }
          this.schedule(this.nextDelay());
        })
        .catch((error) => {
          this.failureCount += 1;
          if (this.handlers.onNetworkState) {
            this.handlers.onNetworkState(
              `${error.message || "Could not reach the server."} Retrying status check...`,
              this.lastData
            );
          }
          this.schedule(this.nextDelay());
        })
        .finally(() => {
          this.inFlight = false;
        });
    }
  }

  window.LingoKatutuboPolling = {
    activeStatuses,
    controllers,
    start: PollingController.start,
  };

  function updateProgressDom(elements, data) {
    const phase = normalizeStatus(data.current_phase || data.status || "queued");
    const status = normalizeStatus(data.status);
    const percent = progressFor(data);
    const message = data.phase_message || data.message || phaseLabels[phase] || "";
    setHidden(elements.progressCard, false);
    setText(elements.title, phaseLabels[phase] || data.current_step || statusLabel(status));
    setText(elements.message, message);
    setText(elements.percent, `${percent}%`);
    if (elements.fill) elements.fill.style.width = `${percent}%`;
    if (elements.progressbar) elements.progressbar.setAttribute("aria-valuenow", String(percent));
    setText(elements.step, data.current_step || phaseLabels[phase] || statusLabel(status));
  }

  function updateLanguageDom(element, data) {
    if (!element || !data.detected_language) return;
    const confidence = data.detection_confidence != null
      ? ` (${Math.round(Number(data.detection_confidence) * 100)}% confidence)`
      : "";
    element.textContent = `Detected source language: ${languageName(data.detected_language)}${confidence}`;
    element.hidden = false;
  }
  function initUpload() {
    const form = document.getElementById("upload-form");
    if (!form) return;

    const fileInput = document.getElementById("id_file");
    const dropZone = document.getElementById("drop-zone");
    const fileName = document.getElementById("selected-file-name");
    const fileMeta = document.getElementById("selected-file-meta");
    const fileRequiredMessage = document.getElementById("file-required-message");
    const readyMessage = document.getElementById("ready-message");
    const errorBox = document.getElementById("upload-error");
    const button = document.getElementById("translate-button");
    const sourceLanguage = document.getElementById("source-language");
    const targetLanguage = document.getElementById("target-language");
    const swapLanguages = document.querySelector("[data-swap-languages]");
    const overlay = document.getElementById("translation-submission-overlay");

    let isUploading = false;
    let isSubmitting = false;
    let currentJobId = null;

    function syncLanguageSwap() {
      if (!swapLanguages || !sourceLanguage) return;
      const canSwap = sourceLanguage.value !== "auto";
      swapLanguages.disabled = !canSwap;
      swapLanguages.setAttribute("aria-disabled", String(!canSwap));
      swapLanguages.title = canSwap
        ? "Swap source and target languages"
        : "Choose a source language to swap";
    }

    if (swapLanguages && sourceLanguage && targetLanguage) {
      syncLanguageSwap();
      sourceLanguage.addEventListener("change", syncLanguageSwap);
      swapLanguages.addEventListener("click", () => {
        if (sourceLanguage.value === "auto") return;
        const sourceValue = sourceLanguage.value;
        sourceLanguage.value = targetLanguage.value;
        targetLanguage.value = sourceValue;
        sourceLanguage.dispatchEvent(new Event("change", { bubbles: true }));
        targetLanguage.dispatchEvent(new Event("change", { bubbles: true }));
      });
    }

    function setSubmissionState(isBusy) {
      form.toggleAttribute("aria-busy", isBusy);
      document.body.classList.toggle("translation-overlay-active", isBusy);
      if (overlay) {
        overlay.hidden = !isBusy;
        overlay.setAttribute("aria-hidden", String(!isBusy));
      }
      button.disabled = isBusy || !(fileInput.files && fileInput.files[0]);
      button.textContent = isBusy ? "Translating" : "Start Translation";
    }

    function beforeUnloadHandler(event) {
      if (!isUploading || currentJobId) return undefined;
      const message = "Your document is still uploading. Leaving now may cancel the upload.";
      event.preventDefault();
      event.returnValue = message;
      return message;
    }

    function enableUploadLeaveWarning() {
      window.addEventListener("beforeunload", beforeUnloadHandler);
    }

    function disableUploadLeaveWarning() {
      window.removeEventListener("beforeunload", beforeUnloadHandler);
    }

    function updateSelectedFile() {
      const file = fileInput.files && fileInput.files[0];
      setError(errorBox, "");
      if (!file) {
        fileName.textContent = "Drop your document here";
        fileMeta.textContent = "PDF or DOCX - up to 50 MB";
        setHidden(fileRequiredMessage, false);
        readyMessage.hidden = true;
        button.disabled = true;
        return;
      }
      fileName.textContent = file.name;
      fileMeta.textContent = `${(file.size / 1024 / 1024).toFixed(2)} MB`;
      setHidden(fileRequiredMessage, true);
      readyMessage.hidden = false;
      button.disabled = false;
    }

    ["dragenter", "dragover"].forEach((eventName) => {
      dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropZone.classList.add("dragging");
      });
    });
    ["dragleave", "drop"].forEach((eventName) => {
      dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropZone.classList.remove("dragging");
      });
    });
    dropZone.addEventListener("drop", (event) => {
      if (event.dataTransfer.files.length) {
        fileInput.files = event.dataTransfer.files;
        updateSelectedFile();
      }
    });
    fileInput.addEventListener("change", updateSelectedFile);

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!form.reportValidity()) return;
      const file = fileInput.files && fileInput.files[0];
      if (!file || isSubmitting) return;
      isSubmitting = true;
      isUploading = true;
      currentJobId = null;
      enableUploadLeaveWarning();
      setError(errorBox, "");
      setSubmissionState(true);

      fetch(form.dataset.uploadUrl, {
        method: "POST",
        body: new FormData(form),
        credentials: "same-origin",
        headers: {
          "X-CSRFToken": csrfToken(),
          Accept: "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
      })
        .then(parseJsonResponse)
        .then(({ response, data }) => {
          if (!response.ok) throw new Error(formatUploadError(data));
          if (!data.job_id) throw new Error("The server did not create a translation job. Please try again.");
          currentJobId = data.job_id;
          isUploading = false;
          disableUploadLeaveWarning();
          const targetUrl = form.dataset.jobBase
            ? form.dataset.jobBase.replace("00000000-0000-0000-0000-000000000000", data.job_id)
            : `/translate/job/${data.job_id}/`;
          window.setTimeout(() => {
            window.location.assign(targetUrl);
          }, 1500);
        })
        .catch((error) => {
          isUploading = false;
          disableUploadLeaveWarning();
          isSubmitting = false;
          setSubmissionState(false);
          setError(errorBox, error.message || "Upload failed.");
        });
    });
  }

  function initStatusPage() {
    const root = document.querySelector("[data-status-poller]");
    if (!root) return;

    const progressFill = document.getElementById("status-monitor-fill");
    const progressElements = {
      progressCard: root,
      title: document.getElementById("status-monitor-title"),
      message: document.getElementById("status-monitor-message"),
      percent: document.getElementById("status-monitor-percent"),
      fill: progressFill,
      progressbar: progressFill ? progressFill.parentElement : null,
      step: document.getElementById("job-current-step"),
    };
    const network = document.getElementById("status-monitor-network");
    const lastCheck = document.getElementById("status-monitor-last-check");
    const phase = document.getElementById("status-monitor-phase");
    const updated = document.getElementById("status-monitor-updated");
    const phaseValue = document.getElementById("job-current-phase");
    const messageValue = document.getElementById("job-phase-message");
    const progressText = document.getElementById("job-progress-text");
    const retryingState = document.getElementById("job-retrying-state");
    const longMessage = document.getElementById("status-monitor-long");
    const failedGuidance = document.getElementById("failed-guidance");
    const statusPill = document.getElementById("job-status-pill");
    const previewAction = document.getElementById("job-preview-action");
    const downloadAction = document.getElementById("job-download-action");
    const processingOverlay = document.getElementById("translation-job-processing-overlay");
    const terminalOverlay = document.getElementById("translation-terminal-overlay");
    const reloadButton = document.getElementById("reload-status-button");

    function setProcessingOverlayState(isActive) {
      document.body.classList.toggle("translation-overlay-active", isActive);
      if (processingOverlay) {
        processingOverlay.hidden = !isActive;
        processingOverlay.setAttribute("aria-hidden", String(!isActive));
      }
    }

    function applyStatus(data) {
      const status = normalizeStatus(data.status);
      const percent = progressFor(data);
      const isProcessing = activeStatuses.has(status);
      root.setAttribute("aria-busy", String(isProcessing));
      setProcessingOverlayState(isProcessing);

      updateProgressDom(progressElements, data);
      setText(phase, data.current_phase || status);
      setText(updated, formatDateTime(data.updated_at));
      setText(lastCheck, nowLabel());
      setText(phaseValue, data.current_phase || status);
      setText(messageValue, data.phase_message || data.message || "");
      setText(progressText, `${percent}%`);
      setText(retryingState, status === "retrying" ? "Yes" : "No");
      setHidden(longMessage, !data.is_taking_longer);
      if (statusPill) {
        statusPill.textContent = statusLabel(status);
        statusPill.className = `status-pill ${status === "queued" ? "pending" : status}`;
      }
      setHidden(previewAction, !data.can_preview);
      setHidden(downloadAction, !data.can_download);
      if (previewAction && data.can_preview && !previewAction.textContent.trim()) {
        previewAction.textContent = "Preview Bilingual";
      }
      if (downloadAction && data.can_download && !downloadAction.textContent.trim()) {
        downloadAction.textContent = "Download";
      }
      if (status === "failed") {
        failedGuidance.hidden = false;
        failedGuidance.textContent = `${data.error || data.message || "Translation failed."} Check the document quality or try uploading again. If this repeats, contact an administrator with this job ID.`;
      }
    }

    function networkState(message) {
      if (!network) return;
      network.hidden = !message;
      network.textContent = message || "";
    }

    let controller = null;
    const handlers = {
      onUpdate: applyStatus,
      onTerminal: (data) => {
        applyStatus(data);
        setProcessingOverlayState(false);
        const status = normalizeStatus(data.status);
        if (status === "completed") {
          const previewUrl = root.getAttribute("data-preview-url") || (data.preview_url) || (window.location.pathname.replace(/\/$/, '') + "/preview/");
          window.location.href = previewUrl;
          return;
        }
        window.setTimeout(() => window.location.reload(), 150);
        controller = null;
      },
      onNetworkState: networkState,
    };
    if (terminalOverlay) {
      document.body.classList.add("translation-overlay-active");
      window.requestAnimationFrame(() => {
        const terminalAction = terminalOverlay.querySelector("[data-terminal-action]");
        if (terminalAction) terminalAction.focus();
      });
    }
    const initialStatus = normalizeStatus(root.dataset.initialStatus);
    if (activeStatuses.has(initialStatus)) {
      setProcessingOverlayState(true);
      controller = PollingController.start(`detail:${root.dataset.jobId}`, root.dataset.statusUrl, handlers);
    } else {
      setProcessingOverlayState(false);
    }

    if (reloadButton) {
      reloadButton.addEventListener("click", () => {
        networkState("");
        if (controller) {
          controller.poll();
          return;
        }
        fetch(root.dataset.statusUrl, {
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        })
          .then(parseJsonResponse)
          .then(({ response, data }) => {
            if (!response.ok) throw new Error(data.error || `Status check failed (${response.status}).`);
            applyStatus(data);
          })
          .catch((error) => networkState(`${error.message || "Could not reach the server."} Retrying status check...`));
      });
    }
  }

  function formatUploadError(data) {
    if (!data) return "Upload failed.";
    if (typeof data.detail === "string") return data.detail;
    if (data.detail && typeof data.detail === "object") {
      return Object.values(data.detail)
        .flat()
        .map((entry) => entry.message || entry)
        .join(" ");
    }
    return data.error || "Upload failed.";
  }

  function initRenderedPreviewControls() {
    const root = document.getElementById("preview-app");
    const scope = document.querySelector("[data-preview-scope]");
    const buttons = document.querySelectorAll("[data-preview-zoom-action]");
    if (!root || !scope || !buttons.length) return;

    const MIN_ZOOM = 0.75;
    const MAX_ZOOM = 1.5;
    const ZOOM_STEP = 0.15;
    let zoom = 1;

    function updateButtons(activeAction) {
      buttons.forEach((button) => {
        const isActive = button.dataset.previewZoomAction === activeAction;
        button.classList.toggle("is-active", isActive);
        button.setAttribute("aria-pressed", isActive ? "true" : "false");
      });
    }

    function setZoom(nextZoom, activeAction) {
      zoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, nextZoom));
      const fitWidth = activeAction === "fit" || activeAction === "reset";
      scope.style.setProperty("--preview-zoom", zoom.toFixed(2));
      scope.style.setProperty("--preview-card-width", `${Math.round(zoom * 100)}%`);
      scope.classList.toggle("is-fit-width", fitWidth);
      updateButtons(activeAction);
    }

    buttons.forEach((button) => {
      button.addEventListener("click", () => {
        const action = button.dataset.previewZoomAction;
        if (action === "fit" || action === "reset") {
          setZoom(1, action);
        } else if (action === "in") {
          setZoom(zoom + ZOOM_STEP, "in");
        } else if (action === "out") {
          setZoom(zoom - ZOOM_STEP, "out");
        }
      });
    });

    setZoom(1, "fit");
  }

  function initPreviewLinks() {
    const links = document.querySelectorAll(".js-preview-link");
    if (!links.length) return;

    const overlay = document.getElementById("page-transition-overlay");
    const overlayText = document.getElementById("page-transition-text");
    const errorBanner = document.getElementById("js-error-banner");
    const errorBannerText = document.getElementById("js-error-banner-text");
    // Minimum time the loading state stays visible before navigating, so the
    // transition reads as intentional instead of a sudden visual jump.
    const MIN_LOADING_MS = 2500;
    const FAILSAFE_TIMEOUT_MS = 12000;

    function showOverlay(message) {
      if (!overlay) return;
      if (overlayText && message) overlayText.textContent = message;
      overlay.classList.add("is-visible");
      overlay.setAttribute("aria-hidden", "false");
    }

    function hideOverlay() {
      if (!overlay) return;
      overlay.classList.remove("is-visible");
      overlay.setAttribute("aria-hidden", "true");
    }

    function resetPreviewLinksState() {
      hideOverlay();
      links.forEach((link) => {
        link.classList.remove("is-loading");
        link.removeAttribute("aria-disabled");
        if (link.dataset.originalText) {
          const keepLabel = link.classList.contains("recent-document-card__check") ||
                            link.classList.contains("document-card-action") ||
                            Boolean(link.closest(".document-card"));
          if (!keepLabel) {
            link.textContent = link.dataset.originalText;
          }
        }
      });
    }

    // Reset overlay and loading indicators if restored from BFCache or history navigation
    window.addEventListener("pageshow", resetPreviewLinksState);
    window.addEventListener("popstate", resetPreviewLinksState);

    function showOpenFailure() {
      if (!errorBanner || !errorBannerText) return;
      errorBannerText.textContent = "Could not open the bilingual preview. Please try again.";
      errorBanner.hidden = false;
    }

    links.forEach((link) => {
      link.addEventListener("click", (event) => {
        // Never intercept a hidden link, a link already loading, or a
        // modified/non-primary click (new tab, new window, etc.) — those
        // must keep their normal browser behavior.
        if (link.hidden || link.classList.contains("is-loading")) {
          event.preventDefault();
          return;
        }
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
          return;
        }
        const href = link.getAttribute("href");
        if (!href || href === "#") return;

        event.preventDefault();
        const loadingText = link.dataset.loadingText || "Preparing bilingual preview…";
        link.dataset.originalText = link.textContent;
        link.classList.add("is-loading");
        link.setAttribute("aria-disabled", "true");
        const keepLabel = link.classList.contains("recent-document-card__check") ||
                          link.classList.contains("document-card-action") ||
                          Boolean(link.closest(".document-card"));
        if (!keepLabel) {
          link.textContent = loadingText;
        }
        showOverlay(loadingText);

        const failsafeTimer = window.setTimeout(() => {
          link.classList.remove("is-loading");
          link.removeAttribute("aria-disabled");
          if (!keepLabel) {
            link.textContent = link.dataset.originalText || loadingText;
          }
          hideOverlay();
          showOpenFailure();
        }, FAILSAFE_TIMEOUT_MS);

        // Hold the loading state for a fixed minimum duration, then navigate.
        // Reduced-motion users still get this same wait — only the spinner
        // animation is suppressed (see the prefers-reduced-motion CSS rule).
        window.setTimeout(() => {
          window.clearTimeout(failsafeTimer);
          window.location.href = href;
        }, MIN_LOADING_MS);
      });
    });
  }

  function initPreviewBackNavigation() {
    const backLinks = document.querySelectorAll(".preview-back-link");
    if (!backLinks.length) return;

    backLinks.forEach((link) => {
      link.addEventListener("click", (event) => {
        const overlay = document.getElementById("page-transition-overlay");
        if (overlay) {
          overlay.classList.remove("is-visible");
          overlay.setAttribute("aria-hidden", "true");
        }
        // If there is prior history in this window/tab, react as a back button
        if (window.history.length > 1) {
          event.preventDefault();
          window.history.back();
        }
      });
    });
  }

  function initMobileNav() {
    const hamburger = document.getElementById("nav-hamburger");
    const navLinks = document.getElementById("nav-links");
    if (!hamburger || !navLinks) return;

    hamburger.addEventListener("click", () => {
      const isOpen = navLinks.classList.toggle("open");
      hamburger.setAttribute("aria-expanded", isOpen ? "true" : "false");
    });

    navLinks.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        navLinks.classList.remove("open");
        hamburger.setAttribute("aria-expanded", "false");
      });
    });

    document.addEventListener("click", (event) => {
      if (!hamburger.contains(event.target) && !navLinks.contains(event.target)) {
        navLinks.classList.remove("open");
        hamburger.setAttribute("aria-expanded", "false");
      }
    });
  }

  function dismissMessage(msg) {
    msg.style.transition = "opacity 200ms ease, transform 200ms ease";
    msg.style.opacity = "0";
    msg.style.transform = "translateY(-4px)";
    setTimeout(() => msg.remove(), 210);
  }

  function initMessageDismiss() {
    document.querySelectorAll(".message-dismiss").forEach((btn) => {
      btn.addEventListener("click", () => {
        const msg = btn.closest(".message");
        if (msg) dismissMessage(msg);
      });
    });
  }

  // Toasts hide themselves after a few seconds (errors get a little longer);
  // hovering pauses the countdown so the user can finish reading. Only
  // messages inside the toast region auto-hide — the reusable #js-error-banner
  // is shown/hidden by its own flows and must not be removed from the DOM.
  const TOAST_DISMISS_MS = 3500;
  const TOAST_ERROR_DISMISS_MS = 4000;
  const TOAST_HOVER_GRACE_MS = 1500;

  function scheduleToastDismiss(msg) {
    const delay = msg.classList.contains("error")
      ? TOAST_ERROR_DISMISS_MS
      : TOAST_DISMISS_MS;
    let timer = window.setTimeout(() => dismissMessage(msg), delay);
    msg.addEventListener("mouseenter", () => window.clearTimeout(timer));
    msg.addEventListener("mouseleave", () => {
      timer = window.setTimeout(() => dismissMessage(msg), TOAST_HOVER_GRACE_MS);
    });
  }

  function initToastAutoDismiss() {
    document
      .querySelectorAll("#messages-region .message")
      .forEach(scheduleToastDismiss);
  }

  function initDocumentRemoveModal() {
    if (!document.querySelector("[data-remove-document]")) return;

    const modal = document.createElement("div");
    modal.className = "remove-document-modal";
    modal.hidden = true;
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    modal.setAttribute("aria-labelledby", "remove-document-modal-title");
    modal.setAttribute("aria-describedby", "remove-document-modal-message");

    const dialog = document.createElement("div");
    dialog.className = "remove-document-dialog";

    const header = document.createElement("div");
    header.className = "remove-document-header";

    const title = document.createElement("h2");
    title.id = "remove-document-modal-title";
    title.textContent = "Remove from History?";

    const closeButton = document.createElement("button");
    closeButton.type = "button";
    closeButton.className = "remove-document-close";
    closeButton.setAttribute("aria-label", "Close remove confirmation");
    closeButton.textContent = "\u00d7";

    const message = document.createElement("p");
    message.id = "remove-document-modal-message";
    message.className = "remove-document-message";

    const error = document.createElement("p");
    error.className = "remove-document-error";
    error.setAttribute("role", "alert");
    error.hidden = true;

    const actions = document.createElement("div");
    actions.className = "remove-document-actions";

    const cancelButton = document.createElement("button");
    cancelButton.type = "button";
    cancelButton.className = "button secondary";
    cancelButton.textContent = "Cancel";

    const confirmButton = document.createElement("button");
    confirmButton.type = "button";
    confirmButton.className = "button danger-outline";
    confirmButton.textContent = "Remove from History";

    header.append(title, closeButton);
    actions.append(cancelButton, confirmButton);
    dialog.append(header, message, error, actions);
    modal.appendChild(dialog);
    document.body.appendChild(modal);

    let activeTrigger = null;
    let activeCard = null;
    let deleteUrl = "";
    let isSubmitting = false;

    function showModal(trigger) {
      activeTrigger = trigger;
      activeCard = trigger.closest("[data-document-card]");
      deleteUrl = trigger.dataset.deleteUrl || "";
      const documentTitle = trigger.dataset.documentTitle || "this document";
      message.textContent = `Remove \u201c${documentTitle}\u201d from your translation history?`;
      error.hidden = true;
      error.textContent = "";
      confirmButton.disabled = false;
      cancelButton.disabled = false;
      closeButton.disabled = false;
      confirmButton.classList.remove("is-loading");
      confirmButton.textContent = "Remove from History";
      modal.hidden = false;
      document.body.classList.add("modal-open");
      window.requestAnimationFrame(() => modal.classList.add("is-visible"));
      cancelButton.focus();
    }

    function hideModal(restoreFocus) {
      if (isSubmitting) return;
      modal.classList.remove("is-visible");
      modal.hidden = true;
      document.body.classList.remove("modal-open");
      if (restoreFocus !== false && activeTrigger && document.body.contains(activeTrigger)) {
        activeTrigger.focus();
      }
      activeTrigger = null;
      activeCard = null;
      deleteUrl = "";
    }

    function removeActiveCard() {
      if (!activeCard) {
        const trigger = activeTrigger;
        const actionGroup = trigger && trigger.closest(".top-action-bar-danger");
        if (actionGroup) actionGroup.remove();
        return;
      }

      const card = activeCard;
      card.classList.add("is-removing");
      window.setTimeout(() => {
        card.remove();
      }, 180);
    }

    document.addEventListener("click", (event) => {
      const trigger = event.target.closest("[data-remove-document]");
      if (!trigger) return;
      event.preventDefault();
      showModal(trigger);
    });

    [cancelButton, closeButton].forEach((button) => {
      button.addEventListener("click", () => hideModal(true));
    });

    modal.addEventListener("click", (event) => {
      if (event.target === modal) hideModal(true);
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !modal.hidden) {
        event.preventDefault();
        hideModal(true);
      }
    });

    confirmButton.addEventListener("click", () => {
      if (isSubmitting || !deleteUrl) return;
      isSubmitting = true;
      error.hidden = true;
      error.textContent = "";
      confirmButton.disabled = true;
      cancelButton.disabled = true;
      closeButton.disabled = true;
      confirmButton.classList.add("is-loading");
      confirmButton.textContent = "Removing...";

      fetch(deleteUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "X-CSRFToken": csrfToken(),
          Accept: "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
      })
        .then(parseJsonResponse)
        .then(({ response, data }) => {
          if (!response.ok || data.ok === false) {
            throw new Error(data.error || data.message || "Could not remove the document.");
          }
          removeActiveCard();
          isSubmitting = false;
          hideModal(false);
          showStatusMessage(data.message || "Document removed from history.", "success");
        })
        .catch((caught) => {
          isSubmitting = false;
          confirmButton.disabled = false;
          cancelButton.disabled = false;
          closeButton.disabled = false;
          confirmButton.classList.remove("is-loading");
          confirmButton.textContent = "Remove from History";
          const messageText = caught.message || "Could not remove the document. Please try again.";
          error.textContent = messageText;
          error.hidden = false;
          showStatusMessage(messageText, "error");
        });
    });
  }

  // Shows a dismissible, accessible status message (e.g. "Translated file is
  // ready.") detected live via polling, without a page reload. Reuses the
  // same markup/classes as Django's server-rendered messages so it looks and
  // behaves identically, and creates the messages region if this page never
  // rendered one (no messages were queued at request time).
  function showStatusMessage(messageText, tone) {
    let region = document.getElementById("messages-region");
    if (!region) {
      region = document.createElement("div");
      region.className = "messages";
      region.id = "messages-region";
      region.setAttribute("aria-label", "Notifications");
      const header = document.querySelector(".site-header");
      if (header) {
        header.insertAdjacentElement("afterend", region);
      } else {
        document.body.prepend(region);
      }
    }

    const item = document.createElement("div");
    item.className = `message ${tone || "info"}`;
    item.setAttribute("role", "status");
    item.setAttribute("aria-live", "polite");

    const span = document.createElement("span");
    span.textContent = messageText;

    const dismissButton = document.createElement("button");
    dismissButton.type = "button";
    dismissButton.className = "message-dismiss";
    dismissButton.setAttribute("aria-label", "Dismiss notification");
    dismissButton.textContent = "✕";
    dismissButton.addEventListener("click", () => dismissMessage(item));

    item.append(span, dismissButton);
    region.appendChild(item);
    scheduleToastDismiss(item);
  }

  function initNavigationDropdowns() {
    const dropdowns = Array.from(document.querySelectorAll("[data-nav-dropdown]"));
    if (!dropdowns.length) return;

    function setExpanded(dropdown, isOpen) {
      const trigger = dropdown.querySelector("[data-nav-dropdown-trigger]");
      const menu = dropdown.querySelector(".nav-dropdown__menu");
      dropdown.classList.toggle("is-open", isOpen);
      if (trigger) trigger.setAttribute("aria-expanded", isOpen ? "true" : "false");
      if (menu) menu.hidden = !isOpen;
    }

    function closeDropdown(dropdown) {
      setExpanded(dropdown, false);
    }

    dropdowns.forEach((dropdown) => {
      const trigger = dropdown.querySelector("[data-nav-dropdown-trigger]");
      const menu = dropdown.querySelector(".nav-dropdown__menu");
      setExpanded(dropdown, false);
      if (trigger) {
        trigger.addEventListener("click", () => {
          const isOpen = !dropdown.classList.contains("is-open");
          setExpanded(dropdown, isOpen);
          if (isOpen) {
            dropdowns.forEach((other) => {
              if (other !== dropdown) closeDropdown(other);
            });
          }
        });
      }
      if (menu) {
        menu.addEventListener("click", () => closeDropdown(dropdown));
      }
    });

    document.addEventListener("click", (event) => {
      if (!dropdowns.some((dropdown) => dropdown.contains(event.target))) {
        dropdowns.forEach(closeDropdown);
      }
    });

    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      const openDropdown = dropdowns.find((dropdown) => dropdown.classList.contains("is-open"));
      if (!openDropdown) return;
      event.preventDefault();
      closeDropdown(openDropdown);
      const trigger = openDropdown.querySelector("[data-nav-dropdown-trigger]");
      if (trigger) trigger.focus();
    });
  }

  function initRevealElements() {
    const elements = Array.from(document.querySelectorAll("[data-reveal]"));
    if (!elements.length) return;

    document.documentElement.classList.add("has-reveal");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reducedMotion || !("IntersectionObserver" in window)) {
      elements.forEach((element) => element.classList.add("is-revealed"));
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-revealed");
          observer.unobserve(entry.target);
        });
      },
      { rootMargin: "0px 0px -8%", threshold: 0.08 }
    );

    elements.forEach((element) => observer.observe(element));
  }

  function initEditorialGalleries() {
    const galleries = Array.from(document.querySelectorAll("[data-gallery]"));
    if (!galleries.length) return;

    galleries.forEach((gallery) => {
      const items = Array.from(gallery.querySelectorAll("[data-gallery-item]"));
      const thumbnails = Array.from(gallery.querySelectorAll("[data-gallery-thumb]"));
      const previous = gallery.querySelector("[data-gallery-previous]");
      const next = gallery.querySelector("[data-gallery-next]");
      const open = gallery.querySelector("[data-gallery-open]");
      const dialog = gallery.querySelector("[data-gallery-lightbox]");
      const dialogImage = gallery.querySelector("[data-gallery-lightbox-image]");
      const dialogCaption = gallery.querySelector("[data-gallery-lightbox-caption]");
      const dialogPrevious = gallery.querySelector("[data-gallery-lightbox-previous]");
      const dialogNext = gallery.querySelector("[data-gallery-lightbox-next]");
      const dialogClose = gallery.querySelector("[data-gallery-lightbox-close]");
      if (!items.length) return;

      let activeIndex = Math.max(0, items.findIndex((item) => item.classList.contains("is-active")));
      let opener = null;

      function normalizeIndex(index) {
        return (index + items.length) % items.length;
      }

      function render(index, focusThumbnail) {
        activeIndex = normalizeIndex(index);
        items.forEach((item, itemIndex) => {
          const active = itemIndex === activeIndex;
          item.hidden = !active;
          item.classList.toggle("is-active", active);
        });
        thumbnails.forEach((thumbnail, thumbnailIndex) => {
          const active = thumbnailIndex === activeIndex;
          thumbnail.classList.toggle("is-active", active);
          thumbnail.setAttribute("aria-selected", active ? "true" : "false");
          thumbnail.tabIndex = active ? 0 : -1;
          if (active && focusThumbnail) thumbnail.focus();
        });

        const activeItem = items[activeIndex];
        const image = activeItem.querySelector("img");
        const caption = activeItem.querySelector("figcaption");
        if (dialogImage && image) {
          dialogImage.src = image.currentSrc || image.src;
          dialogImage.alt = image.alt;
        }
        if (dialogCaption) dialogCaption.textContent = caption ? caption.innerText.trim() : "";
      }

      function openDialog(triggerEl) {
        if (!dialog) return;
        opener = triggerEl || open;
        if (typeof dialog.showModal === "function") {
          if (!dialog.open) dialog.showModal();
        } else {
          dialog.setAttribute("open", "");
        }
        const focusTarget = dialog.querySelector("[data-gallery-lightbox-close]");
        if (focusTarget) focusTarget.focus();
      }

      function closeDialog() {
        if (!dialog) return;
        if (typeof dialog.close === "function" && dialog.open) {
          dialog.close();
        } else {
          dialog.removeAttribute("open");
        }
        if (opener && typeof opener.focus === "function") {
          opener.focus();
        }
      }

      function step(direction, focusThumbnail) {
        render(activeIndex + direction, focusThumbnail);
      }

      if (previous) previous.addEventListener("click", () => step(-1, false));
      if (next) next.addEventListener("click", () => step(1, false));
      thumbnails.forEach((thumbnail, index) => {
        thumbnail.addEventListener("click", () => render(index, true));
        thumbnail.addEventListener("keydown", (event) => {
          if (event.key === "ArrowRight") {
            event.preventDefault();
            render(index + 1, true);
          } else if (event.key === "ArrowLeft") {
            event.preventDefault();
            render(index - 1, true);
          } else if (event.key === "Home") {
            event.preventDefault();
            render(0, true);
          } else if (event.key === "End") {
            event.preventDefault();
            render(items.length - 1, true);
          }
        });
      });

      if (open) {
        open.addEventListener("click", (event) => {
          render(activeIndex, false);
          openDialog(event.currentTarget);
        });
      }
      if (dialogPrevious) dialogPrevious.addEventListener("click", () => step(-1, false));
      if (dialogNext) dialogNext.addEventListener("click", () => step(1, false));
      if (dialogClose) dialogClose.addEventListener("click", closeDialog);

      if (dialog) {
        dialog.addEventListener("click", (event) => {
          if (event.target === dialog) closeDialog();
        });
        dialog.addEventListener("keydown", (event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            closeDialog();
          } else if (event.key === "ArrowLeft") {
            event.preventDefault();
            step(-1, false);
          } else if (event.key === "ArrowRight") {
            event.preventDefault();
            step(1, false);
          } else if (event.key === "Tab") {
            const focusables = Array.from(
              dialog.querySelectorAll('button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')
            );
            if (!focusables.length) return;
            const first = focusables[0];
            const last = focusables[focusables.length - 1];
            if (event.shiftKey && document.activeElement === first) {
              event.preventDefault();
              last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
              event.preventDefault();
              first.focus();
            }
          }
        });
        dialog.addEventListener("close", () => {
          if (opener && typeof opener.focus === "function") opener.focus();
        });
      }

      // External triggers (e.g. Textiles slide detail trigger)
      document.querySelectorAll("[data-open-gallery-item]").forEach((btn) => {
        const itemNumber = parseInt(btn.dataset.openGalleryItem, 10);
        if (!isNaN(itemNumber)) {
          const targetIndex = itemNumber - 1;
          const handler = (e) => {
            e.preventDefault();
            render(targetIndex, false);
            openDialog(btn);
          };
          btn.addEventListener("click", handler);
          if (btn.getAttribute("role") === "button") {
            btn.addEventListener("keydown", (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                handler(e);
              }
            });
          }
        }
      });

      render(activeIndex, false);
    });
  }

  function initEditorialChapterSystem(rail) {
    const track = rail.querySelector("[data-story-track]");
    const prevBtn = rail.querySelector("[data-story-prev]");
    const nextBtn = rail.querySelector("[data-story-next]");
    const currentIndicator = rail.querySelector("[data-story-current]");
    const hint = rail.querySelector("[data-story-hint]");
    const liveRegion = rail.querySelector("[data-story-live]");
    const dots = Array.from(rail.querySelectorAll("[data-story-dots] .story-rail__dot"));
    const slides = Array.from(rail.querySelectorAll("[data-story-slide]"));
    if (!track || !slides.length) return;

    const experience = rail.closest("#interactive-experience");
    const nav = experience?.querySelector("[data-sticky-nav]");
    const navLinks = nav ? Array.from(nav.querySelectorAll("[data-nav-link]")) : [];
    const progressBar = experience?.querySelector("[data-reading-progress-bar]");
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const hintStorageKey = "editorialChapterHintSeen";
    let currentActiveIndex = Math.max(0, slides.findIndex((slide) => !slide.hidden));
    let transitionTimer = null;
    let suppressTrackClick = false;

    const isProtectedTarget = (target) =>
      target instanceof Element &&
      Boolean(
        target.closest(
          "a, button, input, select, textarea, label, form, figcaption, figure, picture, img, [role='button'], [role='dialog'], [contenteditable='true'], .image-credit, .story-slide__media, .contemporary-practices, .story-slide__actions, .gallery, .gallery__controls, [data-gallery], [data-open-gallery-item], dialog"
        )
      );

    const isTextSelectionTarget = (target) =>
      target instanceof Element &&
      Boolean(target.closest("p, h1, h2, h3, h4, li, blockquote, pre, code, [contenteditable='true']"));

    const scrollActiveNavIntoView = (activeSlide) => {
      if (!nav) return;
      const activeLink = navLinks.find((link) => `section-${link.dataset.navLink}` === activeSlide.id);
      if (!activeLink) return;
      const desiredLeft = activeLink.offsetLeft - (nav.clientWidth - activeLink.offsetWidth) / 2;
      const maxLeft = Math.max(0, nav.scrollWidth - nav.clientWidth);
      nav.scrollTo({
        left: Math.min(maxLeft, Math.max(0, desiredLeft)),
        behavior: prefersReducedMotion ? "auto" : "smooth",
      });
    };

    const syncStoryState = (index, activeSlide) => {
      dots.forEach((dot, dotIndex) => {
        const isActive = dotIndex === index;
        dot.classList.toggle("is-active", isActive);
        dot.setAttribute("aria-current", isActive ? "true" : "false");
      });
      navLinks.forEach((link) => {
        const isActive = `section-${link.dataset.navLink}` === activeSlide.id;
        link.classList.toggle("is-active", isActive);
        link.toggleAttribute("aria-current", isActive);
      });
      scrollActiveNavIntoView(activeSlide);
      if (currentIndicator) currentIndicator.textContent = String(index + 1).padStart(2, "0");
      if (prevBtn) prevBtn.disabled = index === 0;
      if (nextBtn) nextBtn.disabled = index === slides.length - 1;
      rail.classList.toggle("has-previous-chapter", index > 0);
      rail.classList.toggle("has-next-chapter", index < slides.length - 1);
      if (progressBar) {
        const chapterProgress = ((index + 1) / slides.length) * 100;
        progressBar.dataset.chapterProgress = String(chapterProgress);
        progressBar.setAttribute("aria-valuenow", String(Math.round(chapterProgress)));
        progressBar.style.width = `${chapterProgress}%`;
      }
    };

    const concealHint = () => {
      if (!hint || hint.hidden) return;
      hint.hidden = true;
      try {
        window.sessionStorage.setItem(hintStorageKey, "true");
      } catch (_) {
        // Private browsing may deny storage; hiding for this page is sufficient.
      }
    };

    try {
      if (window.sessionStorage.getItem(hintStorageKey) === "true" && hint) hint.hidden = true;
    } catch (_) {
      // The hint remains available when storage is unavailable.
    }

    const keepStoryViewportSteady = (previousTop, previousScrollY) => {
      window.requestAnimationFrame(() => {
        const topDrift = track.getBoundingClientRect().top - previousTop;
        if (Math.abs(topDrift) > 1 || Math.abs(window.scrollY - previousScrollY) > 1) {
          // This is a corrective delta only; chapter navigation never scrolls to a section.
          window.scrollTo({ top: previousScrollY, behavior: "auto" });
        }
      });
    };

    function goToChapter(index, source) {
      if (index < 0 || index >= slides.length || index === currentActiveIndex) return false;
      const previousTop = track.getBoundingClientRect().top;
      const previousScrollY = window.scrollY;
      const previousIndex = currentActiveIndex;
      const previousSlide = slides[previousIndex];
      const activeSlide = slides[index];
      const direction = index > previousIndex ? "right" : "left";

      clearTimeout(transitionTimer);
      slides.forEach((slide) => {
        if (slide !== previousSlide && slide !== activeSlide) {
          slide.hidden = true;
          slide.inert = true;
          slide.classList.remove("is-active", "is-leaving", "is-leaving-left", "is-leaving-right", "slide-from-left", "slide-from-right");
          slide.setAttribute("aria-hidden", "true");
        }
      });

      currentActiveIndex = index;
      activeSlide.hidden = false;
      activeSlide.inert = false;
      activeSlide.classList.remove("is-leaving", "is-leaving-left", "is-leaving-right", "slide-from-left", "slide-from-right");
      activeSlide.classList.add("is-active", direction === "right" ? "slide-from-right" : "slide-from-left");
      activeSlide.setAttribute("aria-hidden", "false");

      previousSlide.hidden = false;
      previousSlide.inert = true;
      previousSlide.classList.remove("is-active", "slide-from-left", "slide-from-right");
      previousSlide.classList.add("is-leaving", direction === "right" ? "is-leaving-right" : "is-leaving-left");
      previousSlide.setAttribute("aria-hidden", "true");

      syncStoryState(index, activeSlide);
      concealHint();
      const chapterTitle = activeSlide.querySelector("h2")?.textContent?.trim();
      if (liveRegion) liveRegion.textContent = `Chapter ${index + 1} of ${slides.length}: ${chapterTitle || rail.dataset.storyCategory || "Story"}`;
      rail.dispatchEvent(new CustomEvent("story:change", { bubbles: true, detail: { index, slide: activeSlide, source } }));
      keepStoryViewportSteady(previousTop, previousScrollY);

      transitionTimer = window.setTimeout(() => {
        previousSlide.hidden = true;
        previousSlide.classList.remove("is-leaving", "is-leaving-left", "is-leaving-right");
      }, prefersReducedMotion ? 0 : 340);
      return true;
    }

    if (prevBtn) prevBtn.addEventListener("click", () => goToChapter(currentActiveIndex - 1, "previous"));
    if (nextBtn) nextBtn.addEventListener("click", () => goToChapter(currentActiveIndex + 1, "next"));
    dots.forEach((dot, index) => dot.addEventListener("click", () => goToChapter(index, "dot")));
    rail.addEventListener("story:select", (event) => goToChapter(Number(event.detail?.index), "programmatic"));

    navLinks.forEach((link) => {
      link.addEventListener("click", (event) => {
        const targetIndex = slides.findIndex((slide) => slide.id === `section-${link.dataset.navLink}`);
        if (targetIndex < 0) return;
        event.preventDefault();
        goToChapter(targetIndex, "sticky-navigation");
      });
    });

    function handleKeyNavigation(event) {
      if (isProtectedTarget(event.target) || document.activeElement?.isContentEditable || document.querySelector("dialog[open]")) return;
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        goToChapter(currentActiveIndex - 1, "keyboard");
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        goToChapter(currentActiveIndex + 1, "keyboard");
      } else if (event.key === "Home") {
        event.preventDefault();
        goToChapter(0, "keyboard");
      } else if (event.key === "End") {
        event.preventDefault();
        goToChapter(slides.length - 1, "keyboard");
      }
    }

    window.addEventListener("keydown", (event) => {
      const rect = rail.getBoundingClientRect();
      if (rect.top < window.innerHeight && rect.bottom > 0) handleKeyNavigation(event);
    });

    // Scoped two-finger trackpad handling: vertical and diagonal scrolling remain native.
    let accumulatedDeltaX = 0;
    let trackpadCooldown = false;
    let trackpadTimer = null;
    let horizontalIntentTimer = null;
    track.addEventListener("wheel", (event) => {
      const absX = Math.abs(event.deltaX);
      const absY = Math.abs(event.deltaY);
      if (absX === 0 || absX <= absY * 1.4) {
        accumulatedDeltaX = 0;
        return;
      }
      if (trackpadCooldown) return;
      accumulatedDeltaX += event.deltaX;
      clearTimeout(horizontalIntentTimer);
      horizontalIntentTimer = window.setTimeout(() => { accumulatedDeltaX = 0; }, 180);
      if (Math.abs(accumulatedDeltaX) < 70) return;
      const moved = goToChapter(currentActiveIndex + (accumulatedDeltaX > 0 ? 1 : -1), "trackpad");
      accumulatedDeltaX = 0;
      if (moved) {
        trackpadCooldown = true;
        clearTimeout(trackpadTimer);
        trackpadTimer = window.setTimeout(() => {
          trackpadCooldown = false;
          accumulatedDeltaX = 0;
        }, 650);
      }
    }, { passive: true });

    track.addEventListener("pointermove", (event) => {
      if (event.pointerType === "touch" || isProtectedTarget(event.target) || isTextSelectionTarget(event.target)) {
        track.classList.remove("is-edge-hover-left", "is-edge-hover-right");
        return;
      }
      const rect = track.getBoundingClientRect();
      const edgeZone = Math.max(50, rect.width * 0.14);
      const x = event.clientX - rect.left;
      track.classList.toggle("is-edge-hover-left", x <= edgeZone && currentActiveIndex > 0);
      track.classList.toggle("is-edge-hover-right", x >= rect.width - edgeZone && currentActiveIndex < slides.length - 1);
    });
    track.addEventListener("pointerleave", () => track.classList.remove("is-edge-hover-left", "is-edge-hover-right"));

    track.addEventListener("click", (event) => {
      if (suppressTrackClick || isProtectedTarget(event.target) || isTextSelectionTarget(event.target)) return;
      const selection = window.getSelection();
      if (selection?.toString().trim()) return;
      const rect = track.getBoundingClientRect();
      const edgeZone = Math.max(50, rect.width * 0.14);
      const clickX = event.clientX - rect.left;
      if (clickX <= edgeZone) goToChapter(currentActiveIndex - 1, "edge-click");
      else if (clickX >= rect.width - edgeZone) goToChapter(currentActiveIndex + 1, "edge-click");
    });

    let touchPointer = null;
    track.addEventListener("pointerdown", (event) => {
      if (event.pointerType !== "touch" || !event.isPrimary || isProtectedTarget(event.target)) return;
      touchPointer = { id: event.pointerId, x: event.clientX, y: event.clientY };
    }, { passive: true });
    track.addEventListener("pointerup", (event) => {
      if (!touchPointer || event.pointerId !== touchPointer.id) return;
      const diffX = event.clientX - touchPointer.x;
      const diffY = event.clientY - touchPointer.y;
      touchPointer = null;
      if (Math.abs(diffX) < 48 || Math.abs(diffX) <= Math.abs(diffY) * 1.3) return;
      suppressTrackClick = true;
      goToChapter(currentActiveIndex + (diffX < 0 ? 1 : -1), "touch-swipe");
      window.setTimeout(() => { suppressTrackClick = false; }, 350);
    }, { passive: true });
    track.addEventListener("pointercancel", () => { touchPointer = null; }, { passive: true });

    syncStoryState(currentActiveIndex, slides[currentActiveIndex]);
  }

  function initEditorialChapterSystems() {
    document.querySelectorAll("[data-story-rail]").forEach(initEditorialChapterSystem);
  }

  function initReadingProgress() {
    const bar = document.querySelector("[data-reading-progress-bar]");
    const experience = document.getElementById("interactive-experience");
    if (!bar || !experience) return;

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reducedMotion) return;

    const updateProgress = () => {
      const rect = experience.getBoundingClientRect();
      const scrollHeight = rect.height - window.innerHeight;
      if (scrollHeight <= 0) return;
      let progress = 0;
      if (rect.top <= 0) {
        progress = Math.min(100, (Math.abs(rect.top) / scrollHeight) * 100);
      }
      bar.style.width = `${progress}%`;
    };

    window.addEventListener("scroll", updateProgress, { passive: true });
    updateProgress();
  }

  function initHeroInteractions() {
    const exploreButtons = Array.from(document.querySelectorAll("[data-hero-explore]"));
    if (!exploreButtons.length) return;

    const stopAnimation = () => {
      exploreButtons.forEach((button) => button.classList.add("has-interacted"));
    };

    exploreButtons.forEach((exploreBtn) => {
      exploreBtn.addEventListener("mouseenter", stopAnimation, { once: true });
      exploreBtn.addEventListener("focus", stopAnimation, { once: true });
      exploreBtn.addEventListener("click", (event) => {
        stopAnimation();
        const target = document.getElementById("interactive-experience");
        if (target) {
          event.preventDefault();
          target.scrollIntoView({
            behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
            block: "start",
          });
        }
      });
    });

    window.addEventListener("scroll", stopAnimation, { passive: true, once: true });
  }

  function initBackToTop() {
    const btn = document.querySelector("[data-back-to-top]");
    if (!btn) return;

    let ticking = false;
    const onScroll = () => {
      if (!ticking) {
        window.requestAnimationFrame(() => {
          const totalHeight = document.documentElement.scrollHeight - window.innerHeight;
          const scrollProgress = totalHeight > 0 ? window.scrollY / totalHeight : 0;
          const isVisible = scrollProgress > 0.35;
          btn.hidden = !isVisible;
          btn.classList.toggle("is-visible", isVisible);
          ticking = false;
        });
        ticking = true;
      }
    };
  }

  function initBackToTop() {
    const btn = document.querySelector("[data-back-to-top]");
    if (!btn) return;

    let ticking = false;
    const onScroll = () => {
      if (!ticking) {
        window.requestAnimationFrame(() => {
          const totalHeight = document.documentElement.scrollHeight - window.innerHeight;
          const scrollProgress = totalHeight > 0 ? window.scrollY / totalHeight : 0;
          const isVisible = scrollProgress > 0.35;
          btn.hidden = !isVisible;
          btn.classList.toggle("is-visible", isVisible);
          ticking = false;
        });
        ticking = true;
      }
    };

    window.addEventListener("scroll", onScroll, { passive: true });
    btn.addEventListener("click", () => {
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
    onScroll();
  }

  function initActiveJobNotification() {
    const banner = document.querySelector(".active-job-banner");
    if (!banner) return;
    const dismissBtn = banner.querySelector(".active-job-banner__dismiss");
    if (dismissBtn) {
      dismissBtn.addEventListener("click", () => {
        banner.style.transition = "opacity 200ms ease, transform 200ms ease";
        banner.style.opacity = "0";
        banner.style.transform = "translateY(16px)";
        setTimeout(() => banner.remove(), 210);
      });
    }
  }

  function initDashboardFilters() {
    const tabs = document.querySelectorAll("[data-dashboard-filter]");
    if (!tabs.length) return;

    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        tabs.forEach((t) => {
          t.classList.remove("is-active");
          t.setAttribute("aria-selected", "false");
        });
        tab.classList.add("is-active");
        tab.setAttribute("aria-selected", "true");

        const filter = tab.dataset.dashboardFilter;
        const cards = document.querySelectorAll(".dashboard-recent [data-document-card]");
        cards.forEach((card) => {
          const status = card.dataset.status;
          const matches = filter === "all" || status === filter;
          card.style.display = matches ? "" : "none";
        });

        const dateGroups = document.querySelectorAll(".dashboard-date-group");
        dateGroups.forEach((group) => {
          const visibleCards = group.querySelectorAll('[data-document-card]:not([style*="display: none"])');
          group.style.display = visibleCards.length > 0 ? "" : "none";
        });
      });
    });
  }

  function initNatureSoundscape() {
    const toggleBtn = document.getElementById("ambient-soundscape-toggle");
    if (!toggleBtn) return;

    let audioCtx = null;
    let isPlaying = false;
    let windNode = null;
    let masterGain = null;
    let birdInterval = null;

    function createWindSoundscape(ctx, destination) {
      const bufferSize = ctx.sampleRate * 4;
      const noiseBuffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
      const output = noiseBuffer.getChannelData(0);
      let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0;
      for (let i = 0; i < bufferSize; i++) {
        const white = Math.random() * 2 - 1;
        b0 = 0.99886 * b0 + white * 0.0555179;
        b1 = 0.99332 * b1 + white * 0.0750759;
        b2 = 0.96900 * b2 + white * 0.1538520;
        b3 = 0.86650 * b3 + white * 0.3104856;
        b4 = 0.55000 * b4 + white * 0.5329522;
        b5 = -0.7616 * b5 - white * 0.0168980;
        output[i] = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + white * 0.5362) * 0.04;
        b6 = white * 0.115926;
      }

      const whiteNoise = ctx.createBufferSource();
      whiteNoise.buffer = noiseBuffer;
      whiteNoise.loop = true;

      const filter = ctx.createBiquadFilter();
      filter.type = "bandpass";
      filter.frequency.value = 380;
      filter.Q.value = 1.6;

      const lfo = ctx.createOscillator();
      lfo.frequency.value = 0.12;
      const lfoGain = ctx.createGain();
      lfoGain.gain.value = 140;
      lfo.connect(lfoGain);
      lfoGain.connect(filter.frequency);
      lfo.start();

      whiteNoise.connect(filter);
      filter.connect(destination);
      whiteNoise.start();

      return { whiteNoise, lfo };
    }

    function playBirdChirp(ctx, destination) {
      if (!isPlaying) return;
      try {
        const now = ctx.currentTime;
        const osc = ctx.createOscillator();
        const chirpGain = ctx.createGain();
        osc.type = "sine";

        const baseFreq = 2200 + Math.random() * 800;
        osc.frequency.setValueAtTime(baseFreq, now);
        osc.frequency.exponentialRampToValueAtTime(baseFreq + 600, now + 0.08);
        osc.frequency.exponentialRampToValueAtTime(baseFreq - 200, now + 0.18);

        chirpGain.gain.setValueAtTime(0.001, now);
        chirpGain.gain.linearRampToValueAtTime(0.015, now + 0.04);
        chirpGain.gain.exponentialRampToValueAtTime(0.0001, now + 0.22);

        osc.connect(chirpGain);
        chirpGain.connect(destination);
        osc.start(now);
        osc.stop(now + 0.25);
      } catch (_) {}
    }

    function startSoundscape() {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextClass) return;

      if (!audioCtx) {
        audioCtx = new AudioContextClass();
      }
      if (audioCtx.state === "suspended") {
        audioCtx.resume();
      }

      masterGain = audioCtx.createGain();
      masterGain.gain.setValueAtTime(0.001, audioCtx.currentTime);
      masterGain.gain.linearRampToValueAtTime(0.25, audioCtx.currentTime + 1.2);
      masterGain.connect(audioCtx.destination);

      windNode = createWindSoundscape(audioCtx, masterGain);

      birdInterval = setInterval(() => {
        if (Math.random() > 0.35) {
          playBirdChirp(audioCtx, masterGain);
        }
      }, 3400);

      isPlaying = true;
      toggleBtn.classList.add("is-active");
      toggleBtn.setAttribute("aria-pressed", "true");
      const label = toggleBtn.querySelector(".nature-ambient-label");
      if (label) label.textContent = "Playing Atmosphere";
    }

    function stopSoundscape() {
      if (!audioCtx || !isPlaying) return;

      if (masterGain) {
        masterGain.gain.linearRampToValueAtTime(0.001, audioCtx.currentTime + 0.8);
        setTimeout(() => {
          if (windNode) {
            try {
              windNode.whiteNoise.stop();
              windNode.lfo.stop();
            } catch (_) {}
          }
          if (audioCtx && audioCtx.state !== "closed") {
            audioCtx.suspend();
          }
        }, 850);
      }

      if (birdInterval) {
        clearInterval(birdInterval);
        birdInterval = null;
      }

      isPlaying = false;
      toggleBtn.classList.remove("is-active");
      toggleBtn.setAttribute("aria-pressed", "false");
      const label = toggleBtn.querySelector(".nature-ambient-label");
      if (label) label.textContent = "Mountain Atmosphere";
    }

    toggleBtn.addEventListener("click", () => {
      if (!isPlaying) {
        startSoundscape();
      } else {
        stopSoundscape();
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    // Ensure any stale transition overlay is dismissed on initial page render
    const overlay = document.getElementById("page-transition-overlay");
    if (overlay) {
      overlay.classList.remove("is-visible");
      overlay.setAttribute("aria-hidden", "true");
    }

    initUpload();
    initStatusPage();
    initRenderedPreviewControls();
    initPreviewLinks();
    initPreviewBackNavigation();
    initMobileNav();
    initNavigationDropdowns();
    initRevealElements();
    initEditorialGalleries();
    initEditorialChapterSystems();
    initReadingProgress();
    initHeroInteractions();
    initBackToTop();
    initMessageDismiss();
    initToastAutoDismiss();
    initDocumentRemoveModal();
    initActiveJobNotification();
    initDashboardFilters();
    initNatureSoundscape();
  });
})();
