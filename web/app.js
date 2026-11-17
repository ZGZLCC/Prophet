(() => {
  "use strict";

  const app = window.ProphetApp;
  const {
    ROUTES,
    state,
    $,
    routeFromHash,
    getApi,
    setBridgeStatus,
    setHealthStatus,
    renderProfileRoute,
    renderExportRoute,
    renderAnalysisRoute,
    renderFortuneRoute,
    loadProfileRoute,
    loadFortuneRoute,
    selectPerson,
    openPersonForm,
    savePerson,
    deleteCurrentPerson,
    captureMaterialForm,
    validateMaterialForm,
    chooseMaterialFile,
    previewSelectedMaterial,
    cancelActiveTask,
    deletePrediction,
    rebuildProfile,
    restoreProfile,
    chooseExportDir,
    exportPerson,
    chooseDatabaseFile,
    importDatabase,
    toggleProfileEvidence,
    startMaterialAnalysis,
    startPrediction,
    startPredictionReview,
    captureChatExportForm,
    captureChatAnalysisForm,
    validateChatExportField,
    startChatExport,
    cancelChatTask,
    chooseChatAnalysisFile,
    chooseChatAnalysisDir,
    scheduleChatAnalysisPreview,
    scheduleChatAnalysisValidation,
    resetChatAnalysisValidation,
    updateChatAnalysisAvailability,
    updateChatValidation,
    selectFortuneEngine,
    setFortuneMode,
    captureFortuneForm,
    validateFortuneNumberField,
    validateFortuneTimeField,
    resetFortuneCurrent,
    resetFortuneForm,
    selectedFortuneHistory,
    selectFortuneHistory,
    useFortuneReading,
    deleteFortuneHistory,
    interpretFortune,
    toggleFortunePrompt,
    toggleFortuneInterpretation,
    useFortuneForClaim,
    exportFortuneReport,
    chooseFortuneReportDir,
    openFortuneProfileForm,
    deleteFortuneProfile,
    chooseFortuneBackupDir,
    backupFortuneDatabase,
    verifyFortuneDatabase,
    chooseFortuneImportFile,
    importFortuneDatabase,
    startFortune,
    startFortuneClaim,
    saveFortuneOutcome,
    saveFortuneProfile,
    searchFortuneKnowledge,
    openSettings,
    closeSettings,
    resolveConfirmation,
    chooseDirectory,
    saveAppearanceSettings,
    saveModelSettings,
    savePathSettings,
    copyText,
    connectBridge,
    clearFieldError,
    validateRequiredField,
  } = app;

let animatedRoute = null;

function scrollPageToTop(behavior = "auto") {
  $("#page-view")?.scrollTo({ top: 0, behavior });
  window.scrollTo({ top: 0, behavior });
}

function setHeroText(kicker, description) {
  const hero = $("#page-view .page-intro");
  const eyebrow = $(".eyebrow", hero);
  const copy = $("p", hero);
  if (eyebrow) eyebrow.textContent = kicker;
  if (copy && description) copy.textContent = description;
  if (hero && animatedRoute !== state.route) {
    hero.classList.add("is-entering");
    animatedRoute = state.route;
  }
}

function render() {
  $("#topbar-page-title").textContent = ROUTES[state.route].title;
  document.querySelectorAll(".nav-item[data-route]").forEach((button) => {
    const active = button.dataset.route === state.route;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-current", active ? "page" : "false");
  });
  if (state.route === "profile") {
    renderProfileRoute();
    setHeroText("PERSONAL PROFILE");
  }
  else if (state.route === "export") {
    $("#page-view").innerHTML = renderExportRoute();
    setHeroText("CHAT EXPORT", "读取本机 QQ 或微信的文字消息，按会话和日期筛选后保存到你指定的位置。");
  }
  else if (state.route === "analysis") {
    $("#page-view").innerHTML = renderAnalysisRoute();
    setHeroText("CHAT ANALYSIS", "先按时期和片段处理，完整聊天不会一次性塞给AI，再做有证据边界的概括。");
  }
  else if (state.route === "fortune") {
    renderFortuneRoute();
    setHeroText("FORTUNE TELLING");
  }
}


function handleClick(event) {
  const routeButton = event.target.closest("[data-route]");
  if (routeButton) {
    const nextRoute = routeButton.dataset.route;
    if (nextRoute !== state.route) window.location.hash = nextRoute;
    return;
  }
  if (event.target.closest("[data-back-to-top]")) return scrollPageToTop("smooth");
  if (event.target.closest("[data-open-settings]")) {
    openSettings();
    return;
  }
  if (event.target.closest("[data-close-settings]")) {
    closeSettings();
    return;
  }
  if (event.target.closest("#settings-close")) {
    closeSettings();
    return;
  }
  const sourceOption = event.target.closest("[data-export-source]");
  if (state.route === "export" && sourceOption) {
    captureChatExportForm();
    state.chatExport.source = sourceOption.dataset.exportSource;
    render();
    return;
  }
  const analysisMode = event.target.closest("[data-analysis-mode]");
  if (state.route === "analysis" && analysisMode) {
    captureChatAnalysisForm();
    state.chatAnalysis.mode = analysisMode.dataset.analysisMode;
    if (state.chatAnalysis.mode === "agent") state.chatAnalysis.prompt = "";
    if (state.chatAnalysis.mode === "manual") state.chatAnalysis.commands = "";
    render();
    scheduleChatAnalysisPreview();
    return;
  }
  const fortuneEngine = event.target.closest("[data-fortune-engine]");
  if (state.route === "fortune" && fortuneEngine) {
    selectFortuneEngine(fortuneEngine.dataset.fortuneEngine);
    return;
  }
  const fortuneMode = event.target.closest("[data-fortune-mode]");
  if (state.route === "fortune" && fortuneMode) {
    setFortuneMode(fortuneMode.dataset.fortuneMode);
    return;
  }
  const fortuneTab = event.target.closest("[data-fortune-tab]");
  if (state.route === "fortune" && fortuneTab) {
    captureFortuneForm();
    state.fortune.tab = fortuneTab.dataset.fortuneTab;
    render();
    return;
  }
  const action = event.target.closest("[data-action]")?.dataset.action;
  if (action === "cancel-confirm") return resolveConfirmation(false);
  if (action === "accept-confirm") return resolveConfirmation(true);
  if (state.route === "profile") {
    if (action === "select-person") selectPerson(event.target.closest("[data-person-id]").dataset.personId);
    if (action === "new-person") openPersonForm("new");
    if (action === "edit-person") openPersonForm("edit");
    if (action === "cancel-person") { state.profile.personForm = null; render(); }
    if (action === "delete-person") deleteCurrentPerson();
    if (action === "reload-profile") loadProfileRoute();
    if (action === "new-material") { state.profile.tab = "material"; render(); }
    if (action === "choose-material-file") chooseMaterialFile();
    if (action === "preview-material") { captureMaterialForm(); previewSelectedMaterial(); }
    if (action === "cancel-task") cancelActiveTask();
    if (action === "delete-prediction") deletePrediction(event.target.closest("[data-prediction-id]").dataset.predictionId);
    if (action === "rebuild-profile") rebuildProfile();
    if (action === "restore-profile") restoreProfile();
    if (action === "choose-export-dir") chooseExportDir();
    if (action === "export-person") exportPerson(event.target.closest("[data-export-format]").dataset.exportFormat);
    if (action === "choose-database-file") chooseDatabaseFile();
    if (action === "import-database") importDatabase();
    if (action === "toggle-profile-evidence") toggleProfileEvidence(event.target.closest("[data-evidence-key]").dataset.evidenceKey);
    if (event.target.closest("[data-profile-tab]")) {
      captureMaterialForm();
      state.profile.tab = event.target.closest("[data-profile-tab]").dataset.profileTab;
      render();
    }
  }
  if (state.route === "export") {
    if (action === "choose-chat-export-dir") chooseChatExportDir();
    if (action === "cancel-chat-export") cancelChatTask("export");
    if (action === "retry-chat-export") startChatExport();
  }
  if (state.route === "analysis") {
    if (action === "choose-chat-analysis-file") chooseChatAnalysisFile();
    if (action === "choose-chat-analysis-dir") chooseChatAnalysisDir();
    if (action === "copy-chat-prompt" && state.chatAnalysis.prompt) copyText(state.chatAnalysis.prompt);
    if (action === "copy-chat-commands" && state.chatAnalysis.commands) copyText(state.chatAnalysis.commands);
    if (action === "cancel-chat-analysis") cancelChatTask("analysis");
    if (action === "retry-chat-analysis") startChatAnalysis();
  }
  if (state.route === "fortune") {
    if (action === "reload-fortune") loadFortuneRoute();
    if (action === "clear-fortune-input") { resetFortuneForm(); render(); }
    if (action === "select-fortune-history") selectFortuneHistory(event.target.closest("[data-reading-id]").dataset.readingId);
    if (action === "view-fortune-history") useFortuneReading((state.fortune.history || []).find((item) => item.id === event.target.closest("[data-reading-id]")?.dataset.readingId));
    if (action === "replay-fortune-history") useFortuneReading(selectedFortuneHistory(), true);
    if (action === "delete-fortune-history") deleteFortuneHistory(event.target.closest("[data-reading-id]")?.dataset.readingId);
    if (action === "interpret-fortune") interpretFortune();
    if (action === "prompt-fortune") toggleFortunePrompt();
    if (action === "toggle-fortune-interpretation") toggleFortuneInterpretation();
    if (action === "copy-fortune-prompt" && state.fortune.prompt) copyText(state.fortune.prompt);
    if (action === "use-fortune-for-claim") useFortuneForClaim();
    if (action === "export-fortune-report") exportFortuneReport(event.target.closest("[data-reading-id]")?.dataset.readingId);
    if (action === "choose-fortune-report-dir") chooseFortuneReportDir();
    if (action === "new-fortune-profile") openFortuneProfileForm();
    if (action === "edit-fortune-profile") openFortuneProfileForm(event.target.closest("[data-profile-id]").dataset.profileId);
    if (action === "cancel-fortune-profile") { state.fortune.profileDraft = null; state.fortune.profileEditingId = null; render(); }
    if (action === "delete-fortune-profile") deleteFortuneProfile(event.target.closest("[data-profile-id]").dataset.profileId);
    if (action === "choose-fortune-backup-dir") chooseFortuneBackupDir();
    if (action === "backup-fortune-db") backupFortuneDatabase();
    if (action === "verify-fortune-db") verifyFortuneDatabase();
    if (action === "choose-fortune-import-file") chooseFortuneImportFile();
    if (action === "import-fortune-db") importFortuneDatabase();
  }
  const copyNode = event.target.closest("[data-copy-text]");
  if (copyNode) copyText(copyNode.dataset.copyText);
  if (event.target.closest("#choose-output-dir")) chooseDirectory("#setting-output-dir");
  if (event.target.closest("#choose-database-dir")) chooseDirectory("#setting-database-dir");
}

function handleInput(event) {
  clearFieldError(event.target);
  const formError = event.target.closest?.("form")?.querySelector(".form-message.is-error");
  if (formError) formError.hidden = true;
  if (event.target.id === "material-file-path") {
    state.profile.material.filePath = event.target.value;
    const importButton = $("#material-file-import");
    if (importButton) importButton.disabled = !event.target.value.trim();
  }
  if (event.target.closest?.("#material-form")) state.profile.material.error = "";
  if (event.target.closest?.("#chat-export-form")) state.chatExport.error = "";
  if (event.target.id === "material-content" || event.target.id === "material-occurred-at") validateMaterialForm();
  if (event.target.id === "prediction-event") {
    state.profile.predictionEvent = event.target.value;
    const submit = $("#prediction-submit");
    if (submit) submit.disabled = Boolean(state.profile.activeTask) || !state.settings?.llm_configured || !event.target.value.trim();
  }
  if (event.target.id === "person-search") {
    const cursor = event.target.selectionStart;
    state.profile.search = event.target.value;
    render();
    const input = $("#person-search");
    input?.focus();
    if (input && cursor !== null) input.setSelectionRange(cursor, cursor);
  }
  if (event.target.id === "database-import-path") {
    state.profile.importPath = event.target.value;
    const importButton = $("#database-import-submit");
    if (importButton) importButton.disabled = !event.target.value.trim();
  }
  const exportState = state.chatExport;
  if (event.target.id === "chat-export-chats") exportState.chats = event.target.value;
  if (event.target.id === "chat-export-start") exportState.start = event.target.value;
  if (event.target.id === "chat-export-end") exportState.end = event.target.value;
  if (event.target.id === "chat-export-output-dir") exportState.outputDir = event.target.value;
  if (event.target.id === "chat-export-db-root") exportState.dbRoot = event.target.value;
  if (event.target.id === "chat-export-account") exportState.account = event.target.value;
  if (event.target.id === "chat-export-qq-pid") exportState.qqPid = event.target.value;
  const analysisState = state.chatAnalysis;
  if (event.target.id === "chat-analysis-input") analysisState.inputPath = event.target.value;
  if (event.target.id === "chat-analysis-target") analysisState.target = event.target.value;
  if (event.target.id === "chat-analysis-focus") analysisState.focus = event.target.value;
  if (event.target.id === "chat-analysis-output-dir") analysisState.outputDir = event.target.value;
  if (["chat-analysis-input", "chat-analysis-target", "chat-analysis-focus", "chat-analysis-output-dir"].includes(event.target.id)) {
    analysisState.error = "";
    scheduleChatAnalysisPreview();
    updateChatAnalysisAvailability();
  }
  if (event.target.id === "chat-analysis-input") {
    resetChatAnalysisValidation();
    analysisState.targetChecked = false;
  }
  if (event.target.id === "chat-analysis-target") {
    analysisState.targetChecked = false;
    updateChatValidation();
  }
  if (["chat-export-start", "chat-export-end"].includes(event.target.id)) {
    clearFieldError($(event.target.id === "chat-export-start" ? "#chat-export-end" : "#chat-export-start"));
  }
  const fortuneState = state.fortune;
  if (event.target.id === "fortune-question") fortuneState.question = event.target.value;
  if (event.target.id === "fortune-cast-at") fortuneState.values.castAt = event.target.value;
  if (event.target.id === "fortune-birth-at") fortuneState.values.birthAt = event.target.value;
  if (event.target.id === "fortune-profile-id") fortuneState.values.profileId = event.target.value;
  if (event.target.id === "fortune-upper") fortuneState.values.upper = event.target.value;
  if (event.target.id === "fortune-lower") fortuneState.values.lower = event.target.value;
  if (event.target.id === "fortune-moving") fortuneState.values.moving = event.target.value;
  if (event.target.id === "fortune-flow-count") fortuneState.values.flowYearCount = event.target.value;
  if (event.target.id === "fortune-flow-start") fortuneState.values.flowYearStart = event.target.value;
  if (event.target.id === "fortune-profile-name") fortuneState.profileDraft && (fortuneState.profileDraft.display_name = event.target.value);
  if (event.target.id === "fortune-profile-birth") fortuneState.profileDraft && (fortuneState.profileDraft.birth_at = event.target.value);
  if (event.target.id.startsWith("fortune-")) {
    fortuneState.error = "";
    $("#fortune-route-error")?.remove();
  }
  if (event.target.id === "fortune-report-dir") {
    fortuneState.reportDir = event.target.value;
    const exportButton = $("[data-action='export-fortune-report'][data-reading-id]");
    if (exportButton) exportButton.disabled = !event.target.value.trim();
  }
  if (event.target.id === "fortune-backup-dir") {
    fortuneState.dataBackupDir = event.target.value;
    $("#fortune-backup-submit").disabled = !event.target.value.trim();
  }
  if (event.target.id === "fortune-import-path") {
    fortuneState.dataImportPath = event.target.value;
    $("#fortune-import-submit").disabled = !event.target.value.trim();
  }
}

function handleChange(event) {
  if (event.target.id === "person-select") selectPerson(event.target.value);
  if (event.target.id === "prediction-version") state.profile.predictionVersion = Number(event.target.value);
  if (event.target.id === "material-encoding") {
    state.profile.material.encoding = event.target.value;
    if (state.profile.material.encodingRequired) previewSelectedMaterial();
  }
  if (event.target.id === "chat-export-range") {
    captureChatExportForm();
    state.chatExport.range = event.target.value;
    render();
  }
  if (event.target.id === "chat-export-format") state.chatExport.format = event.target.value;
  if (event.target.id === "chat-export-recover") state.chatExport.recover = event.target.checked;
  if (event.target.id === "fortune-profile-mode") { captureFortuneForm(); state.fortune.values.profileMode = event.target.value; render(); }
  if (event.target.id === "fortune-gender") state.fortune.values.gender = event.target.value;
  if (event.target.id === "fortune-profile-id") state.fortune.values.profileId = event.target.value;
  if (event.target.id === "fortune-luck-direction") state.fortune.values.luckDirection = event.target.value;
  if (event.target.id === "fortune-use-god") state.fortune.values.useGodLine = event.target.value;
  if (event.target.id === "fortune-category") state.fortune.category = event.target.value;
  if (event.target.id === "fortune-policy") state.fortune.policy = event.target.value;
  if (event.target.id === "fortune-profile-gender" && state.fortune.profileDraft) state.fortune.profileDraft.gender = event.target.value;
  if (event.target.id === "fortune-profile-policy" && state.fortune.profileDraft) state.fortune.profileDraft.time_policy_id = event.target.value;
  if (event.target.id === "fortune-import-confirm") state.fortune.dataImportConfirmed = event.target.checked;
  if (event.target.id === "fortune-claim-reading") state.fortune.readingId = event.target.value;
  if (event.target.id === "fortune-knowledge-engine") state.fortune.knowledgeEngine = event.target.value;
}

function handleKeydown(event) {
  const confirmation = $("#confirm-modal");
  const activeDialog = confirmation && !confirmation.hidden ? confirmation.querySelector(".settings-dialog") : state.settingsOpen ? $("#settings-modal .settings-dialog") : null;
  if (!activeDialog) return;
  if (event.key === "Escape") {
    if (confirmation && !confirmation.hidden) resolveConfirmation(false);
    else closeSettings();
    return;
  }
  if (event.key !== "Tab") return;
  const focusable = [...activeDialog.querySelectorAll("button, input, select")].filter((node) => !node.disabled);
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function showFatal(error) {
  const node = $("#fatal-error");
  if (!node) return;
  node.textContent = `页面遇到未处理错误：${error?.message || "未知错误"}`;
  node.hidden = false;
}

function finishStartupSplash() {
  const splash = $("#startup-splash");
  if (!splash) {
    document.documentElement.classList.remove("is-starting");
    return;
  }
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const removeSplash = () => {
    splash.remove();
    document.documentElement.classList.remove("is-starting");
  };
  if (reduceMotion) {
    removeSplash();
    return;
  }
  splash.classList.add("is-playing");
  window.setTimeout(removeSplash, 2000);
}

function startStartupSplash() {
  window.requestAnimationFrame(() => window.requestAnimationFrame(finishStartupSplash));
}

function init() {
  render();
  document.addEventListener("click", handleClick);
  document.addEventListener("submit", (event) => {
    if (event.target.id === "appearance-settings-form") saveAppearanceSettings(event);
    if (event.target.id === "model-settings-form") saveModelSettings(event);
    if (event.target.id === "path-settings-form") savePathSettings(event);
    if (event.target.id === "person-form") savePerson(event);
    if (event.target.id === "material-form") startMaterialAnalysis(event);
    if (event.target.id === "prediction-form") startPrediction(event);
    if (event.target.dataset.form === "prediction-review") startPredictionReview(event);
    if (event.target.id === "chat-export-form") startChatExport(event);
    if (event.target.id === "chat-analysis-form" && state.chatAnalysis.mode === "one-click") startChatAnalysis(event);
    if (event.target.id === "fortune-form") startFortune(event);
    if (event.target.id === "fortune-claim-form") startFortuneClaim(event);
    if (event.target.dataset.form === "fortune-outcome") saveFortuneOutcome(event);
    if (event.target.id === "fortune-profile-form") saveFortuneProfile(event);
    if (event.target.id === "fortune-knowledge-form") searchFortuneKnowledge(event);
  });
  document.addEventListener("input", handleInput);
  document.addEventListener("focusout", (event) => {
    const target = event.target;
    if (target.id === "material-content" || target.id === "material-occurred-at") validateMaterialForm(target.id);
    else if (["chat-export-start", "chat-export-end", "chat-export-qq-pid"].includes(target.id)) validateChatExportField(target);
    else if (target.type === "number" && target.id.startsWith("fortune-")) validateFortuneNumberField(target);
    else if (target.type === "datetime-local" && target.id.startsWith("fortune-")) validateFortuneTimeField(target);
    else if (target.id === "chat-analysis-input") {
      if (validateRequiredField(target)) scheduleChatAnalysisValidation();
    } else if (target.id === "chat-analysis-target") {
      state.chatAnalysis.target = target.value;
      state.chatAnalysis.targetChecked = true;
      validateRequiredField(target);
      updateChatValidation();
    } else validateRequiredField(target);
  });
  document.addEventListener("change", handleChange);
  document.addEventListener("keydown", handleKeydown);
  window.addEventListener("hashchange", () => {
    state.route = routeFromHash();
    render();
    const pageView = $("#page-view");
    scrollPageToTop();
    window.requestAnimationFrame(() => scrollPageToTop());
    pageView?.focus({ preventScroll: true });
    if (state.route === "profile" && state.bridgeReady) loadProfileRoute();
    if (state.route === "fortune" && state.bridgeReady) loadFortuneRoute();
  });
  window.addEventListener("pywebviewready", connectBridge, { once: true });
  window.addEventListener("prophetwindowshown", startStartupSplash, { once: true });
  if (getApi()) connectBridge();
  window.setTimeout(() => {
    if (!state.bridgeReady) {
      setBridgeStatus("error", "浏览器预览模式");
      setHealthStatus("error", "等待本地桥接", "页面可预览，文件与设置需在 Prophet 窗口中操作");
    }
  }, 900);
  if (!window.pywebview) startStartupSplash();
}

window.addEventListener("error", (event) => showFatal(event.error || event));
window.addEventListener("unhandledrejection", (event) => showFatal(event.reason));
window.addEventListener("DOMContentLoaded", init, { once: true });

  app.render = render;
})();
