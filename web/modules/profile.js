(() => {
  "use strict";

  const app = window.ProphetApp;
  const {
    state,
    $,
    ROUTES,
    callApi,
    escapeHtml,
    textHtml,
    formatTimestamp,
    dateTimeInputValue,
    initials,
    confidence,
    PROFILE_LABELS,
    KIND_LABELS,
    ASSESSMENT_LABELS,
    taskBusy,
  } = app;
  const render = (...args) => app.render?.(...args);
  const showToast = (...args) => app.showToast?.(...args);
  const setFieldError = (...args) => app.setFieldError?.(...args);

function profileItem(item, entriesById, itemKey) {
  const evidenceIds = Array.isArray(item.evidence_entry_ids) ? item.evidence_entry_ids : [];
  let expandedEntry = null;
  const evidence = evidenceIds.map((id) => {
    const entry = entriesById[id];
    if (!entry) return `<span class="evidence-chip">材料 #${escapeHtml(id)}</span>`;
    const evidenceKey = `${itemKey}-${id}`;
    const expanded = state.profile.expandedEvidenceKey === evidenceKey;
    if (expanded) expandedEntry = entry;
    return `<button class="evidence-chip ${expanded ? "is-expanded" : ""}" type="button" data-action="toggle-profile-evidence" data-evidence-key="${escapeHtml(evidenceKey)}" aria-expanded="${expanded}">${expanded ? "折叠材料" : `材料 #${escapeHtml(id)}`}</button>`;
  }).join("");
  return `<article class="profile-item">
    <p class="profile-claim">${textHtml(item.claim)}</p>
    <div class="tag-row">
      <span class="tag tag-${escapeHtml(item.kind || "uncertainty")}">${escapeHtml(KIND_LABELS[item.kind] || item.kind || "未知")}</span>
      <span class="tag">置信度 ${escapeHtml(confidence(item.confidence))}</span>
    </div>
    <div class="evidence-row"><span class="tag">证据</span>${evidence || "<span class=\"evidence-chip is-muted\">暂无</span>"}</div>
    ${expandedEntry ? `<div class="evidence-expanded"><div class="evidence-meta">${escapeHtml(expandedEntry.source_name || "未命名材料")} · ${expandedEntry.is_active ? "有效" : "已停用"} · ${escapeHtml(formatTimestamp(expandedEntry.created_at))}</div><pre>${escapeHtml(expandedEntry.content || "")}</pre></div>` : ""}
  </article>`;
}

function renderProfileSummary(workspace) {
  const record = workspace.profile;
  if (!record) {
    return `<div class="empty-panel compact-empty">
      <span class="status-badge">尚未建立</span>
      <h3>添加第一条材料</h3>
      <p>画像会从材料中逐步形成，每条结论都会保留对应的材料编号与置信度。</p>
      <button class="button button-primary" type="button" data-action="new-material">添加材料</button>
    </div>`;
  }
  const profile = record.profile || {};
  const entriesById = Object.fromEntries((workspace.entries || []).map((entry) => [entry.id, entry]));
  const sections = Object.entries(PROFILE_LABELS).map(([key, label]) => {
    const items = Array.isArray(profile[key]) ? profile[key] : [];
    if (!items.length) return "";
    return `<section class="profile-section surface-card"><div class="section-heading"><h3 class="profile-card-title">${label}</h3><span>${items.length} 条</span></div>${items.map((item, index) => profileItem(item, entriesById, `${key}-${index}`)).join("")}</section>`;
  }).join("");
  return `<section class="profile-section profile-summary-card surface-card">
    <div class="section-heading"><h3 class="profile-card-title">总览</h3><span>版本 ${escapeHtml(record.version)}</span></div>
    <div class="profile-summary-copy">${textHtml(profile.overview || "暂无总览")}</div>
    <div class="record-meta">更新时间 ${escapeHtml(formatTimestamp(record.updated_at))} · 画像条目可展开查看材料原文</div>
  </section>${sections || `<div class="empty-panel compact-empty"><p class="muted-copy">当前版本暂时没有可展示的条目。</p></div>`}`;
}

function renderMaterialAnalysis(result) {
  const material = result?.analysis || {};
  const list = (items, title, renderItem) => !items?.length ? "" : `<section class="analysis-section"><h4>${title}</h4>${items.map(renderItem).join("")}</section>`;
  return `<div class="analysis-result surface-card">
    <div class="summary-head"><div><h3>最近一次材料分析</h3></div><span class="version-badge">画像版本 ${escapeHtml(result.profile_version)}</span></div>
    <p class="analysis-summary"><strong>事实摘要：</strong>${textHtml(material.source_summary || "暂无")}</p>
    ${list(material.observed_emotions, "观察到的情绪", (item) => `<div class="analysis-row"><strong>${textHtml(item.name)}</strong><span>强度 ${escapeHtml(confidence(item.intensity))} · 置信度 ${escapeHtml(confidence(item.confidence))}</span><p>依据：${textHtml(item.evidence)}</p></div>`)}
    ${list(material.observed_behaviors, "行为与表达", (item) => `<div class="analysis-row"><strong>${textHtml(item.description)}</strong><span>置信度 ${escapeHtml(confidence(item.confidence))}</span><p>依据：${textHtml(item.evidence)}</p></div>`)}
    ${list(material.possible_needs, "可能需求", (item) => `<div class="analysis-row"><strong>${textHtml(item.description)}</strong><span>推断 · 置信度 ${escapeHtml(confidence(item.confidence))}</span><p>理由：${textHtml(item.reasoning)}</p></div>`)}
    ${list(material.triggers_and_context, "触发因素与上下文", (item) => `<div class="analysis-row"><strong>${textHtml(item.description)}</strong><span>置信度 ${escapeHtml(confidence(item.confidence))}</span><p>依据：${textHtml(item.evidence)}</p></div>`)}
    ${list(material.new_hypotheses, "新增假设", (item) => `<div class="analysis-row"><strong>${textHtml(item.description)}</strong><span>推断 · 置信度 ${escapeHtml(confidence(item.confidence))}</span><p>依据：${textHtml(item.basis)}</p></div>`)}
    ${list(material.contradictions, "与旧画像的冲突", (item) => `<div class="analysis-row"><strong>${textHtml(item.description)}</strong><span>冲突对象：${textHtml(item.conflicts_with)} · 置信度 ${escapeHtml(confidence(item.confidence))}</span></div>`)}
    ${material.missing_context?.length ? `<section class="analysis-section"><h4>缺失上下文</h4><ul class="plain-list">${material.missing_context.map((item) => `<li>${textHtml(item)}</li>`).join("")}</ul></section>` : ""}
    <div class="record-meta">已保存材料 #${escapeHtml(result.entry_id)} · 原文保留在本地数据库</div>
  </div>`;
}

function renderPrediction(prediction) {
  const value = prediction || {};
  return `<div class="prediction-body">
    ${(value.likely_reactions || []).map((item, index) => `<article class="reaction-card"><div class="reaction-title"><span>候选反应 ${index + 1}</span><strong>${textHtml(item.reaction)}</strong></div><p>可能情绪：${textHtml(item.emotion)} · 可能行为：${textHtml(item.behavior)}</p><div class="reaction-meta">条件：${textHtml((item.conditions || []).join("；") || "未明确")}<br>依据：${textHtml((item.evidence || []).join("；") || "暂无")} · 置信度：${escapeHtml(confidence(item.confidence))}</div></article>`).join("")}
    ${value.alternatives?.length ? `<div class="prediction-list"><strong>其他合理反应</strong><ul class="plain-list">${value.alternatives.map((item) => `<li>${textHtml(item)}</li>`).join("")}</ul></div>` : ""}
    ${value.unknowns?.length ? `<div class="prediction-list"><strong>未知信息</strong><ul class="plain-list">${value.unknowns.map((item) => `<li>${textHtml(item)}</li>`).join("")}</ul></div>` : ""}
    ${value.safe_interaction_suggestion ? `<div class="suggestion-box"><strong>温和沟通建议</strong><p>${textHtml(value.safe_interaction_suggestion)}</p></div>` : ""}
  </div>`;
}

function renderReview(review) {
  if (!review) return "";
  const groups = [["符合点", "matched_points"], ["偏差", "differences"], ["可能原因", "possible_reasons"], ["仍未知", "unknowns"], ["画像调整方向", "profile_adjustments"]];
  return `<div class="review-body"><div class="review-assessment">复盘结论：${escapeHtml(ASSESSMENT_LABELS[review.assessment] || review.assessment || "未知")}</div><p>${textHtml(review.summary || "")}</p>${groups.map(([label, key]) => review[key]?.length ? `<div class="review-group"><strong>${label}</strong><ul class="plain-list">${review[key].map((item) => `<li>${textHtml(item)}</li>`).join("")}</ul></div>` : "").join("")}</div>`;
}

function captureMaterialForm() {
  const form = $("#material-form");
  if (!form) return;
  const material = state.profile.material;
  material.content = $("#material-content", form)?.value || "";
  material.title = $("#material-title", form)?.value || "直接输入";
  material.context = $("#material-context", form)?.value || "";
  material.occurredAt = $("#material-occurred-at", form)?.value || "";
  material.encoding = $("#material-encoding", form)?.value || "";
  material.filePath = $("#material-file-path", form)?.value || "";
  material.allowDuplicate = Boolean($("#allow-duplicate", form)?.checked);
}

function validateMaterialForm(showField = "") {
  const dateInput = $("#material-occurred-at");
  const contentInput = $("#material-content");
  const submit = $("#material-submit");
  if (!dateInput || !contentInput || !submit) return;
  const dateInvalid = Boolean(dateInput.value && dateInput.value > dateInput.max);
  const contentInvalid = !contentInput.value.trim();
  submit.disabled = Boolean(state.profile.activeTask || state.profile.material.taskId || !state.settings?.llm_configured || dateInvalid || contentInvalid);
  if (showField === "material-occurred-at") setFieldError(dateInput, dateInvalid ? "发生日期不能晚于今天。" : "");
  if (showField === "material-content") setFieldError(contentInput, contentInvalid ? "请填写材料正文。" : "");
}

function toggleProfileEvidence(evidenceKey) {
  state.profile.expandedEvidenceKey = state.profile.expandedEvidenceKey === evidenceKey ? null : evidenceKey;
  render();
}

function renderPersonForm() {
  const form = state.profile.personForm;
  if (!form) return "";
  const isNew = form.mode === "new";
  return `<div class="inline-form-card surface-card"><div class="section-heading"><div><h3>${isNew ? "新建人物" : "编辑当前人物"}</h3></div></div><form id="person-form"><div class="form-grid"><label class="field"><span>显示名称</span><input id="person-name" name="name" required maxlength="200" value="${escapeHtml(form.name || "")}" placeholder="例如：追光者" /><small id="person-name-error" class="field-error" role="alert" hidden></small></label><label class="field field-wide"><span>背景备注 <em>可选，最多 100 字</em></span><textarea id="person-notes" name="notes" maxlength="100" placeholder="记录有助于理解材料的背景……">${escapeHtml(form.notes || "")}</textarea></label></div><div class="form-actions"><button class="button button-primary" type="submit">${isNew ? "创建人物" : "保存修改"}</button><button class="button button-secondary" type="button" data-action="cancel-person">取消</button></div></form></div>`;
}

function renderPersonList() {
  const people = state.profile.people || [];
  const options = people.length ? people.map((person) => `<option value="${escapeHtml(person.id)}" ${person.id === state.profile.selectedPersonId ? "selected" : ""}>${escapeHtml(person.name)}</option>`).join("") : `<option>暂无人物</option>`;
  return `<section class="person-panel surface-card"><div class="person-selector-row"><div><h2>人物数据</h2></div><div class="person-selector-actions"><label class="person-select-field"><select id="person-select" aria-label="选择人物" ${people.length ? "" : "disabled"}>${options}</select></label><button class="button button-secondary" type="button" data-action="new-person">新建人物</button></div></div></section>`;
}

function renderProfileHeader(workspace) {
  const person = workspace.person;
  const version = workspace.profile ? `画像版本 ${workspace.profile.version}` : "尚未建立画像";
  return `<div class="person-hero surface-card"><div class="person-hero-header"><div class="person-hero-main"><div><h2>${escapeHtml(person.name)}</h2><p>${textHtml(person.notes || "暂无背景备注")}</p><span class="version-badge">${escapeHtml(version)}</span></div></div><div class="hero-actions"><button class="button button-secondary" type="button" data-action="edit-person">编辑</button><button class="button button-secondary" type="button" data-action="delete-person">删除</button></div></div>${state.profile.personForm?.mode === "edit" ? renderPersonForm() : ""}</div>`;
}

function renderProfileTabs() {
  const tabs = [["profile", "当前画像"], ["material", "添加材料"], ["prediction", "预测复盘"], ["history", "数据维护"]];
  return `<div class="profile-tabs" role="tablist" aria-label="人物工作区">${tabs.map(([key, label]) => `<button class="profile-tab ${state.profile.tab === key ? "is-active" : ""}" type="button" role="tab" aria-selected="${state.profile.tab === key}" data-profile-tab="${key}">${label}</button>`).join("")}</div>`;
}

function renderMaterialPanel(workspace) {
  const material = state.profile.material;
  const taskBusy = Boolean(material.taskId || state.profile.activeTask);
  const modelConfigured = Boolean(state.settings?.llm_configured);
  const modelHint = !modelConfigured ? `<div class="notice notice-warning">请先在“设置”中配置模型；材料预览仍可使用。</div>` : "";
  const duplicate = material.duplicate ? `<div id="material-duplicate-warning" class="notice notice-warning">检测到同一人物的重复材料：#${escapeHtml(material.duplicate.id)} · ${escapeHtml(material.duplicate.source_name || "未命名材料")}。<label class="check-line"><input id="allow-duplicate" type="checkbox" ${material.allowDuplicate ? "checked" : ""} />仍然分析并保存重复材料</label></div>` : "";
  const encodings = ["", "gb18030", "big5", "utf-16", "latin-1"].map((value) => `<option value="${value}" ${material.encoding === value ? "selected" : ""}>${value || "自动识别 UTF-8"}</option>`).join("");
  const last = material.lastResult ? renderMaterialAnalysis(material.lastResult) : "";
  const dateInvalid = Boolean(material.occurredAt && material.occurredAt > dateTimeInputValue().slice(0, 10));
  const contentInvalid = !material.content.trim();
  return `<div class="tab-panel"><div class="panel-title-row"><div><h2>添加材料</h2><p>原文只进入本地数据库；分析任务完成后会生成新的画像版本。</p></div></div>${modelHint}<form id="material-form" class="material-form-card surface-card"><div class="form-grid"><label class="field"><span>材料标题</span><input id="material-title" type="text" maxlength="200" value="${escapeHtml(material.title || "直接输入")}" /></label><label class="field"><span>发生日期 <em>可选</em></span><input id="material-occurred-at" type="date" max="${dateTimeInputValue().slice(0, 10)}" value="${escapeHtml(material.occurredAt || "")}" /><small id="material-occurred-at-error" class="field-error" role="alert" hidden></small></label><label class="field field-wide"><span>场景 / 来源备注 <em>可选</em></span><input id="material-context" type="text" maxlength="2000" value="${escapeHtml(material.context || "")}" placeholder="例如：一次重要的工作沟通" /></label><label class="field field-wide"><span>文件导入 <em>可选</em></span><div class="material-file-import"><input id="material-file-path" type="text" value="${escapeHtml(material.filePath)}" placeholder="输入或选择文件地址" /><button class="button button-secondary button-input" type="button" data-action="choose-material-file">选择文件</button><button id="material-file-import" class="button button-secondary button-input" type="button" data-action="preview-material" ${material.filePath.trim() ? "" : "disabled"}>导入</button></div>${material.encodingRequired ? `<div class="encoding-retry"><select id="material-encoding" aria-label="文件编码">${encodings}</select><span>请选择编码后重新导入。</span></div>` : ""}</label></div><label class="field field-wide material-content-field"><span>材料正文</span><textarea id="material-content" required maxlength="200000" placeholder="粘贴一段对话、记录或其他文字材料……">${escapeHtml(material.content || "")}</textarea><small id="material-content-error" class="field-error" role="alert" hidden></small></label>${material.filePreview ? `<div class="material-preview"><div class="preview-head"><strong>文本预览</strong><span>最多展示前 5,000 字符</span></div><pre>${escapeHtml(material.filePreview)}</pre></div>` : ""}<div class="material-meta-row"><span>规范化后字符数：${escapeHtml((material.content || "").trim().length)}</span>${material.fileType ? `<span>文件类型：${escapeHtml(material.fileType)}</span>` : ""}</div>${duplicate}${material.error ? `<div id="material-form-error" class="form-message is-error" role="alert">${textHtml(material.error)}</div>` : ""}<div class="form-actions"><button id="material-submit" class="button button-primary" type="submit" ${taskBusy || !modelConfigured || dateInvalid || contentInvalid ? "disabled" : ""}>${taskBusy ? "任务进行中…" : "分析并保存"}</button>${material.taskId ? `<button class="button button-secondary" type="button" data-action="cancel-task">取消任务</button>` : ""}</div></form>${last}</div>`;
}

function renderPredictionPanel(workspace) {
  const revisions = workspace.profile_revisions || [];
  const predictions = workspace.predictions || [];
  const selectedVersion = state.profile.predictionVersion && revisions.some((item) => item.version === state.profile.predictionVersion) ? state.profile.predictionVersion : revisions[0]?.version;
  const versionOptions = revisions.map((revision) => `<option value="${escapeHtml(revision.version)}" ${revision.version === selectedVersion ? "selected" : ""}>画像版本 ${escapeHtml(revision.version)} · ${escapeHtml(formatTimestamp(revision.created_at))}</option>`).join("");
  const modelConfigured = Boolean(state.settings?.llm_configured);
  const modelHint = !modelConfigured ? `<div class="notice notice-warning">请先在“设置”中配置模型，才能生成预测或提交复盘。</div>` : "";
  const cards = predictions.length ? predictions.map((prediction) => `<article class="prediction-card"><div class="prediction-head"><div><h3>画像版本 ${escapeHtml(prediction.profile_version)}</h3></div><span class="status-badge ${prediction.actual_outcome ? "is-done" : "is-pending"}">${prediction.actual_outcome ? "已复盘" : "待复盘"}</span></div><p class="event-text">${textHtml(prediction.event_text)}</p>${renderPrediction(prediction.prediction)}${prediction.actual_outcome ? `<div class="outcome-box"><strong>实际结果</strong><p>${textHtml(prediction.actual_outcome)}</p>${renderReview(prediction.review)}</div>` : `<form class="review-form" data-form="prediction-review" data-prediction-id="${escapeHtml(prediction.id)}"><label class="field"><span>实际结果</span><textarea id="review-outcome-${escapeHtml(prediction.id)}" required placeholder="事情实际如何发展？">${escapeHtml(state.profile.reviewDrafts[prediction.id] || "")}</textarea><small id="review-outcome-${escapeHtml(prediction.id)}-error" class="field-error" role="alert" hidden></small></label><div class="form-actions"><button class="button button-secondary" type="submit" ${state.profile.activeTask || !modelConfigured ? "disabled" : ""}>提交实际结果并复盘</button></div></form>`}<div class="card-footer"><button class="text-button danger-text" type="button" data-action="delete-prediction" data-prediction-id="${escapeHtml(prediction.id)}">删除预测记录</button><span>创建于 ${escapeHtml(formatTimestamp(prediction.created_at))}</span></div></article>`).join("") : `<div class="empty-panel compact-empty"><h3>暂无预测记录</h3><p>生成一次预测后，它会固定记录所使用的画像版本。</p></div>`;
  return `<div class="tab-panel"><div class="panel-title-row"><div><h2>预测复盘</h2><p>预测只提供有证据的可能性，不保证任何行为一定发生。</p></div></div>${modelHint}${revisions.length ? `<form id="prediction-form" class="prediction-create surface-card"><div class="form-grid"><label class="field"><span>使用画像版本</span><select id="prediction-version">${versionOptions}</select></label><label class="field field-wide"><span>假设事件与必要背景</span><textarea id="prediction-event" required placeholder="例如：如果临时改变原定安排，并提前说明原因……">${escapeHtml(state.profile.predictionEvent || "")}</textarea><small id="prediction-event-error" class="field-error" role="alert" hidden></small></label></div><div class="form-actions"><button id="prediction-submit" class="button button-primary" type="submit" ${state.profile.activeTask || !modelConfigured || !state.profile.predictionEvent.trim() ? "disabled" : ""}>分析并保存预测</button></div></form>` : `<div class="notice notice-info">请先在“添加材料”中生成画像，再创建预测。</div>`}<div class="stack-list">${cards}</div></div>`;
}

function timelineItems(workspace) {
  const items = (workspace.entries || []).map((entry) => ({ timestamp: entry.occurred_at || entry.created_at, type: "entry", value: entry }));
  items.push(...(workspace.predictions || []).map((prediction) => ({ timestamp: prediction.created_at, type: "prediction", value: prediction })));
  items.push(...(workspace.profile_revisions || []).map((revision) => ({ timestamp: revision.created_at, type: "revision", value: revision })));
  return items.sort((a, b) => `${b.timestamp}${b.type}`.localeCompare(`${a.timestamp}${a.type}`));
}

function renderTimeline(workspace) {
  const items = timelineItems(workspace);
  if (!items.length) return `<div class="empty-panel compact-empty"><h3>暂无历史记录</h3><p>添加材料、画像版本和预测后，时间线会从这里展开。</p></div>`;
  return `<div class="timeline">${items.map((item) => {
    if (item.type === "entry") {
      const entry = item.value;
      const kind = entry.entry_type === "actual_outcome" ? "实际结果" : "材料";
      return `<article class="timeline-item ${entry.is_active ? "" : "is-inactive"}"><div class="timeline-marker"></div><div class="timeline-content"><div class="timeline-meta"><span>${escapeHtml(formatTimestamp(item.timestamp))}</span><strong>${kind} #${escapeHtml(entry.id)}</strong><span>${entry.is_active ? "有效" : "已停用"}</span></div><h3>${escapeHtml(entry.source_name || "未命名材料")}</h3><p class="timeline-context">类型：${escapeHtml(entry.entry_type)} · ${escapeHtml(entry.context || "无备注")}</p><details><summary>查看材料正文</summary><pre>${escapeHtml(entry.content)}</pre></details></div></article>`;
    }
    if (item.type === "prediction") {
      const prediction = item.value;
      return `<article class="timeline-item"><div class="timeline-marker marker-violet"></div><div class="timeline-content"><div class="timeline-meta"><span>${escapeHtml(formatTimestamp(item.timestamp))}</span><strong>预测 #${escapeHtml(prediction.id)}</strong><span>画像版本 ${escapeHtml(prediction.profile_version)}</span></div><h3>${textHtml(prediction.event_text)}</h3>${renderPrediction(prediction.prediction)}${prediction.actual_outcome ? `<div class="outcome-box"><strong>实际结果</strong><p>${textHtml(prediction.actual_outcome)}</p>${renderReview(prediction.review)}</div>` : `<p class="muted-copy">待补录实际结果</p>`}</div></article>`;
    }
    const revision = item.value;
    return `<article class="timeline-item"><div class="timeline-marker marker-mint"></div><div class="timeline-content"><div class="timeline-meta"><span>${escapeHtml(formatTimestamp(item.timestamp))}</span><strong>画像版本 ${escapeHtml(revision.version)}</strong><span>触发材料 ${escapeHtml(revision.trigger_entry_id || "无")}</span></div><p>${textHtml(revision.summary_md || "暂无摘要")}</p></div></article>`;
  }).join("")}</div>`;
}

function renderHistoryPanel(workspace) {
  const revisions = workspace.profile_revisions || [];
  const entries = workspace.entries || [];
  const activeCount = entries.filter((entry) => entry.is_active).length;
  const exportDir = state.profile.exportDir || state.settings?.output_dir || "";
  return `<div class="tab-panel"><div class="panel-title-row"><div><h2>数据维护</h2><p>可重建画像，导入导出，还可以查看历史画像与材料</p></div></div><div class="maintenance-grid"><section class="maintenance-card surface-card"><div class="section-heading"><div><h3>画像维护</h3><p>当前有效材料：${activeCount} 条</p></div></div><button class="button button-secondary" type="button" data-action="rebuild-profile" ${state.profile.activeTask ? "disabled" : ""}>从有效材料重建画像</button>${revisions.length ? `<div class="restore-row"><select id="restore-version">${revisions.map((revision) => `<option value="${escapeHtml(revision.version)}">版本 ${escapeHtml(revision.version)} · ${escapeHtml(formatTimestamp(revision.created_at))}</option>`).join("")}</select><button class="button button-secondary" type="button" data-action="restore-profile">回退为新版本</button></div>` : ""}</section><section class="maintenance-card surface-card"><div class="section-heading"><div><h3>导出与备份</h3><p>文件写入本机默认保存位置。</p></div></div><label class="field"><span>保存位置</span><div class="material-file-import export-path-row"><input id="profile-export-dir" type="text" value="${escapeHtml(exportDir)}" /><button class="button button-secondary button-input" type="button" data-action="choose-export-dir">选择文件夹</button></div></label><div class="export-actions"><button class="button button-secondary" type="button" data-action="export-person" data-export-format="json">保存人物 JSON</button><button class="button button-secondary" type="button" data-action="export-person" data-export-format="markdown">保存人物 Markdown</button><button class="button button-secondary" type="button" data-action="export-person" data-export-format="database">保存数据库备份</button></div></section></div>${renderDatabaseImportCard()}${renderTimeline(workspace)}</div>`;
}

function renderDatabaseImportCard() {
  return `<section class="maintenance-card surface-card database-import-card"><div class="section-heading"><div><h3>导入数据库</h3><p>导入会替换当前人物画像库，请先选择备份并确认。</p></div></div><div class="material-file-import"><input id="database-import-path" type="text" value="${escapeHtml(state.profile.importPath)}" placeholder="支持 .db、.sqlite、.sqlite3 文件" /><button class="button button-secondary button-input" type="button" data-action="choose-database-file">选择文件</button><button id="database-import-submit" class="button button-secondary button-input" type="button" data-action="import-database" ${state.profile.importPath.trim() ? "" : "disabled"}>导入</button></div></section>`;
}

function renderProfilePanel(workspace) {
  if (state.profile.tab === "material") return renderMaterialPanel(workspace);
  if (state.profile.tab === "prediction") return renderPredictionPanel(workspace);
  if (state.profile.tab === "history") return renderHistoryPanel(workspace);
  return `<div class="tab-panel"><div class="panel-title-row"><div><h2>当前画像</h2><p>总览与各方面的分析，可查看对应材料证据。</p></div></div>${renderProfileSummary(workspace)}</div>`;
}

function renderProfileRoute() {
  const profileState = state.profile;
  let body = "";
  if (!state.bridgeReady) {
    body = `<div class="empty-panel bridge-empty surface-card"><span class="status-badge">预览模式</span><h2>人物工作区等待本地桥接</h2><p>在 Prophet 桌面窗口中打开后，人物和材料会从本地数据库载入。</p></div>`;
  } else if (profileState.loading && !profileState.workspace) {
    body = `<div class="page-loading" role="status">正在读取人物工作区</div>`;
  } else if (profileState.error && !profileState.workspace) {
    body = `<div class="empty-panel bridge-empty surface-card"><span class="status-badge">读取失败</span><h2>人物数据暂时不可用</h2><p>${textHtml(profileState.error)}</p><button class="button button-primary" type="button" data-action="reload-profile">重新读取</button></div>`;
  } else if (!profileState.workspace) {
    body = `<div class="profile-workbench">${renderPersonList()}${profileState.personForm ? renderPersonForm() : `<div class="empty-panel surface-card"><span class="status-badge">还没有人物</span><h2>先建立一个人物</h2><p>添加人物后，可以在同一个工作区里录入材料、查看有证据的画像，并持续复盘预测。</p><button class="button button-primary" type="button" data-action="new-person">新建人物</button></div>${renderDatabaseImportCard()}`}</div>`;
  } else {
    body = `<div class="profile-workbench">${renderPersonList()}${profileState.personForm?.mode === "new" ? renderPersonForm() : ""}<section class="profile-main">${renderProfileHeader(profileState.workspace)}${renderProfileTabs()}${renderProfilePanel(profileState.workspace)}</section></div>`;
  }
  const pageView = $("#page-view");
  const content = $("[data-route-content='profile']", pageView);
  if (content) {
    content.innerHTML = body;
  } else {
    pageView.innerHTML = `<div class="page-intro"><div class="page-intro-copy"><div class="intro-mark">${ROUTES.profile.icon}</div><div><span class="eyebrow">PERSONAL PROFILE</span><h1>人物画像</h1><p>用带证据的材料建立可回看的画像，在具体情境中观察可能反应，并持续用实际结果校正。</p></div></div><button class="button button-secondary" type="button" data-open-settings="true">设置</button></div><div data-route-content="profile">${body}</div>`;
  }
  if (profileState.personForm) $("#person-name")?.focus();
}


async function loadProfileRoute() {
  if (!state.bridgeReady) return;
  const profileState = state.profile;
  profileState.loading = true;
  profileState.error = "";
  if (!profileState.workspace) render();
  try {
    profileState.people = await callApi("list_people");
    const ids = profileState.people.map((person) => person.id);
    if (!ids.includes(profileState.selectedPersonId)) profileState.selectedPersonId = ids[0] ?? null;
    profileState.workspace = profileState.selectedPersonId == null ? null : await callApi("get_person_workspace", profileState.selectedPersonId);
    if (!profileState.exportDir) profileState.exportDir = state.settings?.output_dir || "";
    await app.refreshHealth?.();
  } catch (error) {
    profileState.error = error.message;
  } finally {
    profileState.loading = false;
    render();
  }
}

async function selectPerson(personId) {
  const numericId = Number(personId);
  if (!Number.isInteger(numericId) || numericId < 1) return;
  if (state.profile.selectedPersonId !== numericId) {
    Object.assign(state.profile.material, { content: "", title: "直接输入", context: "", occurredAt: "", fileType: "", filePath: "", filePreview: "", encoding: "", encodingRequired: false, duplicate: null, allowDuplicate: false, error: "", lastResult: null, taskId: null });
    state.profile.predictionEvent = "";
    state.profile.reviewDrafts = {};
    state.profile.expandedEvidenceKey = null;
  }
  state.profile.selectedPersonId = numericId;
  state.profile.tab = "profile";
  state.profile.error = "";
  state.profile.loading = true;
  state.profile.workspace = null;
  render();
  try {
    state.profile.workspace = await callApi("get_person_workspace", numericId);
  } catch (error) {
    state.profile.error = error.message;
  } finally {
    state.profile.loading = false;
    render();
  }
}

function openPersonForm(mode) {
  const person = state.profile.workspace?.person;
  state.profile.personForm = {
    mode,
    name: mode === "edit" ? person?.name || "" : "",
    notes: mode === "edit" ? person?.notes || "" : "",
  };
  render();
  window.setTimeout(() => $("#person-name")?.focus(), 0);
}

async function savePerson(event) {
  event.preventDefault();
  const form = event.target;
  const name = $("#person-name", form)?.value || "";
  const notes = $("#person-notes", form)?.value || "";
  setFieldError($("#person-name", form), "");
  form.querySelectorAll("input, textarea, button").forEach((control) => { control.disabled = true; });
  try {
    const personForm = state.profile.personForm;
    const workspace = personForm.mode === "new"
      ? await callApi("create_person", name, notes)
      : await callApi("update_person", state.profile.selectedPersonId, name, notes);
    state.profile.selectedPersonId = workspace.person.id;
    state.profile.personForm = null;
    state.profile.workspace = workspace;
    await loadProfileRoute();
    showToast(personForm.mode === "new" ? "人物已创建。" : "人物信息已保存。");
  } catch (error) {
    setFieldError($("#person-name", form), error.message);
    form.querySelectorAll("input, textarea, button").forEach((control) => { control.disabled = false; });
  }
}

async function deleteCurrentPerson() {
  const person = state.profile.workspace?.person;
  if (!person || !(await app.confirmAction(`确定删除“${person.name}”及其全部材料、画像和预测吗？此操作不可撤销。`))) return;
  try {
    await callApi("delete_person", person.id);
    state.profile.selectedPersonId = null;
    state.profile.workspace = null;
    state.profile.personForm = null;
    await loadProfileRoute();
    showToast("人物及其关联数据已删除。");
  } catch (error) {
    showToast(error.message);
  }
}

async function previewSelectedMaterial() {
  const material = state.profile.material;
  material.filePath = material.filePath.trim();
  if (!material.filePath) return;
  material.error = "";
  try {
    const preview = await callApi("preview_material", material.filePath, material.encoding);
    material.content = preview.content;
    material.title = preview.name;
    material.fileType = `.${preview.extension}`;
    material.filePreview = preview.preview;
    material.encodingRequired = false;
    render();
    showToast(`已读取 ${preview.characters} 个字符，原文件不会保存。`);
  } catch (error) {
    material.error = error.message;
    material.encodingRequired = error.code === "ENCODING_REQUIRED";
    render();
  }
}

function captureExportDir() {
  state.profile.exportDir = $("#profile-export-dir")?.value || state.profile.exportDir;
}

async function chooseMaterialFile() {
  captureMaterialForm();
  try {
    const result = await callApi("choose_file", state.settings?.output_dir || "", ["Text files (*.txt;*.md;*.csv;*.json)", "Documents (*.docx;*.pdf;*.xlsx)", "All files (*.*)"], false);
    if (result.cancelled || !result.paths?.[0]) return;
    const material = state.profile.material;
    material.filePath = result.paths[0];
    material.error = "";
    render();
  } catch (error) {
    showToast(error.message);
  }
}

async function startMaterialAnalysis(event) {
  event.preventDefault();
  captureMaterialForm();
  const material = state.profile.material;
  material.error = "";
  material.duplicate = null;
  try {
    const check = await callApi("check_material", state.profile.selectedPersonId, material.content);
    material.duplicate = check.duplicate;
    if (material.duplicate && !material.allowDuplicate) {
      material.error = `该人物已有相同材料（材料 #${material.duplicate.id}）。如仍需保存，请勾选重复材料选项。`;
      render();
      return;
    }
    const task = await callApi("start_material_analysis", state.profile.selectedPersonId, {
      entry_type: material.fileType ? "document" : "text",
      source_name: material.title,
      file_type: material.fileType || null,
      occurred_at: material.occurredAt || null,
      context: material.context,
      content: material.content,
      allow_duplicate: material.allowDuplicate,
    });
    material.taskId = task.task_id;
    state.profile.activeTask = task.task_id;
    state.profile.activeTaskPersonId = state.profile.selectedPersonId;
    render();
    watchTask(task.task_id, "material");
  } catch (error) {
    material.error = error.message;
    render();
  }
}

async function startPrediction(event) {
  event.preventDefault();
  const eventText = $("#prediction-event")?.value || "";
  const version = $("#prediction-version")?.value || null;
  state.profile.predictionEvent = eventText;
  state.profile.predictionVersion = version ? Number(version) : null;
  try {
    const task = await callApi("start_prediction", state.profile.selectedPersonId, eventText, state.profile.predictionVersion);
    state.profile.activeTask = task.task_id;
    state.profile.activeTaskPersonId = state.profile.selectedPersonId;
    render();
    watchTask(task.task_id, "prediction");
  } catch (error) {
    setFieldError($("#prediction-event"), error.message);
  }
}

async function startPredictionReview(event) {
  event.preventDefault();
  const form = event.target;
  const predictionId = Number(form.dataset.predictionId);
  const outcome = $("textarea", form)?.value || "";
  state.profile.reviewDrafts[predictionId] = outcome;
  try {
    const task = await callApi("start_prediction_review", state.profile.selectedPersonId, predictionId, outcome);
    state.profile.activeTask = task.task_id;
    state.profile.activeTaskPersonId = state.profile.selectedPersonId;
    render();
    watchTask(task.task_id, "review");
  } catch (error) {
    setFieldError($("textarea", form), error.message);
  }
}

async function watchTask(taskId, kind) {
  try {
    const task = await callApi("get_task", taskId);
    if (task.status === "queued" || task.status === "running") {
      window.setTimeout(() => watchTask(taskId, kind), 350);
      return;
    }
    state.profile.activeTask = null;
    const samePerson = state.profile.selectedPersonId === state.profile.activeTaskPersonId;
    state.profile.activeTaskPersonId = null;
    if (kind === "material") state.profile.material.taskId = null;
    if (task.status === "cancelled") {
      if (kind === "material") state.profile.material.error = "任务已取消。";
      render();
      return;
    }
    if (task.status === "failed") {
      const message = task.error?.message || "任务执行失败。";
      if (kind === "material") state.profile.material.error = message;
      showToast(message);
      render();
      return;
    }
    if (kind === "material" && samePerson) state.profile.material.lastResult = task.result;
    if (kind === "prediction") state.profile.predictionEvent = "";
    if (kind === "review") state.profile.reviewDrafts = {};
    await loadProfileRoute();
    showToast(kind === "material" ? "材料分析完成，画像已更新。" : kind === "prediction" ? "预测已保存。" : "复盘已完成，画像已更新。");
  } catch (error) {
    state.profile.activeTask = null;
    state.profile.activeTaskPersonId = null;
    if (kind === "material") {
      state.profile.material.taskId = null;
      state.profile.material.error = error.message;
    }
    render();
  }
}

async function cancelActiveTask() {
  const taskId = state.profile.activeTask || state.profile.material.taskId;
  if (!taskId) return;
  try {
    await callApi("cancel_task", taskId);
    showToast("已请求取消任务。正在确认状态……");
  } catch (error) {
    showToast(error.message);
  }
}

async function deletePrediction(predictionId) {
  if (!(await app.confirmAction("确定删除这条预测记录吗？实际结果材料会保留。"))) return;
  try {
    await callApi("delete_prediction", state.profile.selectedPersonId, Number(predictionId));
    await loadProfileRoute();
    showToast("预测记录已删除。");
  } catch (error) {
    showToast(error.message);
  }
}

async function rebuildProfile() {
  if (!(await app.confirmAction("确定从当前所有有效材料重新生成画像吗？这会覆盖原有的画像版本。", "确认重建画像"))) return;
  try {
    const task = await callApi("start_rebuild_profile", state.profile.selectedPersonId);
    state.profile.activeTask = task.task_id;
    state.profile.activeTaskPersonId = state.profile.selectedPersonId;
    render();
    watchTask(task.task_id, "rebuild");
  } catch (error) {
    showToast(error.message);
  }
}

async function restoreProfile() {
  const version = Number($("#restore-version")?.value);
  if (!version || !(await app.confirmAction(`确定根据画像版本 ${version} 创建新的当前版本吗？`, "确认回退画像"))) return;
  try {
    await callApi("restore_profile_version", state.profile.selectedPersonId, version);
    await loadProfileRoute();
    showToast(`已根据版本 ${version} 创建新的当前画像。`);
  } catch (error) {
    showToast(error.message);
  }
}

async function chooseExportDir() {
  captureExportDir();
  try {
    const result = await callApi("choose_directory", state.profile.exportDir || state.settings?.output_dir || "");
    if (!result.cancelled && result.paths?.[0]) {
      state.profile.exportDir = result.paths[0];
      render();
    }
  } catch (error) {
    showToast(error.message);
  }
}

async function exportPerson(format) {
  captureExportDir();
  try {
    const result = await callApi("export_person", state.profile.selectedPersonId, format, state.profile.exportDir);
    showToast(`已保存：${result.path}`);
  } catch (error) {
    showToast(error.message);
  }
}

async function chooseDatabaseFile() {
  try {
    const result = await callApi("choose_file", state.profile.exportDir || state.settings?.database_dir || "", ["SQLite database (*.db;*.sqlite;*.sqlite3)", "All files (*.*)"], false);
    if (!result.cancelled && result.paths?.[0]) {
      state.profile.importPath = result.paths[0];
      state.profile.importConfirmed = false;
      render();
    }
  } catch (error) {
    showToast(error.message);
  }
}

async function importDatabase() {
  state.profile.importPath = ($("#database-import-path")?.value || "").trim();
  if (!state.profile.importPath || !(await app.confirmAction("导入会替换当前人物画像库中的全部数据，是否继续？", "确认导入数据库"))) return;
  try {
    await callApi("import_database", state.profile.importPath, true);
    state.profile.selectedPersonId = null;
    state.profile.workspace = null;
    state.profile.importPath = "";
    state.profile.importConfirmed = false;
    await loadProfileRoute();
    showToast("数据库导入成功。");
  } catch (error) {
    showToast(error.message);
  }
}


  const profileApi = {
    renderProfileRoute,
    loadProfileRoute,
    selectPerson,
    openPersonForm,
    savePerson,
    deleteCurrentPerson,
    previewSelectedMaterial,
    captureMaterialForm,
    validateMaterialForm,
    chooseMaterialFile,
    startMaterialAnalysis,
    startPrediction,
    startPredictionReview,
    cancelActiveTask,
    deletePrediction,
    rebuildProfile,
    restoreProfile,
    chooseExportDir,
    exportPerson,
    chooseDatabaseFile,
    importDatabase,
    toggleProfileEvidence,
  };
  app.profile = profileApi;
  Object.assign(app, profileApi);
})();
