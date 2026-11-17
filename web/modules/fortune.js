(() => {
  "use strict";

  const app = window.ProphetApp;
  const {
    state,
    $,
    ROUTES,
    escapeHtml,
    textHtml,
    formatTimestamp,
    dateTimeInputValue,
    callApi,
    taskBusy,
  } = app;
  const render = (...args) => app.render?.(...args);
  const showToast = (...args) => app.showToast?.(...args);
  const setFieldError = (...args) => app.setFieldError?.(...args);

const FORTUNE_FALLBACK_LABELS = {
  "zhouyi-textual": "周易经义",
  "meihua-yishu": "梅花易数",
  "liuyao-najia": "京房纳甲六爻",
  "bazi-ziping": "子平八字",
  "ziwei": "紫微斗数",
  "qimen": "奇门遁甲",
  "liuren": "大六壬",
};
const FORTUNE_STATUS_LABELS = { open: "待复盘", hit: "命中", miss: "未命中", partial: "部分符合", unknown: "无法判断" };

function fortuneEngineLabel(engine) {
  return state.fortune.workspace?.engines?.[engine] || FORTUNE_FALLBACK_LABELS[engine] || engine || "未知术式";
}

function fortuneCategoryLabel(category) {
  return state.fortune.workspace?.categories?.[category] || { other: "其他", career: "事业", finance: "财务", relationship: "关系", travel: "出行", "lost-item": "失物" }[category] || category || "其他";
}

function fortunePolicyLabel(policy) {
  return state.fortune.workspace?.policies?.[policy] || policy || "默认策略";
}

function fortuneOptionList(items, selected, labels = {}) {
  return Object.entries(items || {}).map(([key, label]) => `<option value="${escapeHtml(key)}" ${String(key) === String(selected) ? "selected" : ""}>${escapeHtml(labels[key] || label || key)}</option>`).join("");
}

function fortuneEngineCards() {
  const engines = state.fortune.workspace?.engines || FORTUNE_FALLBACK_LABELS;
  return Object.entries(engines).map(([id, label]) => `<button class="fortune-method-card fortune-method-${escapeHtml(id)} ${state.fortune.engine === id ? "is-active" : ""}" type="button" data-fortune-engine="${escapeHtml(id)}" aria-pressed="${state.fortune.engine === id}"><span class="fortune-method-glyph">${escapeHtml(id === "zhouyi-textual" ? "卦" : id === "meihua-yishu" ? "梅" : id === "liuyao-najia" ? "爻" : id === "bazi-ziping" ? "柱" : id === "ziwei" ? "曜" : id === "qimen" ? "局" : "课")}</span><span><strong>${escapeHtml(label)}</strong><small>${escapeHtml({ "zhouyi-textual": "经义", "meihua-yishu": "体用", "liuyao-najia": "纳甲", "bazi-ziping": "四柱", ziwei: "十二宫", qimen: "九宫", liuren: "四课三传" }[id] || "研究模式")}</small></span></button>`).join("");
}

function fortuneTimeField(label, id, value, required = true) {
  const current = dateTimeInputValue();
  const inputValue = dateTimeInputValue(value);
  const invalid = Boolean(inputValue && inputValue > current);
  return `<label class="field"><span>${escapeHtml(label)}${required ? "" : " <em>可选</em>"}</span><input id="${escapeHtml(id)}" type="datetime-local" max="${current}" value="${escapeHtml(inputValue)}" aria-describedby="${escapeHtml(id)}-error" ${required ? "required" : ""} /><small id="${escapeHtml(id)}-error" class="field-error" role="alert" ${invalid ? "" : "hidden"}>${escapeHtml(label)}不能晚于当前时间。</small></label>`;
}

function fortuneLinesField(prefix, values) {
  const lines = Array.isArray(values) ? values : [7, 7, 7, 7, 7, 7];
  return `<div class="fortune-line-grid">${lines.map((line, index) => `<label class="field"><span>第 ${index + 1} 爻</span><select id="${escapeHtml(prefix)}-${index + 1}"><option value="6" ${Number(line) === 6 ? "selected" : ""}>6 · 老阴</option><option value="7" ${Number(line) === 7 ? "selected" : ""}>7 · 少阳</option><option value="8" ${Number(line) === 8 ? "selected" : ""}>8 · 少阴</option><option value="9" ${Number(line) === 9 ? "selected" : ""}>9 · 老阳</option></select></label>`).join("")}</div>`;
}

function fortuneProfileFields() {
  const f = state.fortune;
  const v = f.values;
  const profiles = f.profiles || [];
  const profileOptions = profiles.map((profile) => `<option value="${escapeHtml(profile.id)}" ${profile.id === v.profileId ? "selected" : ""}>${escapeHtml(profile.display_name || "未命名档案")} · ${escapeHtml((f.workspace?.genders || {})[profile.gender] || profile.gender || "未指定")}</option>`).join("");
  const source = `<label class="field field-wide"><span>命主信息来源</span><select id="fortune-profile-mode"><option value="manual" ${v.profileMode !== "profile" ? "selected" : ""}>手动输入</option><option value="profile" ${v.profileMode === "profile" ? "selected" : ""}>命主档案</option></select></label>`;
  if (v.profileMode === "profile") {
    return `${source}<label class="field field-wide"><span>选择档案</span><select id="fortune-profile-id" ${profiles.length ? "required" : "disabled"}>${profiles.length ? profileOptions : "<option>暂无命主档案</option>"}</select></label>${profiles.length ? "" : `<div class="notice notice-warning field-wide">还没有命主档案，请切换为“手动输入”，或在下方“命主档案”标签建立档案。</div>`}`;
  }
  return `${source}${fortuneTimeField("出生时间", "fortune-birth-at", v.birthAt)}<label class="field"><span>性别</span><select id="fortune-gender">${fortuneOptionList(f.workspace?.genders || { unspecified: "未指定", male: "男", female: "女" }, v.gender)}</select></label>`;
}

function renderFortuneInputFields() {
  const f = state.fortune;
  const v = f.values;
  const engine = f.engine;
  if (engine === "zhouyi-textual") {
    return `<div class="field field-wide"><span>起卦方式</span><div class="mode-switch mode-switch-wide" role="tablist" aria-label="周易起卦方式"><button class="mode-button ${v.zhouyiMode === "auto" ? "is-active" : ""}" type="button" data-fortune-mode="zhouyi-auto">自动起卦</button><button class="mode-button ${v.zhouyiMode === "manual" ? "is-active" : ""}" type="button" data-fortune-mode="zhouyi-manual">手动六爻</button></div></div>${v.zhouyiMode === "manual" ? fortuneLinesField("fortune-line", v.lines) : `<div class="inline-hint">自动生成六爻；若要复盘固定输入，可切换为手动六爻。</div>`}${fortuneTimeField("起盘时间", "fortune-cast-at", v.castAt)}`;
  }
  if (engine === "meihua-yishu") {
    const method = v.meihuaMethod || "time";
    return `<div class="field field-wide"><span>起卦方式</span><div class="mode-switch mode-switch-wide" role="tablist" aria-label="梅花易数起卦方式"><button class="mode-button ${method === "time" ? "is-active" : ""}" type="button" data-fortune-mode="meihua-time">时间起卦</button><button class="mode-button ${method === "number" ? "is-active" : ""}" type="button" data-fortune-mode="meihua-number">数字起卦</button><button class="mode-button ${method === "manual" ? "is-active" : ""}" type="button" data-fortune-mode="meihua-manual">手动起卦</button></div></div>${method === "time" ? fortuneTimeField("起盘时间", "fortune-cast-at", v.castAt) : `<div class="form-grid ${method === "manual" ? "meihua-manual-grid" : ""}"><label class="field"><span>上卦数</span><input id="fortune-upper" type="number" min="1" max="${method === "manual" ? "8" : "999"}" step="1" value="${escapeHtml(v.upper)}" required /><small id="fortune-upper-error" class="field-error" role="alert" hidden></small></label><label class="field"><span>下卦数</span><input id="fortune-lower" type="number" min="1" max="${method === "manual" ? "8" : "999"}" step="1" value="${escapeHtml(v.lower)}" required /><small id="fortune-lower-error" class="field-error" role="alert" hidden></small></label>${method === "manual" ? `<label class="field"><span>动爻</span><input id="fortune-moving" type="number" min="1" max="6" step="1" value="${escapeHtml(v.moving)}" required /><small id="fortune-moving-error" class="field-error" role="alert" hidden></small></label>` : ""}</div>`}`;
  }
  if (engine === "liuyao-najia") {
    return `<div class="field field-wide"><span>起卦方式</span><div class="mode-switch mode-switch-wide" role="tablist" aria-label="京房纳甲起卦方式"><button class="mode-button ${v.liuyaoMode !== "manual" ? "is-active" : ""}" type="button" data-fortune-mode="liuyao-coins">自动起卦</button><button class="mode-button ${v.liuyaoMode === "manual" ? "is-active" : ""}" type="button" data-fortune-mode="liuyao-manual">手动六爻</button></div></div>${v.liuyaoMode === "manual" ? fortuneLinesField("fortune-line", v.lines) : ""}<label class="field"><span>指定用神爻 <em>可选</em></span><select id="fortune-use-god"><option value="" ${!v.useGodLine ? "selected" : ""}>自动列出候选</option>${[1, 2, 3, 4, 5, 6].map((line) => `<option value="${line}" ${Number(v.useGodLine) === line ? "selected" : ""}>第 ${line} 爻</option>`).join("")}</select></label>${fortuneTimeField("起盘时间", "fortune-cast-at", v.castAt)}`;
  }
  if (engine === "bazi-ziping" || engine === "ziwei") {
    return `${fortuneProfileFields()}${engine === "bazi-ziping" ? `<label class="field"><span>大运方向</span><select id="fortune-luck-direction">${fortuneOptionList(f.workspace?.luck_directions || { "auto-gender-year-stem": "自动判断", forward: "顺行", backward: "逆行" }, v.luckDirection)}</select></label>` : ""}<label class="field"><span>流年数量</span><input id="fortune-flow-count" type="number" min="1" max="50" value="${escapeHtml(v.flowYearCount)}" /><small id="fortune-flow-count-error" class="field-error" role="alert" hidden></small></label>${engine === "ziwei" ? `<label class="field"><span>流年起始年 <em>可选</em></span><input id="fortune-flow-start" type="number" min="1900" max="2500" value="${escapeHtml(v.flowYearStart)}" placeholder="按出生年起算" /><small id="fortune-flow-start-error" class="field-error" role="alert" hidden></small></label>` : ""}`;
  }
  return fortuneTimeField("起盘时间", "fortune-cast-at", v.castAt);
}

function captureFortuneForm() {
  const form = $("#fortune-form");
  if (!form) return;
  const f = state.fortune;
  const v = f.values;
  f.question = $("#fortune-question", form)?.value || "";
  f.category = $("#fortune-category", form)?.value || f.category;
  f.policy = $("#fortune-policy", form)?.value || f.policy;
  const get = (id) => $(id, form)?.value;
  if ($("#fortune-cast-at", form)) v.castAt = get("#fortune-cast-at") || "";
  if ($("#fortune-birth-at", form)) v.birthAt = get("#fortune-birth-at") || "";
  if ($("#fortune-gender", form)) v.gender = get("#fortune-gender") || "unspecified";
  if ($("#fortune-profile-mode", form)) v.profileMode = get("#fortune-profile-mode") || "manual";
  if ($("#fortune-profile-id", form)) v.profileId = get("#fortune-profile-id") || "";
  if ($("#fortune-use-god", form)) v.useGodLine = get("#fortune-use-god") || "";
  if ($("#fortune-upper", form)) v.upper = get("#fortune-upper") || "";
  if ($("#fortune-lower", form)) v.lower = get("#fortune-lower") || "";
  if ($("#fortune-moving", form)) v.moving = get("#fortune-moving") || "";
  if ($("#fortune-luck-direction", form)) v.luckDirection = get("#fortune-luck-direction") || "auto-gender-year-stem";
  if ($("#fortune-flow-count", form)) v.flowYearCount = get("#fortune-flow-count") || 12;
  if ($("#fortune-flow-start", form)) v.flowYearStart = get("#fortune-flow-start") || "";
  if ($("#fortune-line-1", form)) v.lines = [1, 2, 3, 4, 5, 6].map((index) => Number(get(`#fortune-line-${index}`)));
}

function validateFortuneNumberField(input) {
  if (!input || input.type !== "number" || !input.id.startsWith("fortune-")) return;
  const value = input.value.trim();
  const min = Number(input.min);
  const max = Number(input.max);
  const valid = !value || (Number.isInteger(Number(value)) && Number(value) >= min && Number(value) <= max);
  const label = input.closest("label")?.querySelector(":scope > span")?.textContent?.replace(/可选.*/, "").trim() || "此项";
  setFieldError(input, !value && input.required ? `请填写${label}。` : valid ? "" : `请输入 ${min}–${max} 的整数。`);
}

function validateFortuneTimeField(input) {
  if (!input || input.type !== "datetime-local" || !input.id.startsWith("fortune-")) return;
  input.max = dateTimeInputValue();
  const label = input.closest("label")?.querySelector(":scope > span")?.textContent?.replace(/可选.*/, "").trim() || "时间";
  const message = !input.value && input.required
    ? `请填写${label}。`
    : input.value && input.max && input.value > input.max ? `${label}不能晚于当前时间。` : "";
  setFieldError(input, message);
}

function fortunePayload() {
  captureFortuneForm();
  const f = state.fortune;
  const v = { ...f.values };
  delete v.zhouyiMode;
  delete v.meihuaMethod;
  delete v.liuyaoMode;
  delete v.profileMode;
  if (f.engine === "meihua-yishu") v.method = f.values.meihuaMethod;
  if (f.engine === "zhouyi-textual" && f.values.zhouyiMode !== "manual") delete v.lines;
  if (f.engine === "liuyao-najia" && f.values.liuyaoMode !== "manual") delete v.lines;
  if (f.engine !== "meihua-yishu" || f.values.meihuaMethod !== "manual") delete v.moving;
  if (f.engine === "meihua-yishu" && f.values.meihuaMethod !== "time") delete v.castAt;
  if (f.engine !== "ziwei") delete v.flowYearStart;
  if (f.engine === "ziwei") v.fixLeap = true;
  if ((f.engine === "bazi-ziping" || f.engine === "ziwei") && f.values.profileMode !== "profile") {
    delete v.profileId;
    delete v.displayName;
  }
  if (f.engine !== "bazi-ziping" && f.engine !== "ziwei") {
    delete v.birthAt;
    delete v.gender;
    delete v.profileId;
    delete v.displayName;
    delete v.luckDirection;
    delete v.fixLeap;
    delete v.flowYearCount;
  }
  if (f.engine !== "bazi-ziping") delete v.luckDirection;
  return { engine: f.engine, question: f.question, category: f.category, policy: f.policy, timezone: state.settings?.timezone || "Asia/Shanghai", values: v };
}

function renderFortuneFactTables(facts) {
  if (facts.engineId === "qimen" && Array.isArray(facts.palaces)) {
    return `<div class="qimen-grid">${facts.palaces.map((cell) => `<article class="qimen-cell ${cell.isCenter ? "is-center" : ""} ${cell.isValueStar || cell.isValueGate ? "is-marked" : ""}" style="grid-row:${Number(cell.row) || 1};grid-column:${Number(cell.column) || 1};"><span class="qimen-palace">${escapeHtml(cell.palace)} 宫</span><strong>${escapeHtml(cell.heavenlyStem || "")}</strong><div>${escapeHtml(cell.star || "")}</div><div>${escapeHtml(cell.gate || "")}</div><small>${escapeHtml(cell.spirit || "")}${cell.isVoid ? " · 空亡" : ""}${cell.isHorse ? " · 驿马" : ""}</small></article>`).join("")}</div>`;
  }
  if (facts.engineId === "ziwei" && Array.isArray(facts.palaces)) {
    return `<div class="fortune-table-wrap"><table class="fortune-table"><thead><tr><th>宫位</th><th>天干地支</th><th>主星</th><th>辅星 / 杂曜</th><th>大限</th></tr></thead><tbody>${facts.palaces.map((palace) => `<tr><td><strong>${escapeHtml(palace.name || "")}</strong>${palace.isBodyPalace ? " · 身宫" : ""}${palace.isOriginalPalace ? " · 本命" : ""}</td><td>${escapeHtml(`${palace.heavenlyStem || ""}${palace.earthlyBranch || ""}`)}</td><td>${escapeHtml((palace.majorStars || []).map((star) => star.name || "").join("、") || "无")}</td><td>${escapeHtml([...(palace.minorStars || []), ...(palace.adjectiveStars || [])].map((star) => star.name || "").join("、") || "无")}</td><td>${escapeHtml((palace.decadal?.range || []).length ? `${palace.decadal.range[0]}—${palace.decadal.range.at(-1)}岁` : "")}</td></tr>`).join("")}</tbody></table></div>`;
  }
  if (facts.engineId === "bazi-ziping" && facts.pillars) {
    const pillars = Object.values(facts.pillars);
    const flow = Array.isArray(facts.flowYears) ? facts.flowYears : [];
    return `<div class="bazi-pillar-grid">${pillars.map((pillar) => `<article class="bazi-pillar"><span>${escapeHtml(pillar.label || "")}</span><strong>${escapeHtml(`${pillar.ganZhi?.stem || ""}${pillar.ganZhi?.branch || ""}`)}</strong><small>${escapeHtml(pillar.naYin || "")}</small><em>${escapeHtml(pillar.stem?.tenGod || "")}</em></article>`).join("")}</div>${flow.length ? `<div class="fortune-table-wrap"><table class="fortune-table"><thead><tr><th>流年</th><th>干支</th><th>年龄</th><th>纳音</th></tr></thead><tbody>${flow.map((item) => `<tr><td>${escapeHtml(item.year)}</td><td>${escapeHtml(`${item.ganZhi?.stem || ""}${item.ganZhi?.branch || ""}`)}</td><td>${escapeHtml(item.age)}</td><td>${escapeHtml(item.naYin || "")}</td></tr>`).join("")}</tbody></table></div>` : ""}`;
  }
  if (facts.engineId === "liuyao-najia" && Array.isArray(facts.linesDetail)) {
    return `<div class="fortune-table-wrap"><table class="fortune-table"><thead><tr><th>爻</th><th>纳甲</th><th>六亲</th><th>六神</th><th>状态</th><th>世应</th></tr></thead><tbody>${facts.linesDetail.map((line) => `<tr><td>${escapeHtml(line.line)}</td><td>${escapeHtml(`${line.stem || ""}${line.branch || ""}`)}</td><td>${escapeHtml(line.relation || "")}</td><td>${escapeHtml(line.spirit || "")}</td><td>${escapeHtml(`${line.seasonalStrength || ""}${line.inXunKong ? " · 旬空" : ""}`)}</td><td>${line.isShi ? "世" : line.isYing ? "应" : ""}</td></tr>`).join("")}</tbody></table></div>`;
  }
  if (facts.engineId === "liuren" && Array.isArray(facts.lessons)) {
    return `<div class="fortune-table-wrap"><table class="fortune-table"><thead><tr><th>课序</th><th>地盘</th><th>天盘</th></tr></thead><tbody>${facts.lessons.map((lesson) => `<tr><td>${escapeHtml(lesson.number)}</td><td>${escapeHtml(lesson.lower || "")}</td><td>${escapeHtml(lesson.upper || "")}</td></tr>`).join("")}</tbody></table></div><div class="transmission-row">${(facts.transmissions || []).map((item) => `<span><small>${escapeHtml(item.stage || "")}</small><strong>${escapeHtml(item.branch || "")}</strong><em>${escapeHtml(item.general || "")}</em></span>`).join("")}</div>`;
  }
  return "";
}

function renderFortuneFacts(facts) {
  if (!facts || typeof facts !== "object") return `<div class="fortune-result-empty"><span class="status-badge">暂无结果</span><h3>先完成一次起盘</h3><p>上方提交后，结构化盘面会在这里展开。</p></div>`;
  const metrics = [];
  if (facts.primary) {
    metrics.push(["本卦", `${facts.primary.number} · ${facts.primary.nameSimplified || facts.primary.nameTraditional || ""}`]);
    if (facts.changed) metrics.push(["变卦", `${facts.changed.number} · ${facts.changed.nameSimplified || facts.changed.nameTraditional || ""}`]);
    metrics.push(["动爻", Array.isArray(facts.movingLines) && facts.movingLines.length ? facts.movingLines.join("、") : "无"]);
    if (facts.fiveElements) metrics.push(["体 / 用", `${facts.fiveElements.body || ""} / ${facts.fiveElements.use || ""}`]);
    if (facts.fiveElements?.relation) metrics.push(["体用关系", facts.fiveElements.relation]);
  } else if (facts.pillars) {
    metrics.push(["日主", `${facts.dayMaster?.stem || ""} · ${facts.dayMaster?.element || ""}`]);
    metrics.push(["四柱", Object.values(facts.pillars).map((item) => `${item.ganZhi?.stem || ""}${item.ganZhi?.branch || ""}`).join(" / ")]);
    metrics.push(["流年", Array.isArray(facts.flowYears) ? facts.flowYears.length : 0]);
  } else if (facts.setup) {
    metrics.push(["局式", facts.setup.juLabel || ""]);
    metrics.push(["遁局", facts.setup.dun || ""]);
    metrics.push(["值符 / 值使", `${facts.value?.valueStar || ""} / ${facts.value?.valueGate || ""}`]);
  } else if (facts.course) {
    metrics.push(["课体", facts.course.name || ""]);
    metrics.push(["月将", facts.monthGeneral?.branch || ""]);
    metrics.push(["三传", (facts.transmissions || []).map((item) => item.branch || "").join(" · ")]);
  } else if (facts.fiveElements) {
    metrics.push(["体用", `${facts.fiveElements.body || ""} / ${facts.fiveElements.use || ""}`]);
    metrics.push(["关系", facts.fiveElements.relation || ""]);
  }
  const profile = facts.birth?.displayName ? `<div class="fortune-fact-tags"><span class="tag">命主：${escapeHtml(facts.birth.displayName)}</span></div>` : "";
  return `<div class="fortune-metric-grid">${metrics.map(([label, value]) => `<div class="fortune-metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("")}</div>${profile}${renderFortuneFactTables(facts)}`;
}

function renderFortuneTask() {
  const task = state.fortune.activeTask;
  if (!task) return "";
  const status = task.task?.status || "queued";
  const busy = status === "queued" || status === "running";
  const message = status === "failed" ? task.task?.error?.message || "任务失败。" : status === "cancelled" ? "任务已取消。" : busy ? "模型正在本机后台处理，盘面事实不会被覆盖。" : "解读已保存到当前历史记录。";
  return `<section class="task-card surface-card ${status === "failed" ? "is-error" : status === "succeeded" ? "is-done" : "is-pending"}" aria-live="polite"><div class="task-head"><div><h3>模型解读</h3></div><span class="status-badge">${escapeHtml({ queued: "排队中", running: "进行中", succeeded: "已完成", failed: "失败", cancelled: "已取消" }[status] || status)}</span></div>${busy ? `<div class="task-progress" role="progressbar" aria-label="模型解读进行中"><span></span></div>` : ""}<p class="task-detail">${textHtml(message)}</p></section>`;
}

function renderFortuneResult() {
  const f = state.fortune;
  if (!f.facts) return `<section class="fortune-result-card surface-card"><div class="fortune-result-empty"><h2>结果会在这里展开</h2><p>在上方选定术式和输入，或者从历史记录中导入。</p></div></section>`;
  const modelConfigured = Boolean(state.settings?.llm_configured);
  const busy = taskBusy(f.activeTask?.task);
  const reportDir = f.reportDir || state.settings?.output_dir || "";
  return `<section class="fortune-result-card surface-card"><div class="fortune-result-header"><div><h2>${escapeHtml(f.question || "未命名占测")}</h2><p>${escapeHtml(fortuneEngineLabel(f.engine))} · ${escapeHtml(fortuneCategoryLabel(f.category))} · ${escapeHtml(fortunePolicyLabel(f.policy))}</p></div></div><div class="fortune-facts">${renderFortuneFacts(f.facts)}</div><label class="field fortune-result-export"><span>保存位置</span><div class="material-file-import"><input id="fortune-report-dir" type="text" value="${escapeHtml(reportDir)}" placeholder="选择报告保存位置" /><button class="button button-secondary button-input" type="button" data-action="choose-fortune-report-dir">选择文件夹</button><button class="button button-secondary button-input" type="button" data-action="export-fortune-report" data-reading-id="${escapeHtml(f.readingId)}" ${reportDir.trim() ? "" : "disabled"}>导出报告</button></div></label><div class="fortune-result-actions"><button class="button button-secondary" type="button" data-action="interpret-fortune" ${modelConfigured && !busy ? "" : "disabled"}>${f.interpretation ? "再次生成解读" : "生成模型解读"}</button><button class="button button-secondary" type="button" data-action="toggle-fortune-interpretation" ${f.interpretation ? "" : "disabled"}>${f.interpretationExpanded ? "收起解读" : "展开解读"}</button><button class="button button-secondary" type="button" data-action="prompt-fortune">${f.prompt && f.promptExpanded ? "收起agent提示词" : "展开agent提示词"}</button></div>${!modelConfigured ? `<div class="notice notice-warning">尚未配置模型；盘面事实、历史和 agent 提示词仍可使用。</div>` : ""}${f.interpretation && f.interpretationExpanded ? `<section class="fortune-interpretation"><div class="section-heading"><div><h3>模型解读</h3></div></div><div class="markdown-copy">${textHtml(f.interpretation)}</div></section>` : ""}${f.prompt && f.promptExpanded ? `<section class="fortune-prompt"><div class="section-heading"><div><h3>agent 提示词</h3></div><button class="button button-secondary button-small" type="button" data-action="copy-fortune-prompt">复制</button></div><pre>${escapeHtml(f.prompt)}</pre></section>` : ""}</section>${renderFortuneTask()}`;
}

function fortuneHistoryItem(reading) {
  const run = reading.runs?.[0] || {};
  return `<article class="fortune-history-card surface-card"><div class="fortune-history-card-head"><div><h2>${escapeHtml(reading.question || "未命名占测")}</h2><p>${escapeHtml(fortuneCategoryLabel(reading.category))} · ${escapeHtml(formatTimestamp(reading.created_at))}</p><div class="tag-row"><span class="tag">${escapeHtml(fortuneEngineLabel(run.engine_id))}</span></div></div><div class="card-actions"><button class="button button-secondary" type="button" data-action="view-fortune-history" data-reading-id="${escapeHtml(reading.id)}">查看结果</button><button class="button button-secondary" type="button" data-action="export-fortune-report" data-reading-id="${escapeHtml(reading.id)}">导出报告</button><button class="button button-secondary" type="button" data-action="delete-fortune-history" data-reading-id="${escapeHtml(reading.id)}">删除</button></div></div></article>`;
}

function selectedFortuneHistory() {
  return (state.fortune.history || []).find((item) => item.id === state.fortune.selectedHistoryId) || state.fortune.history?.[0] || null;
}

function renderFortuneHistory() {
  const f = state.fortune;
  return `<div class="fortune-history-layout"><section class="fortune-history-heading surface-card"><div class="section-heading"><div><h2>历史记录</h2><p>每一条记录都保留输入和结构化盘面。</p></div></div></section>${f.history.length ? f.history.map(fortuneHistoryItem).join("") : `<div class="empty-panel compact-empty surface-card"><h3>还没有历史记录</h3><p>完成一次起盘后，结果会自动进入这里。</p></div>`}</div>`;
}

function renderFortuneReview() {
  const f = state.fortune;
  const selectedId = f.readingId || f.history[0]?.id || "";
  const claimCards = f.claims.length ? f.claims.map((claim) => `<article class="fortune-claim-card"><div class="claim-head"><div><h3>${textHtml(claim.statement || "")}</h3></div><span class="status-badge ${claim.status === "hit" ? "is-done" : claim.status === "open" ? "is-pending" : ""}">${escapeHtml(FORTUNE_STATUS_LABELS[claim.status] || claim.status || "待复盘")}</span></div><p>目标日期：${escapeHtml(claim.target_at || "未记录")}</p><form class="fortune-outcome-form" data-form="fortune-outcome" data-claim-id="${escapeHtml(claim.id)}"><div class="form-grid"><label class="field"><span>结果</span><select id="fortune-status-${escapeHtml(claim.id)}">${["hit", "miss", "partial", "unknown"].map((status) => `<option value="${status}" ${claim.status === status ? "selected" : ""}>${escapeHtml(FORTUNE_STATUS_LABELS[status])}</option>`).join("")}</select></label><label class="field field-wide"><span>观察记录</span><textarea id="fortune-note-${escapeHtml(claim.id)}" placeholder="实际发生了什么？">${escapeHtml(claim.note || "")}</textarea></label></div><div class="form-actions"><button class="button button-secondary" type="submit">保存复盘结果</button></div></form></article>`).join("") : `<div class="empty-panel compact-empty"><h3>还没有预测陈述</h3><p>在当前盘面下锁定一个具体、可观察的陈述，事情发生后再回来记录。</p></div>`;
  return `<div class="fortune-review-layout"><section class="fortune-review-create surface-card"><div class="section-heading"><div><h2>锁定一条可验证陈述</h2><p>复盘只记录发生了什么，不把结果倒写回当时的盘面。</p></div></div>${f.history.length ? `<form id="fortune-claim-form"><label class="field"><span>关联盘面</span><select id="fortune-claim-reading">${f.history.map((item) => `<option value="${escapeHtml(item.id)}" ${item.id === selectedId ? "selected" : ""}>${escapeHtml(item.question || "未命名占测")} · ${escapeHtml(fortuneEngineLabel(item.runs?.[0]?.engine_id))}</option>`).join("")}</select></label><label class="field field-wide"><span>可验证的预测陈述</span><textarea id="fortune-claim-statement" required placeholder="例如：在本周内完成一次明确的沟通，并得到对方回复。"></textarea></label><label class="field"><span>目标日期</span><input id="fortune-claim-target" type="date" required /></label><div class="form-actions"><button class="button button-primary" type="submit">锁定预测</button></div></form>` : `<div class="notice notice-info">先完成一次起盘，再锁定预测。</div>`}</section><section class="fortune-claims-list"><div class="section-heading"><div><h2>复盘记录</h2></div><span class="count-badge">${f.claims.length}</span></div>${claimCards}</section></div>`;
}

function renderFortuneProfileForm() {
  const f = state.fortune;
  if (!f.profileDraft) return "";
  const draft = f.profileDraft;
  const editing = Boolean(f.profileEditingId);
  const content = `<div class="section-heading"><div><h2>${editing ? "修改命主档案" : "新建命主档案"}</h2><p>档案只保存起盘需要的出生信息，不与人物画像数据库相连。</p></div></div><form id="fortune-profile-form"><div class="form-grid"><label class="field"><span>姓名或代称</span><input id="fortune-profile-name" type="text" maxlength="200" value="${escapeHtml(draft.display_name || "")}" required /></label><label class="field"><span>性别</span><select id="fortune-profile-gender">${fortuneOptionList(f.workspace?.genders || { unspecified: "未指定", male: "男", female: "女" }, draft.gender || "unspecified")}</select></label>${fortuneTimeField("出生时间", "fortune-profile-birth", draft.birth_at)}<label class="field"><span>换日与年界</span><select id="fortune-profile-policy">${fortuneOptionList(f.workspace?.policies || {}, draft.time_policy_id || "traditional-zi-chu-li-chun-v1")}</select></label></div><div class="form-actions"><button class="button button-primary" type="submit">${editing ? "保存修改" : "保存档案"}</button><button class="button button-secondary" type="button" data-action="cancel-fortune-profile">取消</button></div></form>`;
  return editing ? `<div class="fortune-profile-inline-form">${content}</div>` : `<section class="fortune-profile-form surface-card">${content}</section>`;
}

function renderFortuneProfiles() {
  const f = state.fortune;
  const profiles = state.fortune.profiles || [];
  const newForm = f.profileDraft && !f.profileEditingId ? renderFortuneProfileForm() : "";
  const cards = profiles.map((profile) => `<article class="fortune-profile-card surface-card"><div class="fortune-profile-card-head"><div><h2>${escapeHtml(profile.display_name || "未命名档案")}</h2><p>${escapeHtml((f.workspace?.genders || {})[profile.gender] || profile.gender || "未指定")} · ${escapeHtml(formatTimestamp(profile.birth_at))}</p></div><div class="card-actions"><button class="button button-secondary" type="button" data-action="edit-fortune-profile" data-profile-id="${escapeHtml(profile.id)}">编辑</button><button class="button button-secondary" type="button" data-action="delete-fortune-profile" data-profile-id="${escapeHtml(profile.id)}">删除</button></div></div><div class="tag-row"><span class="tag">${escapeHtml(fortunePolicyLabel(profile.time_policy_id))}</span></div>${f.profileEditingId === profile.id ? renderFortuneProfileForm() : ""}</article>`).join("");
  return `<div class="fortune-profiles-layout"><section class="fortune-profile-heading surface-card"><div class="section-heading"><div><h2>命主档案</h2><p>用于八字和紫微起盘的可复用出生信息。</p></div><button class="button button-primary button-small" type="button" data-action="new-fortune-profile">新建档案</button></div></section>${newForm}${cards || `<div class="empty-panel compact-empty surface-card"><h3>还没有命主档案</h3><p>建立档案后，八字和紫微输入可以直接复用。</p></div>`}</div>`;
}

function renderFortuneKnowledge() {
  const f = state.fortune;
  const results = f.knowledgeResults || [];
  return `<div class="fortune-knowledge-layout"><section class="fortune-knowledge-search surface-card"><div class="section-heading"><div><h2>知识检索</h2><p>只检索随应用分发的本地语料，不临时抓取网页内容。</p></div></div><form id="fortune-knowledge-form"><div class="input-with-action"><input id="fortune-knowledge-query" type="search" value="${escapeHtml(f.knowledgeQuery)}" placeholder="例如：用神、四化、月将、卦辞" required /><button class="button button-primary button-input" type="submit">检索</button></div><label class="field"><span>限定术式 <em>可选</em></span><select id="fortune-knowledge-engine"><option value="" ${!f.knowledgeEngine ? "selected" : ""}>全部语料</option>${Object.entries(f.workspace?.engines || FORTUNE_FALLBACK_LABELS).map(([id, label]) => `<option value="${escapeHtml(id)}" ${f.knowledgeEngine === id ? "selected" : ""}>${escapeHtml(label)}</option>`).join("")}</select></label></form><div class="knowledge-results">${results.length ? results.map((row) => `<article class="knowledge-result"><div class="knowledge-result-head"><span class="tag">${escapeHtml(fortuneEngineLabel(row.engine))}</span><strong>${escapeHtml([row.work, row.section].filter(Boolean).join(" · ") || row.id || "来源段落")}</strong></div><p>${textHtml(row.textSimplified || row.textTraditional || row.content || row.result || "暂无正文")}</p>${row.sourcePage ? `<small>${escapeHtml(row.sourcePage)}</small>` : ""}</article>`).join("") : `<div class="empty-panel compact-empty"><h3>输入关键词开始检索</h3><p>搜索结果会显示来源段落与规则证据。</p></div>`}</div></section></div>`;
}

function renderFortuneData() {
  const f = state.fortune;
  const backupDir = f.dataBackupDir || state.settings?.output_dir || "";
  return `<div class="fortune-data-layout"><section class="fortune-db-status maintenance-card surface-card"><div class="section-heading"><div><h2>备份数据库</h2><p>选择保存位置，将当前数据库备份到本机。</p></div></div><div class="material-file-import"><input id="fortune-backup-dir" type="text" value="${escapeHtml(backupDir)}" placeholder="选择数据库备份保存位置" /><button class="button button-secondary button-input" type="button" data-action="choose-fortune-backup-dir">选择文件夹</button><button id="fortune-backup-submit" class="button button-secondary button-input" type="button" data-action="backup-fortune-db" ${backupDir.trim() ? "" : "disabled"}>备份</button></div></section><section class="fortune-db-import maintenance-card surface-card"><div class="section-heading"><div><h2>导入数据库</h2><p>导入会直接替换当前数据库。</p></div></div><div class="material-file-import"><input id="fortune-import-path" type="text" value="${escapeHtml(f.dataImportPath)}" placeholder="支持 .db、.sqlite、.sqlite3 文件" /><button class="button button-secondary button-input" type="button" data-action="choose-fortune-import-file">选择文件</button><button id="fortune-import-submit" class="button button-secondary button-input" type="button" data-action="import-fortune-db" ${f.dataImportPath.trim() ? "" : "disabled"}>导入</button></div></section></div>`;
}

function renderFortuneSecondary() {
  const tab = state.fortune.tab;
  if (tab === "review") return renderFortuneReview();
  if (tab === "profiles") return renderFortuneProfiles();
  if (tab === "knowledge") return renderFortuneKnowledge();
  if (tab === "data") return renderFortuneData();
  return renderFortuneHistory();
}

function renderFortuneTabs() {
  const tabs = [["history", "历史记录"], ["profiles", "命主档案"], ["knowledge", "规则检索"], ["data", "数据维护"]];
  return `<div class="fortune-tabs" role="tablist" aria-label="赛博算命工作区">${tabs.map(([key, label]) => `<button class="fortune-tab ${state.fortune.tab === key ? "is-active" : ""}" type="button" role="tab" aria-selected="${state.fortune.tab === key}" data-fortune-tab="${key}">${label}</button>`).join("")}</div>`;
}

function renderFortuneRoute() {
  const f = state.fortune;
  let body = "";
  if (!state.bridgeReady) {
    body = `<div class="empty-panel bridge-empty surface-card"><span class="status-badge">预览模式</span><h2>赛博算命工作区等待本地桥接</h2><p>在 Prophet 桌面窗口中打开后，七种术式和独立数据库会在这里载入。</p></div>`;
  } else if (f.loading && !f.workspace) {
    body = `<div class="page-loading" role="status">正在读取赛博算命工作区</div>`;
  } else if (f.error && !f.workspace) {
    body = `<div class="empty-panel bridge-empty surface-card"><span class="status-badge">读取失败</span><h2>赛博算命数据暂时不可用</h2><p>${textHtml(f.error)}</p><button class="button button-primary" type="button" data-action="reload-fortune">重新读取</button></div>`;
  } else {
    body = `<div class="fortune-layout"><div class="fortune-input-stack"><section class="fortune-input-card surface-card"><div class="fortune-input-heading"><div><h2>选择术式</h2><p>选择一种术式开始起盘。</p></div></div><div class="fortune-method-grid">${fortuneEngineCards()}</div></section><section class="fortune-input-card surface-card"><div class="fortune-input-heading"><div><h2>术式配置</h2><p>填写问题与当前术式所需配置。</p></div></div><form id="fortune-form"><div class="form-grid"><label class="field field-wide"><span>所问事项 <em>可选</em></span><input id="fortune-question" type="text" maxlength="2000" value="${escapeHtml(f.question)}" placeholder="把问题写得具体" /></label><label class="field"><span>分类</span><select id="fortune-category">${fortuneOptionList(f.workspace?.categories || { other: "其他", career: "事业", finance: "财务", relationship: "关系", travel: "出行", "lost-item": "失物" }, f.category)}</select></label><label class="field"><span>换日与年界</span><select id="fortune-policy">${fortuneOptionList(f.workspace?.policies || {}, f.policy)}</select></label></div><div class="fortune-dynamic-fields">${renderFortuneInputFields()}</div><div class="form-actions"><button class="button button-primary" type="submit">起盘并保存</button><button class="button button-secondary" type="button" data-action="clear-fortune-input">清空结果</button></div></form></section></div><div id="fortune-result-column" class="fortune-result-column">${renderFortuneResult()}</div></div>${renderFortuneTabs()}<section class="fortune-secondary">${renderFortuneSecondary()}</section>`;
  }
  if (f.error && f.workspace) body = `<div id="fortune-route-error" class="form-message is-error" role="alert">${textHtml(f.error)}</div>${body}`;
  const pageView = $("#page-view");
  const content = $("[data-route-content='fortune']", pageView);
  if (content) {
    content.innerHTML = body;
  } else {
    pageView.innerHTML = `<div class="page-intro"><div class="page-intro-copy"><div class="intro-mark">${ROUTES.fortune.icon}</div><div><span class="eyebrow">赛博算命 / FORTUNE TELLING</span><h1>赛博算命</h1><p>七种术式的算命预测，可复现盘面、证据检索。</p></div></div><div class="page-intro-actions"><span class="version-badge">独立 SQLite</span><button class="button button-secondary" type="button" data-open-settings="true">设置</button></div></div><div data-route-content="fortune">${body}</div>`;
  }
}


function applyFortuneWorkspace(data) {
  const f = state.fortune;
  f.workspace = data;
  f.history = data.readings || [];
  f.claims = data.claims || [];
  f.profiles = data.profiles || [];
  if (!f.selectedHistoryId || !f.history.some((item) => item.id === f.selectedHistoryId)) f.selectedHistoryId = f.history[0]?.id || null;
  if (!f.values.castAt) f.values.castAt = dateTimeInputValue();
  if (!f.dataBackupDir) f.dataBackupDir = state.settings?.output_dir || "";
}

async function loadFortuneRoute() {
  if (!state.bridgeReady) return;
  const f = state.fortune;
  f.loading = true;
  f.error = "";
  if (!f.workspace) render();
  try {
    applyFortuneWorkspace(await callApi("get_fortune_workspace"));
  } catch (error) {
    f.error = error.message;
  } finally {
    f.loading = false;
    render();
  }
}

async function refreshFortuneWorkspace() {
  applyFortuneWorkspace(await callApi("get_fortune_workspace"));
  await app.refreshHealth?.();
}

function resetFortuneCurrent() {
  const f = state.fortune;
  Object.assign(f, {
    error: "", facts: null, readingId: null, interpretation: "",
    interpretationExpanded: false, prompt: "", promptExpanded: false, activeTask: null,
  });
}

function resetFortuneForm() {
  const f = state.fortune;
  f.question = "";
  f.category = "other";
  f.policy = "traditional-zi-chu-li-chun-v1";
  f.values = {
    castAt: dateTimeInputValue(),
    birthAt: "",
    gender: "unspecified",
    zhouyiMode: "auto",
    lines: [7, 7, 7, 7, 7, 7],
    meihuaMethod: "time",
    upper: 1,
    lower: 1,
    moving: 1,
    liuyaoMode: "coins",
    useGodLine: "",
    profileMode: "profile",
    profileId: "",
    luckDirection: "auto-gender-year-stem",
    flowYearCount: 12,
    flowYearStart: "",
    fixLeap: true,
  };
  resetFortuneCurrent();
}

function selectFortuneEngine(engine) {
  captureFortuneForm();
  if (!FORTUNE_FALLBACK_LABELS[engine]) return;
  state.fortune.engine = engine;
  resetFortuneCurrent();
  render();
}

function setFortuneMode(mode) {
  captureFortuneForm();
  if (mode === "zhouyi-auto" || mode === "zhouyi-manual") state.fortune.values.zhouyiMode = mode.endsWith("manual") ? "manual" : "auto";
  if (mode.startsWith("meihua-")) state.fortune.values.meihuaMethod = mode.slice("meihua-".length);
  if (mode === "liuyao-coins" || mode === "liuyao-manual") state.fortune.values.liuyaoMode = mode.endsWith("manual") ? "manual" : "coins";
  render();
}

async function startFortune(event) {
  event?.preventDefault();
  const f = state.fortune;
  f.error = "";
  try {
    const result = await callApi("calculate_fortune", fortunePayload());
    Object.assign(f, {
      engine: result.engine, question: result.question, category: result.category,
      facts: result.facts, readingId: result.reading_id, interpretation: "",
      interpretationExpanded: false, prompt: "", promptExpanded: false,
    });
    await refreshFortuneWorkspace();
    f.selectedHistoryId = result.reading_id;
    render();
    showToast("盘面已保存到赛博算命数据库。");
  } catch (error) {
    f.error = error.message;
    render();
  }
}

function useFortuneReading(item, replay = false) {
  if (!item) return;
  const f = state.fortune;
  const run = item.runs?.[0] || {};
  const input = run.input || {};
  f.engine = run.engine_id || f.engine;
  f.question = item.question || "";
  f.category = item.category || "other";
  f.policy = input.timePolicyId || f.policy;
  f.values.castAt = input.castAt || f.values.castAt;
  f.values.birthAt = input.birthAt || f.values.birthAt;
  f.values.gender = input.gender || f.values.gender;
  f.values.lines = Array.isArray(input.lines) ? input.lines.map(Number) : f.values.lines;
  f.values.zhouyiMode = Array.isArray(input.lines) ? "manual" : "auto";
  f.values.meihuaMethod = input.method || "time";
  f.values.upper = input.upper ?? f.values.upper;
  f.values.lower = input.lower ?? f.values.lower;
  f.values.moving = input.moving ?? input.movingLine ?? f.values.moving;
  f.values.liuyaoMode = Array.isArray(input.lines) ? "manual" : "coins";
  f.values.useGodLine = input.useGodLine ?? "";
  f.values.profileId = input.profileId || "";
  f.values.profileMode = input.profileId ? "profile" : "manual";
  f.values.luckDirection = input.luckDirection || f.values.luckDirection;
  f.values.flowYearCount = input.flowYearCount || f.values.flowYearCount;
  f.values.flowYearStart = input.flowYearStart || "";
  f.values.fixLeap = input.fixLeap !== false;
  f.selectedHistoryId = item.id;
  f.tab = "history";
  if (replay) {
    resetFortuneCurrent();
    f.tab = "history";
    render();
    showToast("已把历史输入带回上方，可修改后重新起盘。");
    return;
  }
  Object.assign(f, {
    facts: run.facts || null, readingId: item.id,
    interpretation: run.interpretations?.at(-1)?.content_markdown || "",
    interpretationExpanded: false, prompt: "", promptExpanded: false,
  });
  render();
  $("#fortune-result-column")?.scrollIntoView({ block: "start" });
}

function selectFortuneHistory(readingId) {
  state.fortune.selectedHistoryId = readingId;
  render();
}

async function interpretFortune() {
  const f = state.fortune;
  if (!f.readingId) return showToast("请先选择一条已保存的盘面。");
  try {
    const task = await callApi("start_fortune_interpretation", f.readingId);
    f.activeTask = { taskId: task.task_id, task };
    render();
    watchFortuneTask(task.task_id);
  } catch (error) {
    f.error = error.message;
    render();
  }
}

async function watchFortuneTask(taskId) {
  const f = state.fortune;
  if (!f.activeTask || f.activeTask.taskId !== taskId) return;
  try {
    const task = await callApi("get_task", taskId);
    if (!f.activeTask || f.activeTask.taskId !== taskId) return;
    f.activeTask.task = task;
    if (task.status === "succeeded") {
      f.interpretation = task.result?.content || f.interpretation;
      f.interpretationExpanded = false;
      await refreshFortuneWorkspace();
    }
    render();
    if (taskBusy(task)) window.setTimeout(() => watchFortuneTask(taskId), 500);
  } catch (error) {
    if (!f.activeTask || f.activeTask.taskId !== taskId) return;
    f.activeTask.task = { status: "failed", error: { message: error.message } };
    render();
  }
}

async function toggleFortunePrompt() {
  const f = state.fortune;
  if (!f.readingId) return showToast("请先选择一条已保存的盘面。");
  if (f.prompt) {
    f.promptExpanded = !f.promptExpanded;
    if (f.promptExpanded) f.interpretationExpanded = false;
    render();
    return;
  }
  try {
    const result = await callApi("get_fortune_agent_prompt", f.readingId);
    f.prompt = result.prompt || "";
    f.promptExpanded = true;
    f.interpretationExpanded = false;
    render();
  } catch (error) {
    f.error = error.message;
    render();
  }
}

function toggleFortuneInterpretation() {
  const f = state.fortune;
  if (!f.interpretation) return;
  f.interpretationExpanded = !f.interpretationExpanded;
  if (f.interpretationExpanded) f.promptExpanded = false;
  render();
}

function useFortuneForClaim() {
  state.fortune.tab = "review";
  render();
}

async function chooseFortuneReportDir() {
  try {
    const result = await callApi("choose_directory", state.fortune.reportDir || state.settings?.output_dir || "");
    if (!result.cancelled && result.paths?.[0]) {
      state.fortune.reportDir = result.paths[0];
      render();
    }
  } catch (error) {
    state.fortune.error = error.message;
    render();
  }
}

async function exportFortuneReport(readingId) {
  const item = (state.fortune.history || []).find((entry) => entry.id === readingId) || selectedFortuneHistory();
  if (!item) return showToast("请先选择一条历史记录。");
  state.fortune.reportDir = $("#fortune-report-dir")?.value || state.fortune.reportDir;
  try {
    const result = await callApi("export_fortune_reading", item.id, state.fortune.reportDir || state.settings?.output_dir || "");
    showToast(`报告已导出：${result.path}`);
  } catch (error) {
    state.fortune.error = error.message;
    render();
  }
}

async function deleteFortuneHistory(readingId) {
  const item = (state.fortune.history || []).find((entry) => entry.id === readingId) || selectedFortuneHistory();
  if (!item || !(await app.confirmAction(`确定删除“${item.question || "未命名占测"}”及其复盘吗？此操作不可撤销。`))) return;
  try {
    await callApi("delete_fortune_reading", item.id, true);
    resetFortuneCurrent();
    await refreshFortuneWorkspace();
    render();
    showToast("历史记录已删除。");
  } catch (error) {
    state.fortune.error = error.message;
    render();
  }
}

async function startFortuneClaim(event) {
  event.preventDefault();
  const readingId = $("#fortune-claim-reading")?.value || "";
  const statement = $("#fortune-claim-statement")?.value || "";
  const target = $("#fortune-claim-target")?.value || "";
  try {
    await callApi("create_fortune_claim", readingId, statement, target);
    await refreshFortuneWorkspace();
    render();
    showToast("预测陈述已锁定。");
  } catch (error) {
    state.fortune.error = error.message;
    render();
  }
}

async function saveFortuneOutcome(event) {
  event.preventDefault();
  const form = event.target;
  const claimId = form.dataset.claimId;
  const status = $("select", form)?.value || "unknown";
  const note = $("textarea", form)?.value || "";
  try {
    await callApi("save_fortune_outcome", claimId, status, note);
    await refreshFortuneWorkspace();
    render();
    showToast("复盘结果已保存。");
  } catch (error) {
    state.fortune.error = error.message;
    render();
  }
}

function openFortuneProfileForm(profileId = null) {
  const profile = profileId ? state.fortune.profiles.find((item) => item.id === profileId) : null;
  state.fortune.profileEditingId = profile?.id || null;
  state.fortune.profileDraft = profile ? { ...profile } : { display_name: "", gender: "unspecified", birth_at: "", time_policy_id: "traditional-zi-chu-li-chun-v1" };
  render();
  window.setTimeout(() => $("#fortune-profile-name")?.focus(), 0);
}

function captureFortuneProfileForm() {
  const form = $("#fortune-profile-form");
  if (!form || !state.fortune.profileDraft) return;
  Object.assign(state.fortune.profileDraft, {
    display_name: $("#fortune-profile-name", form)?.value || "",
    gender: $("#fortune-profile-gender", form)?.value || "unspecified",
    birth_at: $("#fortune-profile-birth", form)?.value || "",
    time_policy_id: $("#fortune-profile-policy", form)?.value || "traditional-zi-chu-li-chun-v1",
    timezone: state.settings?.timezone || "Asia/Shanghai",
  });
}

async function saveFortuneProfile(event) {
  event.preventDefault();
  captureFortuneProfileForm();
  const f = state.fortune;
  try {
    if (f.profileEditingId) await callApi("update_fortune_profile", f.profileEditingId, f.profileDraft);
    else await callApi("create_fortune_profile", f.profileDraft);
    f.profileDraft = null;
    f.profileEditingId = null;
    await refreshFortuneWorkspace();
    render();
    showToast("命主档案已保存。");
  } catch (error) {
    f.error = error.message;
    render();
  }
}

async function deleteFortuneProfile(profileId) {
  const profile = state.fortune.profiles.find((item) => item.id === profileId);
  if (!profile || !(await app.confirmAction(`确定删除“${profile.display_name || "未命名档案"}”吗？已保存的盘面不会被删除。`))) return;
  try {
    await callApi("delete_fortune_profile", profileId, true);
    await refreshFortuneWorkspace();
    render();
    showToast("命主档案已删除。");
  } catch (error) {
    state.fortune.error = error.message;
    render();
  }
}

async function searchFortuneKnowledge(event) {
  event.preventDefault();
  const f = state.fortune;
  f.knowledgeQuery = $("#fortune-knowledge-query")?.value || "";
  f.knowledgeEngine = $("#fortune-knowledge-engine")?.value || "";
  try {
    f.knowledgeResults = await callApi("search_fortune_knowledge", f.knowledgeQuery, f.knowledgeEngine);
    render();
  } catch (error) {
    f.error = error.message;
    render();
  }
}

async function chooseFortuneBackupDir() {
  try {
    const result = await callApi("choose_directory", state.fortune.dataBackupDir || state.settings?.output_dir || "");
    if (!result.cancelled && result.paths?.[0]) {
      state.fortune.dataBackupDir = result.paths[0];
      render();
    }
  } catch (error) {
    state.fortune.error = error.message;
    render();
  }
}

async function backupFortuneDatabase() {
  state.fortune.dataBackupDir = $("#fortune-backup-dir")?.value || state.fortune.dataBackupDir;
  try {
    const result = await callApi("backup_fortune_database", state.fortune.dataBackupDir || state.settings?.output_dir || "");
    state.fortune.dataMessage = `数据库备份已保存：${result.path}`;
    await refreshFortuneWorkspace();
    render();
    showToast(state.fortune.dataMessage);
  } catch (error) {
    state.fortune.error = error.message;
    render();
  }
}

async function verifyFortuneDatabase() {
  try {
    const result = await callApi("verify_fortune_database");
    state.fortune.dataMessage = result.ok ? "数据库完整性校验通过。" : "数据库校验未通过，请先备份后处理。";
    await refreshFortuneWorkspace();
    render();
  } catch (error) {
    state.fortune.error = error.message;
    render();
  }
}

async function chooseFortuneImportFile() {
  try {
    const result = await callApi("choose_file", state.settings?.output_dir || "", ["SQLite database (*.db;*.sqlite;*.sqlite3)", "All files (*.*)"], false);
    if (!result.cancelled && result.paths?.[0]) {
      state.fortune.dataImportPath = result.paths[0];
      state.fortune.dataImportConfirmed = false;
      render();
    }
  } catch (error) {
    state.fortune.error = error.message;
    render();
  }
}

async function importFortuneDatabase() {
  const f = state.fortune;
  f.dataImportPath = $("#fortune-import-path")?.value || f.dataImportPath;
  if (!f.dataImportPath) return;
  if (!(await app.confirmAction("导入会直接替换当前赛博算命数据库，且无法撤销。是否继续？", "确认导入数据库"))) return;
  try {
    await callApi("import_fortune_database", f.dataImportPath, true);
    f.dataMessage = "数据库已替换。";
    f.dataImportPath = "";
    f.dataImportConfirmed = false;
    await refreshFortuneWorkspace();
    render();
    showToast(f.dataMessage);
  } catch (error) {
    f.error = error.message;
    render();
  }
}

  const fortuneApi = {
    renderFortuneRoute,
    applyFortuneWorkspace,
    loadFortuneRoute,
    refreshFortuneWorkspace,
    resetFortuneCurrent,
    resetFortuneForm,
    selectFortuneEngine,
    setFortuneMode,
    startFortune,
    useFortuneReading,
    selectFortuneHistory,
    interpretFortune,
    toggleFortunePrompt,
    toggleFortuneInterpretation,
    useFortuneForClaim,
    chooseFortuneReportDir,
    exportFortuneReport,
    deleteFortuneHistory,
    startFortuneClaim,
    saveFortuneOutcome,
    openFortuneProfileForm,
    saveFortuneProfile,
    deleteFortuneProfile,
    searchFortuneKnowledge,
    chooseFortuneBackupDir,
    backupFortuneDatabase,
    verifyFortuneDatabase,
    chooseFortuneImportFile,
    importFortuneDatabase,
    captureFortuneForm,
    validateFortuneNumberField,
    validateFortuneTimeField,
    captureFortuneProfileForm,
    selectedFortuneHistory,
    fortunePayload,
  };
  app.fortune = fortuneApi;
  Object.assign(app, fortuneApi);
})();
