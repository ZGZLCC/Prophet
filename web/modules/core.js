(() => {
  "use strict";

// 聊天导出只实现了 Windows 客户端；必须在 state 初始化之前声明，
// 因为 state.route 会在初始化时调用 routeFromHash()。
let chatExportSupported = true;

const ROUTES = {
  profile: {
    title: "人物画像",
    label: "人物画像",
    subtitle: "用带证据的材料建立可回看的画像，在具体情境中观察可能反应，并持续用实际结果校正。",
    icon: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="3.25"></circle><path d="M5.5 19.25c.9-3.1 3.08-4.65 6.5-4.65s5.6 1.55 6.5 4.65"></path></svg>',
  },
  export: {
    title: "聊天导出",
    label: "聊天导出",
    subtitle: "读取本机 QQ 或微信的文字消息，按会话和日期筛选后保存到你指定的位置。",
    icon: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3.75h8.25L18.5 8v12.25H6z"></path><path d="M14 3.75V8h4.5M8.75 12.25h6.5M8.75 15.5h6.5"></path></svg>',
  },
  analysis: {
    title: "聊天分析",
    label: "聊天分析",
    subtitle: "先按时期和片段处理，完整聊天不会一次性塞给AI，再做有证据边界的概括。",
    icon: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 19.25V11M12 19.25V5M19 19.25v-8"></path><path d="M3.75 19.25h16.5"></path></svg>',
  },
  fortune: {
    title: "赛博算命",
    label: "赛博算命",
    subtitle: "七种术式的算命预测，可复现盘面、证据检索。",
    icon: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="7.75"></circle><path d="m12 7.2 1.5 3.3 3.3 1.5-3.3 1.5-1.5 3.3-1.5-3.3-3.3-1.5 3.3-1.5z"></path></svg>',
  },
};

const state = {
  route: routeFromHash(),
  bridgeReady: false,
  settings: null,
  settingsOpen: false,
  toastTimer: null,
  chatExport: {
    source: "qq",
    chats: "",
    range: "all",
    start: "",
    end: "",
    format: "json",
    outputDir: "",
    dbRoot: "",
    account: "",
    qqPid: "",
    recover: false,
    taskId: null,
    task: null,
    error: "",
  },
  chatAnalysis: {
    inputPath: "",
    target: "",
    focus: "",
    outputDir: "",
    mode: "one-click",
    taskId: null,
    task: null,
    error: "",
    validation: null,
    targetChecked: false,
    prompt: "",
    commands: "",
  },
  profile: {
    loading: false,
    error: "",
    people: [],
    selectedPersonId: null,
    workspace: null,
    tab: "profile",
    personForm: null,
    activeTask: null,
    activeTaskPersonId: null,
    search: "",
    material: {
      content: "",
      title: "直接输入",
      context: "",
      occurredAt: "",
      fileType: "",
      filePath: "",
      filePreview: "",
      encoding: "",
      encodingRequired: false,
      duplicate: null,
      allowDuplicate: false,
      error: "",
      taskId: null,
      lastResult: null,
    },
    predictionEvent: "",
    predictionVersion: null,
    reviewDrafts: {},
    exportDir: "",
    importPath: "",
    importConfirmed: false,
    expandedEvidenceKey: null,
  },
  fortune: {
    loading: false,
    error: "",
    workspace: null,
    engine: "zhouyi-textual",
    tab: "history",
    question: "",
    category: "other",
    policy: "traditional-zi-chu-li-chun-v1",
    values: {
      castAt: "",
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
    },
    facts: null,
    readingId: null,
    interpretation: "",
    interpretationExpanded: false,
    prompt: "",
    promptExpanded: false,
    activeTask: null,
    history: [],
    selectedHistoryId: null,
    claims: [],
    profiles: [],
    profileEditingId: null,
    profileDraft: null,
    knowledgeQuery: "",
    knowledgeEngine: "",
    knowledgeResults: [],
    dataImportPath: "",
    dataImportConfirmed: false,
    dataBackupDir: "",
    dataMessage: "",
    reportDir: "",
  },
};

const $ = (selector, root = document) => root.querySelector(selector);

function setChatExportSupported(value) {
  chatExportSupported = Boolean(value);
}

function routeFromHash() {
  const route = window.location.hash.replace(/^#/, "");
  if (!ROUTES[route]) return "profile";
  if (route === "export" && !chatExportSupported) return "profile";
  return route;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function getApi() {
  return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
}

async function callApi(method, ...args) {
  const api = getApi();
  if (!api || typeof api[method] !== "function") {
    const error = new Error("本地桥接尚未连接，请在 Prophet 窗口中重试。你可以先浏览当前页面结构。");
    error.code = "BRIDGE_UNAVAILABLE";
    throw error;
  }
  const result = await api[method](...args);
  if (result && result.ok === false) {
    const error = new Error(result.error?.message || "操作失败，请稍后重试。");
    error.code = result.error?.code || "API_ERROR";
    throw error;
  }
  return result?.data ?? result;
}

function setBridgeStatus(kind, label) {
  const status = $("#bridge-status");
  if (!status) return;
  status.classList.remove("is-loading", "is-error");
  if (kind === "loading") status.classList.add("is-loading");
  if (kind === "error") status.classList.add("is-error");
  status.textContent = label;
}

function setHealthStatus(kind, label, detail) {
  const dot = $("#health-dot");
  const labelNode = $("#health-label");
  const detailNode = $("#health-detail");
  if (!dot || !labelNode || !detailNode) return;
  dot.classList.remove("is-loading", "is-error");
  if (kind === "loading") dot.classList.add("is-loading");
  if (kind === "error") dot.classList.add("is-error");
  labelNode.textContent = label;
  detailNode.textContent = detail;
}

function setModelStatus(settings) {
  const dot = $("#model-dot");
  const label = $("#model-label");
  const detail = $("#model-detail");
  if (!dot || !label || !detail) return;
  dot.classList.remove("is-loading", "is-error");
  if (!settings?.llm_configured) {
    dot.classList.add("is-loading");
    label.textContent = "模型尚未配置";
    detail.textContent = "不影响本地整理与起盘";
    return;
  }
  label.textContent = "模型已配置";
  detail.textContent = settings.model || settings.provider || "可用于模型解读";
}

const PROFILE_LABELS = {
  emotion_patterns: "常见情绪模式",
  triggers: "可能的触发因素",
  behavior_tendencies: "应对方式与行为倾向",
  communication_preferences: "沟通偏好",
  values_and_needs: "重视的事物与可能需求",
  situational_differences: "情境差异与例外",
  uncertainties_and_contradictions: "不确定或相互矛盾的结论",
};
const CONFIDENCE_LABELS = { low: "低", medium: "中", high: "高" };
const KIND_LABELS = { observation: "观察", inference: "推断", uncertainty: "不确定" };
const ASSESSMENT_LABELS = {
  matched: "基本符合",
  partially_matched: "部分符合",
  diverged: "明显偏离",
  unclear: "暂时无法判断",
};

function textHtml(value) {
  return escapeHtml(value).replaceAll("\n", "<br>");
}

function cleanChatPath(value) {
  const text = String(value || "").trim();
  return text.startsWith('"') && text.endsWith('"') ? text.slice(1, -1) : text;
}

function formatTimestamp(value) {
  if (!value) return "未记录";
  if (/^\d{4}-\d{2}-\d{2}$/.test(String(value))) return String(value);
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).replace("T", " ");
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: state.settings?.timezone || "Asia/Shanghai",
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
  }).format(date).replaceAll("/", "-");
}

function dateTimeInputValue(value = "") {
  if (value && !/(Z|[+-]\d\d:\d\d)$/.test(String(value))) return String(value).slice(0, 16);
  const date = value ? new Date(value) : new Date();
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 16);
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-CA", {
    timeZone: state.settings?.timezone || "Asia/Shanghai",
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(date).map(({ type, value: part }) => [type, part]));
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}

function confidence(value) {
  return CONFIDENCE_LABELS[value] || value || "未知";
}

function taskBusy(task) {
  return Boolean(task && (task.status === "queued" || task.status === "running"));
}

function taskLabel(status) {
  return {
    queued: "排队中",
    running: "进行中",
    succeeded: "已完成",
    failed: "失败",
    cancelled: "已取消",
  }[status] || "等待中";
}

  window.ProphetApp = {
    ROUTES,
    state,
    $,
    routeFromHash,
    setChatExportSupported,
    escapeHtml,
    getApi,
    callApi,
    setBridgeStatus,
    setHealthStatus,
    setModelStatus,
    PROFILE_LABELS,
    CONFIDENCE_LABELS,
    KIND_LABELS,
    ASSESSMENT_LABELS,
    textHtml,
    cleanChatPath,
    formatTimestamp,
    dateTimeInputValue,
    confidence,
    taskBusy,
    taskLabel,
    profile: {},
    chat: {},
    fortune: {},
  };
})();
