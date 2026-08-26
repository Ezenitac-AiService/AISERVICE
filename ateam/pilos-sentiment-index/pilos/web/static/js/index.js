/**
 * index.js — Stock Sentiment Explorer 메인 페이지
 *
 * 데이터 책임 구분:
 * - 전체 종목의 기본 정보와 최신 수급 상태는 서버 API에서 받아옵니다.
 * - 댓글 수급 신호는 각 종목의 최신 보고서 API에서 받아옵니다.
 * - 검색은 서버(/api/search)를 매 입력마다 호출하지 않고, 페이지 진입 시 받아온
 *   전체 종목 목록(/api/stocks, allStocksCache)을 클라이언트에서 필터링합니다.
 *   종목 수가 아주 많아지거나 서버 측 검색(예: DB 인덱스)이 필요해지면
 *   다시 서버 호출 방식으로 되돌릴 수 있습니다.
 *
 * API 응답 필드는 손성욱.md §5(확정 Flask API 계약) 기준 snake_case로 확정되어
 * 있습니다. 여기서는 그 필드명(stock_code, stock_name, positive_model,
 * negative_model, analysis_status, supply_data_status 등)을 그대로 사용하며,
 * 과거 camelCase 별칭이나 artifact_id는 만들지 않습니다.
 */

const rowTemplate = document.getElementById("row-template");

const allListEl = document.getElementById("all-stock-list");
const allEmptyStateEl = document.getElementById("all-empty-state");
const allListLoadingEl = document.getElementById("all-list-loading");
const allListErrorEl = document.getElementById("all-list-error");
const allListRetryBtn = document.getElementById("all-list-retry");

const searchInput = document.getElementById("search-input");
const searchResultsEl = document.getElementById("search-results");

const pipelineStatusEl = document.querySelector(".pipeline-status");
const pipelineStatusBadgeEl = document.getElementById("pipeline-status-badge");
const pipelineStatusMessageEl = document.getElementById("pipeline-status-message");
const pipelineStatusMetaEl = document.getElementById("pipeline-status-meta");
const pipelineStatusRetryBtn = document.getElementById("pipeline-status-retry");

const mainScForm = document.getElementById("main-sc-form");
const mainScInput = document.getElementById("main-sc-input");
const mainScSubmitBtn = document.getElementById("main-sc-submit");
const mainScLoadingEl = document.getElementById("main-sc-loading");
const mainScErrorEl = document.getElementById("main-sc-error");
const mainScResultEl = document.getElementById("main-sc-result");
const mainScNoticeEl = document.getElementById("main-sc-notice");

const PIPELINE_STATUS_POLL_INTERVAL_MS = 30_000;
let pipelineStatusLoading = false;
let mainScSubmitting = false;

// 전체 종목 목록 캐시. /api/stocks 응답을 그대로 보관해 검색창에서
// 서버를 다시 호출하지 않고 이 안에서 이름/코드로 필터링합니다.
// null이면 아직 한 번도 불러오지 못한 상태(로딩 중 또는 실패)입니다.
let allStocksCache = null;

// 재시도나 검색이 겹쳐도 진행 중인 /api/stocks 요청을 공유합니다.
let allStocksFetchPromise = null;

// 같은 종목·기준일의 기존 v13 보고서 API 요청을 Promise 단위로 캐시합니다.
const mainSignalFetchCache = new Map();

// 연속 재시도 중 먼저 시작된 응답이 최신 화면을 덮어쓰지 않게 구분합니다.
let allListGeneration = 0;

/* ---------------- 서비스 파이프라인 상태 ---------------- */

const PIPELINE_STATUS_META = {
  not_started: {
    label: "실행 기록 없음",
    tone: "muted",
    message: "아직 자동화 파이프라인 실행 기록이 없습니다.",
  },
  running: {
    label: "갱신 중",
    tone: "pending",
    message: "댓글 수집부터 분석 보고서 생성까지 순서대로 갱신하고 있습니다.",
  },
  completed: {
    label: "갱신 완료",
    tone: "success",
    message: "최신 서비스 데이터 갱신이 정상적으로 완료됐습니다.",
  },
  failed: {
    label: "갱신 중단",
    tone: "danger",
    message: "최신 서비스 데이터 갱신 중 오류가 발생했습니다.",
  },
};

const PIPELINE_STAGE_LABELS = {
  comment_collection: "댓글 수집",
  comment_preprocessing: "댓글 전처리",
  comment_tokenization: "댓글 토큰화",
  daily_document: "일별 문서 생성",
  supply_demand: "수급 수집",
  model_inference: "모델 추론",
  llm_report: "분석 보고서 생성",
  pipeline_status_start: "실행 상태 기록",
  pipeline_status_finish: "종료 상태 기록",
};

const PIPELINE_TARGET_LABELS = {
  all: "전체 종목",
  sk: "SK하이닉스",
  others: "기타 종목",
};

function formatPipelineTimestamp(value) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatPipelineElapsed(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  const seconds = Math.max(0, Math.round(value));
  if (seconds < 60) return `${seconds}초`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return remainingSeconds ? `${minutes}분 ${remainingSeconds}초` : `${minutes}분`;
}

function renderPipelineStatus(data) {
  const meta = PIPELINE_STATUS_META[data?.status] || {
    label: "상태 확인 불가",
    tone: "muted",
    message: "자동화 실행 상태를 확인할 수 없습니다.",
  };

  pipelineStatusEl.dataset.status = data?.status || "unknown";
  pipelineStatusBadgeEl.textContent = meta.label;
  pipelineStatusBadgeEl.className = `status-badge status-badge--${meta.tone}`;
  pipelineStatusMessageEl.textContent = meta.message;
  pipelineStatusRetryBtn.hidden = true;

  const details = [];
  const targetLabel = PIPELINE_TARGET_LABELS[data?.target];
  if (targetLabel) details.push(targetLabel);

  const startedAt = formatPipelineTimestamp(data?.started_at);
  const finishedAt = formatPipelineTimestamp(data?.finished_at);
  if (data?.status === "running" && startedAt) details.push(`시작 ${startedAt}`);
  if (data?.status === "completed" && finishedAt) details.push(`완료 ${finishedAt}`);
  if (data?.status === "failed" && finishedAt) details.push(`중단 ${finishedAt}`);

  const elapsed = formatPipelineElapsed(data?.elapsed_seconds);
  if (elapsed) details.push(`소요 ${elapsed}`);

  if (data?.status === "failed" && data?.stopped_stage) {
    const stageLabel = PIPELINE_STAGE_LABELS[data.stopped_stage] || data.stopped_stage;
    details.push(`중단 단계 ${stageLabel}`);
  }

  pipelineStatusMetaEl.textContent = details.join(" · ");
  pipelineStatusMetaEl.hidden = details.length === 0;
}

function renderPipelineStatusError() {
  pipelineStatusEl.dataset.status = "error";
  pipelineStatusBadgeEl.textContent = "조회 실패";
  pipelineStatusBadgeEl.className = "status-badge status-badge--danger";
  pipelineStatusMessageEl.textContent = "자동화 실행 상태를 불러오지 못했습니다.";
  pipelineStatusMetaEl.hidden = true;
  pipelineStatusRetryBtn.hidden = false;
}

async function loadPipelineStatus() {
  if (pipelineStatusLoading || document.hidden) return;
  pipelineStatusLoading = true;

  try {
    const response = await fetch("/api/pipeline/status", { cache: "no-store" });
    const body = await response.json().catch(() => null);
    if (!response.ok || !body) throw new Error("pipeline status fetch failed");
    renderPipelineStatus(body);
  } catch (error) {
    console.warn("자동화 실행 상태를 불러오지 못했습니다.", error);
    renderPipelineStatusError();
  } finally {
    pipelineStatusLoading = false;
  }
}

/* ---------------- 표시 유틸 ----------------
 * 여러 페이지에서 쓰는 날짜·모델 값 포맷 함수는 common.js에 있습니다. */

const AVATAR_PALETTE = [
  "#ef4a34", "#1a9c6b", "#2f6fed", "#b7791f", "#7c5cf0", "#0f8a78",
];

function avatarColor(code) {
  const safeCode = code ?? "";
  let hash = 0;
  for (let i = 0; i < safeCode.length; i += 1) {
    hash = (hash * 31 + safeCode.charCodeAt(i)) % AVATAR_PALETTE.length;
  }
  return AVATAR_PALETTE[hash];
}

function renderStockAvatar(avatar, stockCode, displayName) {
  avatar.classList.remove("avatar--logo");
  avatar.textContent = displayName.slice(0, 1);
  avatar.style.setProperty("--avatar-color", avatarColor(stockCode));

  if (!stockCode) return;
  const image = new Image(30, 30);
  image.alt = "";
  image.decoding = "async";
  image.addEventListener("load", () => {
    avatar.replaceChildren(image);
    avatar.classList.add("avatar--logo");
  });
  image.src = `/static/images/stock-logos/${encodeURIComponent(stockCode)}.png`;
}

function formatSupplyStrength(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  const formatted = Math.abs(value).toLocaleString("ko-KR", {
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
  });
  if (value > 0) return `+${formatted}`;
  if (value < 0) return `-${formatted}`;
  return formatted;
}

function supplyDirectionFromIndex(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  if (value > 0) return "BUY";
  if (value < 0) return "SELL";
  return "NEUTRAL";
}

// pilos.analysis.llm_report.classify_supply_state()의 확정 구간을 화면용
// 쉬운 문장으로 옮긴다. 프론트에서 별도의 강도 기준을 만들지 않는다.
function supplyShareInterpretation(index) {
  if (typeof index !== "number" || !Number.isFinite(index)) return "수급 정보 없음";
  if (index === 0) return "매수·매도 비중이 같음";

  const side = index > 0 ? "매수" : "매도";
  const magnitude = Math.abs(index);
  if (magnitude < 0.05) return "매수·매도 비중이 거의 비슷함";
  if (magnitude < 0.15) return `${side}가 조금 더 많음`;
  if (magnitude < 0.30) return `${side}가 더 많음`;
  return `${side}가 뚜렷하게 많음`;
}

function renderSupplyShare(node, data) {
  const visual = node.querySelector(".supply-share");
  const donut = node.querySelector(".supply-share__donut");
  const dominantLabelEl = node.querySelector(".supply-share__dominant-label");
  const dominantValueEl = node.querySelector(".supply-share__dominant-value");
  const buyShareEl = node.querySelector(".supply-share__buy");
  const sellShareEl = node.querySelector(".supply-share__sell");
  const interpretationEl = node.querySelector(".supply-share__interpretation");
  const buyVolume = data.actual_buy_volume;
  const sellVolume = data.actual_sell_volume;
  const hasVolumes = typeof buyVolume === "number"
    && Number.isFinite(buyVolume)
    && buyVolume >= 0
    && typeof sellVolume === "number"
    && Number.isFinite(sellVolume)
    && sellVolume >= 0
    && buyVolume + sellVolume > 0;

  if (!hasVolumes) {
    visual.dataset.state = "missing";
    visual.dataset.dominant = "NEUTRAL";
    dominantLabelEl.textContent = "정보 없음";
    dominantValueEl.textContent = "—";
    buyShareEl.textContent = "—";
    sellShareEl.textContent = "—";
    interpretationEl.textContent = "수급 정보 없음";
    donut.setAttribute("aria-label", "개인 투자자 매수·매도 비중 정보 없음");
    return;
  }

  const buyShare = (buyVolume / (buyVolume + sellVolume)) * 100;
  const sellShare = 100 - buyShare;
  const dominantDirection = buyShare === sellShare
    ? "NEUTRAL"
    : buyShare > sellShare ? "BUY" : "SELL";
  const dominantShare = Math.max(buyShare, sellShare);
  const formatShare = (value) => `${value.toLocaleString("ko-KR", {
    maximumFractionDigits: 1,
  })}%`;

  visual.dataset.state = "ready";
  visual.dataset.dominant = dominantDirection;
  visual.style.setProperty("--dominant-angle", `${dominantShare * 3.6}deg`);
  dominantLabelEl.textContent = dominantDirection === "NEUTRAL"
    ? "균형"
    : dominantDirection === "BUY" ? "매수" : "매도";
  dominantValueEl.textContent = formatShare(dominantShare);
  buyShareEl.textContent = formatShare(buyShare);
  sellShareEl.textContent = formatShare(sellShare);
  interpretationEl.textContent = supplyShareInterpretation(
    data.actual_supply_demand_index,
  );
  donut.setAttribute(
    "aria-label",
    `개인 투자자 매수 ${formatShare(buyShare)}, 매도 ${formatShare(sellShare)}. `
      + `매수량 ${formatTradingVolume(buyVolume)}, 매도량 ${formatTradingVolume(sellVolume)}`,
  );
}

/* ---------------- API ---------------- */

async function fetchAllStocks() {
  const res = await fetch("/api/stocks");
  if (!res.ok) throw new Error("all stocks fetch failed");
  return res.json();
}

function mainSignalCacheKey(stock) {
  return `${stock.stock_code}:${stock.model_date || "no-date"}`;
}

async function fetchMainSignal(stock) {
  if (!stock.model_date) {
    return { report_status: "not_found", signal_status: null };
  }

  const params = new URLSearchParams({ model_date: stock.model_date });
  const res = await fetch(
    `/api/stocks/${encodeURIComponent(stock.stock_code)}/llm-reports?${params}`,
  );
  const body = await res.json().catch(() => ({}));

  if (res.ok) {
    return { ...body, report_status: body.status || "ready" };
  }

  return {
    report_status: body.status || "internal_error",
    signal_status: null,
  };
}

function loadMainSignal(stock) {
  const cacheKey = mainSignalCacheKey(stock);
  if (!mainSignalFetchCache.has(cacheKey)) {
    const request = fetchMainSignal(stock).catch(() => ({
      report_status: "internal_error",
      signal_status: null,
    }));
    mainSignalFetchCache.set(cacheKey, request);
  }
  return mainSignalFetchCache.get(cacheKey);
}

/** 진행 중인 전체 종목 요청을 공유하고 완료 후에는 재시도할 수 있게 비웁니다. */
function ensureAllStocksLoaded() {
  if (allStocksFetchPromise) return allStocksFetchPromise;

  allStocksFetchPromise = fetchAllStocks().finally(() => {
    allStocksFetchPromise = null;
  });

  return allStocksFetchPromise;
}

/* ---------------- 렌더링 ---------------- */

function mainSignalDirectionLabel(direction) {
  if (direction === "BUY") return "매수 우위";
  if (direction === "SELL") return "매도 우위";
  if (direction === "NEUTRAL") return "수급 균형";
  return null;
}

function signalLevelDescription(level) {
  const descriptions = {
    "매우 높음": "매우 강하게 보입니다.",
    높음: "비교적 강하게 보입니다.",
    보통: "평소와 비슷한 수준으로 보입니다.",
    낮음: "적게 보입니다.",
    "매우 낮음": "거의 보이지 않습니다.",
  };
  return descriptions[level] || null;
}

function mainSignalRelationship(signal, actualDirection) {
  if (
    signal.report_refresh_status === "pending"
    || (actualDirection && actualDirection !== signal.supply_direction)
  ) {
    return "현재 수급 방향 반영을 기다리는 댓글 신호입니다.";
  }

  const direction = mainSignalDirectionLabel(actualDirection);
  const description = signalLevelDescription(signal.signal_level);
  if (!direction || !description) return "";
  return `오늘 댓글에서 과거 ${direction} 때 자주 나타난 표현이 ${description}`;
}

function mainSignalUnavailableMessage(signal) {
  if (signal.signal_status === "insufficient_features") return "분석 근거 부족";
  if (signal.signal_status === "no_direction") return "실제 수급 방향 없음";
  if (signal.report_status === "ready") return "신호 정보 없음";
  return llmReportStatusLabel(signal.report_status);
}

function applyMainSignal(node, signal) {
  const gauge = node.querySelector(".signal-gauge");
  const scoreEl = node.querySelector(".signal-gauge__score");
  const metaEl = node.querySelector(".signal-gauge__meta");
  const trackEl = node.querySelector(".signal-gauge__track");
  const fillEl = node.querySelector(".signal-gauge__fill");
  const markerEl = node.querySelector(".signal-gauge__marker");
  const relationshipEl = node.querySelector(".signal-relationship");
  const score = signal.comment_signal_score;
  const isReady = signal.signal_status === "ready"
    && typeof score === "number"
    && Number.isFinite(score)
    && score >= 0
    && score <= 100;

  if (!isReady) {
    const message = mainSignalUnavailableMessage(signal);
    gauge.dataset.state = signal.report_status === "internal_error"
      ? "error"
      : "unavailable";
    gauge.removeAttribute("data-direction");
    scoreEl.textContent = "—";
    metaEl.textContent = message;
    fillEl.style.width = "0%";
    markerEl.style.left = "0%";
    trackEl.removeAttribute("aria-valuenow");
    trackEl.setAttribute("aria-valuetext", message);
    relationshipEl.textContent = "";
    return;
  }

  const directionLabel = mainSignalDirectionLabel(signal.supply_direction);
  const refreshLabel = signal.report_refresh_status === "pending"
    ? "갱신 대기"
    : null;
  const meta = [directionLabel, signal.signal_level, refreshLabel].filter(Boolean).join(" · ");

  gauge.dataset.state = "ready";
  gauge.dataset.direction = signal.supply_direction || "";
  scoreEl.textContent = `${score}`;
  metaEl.textContent = meta;
  fillEl.style.width = `${score}%`;
  markerEl.style.left = `${score}%`;
  trackEl.setAttribute("aria-valuenow", `${score}`);
  trackEl.setAttribute("aria-valuetext", `${score} / 100, ${meta}`);
  relationshipEl.textContent = mainSignalRelationship(
    signal,
    node.querySelector(".col--actual").dataset.direction || null,
  );
}

function renderMainSignal(node, stock) {
  loadMainSignal(stock).then((signal) => {
    // 목록 재조회로 이미 제거된 행에는 비동기 결과를 반영하지 않습니다.
    if (!node.isConnected) return;
    applyMainSignal(node, signal);
  });
}

function getStockDetailUrl(stockCode) {
  const pathname = (window.location && window.location.pathname) || "";
  const prefix = pathname.startsWith("/ateam/pilos") ? "/ateam/pilos" : "";
  return `${prefix}/stocks/${encodeURIComponent(stockCode)}`;
}

function renderRow(data) {
  const node = rowTemplate.content.firstElementChild.cloneNode(true);

  node.href = getStockDetailUrl(data.stock_code);

  node.querySelectorAll(".metric-help").forEach((help) => {
    help.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      help.focus();
    });
    help.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      event.stopPropagation();
      help.focus();
    });
  });

  // 종목 식별
  const avatar = node.querySelector(".avatar");
  const displayName = data.stock_name || data.stock_code || "?";
  renderStockAvatar(avatar, data.stock_code, displayName);

  node.querySelector(".identity-text__name").textContent = displayName;
  node.querySelector(".identity-text__code").textContent = data.stock_code;

  const supplyIndex = data.actual_supply_demand_index;
  const actualColumn = node.querySelector(".col--actual");
  const actualDirection = supplyDirectionFromIndex(supplyIndex);
  if (actualDirection) actualColumn.dataset.direction = actualDirection;
  node.querySelector(".actual-supply-score").textContent = formatSupplyStrength(supplyIndex);
  renderSupplyShare(node, data);

  renderMainSignal(node, data);

  node.querySelector(".model-date").textContent = formatModelDate(data.model_date);
  node.querySelector(".model-comment-count").textContent =
    typeof data.comment_count === "number" ? `댓글 ${data.comment_count}개` : "댓글 수 없음";

  // 목록 상태 배지는 있음/없음이 아니라 analysis_status 6단계를 그대로 보여줍니다.
  // inference_pending/unknown/insufficient_features를 정상 점수처럼 강조하지 않습니다.
  const statusEl = node.querySelector(".model-status");
  statusEl.textContent = analysisStatusLabel(data.analysis_status);
  statusEl.className = `model-status status-badge status-badge--${analysisStatusTone(data.analysis_status)}`;

  return node;
}

/* ---------------- 전체 종목 목록 ---------------- */
async function renderAllList() {
  const generation = ++allListGeneration;

  allListErrorEl.hidden = true;
  allEmptyStateEl.hidden = true;
  allListEl.hidden = true;
  allListEl.innerHTML = "";
  allListLoadingEl.hidden = false;

  let stocks;
  try {
    stocks = await ensureAllStocksLoaded();
  } catch (err) {
    console.warn("전체 종목 목록을 불러오지 못했습니다.", err);
    if (generation !== allListGeneration) return; // 그 사이 더 최신 호출이 시작됨
    allListLoadingEl.hidden = true;
    allListErrorEl.hidden = false;
    // 검색이 계속 로딩 상태로 남지 않도록 실패 시 빈 배열로 확정합니다.
    allStocksCache = allStocksCache ?? [];
    return;
  }

  // await 하는 동안 더 최신 renderAllList() 호출이 시작됐다면 이 결과는 버립니다.
  if (generation !== allListGeneration) return;

  allStocksCache = stocks;
  allListLoadingEl.hidden = true;

  if (stocks.length === 0) {
    allListEl.hidden = true;
    allEmptyStateEl.hidden = false;
    return;
  }

  allListEl.hidden = false;
  stocks.forEach((stock) => {
    allListEl.appendChild(renderRow(stock));
  });
}

allListRetryBtn.addEventListener("click", () => {
  renderAllList();
});

pipelineStatusRetryBtn.addEventListener("click", loadPipelineStatus);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) loadPipelineStatus();
});
setInterval(loadPipelineStatus, PIPELINE_STATUS_POLL_INTERVAL_MS);

// 현재 드롭다운에 표시 중인 검색 결과와, 키보드(↑/↓)로 선택된 항목의 인덱스입니다.
// -1은 아직 아무 항목도 키보드로 선택하지 않은 상태(입력창에 포커스)를 뜻합니다.
let currentSearchMatches = [];
let searchActiveIndex = -1;

/**
 * 검색 결과 하나를 선택했을 때(클릭 또는 Enter) 공통으로 실행되는 동작입니다.
 * 별도 최근 조회 상태를 만들지 않고 바로 상세 페이지로 이동합니다.
 */
function selectSearchResult(stock) {
  window.location.href = getStockDetailUrl(stock.stock_code);
}

/**
 * 검색 결과 드롭다운의 표시 여부를 `hidden` 속성과 콤보박스의
 * `aria-expanded` 값에 함께 반영합니다.
 */
function setSearchResultsHidden(hidden) {
  searchResultsEl.hidden = hidden;
  searchInput.setAttribute("aria-expanded", hidden ? "false" : "true");
}

/**
 * 전체 종목 캐시(allStocksCache)에서 이름 또는 코드가 검색어를 포함하는
 * 항목을 찾습니다. 서버를 다시 호출하지 않습니다.
 */
function searchLocally(query) {
  const q = query.trim().toLowerCase();
  if (!q || !allStocksCache) return [];
  return allStocksCache.filter((s) => {
    const name = (s.stock_name ?? "").toLowerCase();
    const code = s.stock_code ?? "";
    return name.includes(q) || code.includes(q);
  });
}

searchInput.addEventListener("input", () => {
  const query = searchInput.value.trim();
  searchActiveIndex = -1;

  if (!query) {
    currentSearchMatches = [];
    setSearchResultsHidden(true);
    searchResultsEl.innerHTML = "";
    return;
  }

  if (allStocksCache === null) {
    // 페이지 진입 직후 전체 종목을 아직 못 받아온 짧은 순간입니다.
    currentSearchMatches = [];
    renderSearchLoading();
    return;
  }

  renderSearchResults(searchLocally(query));
});

function renderSearchLoading() {
  searchResultsEl.innerHTML = "";
  const loading = document.createElement("div");
  loading.className = "search__empty";
  loading.textContent = "종목 목록을 불러오는 중입니다…";
  searchResultsEl.appendChild(loading);
  setSearchResultsHidden(false);
}

function renderSearchResults(matches) {
  currentSearchMatches = matches;
  searchResultsEl.innerHTML = "";

  if (matches.length === 0) {
    const empty = document.createElement("div");
    empty.className = "search__empty";
    empty.textContent = "검색 결과가 없습니다";
    searchResultsEl.appendChild(empty);
    setSearchResultsHidden(false);
    return;
  }

  matches.forEach((m, index) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.id = `search-result-${index}`;
    btn.className = "search__result-item";
    btn.setAttribute("role", "option");
    btn.setAttribute("aria-selected", "false");

    // 종목명/코드는 서버 응답값이라도 innerHTML에 직접 넣지 않고
    // textContent로 채워 마크업이 실행되지 않도록 합니다.
    const nameEl = document.createElement("span");
    nameEl.textContent = m.stock_name;
    const codeEl = document.createElement("span");
    codeEl.className = "search__result-code";
    codeEl.textContent = m.stock_code;
    btn.append(nameEl, codeEl);

    // 마우스로 올렸을 때도 키보드 선택 위치와 함께 움직이도록 맞춰줍니다.
    btn.addEventListener("mouseenter", () => {
      searchActiveIndex = index;
      highlightSearchResult(searchActiveIndex);
    });

    btn.addEventListener("click", () => selectSearchResult(m));
    searchResultsEl.appendChild(btn);
  });

  setSearchResultsHidden(false);
}

/**
 * 검색 결과 중 index번째 항목에 시각적 강조(하이라이트) 표시를 하고,
 * 스크린리더가 알 수 있도록 aria-selected/aria-activedescendant도 갱신합니다.
 */
function highlightSearchResult(index) {
  const items = searchResultsEl.querySelectorAll(".search__result-item");
  items.forEach((el, i) => {
    const active = i === index;
    el.classList.toggle("search__result-item--active", active);
    el.setAttribute("aria-selected", active ? "true" : "false");
  });

  if (index >= 0 && items[index]) {
    items[index].scrollIntoView({ block: "nearest" });
    searchInput.setAttribute("aria-activedescendant", items[index].id);
  } else {
    searchInput.removeAttribute("aria-activedescendant");
  }
}

// ↑/↓ 로 검색 결과 사이를 이동하고, Enter로 선택한(또는 아무것도 선택하지
// 않았다면 첫 번째) 항목의 상세 페이지로 이동합니다.
searchInput.addEventListener("keydown", (e) => {
  if (searchResultsEl.hidden || currentSearchMatches.length === 0) return;

  if (e.key === "ArrowDown") {
    e.preventDefault();
    searchActiveIndex = Math.min(searchActiveIndex + 1, currentSearchMatches.length - 1);
    highlightSearchResult(searchActiveIndex);
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    searchActiveIndex = Math.max(searchActiveIndex - 1, 0);
    highlightSearchResult(searchActiveIndex);
  } else if (e.key === "Enter") {
    e.preventDefault();
    const index = searchActiveIndex === -1 ? 0 : searchActiveIndex;
    const target = currentSearchMatches[index];
    if (target) selectSearchResult(target);
  }
});

document.addEventListener("click", (e) => {
  if (!e.target.closest(".search")) {
    setSearchResultsHidden(true);
    searchActiveIndex = -1;
    searchInput.removeAttribute("aria-activedescendant");
  }
});

// "/" 단축키로 검색창 포커스
document.addEventListener("keydown", (e) => {
  if (e.key === "/" && document.activeElement !== searchInput) {
    e.preventDefault();
    searchInput.focus();
  }
  if (e.key === "Escape") {
    setSearchResultsHidden(true);
    searchActiveIndex = -1;
    searchInput.removeAttribute("aria-activedescendant");
    searchInput.blur();
  }
});

/* ---------------- 단일 댓글 모델 반응 실험 ---------------- */

function formatMainScCount(value) {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString("ko-KR")
    : "—";
}

function renderMainScKeywords(container, model) {
  container.innerHTML = "";
  const groups = [
    {
      title: "점수를 강화한 표현",
      tone: "positive",
      items: Array.isArray(model?.positive_keywords) ? model.positive_keywords : [],
    },
    {
      title: "점수를 낮춘 표현",
      tone: "negative",
      items: Array.isArray(model?.negative_keywords) ? model.negative_keywords : [],
    },
  ];

  if (!groups.some((group) => group.items.length)) {
    const empty = document.createElement("p");
    empty.className = "main-sc-model__empty";
    empty.textContent = "인식된 주요 표현이 없습니다.";
    container.appendChild(empty);
    return;
  }

  groups.forEach((groupData) => {
    if (!groupData.items.length) return;
    const group = document.createElement("section");
    group.className = "main-sc-keyword-group";
    const heading = document.createElement("h4");
    heading.textContent = groupData.title;
    const list = document.createElement("div");
    list.className = "main-sc-keyword-list";

    groupData.items.forEach((item) => {
      const keyword = document.createElement("span");
      keyword.className = `main-sc-keyword main-sc-keyword--${groupData.tone}`;
      const word = document.createElement("span");
      word.textContent = item.keyword || "—";
      const contribution = document.createElement("strong");
      contribution.textContent = formatModelValue(item.contribution);
      keyword.append(word, contribution);
      list.appendChild(keyword);
    });

    group.append(heading, list);
    container.appendChild(group);
  });
}

function renderMainScModel(direction, model) {
  const scoreEl = document.querySelector(`[data-main-sc-field="${direction}-score"]`);
  const metaEl = document.querySelector(`[data-main-sc-field="${direction}-meta"]`);
  const keywordsEl = document.querySelector(`[data-main-sc-field="${direction}-keywords"]`);

  if (!model) {
    scoreEl.textContent = "결과 없음";
    metaEl.textContent = "해당 방향 모델의 결과가 없습니다.";
    keywordsEl.innerHTML = "";
    return;
  }

  scoreEl.textContent = formatModelValue(model.text_score);
  metaEl.textContent = `인식 feature ${formatMainScCount(model.recognized_feature_count)}개`;
  renderMainScKeywords(keywordsEl, model);
}

async function requestSingleCommentInference(text) {
  const response = await fetch("/api/inference/single-comment", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ comment_text: text }),
  });
  const body = await response.json().catch(() => null);
  if (response.ok) return body;
  throw new Error(
    (body && (body.message || body.error)) ||
      `댓글 분석을 처리하지 못했습니다. (${response.status})`,
  );
}

mainScForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (mainScSubmitting) return;

  const text = mainScInput.value.trim();
  mainScErrorEl.hidden = true;
  if (!text) {
    mainScErrorEl.textContent = "분석할 댓글 내용을 입력해주세요.";
    mainScErrorEl.hidden = false;
    mainScInput.focus();
    return;
  }

  mainScSubmitting = true;
  mainScSubmitBtn.disabled = true;
  mainScSubmitBtn.querySelector("span").textContent = "분석 중…";
  mainScLoadingEl.hidden = false;
  mainScResultEl.hidden = true;

  try {
    const body = await requestSingleCommentInference(text);
    renderMainScModel("positive", body.positive_model);
    renderMainScModel("negative", body.negative_model);
    mainScNoticeEl.textContent = body.notice || "";
    mainScResultEl.hidden = false;
    mainScResultEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (error) {
    mainScErrorEl.textContent = error.message || "댓글 분석 요청에 실패했습니다.";
    mainScErrorEl.hidden = false;
  } finally {
    mainScSubmitting = false;
    mainScSubmitBtn.disabled = false;
    mainScSubmitBtn.querySelector("span").textContent = "두 모델로 분석하기";
    mainScLoadingEl.hidden = true;
  }
});

/* ---------------- 초기화 ---------------- */

loadPipelineStatus();
renderAllList();
