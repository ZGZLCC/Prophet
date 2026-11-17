(() => {
  "use strict";

  const app = window.ProphetApp;
  const {
    state,
    $,
    getApi,
    callApi,
    escapeHtml,
    setBridgeStatus,
    setHealthStatus,
    setModelStatus,
  } = app;
  const render = (...args) => app.render?.(...args);

function showToast(message) {
  const region = $("#toast-region");
  if (!region) return;
  window.clearTimeout(state.toastTimer);
  region.innerHTML = `<div class="toast">${escapeHtml(message)}</div>`;
  state.toastTimer = window.setTimeout(() => {
    region.innerHTML = "";
  }, 3600);
}

function showFormMessage(id, message) {
  const node = $(`#${id}`);
  if (!node) return;
  node.textContent = message || "";
  node.hidden = !message;
}

function fieldErrorNode(input) {
  if (!input?.id) return null;
  let node = $(`#${input.id}-error`);
  if (node) return node;
  node = document.createElement("small");
  node.id = `${input.id}-error`;
  node.className = "field-error";
  node.setAttribute("role", "alert");
  node.hidden = true;
  const anchor = input.closest(".input-with-action, .material-file-import") || input;
  anchor.insertAdjacentElement("afterend", node);
  input.setAttribute("aria-describedby", node.id);
  return node;
}

function setFieldError(input, message = "") {
  if (!input) return;
  input.setCustomValidity(message);
  const node = fieldErrorNode(input);
  if (!node) return;
  node.textContent = message;
  node.hidden = !message;
}

function clearFieldError(input) {
  if (!input?.matches?.("input, textarea, select")) return;
  if (input.matches('input[type="checkbox"], input[type="radio"], input[type="hidden"]')) return;
  setFieldError(input, "");
}

function validateRequiredField(input) {
  if (!input?.required || !input.matches("input, textarea, select")) return true;
  const value = typeof input.value === "string" ? input.value.trim() : input.value;
  const label = input.closest("label")?.querySelector(":scope > span")?.textContent
    ?.replace(/可选.*/, "").trim() || "此项";
  const message = value ? "" : `请填写${label}。`;
  setFieldError(input, message);
  return !message;
}

let confirmResolver = null;

function confirmAction(message, title = "确认") {
  const modal = $("#confirm-modal");
  $("#confirm-title").textContent = title;
  $("#confirm-message").textContent = message;
  modal.hidden = false;
  window.setTimeout(() => $("[data-action='cancel-confirm']", modal)?.focus(), 0);
  return new Promise((resolve) => { confirmResolver = resolve; });
}

function resolveConfirmation(accepted) {
  $("#confirm-modal").hidden = true;
  confirmResolver?.(accepted);
  confirmResolver = null;
}

function setFormBusy(form, busy) {
  form.querySelectorAll("input, select, button").forEach((control) => {
    control.disabled = busy;
  });
  const submit = form.querySelector('button[type="submit"]');
  if (submit) submit.textContent = busy ? "保存中…" : form.dataset.submitLabel;
}

const systemTheme = window.matchMedia("(prefers-color-scheme: dark)");
let savedTheme = ["system", "light", "dark"].includes(localStorage.getItem("prophet-theme"))
  ? localStorage.getItem("prophet-theme")
  : "system";

function applyTheme(choice) {
  document.documentElement.dataset.theme = choice === "system"
    ? (systemTheme.matches ? "dark" : "light")
    : choice;
  document.documentElement.style.colorScheme = document.documentElement.dataset.theme;
}

async function saveAppearanceSettings(event) {
  event.preventDefault();
  const form = event.target;
  const choice = $("#setting-theme").value;
  setFormBusy(form, true);
  try {
    state.settings = await callApi("save_appearance_settings", {
      theme: choice,
      timezone: $("#setting-timezone").value,
    });
    savedTheme = state.settings.theme;
    localStorage.setItem("prophet-theme", savedTheme);
    applyTheme(savedTheme);
    render();
    showToast("显示设置已保存。 ");
  } catch (error) {
    showToast(error.message);
  } finally {
    setFormBusy(form, false);
  }
}

systemTheme.addEventListener("change", () => {
  if ((localStorage.getItem("prophet-theme") || "system") === "system") applyTheme("system");
});

$("#setting-theme").value = savedTheme;
applyTheme(savedTheme);

function updateSettingsForm(settings) {
  if (!settings) return;
  $("#settings-description").textContent = `配置保存在${settings.env_path || ".env"}`;
  savedTheme = settings.theme || "system";
  localStorage.setItem("prophet-theme", savedTheme);
  applyTheme(savedTheme);
  $("#setting-theme").value = savedTheme;
  $("#setting-timezone").value = settings.timezone || "Asia/Shanghai";
  $("#setting-provider").value = settings.provider || "openai-responses";
  $("#setting-model").value = settings.model || "";
  $("#setting-base-url").value = settings.base_url || "";
  $("#setting-api-key").value = "";
  $("#setting-api-key").placeholder = settings.api_key_configured
    ? `已配置 ${settings.api_key_masked || "密钥"}，留空保持不变`
    : "尚未配置，保存前请输入 API Key";
  const keyState = $("#api-key-state");
  keyState.textContent = settings.api_key_configured ? (settings.api_key_masked || "已配置") : "未配置";
  keyState.classList.toggle("is-configured", Boolean(settings.api_key_configured));
  $("#setting-output-dir").value = settings.output_dir || "";
  $("#setting-database-dir").value = settings.database_dir || "";
  setModelStatus(settings);
}

async function refreshHealth() {
  try {
    const health = await callApi("health_check");
    if (health.status === "ok") {
      setHealthStatus("ok", "本地状态正常", health.database_summary || "本地数据可读");
    } else if (health.status === "warning") {
      setHealthStatus("loading", "本地状态待处理", health.database_summary || "部分数据尚未创建");
    } else {
      setHealthStatus("error", "本地状态异常", "请打开设置检查路径");
    }
  } catch (error) {
    setHealthStatus("error", "本地状态读取失败", error.message);
  }
}

function applyPlatformCapabilities(info) {
  app.setChatExportSupported?.(info.chat_export);
  if (info.chat_export) return;
  // 聊天导出依赖 Windows 客户端实现：隐藏入口，并把停留在这个路由的页面切回人物画像。
  document.querySelector('.nav-item[data-route="export"]')?.remove();
  if (state.route === "export") window.location.hash = "profile";
}

async function connectBridge() {
  if (state.bridgeReady || !getApi()) return;
  try {
    const info = await callApi("get_app_info");
    state.bridgeReady = true;
    applyPlatformCapabilities(info);
    setBridgeStatus("ok", info.local_only ? "本地桥接已连接" : "桥接已连接");
    setHealthStatus("loading", "正在读取本地状态", "检查两个本地数据库");
    const settingsTask = callApi("get_settings")
      .then((settings) => {
        state.settings = settings;
        updateSettingsForm(settings);
      })
      .catch((error) => {
        setHealthStatus("error", "设置读取失败", error.message);
      });
    await settingsTask;
    const healthTask = refreshHealth();
    const routeTask = state.route === "profile"
      ? app.loadProfileRoute()
      : state.route === "fortune"
        ? app.loadFortuneRoute()
        : Promise.resolve(render());
    await Promise.all([settingsTask, healthTask, routeTask]);
  } catch (error) {
    setBridgeStatus("error", "桥接连接失败");
    setHealthStatus("error", "本地状态不可用", error.message);
  }
}

async function openSettings() {
  state.settingsOpen = true;
  $("#settings-modal").hidden = false;
  showFormMessage("model-settings-error", "");
  showFormMessage("path-settings-error", "");
  const firstField = $("#setting-provider");
  window.setTimeout(() => firstField?.focus(), 0);
  if (!state.settings && getApi()) {
    try {
      state.settings = await callApi("get_settings");
      updateSettingsForm(state.settings);
    } catch (error) {
      showFormMessage("model-settings-error", error.message);
    }
  }
}

function closeSettings() {
  state.settingsOpen = false;
  $("#settings-modal").hidden = true;
  $("#top-settings")?.focus();
}

async function copyText(value) {
  if (!navigator.clipboard) {
    showToast("当前窗口不支持自动复制，请手动选择路径。 ");
    return;
  }
  try {
    await navigator.clipboard.writeText(value);
    showToast("已复制到剪贴板。");
  } catch (error) {
    showToast("复制失败，请手动复制。");
  }
}

async function chooseDirectory(targetId) {
  try {
    const current = $(targetId).value || "";
    const result = await callApi("choose_directory", current);
    if (!result.cancelled && result.paths?.[0]) $(targetId).value = result.paths[0];
  } catch (error) {
    showFormMessage("path-settings-error", error.message);
  }
}

async function saveModelSettings(event) {
  event.preventDefault();
  const form = event.target;
  showFormMessage("model-settings-error", "");
  setFormBusy(form, true);
  try {
    state.settings = await callApi("save_settings", {
      provider: $("#setting-provider").value,
      model: $("#setting-model").value,
      base_url: $("#setting-base-url").value,
      api_key: $("#setting-api-key").value,
    });
    updateSettingsForm(state.settings);
    render();
    showToast("模型设置已保存到本机。");
    await refreshHealth();
  } catch (error) {
    showFormMessage("model-settings-error", error.message);
  } finally {
    setFormBusy(form, false);
  }
}

async function savePathSettings(event) {
  event.preventDefault();
  const form = event.target;
  showFormMessage("path-settings-error", "");
  setFormBusy(form, true);
  try {
    state.settings = await callApi("save_path_settings", {
      output_dir: $("#setting-output-dir").value,
      database_dir: $("#setting-database-dir").value,
    });
    state.profile.exportDir = state.settings.output_dir || "";
    state.chatExport.outputDir = state.settings.output_dir || "";
    state.chatAnalysis.outputDir = state.settings.output_dir || "";
    state.fortune.reportDir = state.settings.output_dir || "";
    state.fortune.dataBackupDir = state.settings.output_dir || "";
    updateSettingsForm(state.settings);
    render();
    showToast("本地路径设置已保存。");
    await refreshHealth();
  } catch (error) {
    showFormMessage("path-settings-error", error.message);
  } finally {
    setFormBusy(form, false);
  }
}

  Object.assign(app, {
    showToast,
    showFormMessage,
    setFieldError,
    clearFieldError,
    validateRequiredField,
    confirmAction,
    resolveConfirmation,
    setFormBusy,
    saveAppearanceSettings,
    updateSettingsForm,
    refreshHealth,
    connectBridge,
    openSettings,
    closeSettings,
    copyText,
    chooseDirectory,
    saveModelSettings,
    savePathSettings,
  });
})();
