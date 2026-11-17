(() => {
  "use strict";

  const app = window.ProphetApp;
  const {
    state,
    $,
    ROUTES,
    escapeHtml,
    textHtml,
    cleanChatPath,
    dateTimeInputValue,
    callApi,
    taskBusy,
    taskLabel,
  } = app;
  const render = (...args) => app.render?.(...args);
  const showToast = (...args) => app.showToast?.(...args);

function renderChatTask(kind) {
  const record = kind === "export" ? state.chatExport : state.chatAnalysis;
  if (!record.taskId && !record.task) return "";
  const task = record.task || { status: "queued", task_id: record.taskId };
  const status = task.status || "queued";
  const statusClass = status === "succeeded" ? "is-done" : status === "failed" ? "is-error" : status === "cancelled" ? "is-cancelled" : "is-pending";
  const action = status === "failed"
    ? `<button class="button button-secondary button-small" type="button" data-action="retry-chat-${kind}">重新尝试</button>`
    : "";
  let detail = status === "queued" ? "任务将在本机后台启动。" : status === "running" ? (kind === "export" ? "正在读取本机客户端数据，原始数据库保持只读。" : "正在按片段 → 分期 → 跨期的顺序生成报告。") : "";
  if (status === "failed") detail = task.error?.message || "任务失败，请检查输入后重试。";
  if (status === "cancelled") detail = "已停止本次任务，没有把未完成结果当作成品。";
  if (status === "succeeded") {
    const result = task.result || {};
    const paths = kind === "export"
      ? [result.output]
      : [result.core_report, result.full_report];
    detail = `<div class="task-result"><strong>${kind === "export" ? "导出文件" : "报告文件"}</strong>${paths.filter(Boolean).map((path) => `<div class="result-path"><span>${kind === "export" ? "" : path === result.core_report ? "核心报告 · " : "完整报告 · "}</span><code>${escapeHtml(path)}</code><button class="text-button" type="button" data-copy-text="${escapeHtml(path)}">复制路径</button></div>`).join("")}</div>`;
  }
  const progress = taskBusy(task) ? `<div class="task-progress" role="progressbar" aria-label="任务进行中"><span></span></div>` : "";
  return `<section class="task-card surface-card ${statusClass}" aria-live="polite"><div class="task-head"><div><h3>${kind === "export" ? "导出任务" : "分析任务"}</h3></div><div class="task-head-right"><span class="status-badge ${statusClass}">${taskLabel(status)}</span><small>${escapeHtml(task.task_id || record.taskId)}</small></div></div>${progress}${status === "succeeded" ? detail : status === "failed" ? `<div class="task-error" role="alert">${textHtml(detail)}</div>` : `<p class="task-detail">${textHtml(detail)}</p>`}<div class="task-actions">${taskBusy(task) ? `<button class="button button-secondary button-small" type="button" data-action="cancel-chat-${kind}">取消任务</button>` : ""}${action}</div></section>`;
}

function renderExportRoute() {
  const exportState = state.chatExport;
  const outputDir = exportState.outputDir || state.settings?.output_dir || "";
  const busy = taskBusy(exportState.task);
  const today = dateTimeInputValue().slice(0, 10);
  const dateFields = exportState.range === "custom" ? `<div class="form-grid"><label class="field"><span>开始日期（含）</span><input id="chat-export-start" type="date" max="${today}" value="${escapeHtml(exportState.start)}" /><small id="chat-export-start-error" class="field-error" role="alert" hidden></small></label><label class="field"><span>结束日期（含当天）</span><input id="chat-export-end" type="date" max="${today}" value="${escapeHtml(exportState.end)}" /><small id="chat-export-end-error" class="field-error" role="alert" hidden></small></label></div>` : `<div class="inline-hint">不限定时间，保留来源中的全部文字消息。</div>`;
  const advanced = exportState.source === "wechat"
    ? `<label class="field field-wide"><span>微信账号目录名 <em>可选</em></span><input id="chat-export-account" type="text" value="${escapeHtml(exportState.account)}" placeholder="例如 wxid_xxx_abcd" /></label>`
    : `<label class="field"><span>QQ 数据库密钥 <em>可选</em></span><input id="chat-export-qq-key" type="password" autocomplete="off" placeholder="通常留空，由 Windows 登录进程读取" /></label><label class="field"><span>QQ.exe PID <em>可选</em></span><input id="chat-export-qq-pid" type="text" inputmode="numeric" value="${escapeHtml(exportState.qqPid)}" placeholder="仅同时运行多个 QQ 时填写" /><small id="chat-export-qq-pid-error" class="field-error" role="alert" hidden>QQ.exe PID 必须是正整数。</small></label><label class="check-line field-wide"><input id="chat-export-recover" type="checkbox" ${exportState.recover ? "checked" : ""} />恢复模式：跳过损坏页并尽量导出可读消息</label>`;
  return `<div class="page-intro"><div class="page-intro-copy"><div class="intro-mark">${ROUTES.export.icon}</div><div><span class="eyebrow">聊天导出 / CHAT EXPORT</span><h1>聊天导出</h1><p>读取本机 QQ 或微信的文字消息，按会话和日期筛选后保存到你指定的位置。</p></div></div><button class="button button-secondary" type="button" data-open-settings="true">设置</button></div><div class="stage3-layout"><section class="workflow-card surface-card"><div class="workflow-heading"><div><h2>导出设置</h2><p>原始客户端数据只读。</p></div></div><form id="chat-export-form"><div class="source-switch" role="tablist" aria-label="聊天来源"><button class="source-option ${exportState.source === "qq" ? "is-active" : ""}" type="button" data-export-source="qq" aria-pressed="${exportState.source === "qq"}"><strong>QQ</strong><span>NTQQ 本地文字消息</span></button><button class="source-option ${exportState.source === "wechat" ? "is-active" : ""}" type="button" data-export-source="wechat" aria-pressed="${exportState.source === "wechat"}"><strong>微信</strong><span>微信 4.x 解密数据库</span></button></div><label class="field field-wide"><span>会话对象 <em>可选</em></span><textarea id="chat-export-chats" placeholder="留空导出全部；多个联系人或群聊用逗号或换行分隔">${escapeHtml(exportState.chats)}</textarea><small>QQ 支持 QQ 号、UID 或聊天名称；微信支持会话名称、会话 ID 或 MD5。</small></label><div class="form-grid"><label class="field"><span>时间范围</span><select id="chat-export-range"><option value="all" ${exportState.range === "all" ? "selected" : ""}>所有时间</option><option value="custom" ${exportState.range === "custom" ? "selected" : ""}>指定日期范围</option></select></label><label class="field"><span>保存格式</span><select id="chat-export-format"><option value="json" ${exportState.format === "json" ? "selected" : ""}>JSON · 推荐</option><option value="txt" ${exportState.format === "txt" ? "selected" : ""}>TXT · 文本</option><option value="csv" ${exportState.format === "csv" ? "selected" : ""}>CSV · 表格</option></select></label></div>${dateFields}<label class="field field-wide"><span>保存位置</span><div class="input-with-action"><input id="chat-export-output-dir" type="text" value="${escapeHtml(outputDir)}" placeholder="选择导出文件夹" /><button class="button button-secondary button-input" type="button" data-action="choose-chat-export-dir">选择文件夹</button></div></label><details class="advanced-box"><summary>高级选项（通常无需修改）</summary><div class="form-grid"><label class="field field-wide"><span>数据目录或数据库路径 <em>可选</em></span><input id="chat-export-db-root" type="text" value="${escapeHtml(exportState.dbRoot)}" placeholder="留空使用 Windows 默认位置" /></label>${advanced}</div></details>${exportState.error ? `<div id="chat-export-error" class="form-message is-error" role="alert">${textHtml(exportState.error)}</div>` : ""}<div class="form-actions"><button class="button button-primary" type="submit" ${busy ? "disabled" : ""}>${busy ? "正在后台导出…" : "开始导出"}</button>${busy ? `<button class="button button-secondary" type="button" data-action="cancel-chat-export">取消任务</button>` : ""}</div></form></section><aside class="info-rail"><section class="surface-card rail-card"><h3>导出边界</h3><p>登录并保持 ${exportState.source === "qq" ? "QQ" : "微信"} 客户端运行。导出过程不上传聊天原文，也不会修改来源数据库。</p><div class="rail-flow"><span>选择来源</span><i>→</i><span>筛选消息</span><i>→</i><span>保存文件</span></div></section><section class="surface-card rail-card"><h3>格式怎么选</h3><p><strong>JSON</strong> 最适合交给聊天分析；TXT 便于快速阅读；CSV 适合表格查看。</p><div class="rail-note">仅 Windows 支持 QQ / 微信本地导出。</div></section></aside></div>${renderChatTask("export")}`;
}

function renderAnalysisRoute() {
  const analysisState = state.chatAnalysis;
  const outputDir = analysisState.outputDir || state.settings?.output_dir || "";
  const busy = taskBusy(analysisState.task);
  const ready = chatAnalysisReady(analysisState, outputDir);
  const modelConfigured = Boolean(state.settings?.llm_configured);
  const modelHint = analysisState.mode === "one-click" && !modelConfigured
    ? `<div class="notice notice-warning">请先在“设置”中配置模型，才能一键执行聊天分析。</div>`
    : "";
  const modePanel = analysisState.mode === "agent"
    ? `<div class="analysis-code-box"><button class="button button-secondary button-small" type="button" data-action="copy-chat-prompt" ${ready && analysisState.prompt ? "" : "disabled"}>复制</button><pre>${escapeHtml(analysisState.prompt || (ready ? "" : "填写文件和目标发送者后，提示词会自动显示。"))}</pre></div>`
    : analysisState.mode === "manual"
      ? `<div class="analysis-code-box analysis-code-box-manual"><button class="button button-secondary button-small" type="button" data-action="copy-chat-commands" ${ready && analysisState.commands ? "" : "disabled"}>复制</button><pre>${escapeHtml(analysisState.commands || (ready ? "" : "填写文件和目标发送者后，命令会自动显示。"))}</pre></div>`
      : `<button class="button button-primary analysis-start-button" type="submit" ${busy || !ready || !modelConfigured ? "disabled" : ""}>${busy ? "正在后台分析…" : "开始分析"}</button>`;
  const fileError = analysisState.validation?.path === cleanChatPath(analysisState.inputPath) ? analysisState.validation?.error || "" : "";
  return `<div class="page-intro"><div class="page-intro-copy"><div class="intro-mark">${ROUTES.analysis.icon}</div><div><span class="eyebrow">聊天分析 / CHAT ANALYSIS</span><h1>聊天分析</h1><p>先按时期和片段处理，完整聊天不会一次性塞给AI，再做有证据边界的概括。</p></div></div><button class="button button-secondary" type="button" data-open-settings="true">设置</button></div><div class="stage3-layout"><section class="workflow-card surface-card"><div class="workflow-heading"><div><h2>分析设置</h2><p>选择聊天记录，填写目标发送者。</p></div></div><form id="chat-analysis-form"><label class="field field-wide"><span>聊天记录文件</span><div class="input-with-action"><input id="chat-analysis-input" type="text" value="${escapeHtml(analysisState.inputPath)}" placeholder="支持 JSON、JSONL" required /><button class="button button-secondary button-input" type="button" data-action="choose-chat-analysis-file">选择文件</button></div><small id="chat-analysis-input-error" class="field-error" role="alert" ${fileError ? "" : "hidden"}>${textHtml(fileError)}</small><small class="chat-file-validation field-status" aria-live="polite">${chatFileValidationContent(analysisState)}</small></label><div class="form-grid"><label class="field"><span>目标发送者</span><input id="chat-analysis-target" type="text" value="${escapeHtml(analysisState.target)}" placeholder="必须与文件中发送者完全一致" required /><small id="chat-analysis-target-error" class="field-error chat-target-validation" role="alert" ${chatTargetValidationContent(analysisState) ? "" : "hidden"}>${chatTargetValidationContent(analysisState)}</small></label><label class="field"><span>关注主题 <em>可选</em></span><input id="chat-analysis-focus" type="text" value="${escapeHtml(analysisState.focus)}" placeholder="例如：冲突、压力下的沟通" /></label></div><label class="field field-wide"><span>报告保存位置</span><div class="input-with-action"><input id="chat-analysis-output-dir" type="text" value="${escapeHtml(outputDir)}" placeholder="选择报告文件夹" required /><button class="button button-secondary button-input" type="button" data-action="choose-chat-analysis-dir">选择文件夹</button></div></label>${analysisState.error ? `<div class="form-message is-error" role="alert">${textHtml(analysisState.error)}</div>` : ""}<div class="mode-switch mode-switch-wide" role="tablist" aria-label="分析方式"><button class="mode-button ${analysisState.mode === "one-click" ? "is-active" : ""}" type="button" data-analysis-mode="one-click">一键执行</button><button class="mode-button ${analysisState.mode === "agent" ? "is-active" : ""}" type="button" data-analysis-mode="agent">交给agent</button><button class="mode-button ${analysisState.mode === "manual" ? "is-active" : ""}" type="button" data-analysis-mode="manual">手动处理</button></div>${modelHint}${modePanel}</form></section><aside class="info-rail"><section class="surface-card rail-card"><h3>分析顺序</h3><ol class="rail-steps"><li><strong>选择</strong><span>指定需要观察的发送者。</span></li><li><strong>分析</strong><span>按片段和时期逐步处理。</span></li><li><strong>交付</strong><span>保留片段、时期和跨期证据链。</span></li></ol></section><section class="surface-card rail-card"><h3>隐私提醒</h3><p>原文件与工作目录留在本机。一键执行只把当前选中的分析片段发送给已配置的模型服务。</p><div class="rail-note">结果仅用于整理与参考，不构成心理、人格或医疗诊断。</div></section></aside></div>${renderChatTask("analysis")}`;
}

function chatFileValidationContent(analysisState) {
  const path = cleanChatPath(analysisState.inputPath);
  const validation = analysisState.validation;
  if (!path) return "";
  if (!validation || validation.path !== path) return "";
  if (validation.pending) return "正在检查聊天文件格式…";
  if (validation.error) return "";
  const senders = Object.keys(validation.result?.senders || {});
  const senderText = senders.length ? senders.join("、") : "未识别到发送者";
  return `文件格式正确；发送者：${escapeHtml(senderText)}。`;
}

function chatTargetValidationContent(analysisState) {
  const path = cleanChatPath(analysisState.inputPath);
  const validation = analysisState.validation;
  const target = analysisState.targetChecked ? analysisState.target.trim() : "";
  if (!path || !target || !validation?.result || validation.path !== path) return "";
  const senders = Object.keys(validation.result.senders || {});
  return senders.includes(target) ? "" : `未在聊天文件中找到“${escapeHtml(target)}”。`;
}

function validateChatExportField(input) {
  if (!input) return;
  if (["chat-export-start", "chat-export-end"].includes(input.id)) {
    const start = $("#chat-export-start");
    const end = $("#chat-export-end");
    const today = dateTimeInputValue().slice(0, 10);
    const startMessage = start?.value && start.value > today
      ? "开始日期不能晚于今天。"
      : start?.value && end?.value && start.value > end.value ? "开始日期不能晚于结束日期。" : "";
    const endMessage = end?.value && end.value > today ? "结束日期不能晚于今天。" : "";
    for (const [field, message] of [[start, startMessage], [end, endMessage]]) {
      if (!field) continue;
      field.setCustomValidity(message);
      const error = $(`#${field.id}-error`);
      if (error) {
        error.textContent = message;
        error.hidden = !message;
      }
    }
  }
  if (input.id === "chat-export-qq-pid") {
    const message = input.value.trim() && (!/^\d+$/.test(input.value.trim()) || Number(input.value) < 1) ? "QQ.exe PID 必须是正整数。" : "";
    input.setCustomValidity(message);
    const error = $("#chat-export-qq-pid-error");
    if (error) error.hidden = !message;
  }
}

function chatAnalysisReady(analysisState, outputDir = analysisState.outputDir || state.settings?.output_dir || "") {
  const path = cleanChatPath(analysisState.inputPath);
  const senders = Object.keys(analysisState.validation?.result?.senders || {});
  return Boolean(path && analysisState.targetChecked && analysisState.target.trim() && outputDir.trim()
    && analysisState.validation?.path === path && senders.includes(analysisState.target.trim()));
}

function updateChatValidation() {
  const inputError = $("#chat-analysis-input-error");
  const fileStatus = $(".chat-file-validation");
  const validation = state.chatAnalysis.validation;
  if (inputError) {
    inputError.textContent = validation?.error || "";
    inputError.hidden = !validation?.error;
  }
  if (fileStatus) fileStatus.innerHTML = chatFileValidationContent(state.chatAnalysis);
  const targetError = $(".chat-target-validation");
  if (targetError) {
    const message = chatTargetValidationContent(state.chatAnalysis);
    if (message || (state.chatAnalysis.targetChecked && state.chatAnalysis.target.trim() && validation?.result)) {
      targetError.innerHTML = message;
      targetError.hidden = !message;
    }
  }
  updateChatAnalysisAvailability();
}

function updateChatAnalysisAvailability() {
  const ready = chatAnalysisReady(state.chatAnalysis);
  const start = $(".analysis-start-button");
  const copyPrompt = $('[data-action="copy-chat-prompt"]');
  const copyCommands = $('[data-action="copy-chat-commands"]');
  if (start) start.disabled = taskBusy(state.chatAnalysis.task) || !ready || !state.settings?.llm_configured;
  if (copyPrompt) copyPrompt.disabled = !ready || !state.chatAnalysis.prompt;
  if (copyCommands) copyCommands.disabled = !ready || !state.chatAnalysis.commands;
}


function captureChatExportForm() {
  const form = $("#chat-export-form");
  if (!form) return;
  const exportState = state.chatExport;
  exportState.chats = $("#chat-export-chats", form)?.value || "";
  exportState.range = $("#chat-export-range", form)?.value || exportState.range;
  exportState.start = $("#chat-export-start", form)?.value || "";
  exportState.end = $("#chat-export-end", form)?.value || "";
  exportState.format = $("#chat-export-format", form)?.value || exportState.format;
  exportState.outputDir = $("#chat-export-output-dir", form)?.value || "";
  exportState.dbRoot = $("#chat-export-db-root", form)?.value || "";
  exportState.account = $("#chat-export-account", form)?.value || "";
  exportState.qqPid = $("#chat-export-qq-pid", form)?.value || "";
  exportState.recover = Boolean($("#chat-export-recover", form)?.checked);
}

function readChatExportPayload() {
  captureChatExportForm();
  const exportState = state.chatExport;
  return {
    source: exportState.source,
    chat_text: exportState.chats,
    start_time: exportState.range === "custom" ? exportState.start || null : null,
    end_time: exportState.range === "custom" ? exportState.end || null : null,
    output_format: exportState.format,
    output_dir: exportState.outputDir || state.settings?.output_dir || "",
    db_root: exportState.dbRoot,
    account: exportState.account,
    qq_key: $("#chat-export-qq-key")?.value || "",
    qq_pid: exportState.qqPid,
    recover: exportState.recover,
  };
}

function captureChatAnalysisForm() {
  const form = $("#chat-analysis-form");
  if (!form) return;
  const analysisState = state.chatAnalysis;
  analysisState.inputPath = $("#chat-analysis-input", form)?.value || "";
  analysisState.target = $("#chat-analysis-target", form)?.value || "";
  analysisState.focus = $("#chat-analysis-focus", form)?.value || "";
  analysisState.outputDir = $("#chat-analysis-output-dir", form)?.value || "";
}

function chatAnalysisValues() {
  captureChatAnalysisForm();
  const analysisState = state.chatAnalysis;
  return {
    inputPath: analysisState.inputPath,
    target: analysisState.target,
    outputDir: analysisState.outputDir || state.settings?.output_dir || "",
    focus: analysisState.focus,
  };
}

async function startChatExport(event) {
  event?.preventDefault();
  const exportState = state.chatExport;
  exportState.error = "";
  try {
    const task = await callApi("start_chat_export", readChatExportPayload());
    exportState.taskId = task.task_id;
    exportState.task = task;
    render();
    watchChatTask("export", task.task_id);
  } catch (error) {
    exportState.error = error.message;
    render();
  }
}

async function startChatAnalysis(event) {
  event?.preventDefault();
  const values = chatAnalysisValues();
  const analysisState = state.chatAnalysis;
  analysisState.error = "";
  if (!state.settings?.llm_configured) {
    analysisState.error = "请先在“设置”中配置模型，才能一键执行聊天分析。";
    render();
    return;
  }
  try {
    const task = await callApi("start_chat_analysis", values.inputPath, values.target, values.outputDir, values.focus);
    analysisState.taskId = task.task_id;
    analysisState.task = task;
    render();
    watchChatTask("analysis", task.task_id);
  } catch (error) {
    analysisState.error = error.message;
    render();
  }
}

let analysisPreviewVersion = 0;

async function generateChatPrompt(version) {
  const values = chatAnalysisValues();
  try {
    const result = await callApi("get_chat_agent_prompt", values.inputPath, values.target, values.outputDir, values.focus);
    if (version !== analysisPreviewVersion || state.chatAnalysis.mode !== "agent") return;
    state.chatAnalysis.prompt = result.prompt || "";
    render();
  } catch (error) {
    if (version !== analysisPreviewVersion || state.chatAnalysis.mode !== "agent") return;
    state.chatAnalysis.error = error.message;
    render();
  }
}

async function generateChatCommands(version) {
  const values = chatAnalysisValues();
  try {
    const result = await callApi("get_chat_manual_commands", values.inputPath, values.target, values.outputDir, values.focus);
    if (version !== analysisPreviewVersion || state.chatAnalysis.mode !== "manual") return;
    state.chatAnalysis.commands = result.commands || "";
    render();
  } catch (error) {
    if (version !== analysisPreviewVersion || state.chatAnalysis.mode !== "manual") return;
    state.chatAnalysis.error = error.message;
    render();
  }
}

let analysisPreviewTimer = null;
let analysisValidationTimer = null;
let analysisValidationVersion = 0;

function resetChatAnalysisValidation() {
  window.clearTimeout(analysisValidationTimer);
  analysisValidationVersion += 1;
  state.chatAnalysis.validation = null;
  updateChatValidation();
}

function scheduleChatAnalysisValidation() {
  window.clearTimeout(analysisValidationTimer);
  const analysisState = state.chatAnalysis;
  const path = cleanChatPath(analysisState.inputPath);
  const version = ++analysisValidationVersion;
  if (!path) {
    analysisState.validation = null;
    updateChatValidation();
    return;
  }
  if (analysisState.validation?.path === path && analysisState.validation.result) {
    updateChatValidation();
    return;
  }
  analysisState.validation = { path, pending: true };
  updateChatValidation();
  analysisValidationTimer = window.setTimeout(async () => {
    try {
      const result = await callApi("inspect_chat", path);
      if (version !== analysisValidationVersion) return;
      analysisState.validation = { path, result };
    } catch (error) {
      if (version !== analysisValidationVersion) return;
      analysisState.validation = { path, error: error.message };
    }
    updateChatValidation();
  }, 300);
}

function scheduleChatAnalysisPreview() {
  window.clearTimeout(analysisPreviewTimer);
  const version = ++analysisPreviewVersion;
  if (!['agent', 'manual'].includes(state.chatAnalysis.mode)) return;
  if (state.chatAnalysis.mode === 'agent') state.chatAnalysis.prompt = '';
  else state.chatAnalysis.commands = '';
  const panel = $('.analysis-code-box pre');
  if (panel) panel.textContent = '';
  updateChatAnalysisAvailability();
  analysisPreviewTimer = window.setTimeout(
    () => state.chatAnalysis.mode === 'agent' ? generateChatPrompt(version) : generateChatCommands(version),
    300,
  );
}

async function watchChatTask(kind, taskId) {
  const record = kind === "export" ? state.chatExport : state.chatAnalysis;
  try {
    const task = await callApi("get_task", taskId);
    if (record.taskId !== taskId) return;
    record.task = task;
    render();
    if (taskBusy(task)) window.setTimeout(() => watchChatTask(kind, taskId), 500);
  } catch (error) {
    if (record.taskId !== taskId) return;
    record.task = { task_id: taskId, status: "failed", error: { message: error.message } };
    render();
  }
}

async function cancelChatTask(kind) {
  const record = kind === "export" ? state.chatExport : state.chatAnalysis;
  if (!record.taskId) return;
  try {
    await callApi("cancel_task", record.taskId);
    showToast("已请求取消任务，正在确认状态……");
    window.setTimeout(() => watchChatTask(kind, record.taskId), 120);
  } catch (error) {
    showToast(error.message);
  }
}

async function chooseChatExportDir() {
  captureChatExportForm();
  try {
    const result = await callApi("choose_directory", state.chatExport.outputDir || state.settings?.output_dir || "");
    if (!result.cancelled && result.paths?.[0]) {
      state.chatExport.outputDir = result.paths[0];
      render();
    }
  } catch (error) {
    state.chatExport.error = error.message;
    render();
  }
}

async function chooseChatAnalysisFile() {
  try {
    const result = await callApi("choose_file", state.settings?.output_dir || "", ["Chat records (*.json;*.jsonl)", "All files (*.*)"], false);
    if (!result.cancelled && result.paths?.[0]) {
      state.chatAnalysis.inputPath = result.paths[0];
      state.chatAnalysis.error = "";
      render();
      scheduleChatAnalysisValidation();
      scheduleChatAnalysisPreview();
    }
  } catch (error) {
    showToast(error.message);
  }
}

async function chooseChatAnalysisDir() {
  captureChatAnalysisForm();
  try {
    const result = await callApi("choose_directory", state.chatAnalysis.outputDir || state.settings?.output_dir || "");
    if (!result.cancelled && result.paths?.[0]) {
      state.chatAnalysis.outputDir = result.paths[0];
      render();
      scheduleChatAnalysisPreview();
    }
  } catch (error) {
    state.chatAnalysis.error = error.message;
    render();
  }
}


  const chatApi = {
    renderExportRoute,
    renderAnalysisRoute,
    captureChatExportForm,
    readChatExportPayload,
    captureChatAnalysisForm,
    chatAnalysisValues,
    startChatExport,
    startChatAnalysis,
    scheduleChatAnalysisPreview,
    scheduleChatAnalysisValidation,
    resetChatAnalysisValidation,
    updateChatAnalysisAvailability,
    updateChatValidation,
    validateChatExportField,
    cancelChatTask,
    chooseChatExportDir,
    chooseChatAnalysisFile,
    chooseChatAnalysisDir,
    watchChatTask,
  };
  app.chat = chatApi;
  Object.assign(app, chatApi);
})();
