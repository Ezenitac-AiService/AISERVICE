/**
 * 종목 상세 화면.
 * 공개 API가 제공하는 날짜별 수급·모델 산출물·v13 리포트·챗봇 응답만 표시한다.
 * 프론트에서 새로운 모델 지표나 방향을 추정하지 않는다.
 */

const root = document.getElementById("detail-root");
const CODE = root.dataset.code;
const PAGE_STOCK_CODE = String(CODE || "").trim().padStart(6, "0");

const loadingEl = document.getElementById("d-loading");
const errorEl = document.getElementById("d-error");
const errorTextEl = document.getElementById("d-error-text");
const retryBtn = document.getElementById("d-retry");
const contentEl = document.getElementById("d-content");
const nameEl = document.getElementById("d-stock-name");
const codeEl = document.getElementById("d-stock-code");
const dateInputEl = document.getElementById("d-date-input");
const dateHintEl = document.getElementById("d-date-hint");
const datePrevBtn = document.getElementById("d-date-prev");
const dateNextBtn = document.getElementById("d-date-next");
const stockLogoEl = document.getElementById("d-stock-logo");

const modelDateEl = document.getElementById("d-model-date");
const commentCountEl = document.getElementById("d-comment-count");
const actualIndexEl = document.getElementById("d-actual-supply-demand-index");
const buyVolumeEl = document.getElementById("d-actual-buy-volume");
const sellVolumeEl = document.getElementById("d-actual-sell-volume");
const buyShareEl = document.getElementById("d-buy-share");
const sellShareEl = document.getElementById("d-sell-share");
const buyShareBarEl = document.getElementById("d-buy-share-bar");
const supplyStatusEl = document.getElementById("d-supply-status");
const supplyObservedAtEl = document.getElementById("d-supply-observed-at");
const analysisStatusEl = document.getElementById("d-analysis-status");
const positiveKeywordsEl = document.getElementById("d-positive-keywords");
const negativeKeywordsEl = document.getElementById("d-negative-keywords");

const llmStatusEl = document.getElementById("d-llm-status");
const llmLoadingEl = document.getElementById("d-llm-loading");
const llmEmptyEl = document.getElementById("d-llm-empty");
const llmContentEl = document.getElementById("d-llm-content");
const llmDirectionEl = document.getElementById("d-llm-direction");
const llmSignalScoreEl = document.getElementById("d-llm-signal-score");
const llmSignalLevelEl = document.getElementById("d-llm-signal-level");
const llmSummaryEl = document.getElementById("d-llm-summary");
const llmConclusionEl = document.getElementById("d-llm-conclusion");
const llmActualIndexEl = document.getElementById("d-llm-actual-index");
const llmSignalChangeEl = document.getElementById("d-llm-signal-change");
const llmSignalMa5El = document.getElementById("d-llm-signal-ma5");
const llmCommentCountEl = document.getElementById("d-llm-comment-count");
const llmRefreshBannerEl = document.getElementById("d-llm-refresh-banner");
const llmDateEl = document.getElementById("d-llm-date");
const llmSourceEl = document.getElementById("d-llm-source");
const llmSignalStatusEl = document.getElementById("d-llm-signal-status");
const llmReportSupplyStatusEl = document.getElementById("d-llm-report-supply-status");
const llmReportObservedAtEl = document.getElementById("d-llm-report-observed-at");
const llmCurrentSupplyStatusEl = document.getElementById("d-llm-current-supply-status");
const llmCurrentObservedAtEl = document.getElementById("d-llm-current-observed-at");
const llmRefreshStatusEl = document.getElementById("d-llm-refresh-status");
const llmNoticeEl = document.getElementById("d-llm-notice");

const chatContextNameEl = document.getElementById("d-chat-context-name");

let stockPayload = null;
let entries = [];
let selectedIndex = 0;
let llmRequestId = 0;

function readJson(response) {
  return response.json().catch(() => null);
}

function renderStockLogo(stockCode, stockName) {
  if (!stockLogoEl) return;

  const fallback = document.createElement("span");
  fallback.className = "d-stock-logo__fallback";
  fallback.textContent = String(stockName || stockCode || "?").slice(0, 1);
  stockLogoEl.replaceChildren(fallback);
  stockLogoEl.classList.remove("d-stock-logo--ready");

  if (!stockCode) return;
  const image = new Image(30, 30);
  image.alt = "";
  image.decoding = "async";
  image.addEventListener("load", () => {
    stockLogoEl.replaceChildren(image);
    stockLogoEl.classList.add("d-stock-logo--ready");
  });
  image.src = `/static/images/stock-logos/${encodeURIComponent(stockCode)}.png`;
}

function setPageState(state, message = "") {
  loadingEl.hidden = state !== "loading";
  errorEl.hidden = state !== "error";
  contentEl.hidden = state !== "ready";
  if (state === "error") errorTextEl.textContent = message;
}

function formatObservedAt(value) {
  if (!value) return "정보 없음";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatCount(value, suffix = "") {
  return typeof value === "number" && Number.isFinite(value)
    ? `${value.toLocaleString("ko-KR")}${suffix}`
    : "—";
}

function formatShare(value) {
  return typeof value === "number" && Number.isFinite(value)
    ? `${value.toLocaleString("ko-KR", { maximumFractionDigits: 1 })}%`
    : "—";
}

function formatSignalScore(value) {
  return typeof value === "number" && Number.isFinite(value) ? `${value} / 100` : "—";
}

function formatSigned(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return value > 0 ? `+${value}` : `${value}`;
}

function directionLabel(direction) {
  if (direction === "BUY") return "매수 우위";
  if (direction === "SELL") return "매도 우위";
  if (direction === "NEUTRAL") return "중립";
  return "방향 없음";
}

function signalStatusLabel(status) {
  const labels = {
    ready: "계산 완료",
    insufficient_features: "인식 feature 부족",
    no_direction: "실제 수급 방향 없음",
  };
  return labels[status] || status || "정보 없음";
}

function renderEmptyState(container, message) {
  container.innerHTML = "";
  const text = document.createElement("p");
  text.className = "d-empty-state";
  text.textContent = message;
  container.appendChild(text);
}

async function fetchStockDetail(code) {
  const response = await fetch(`/api/stocks/${encodeURIComponent(code)}`);
  const body = await readJson(response);
  if (response.ok) return body;
  throw new Error(
    (body && (body.message || body.error)) ||
      `종목 데이터를 불러오지 못했습니다. (${response.status})`,
  );
}

async function fetchLlmReport(code, modelDate) {
  const query = new URLSearchParams({ model_date: modelDate });
  const response = await fetch(
    `/api/stocks/${encodeURIComponent(code)}/llm-reports?${query}`,
  );
  const body = await readJson(response);
  if (response.ok) return { state: body.status || "ready", report: body };
  return {
    state: (body && body.status) || "internal_error",
    message:
      (body && (body.message || body.error)) ||
      `리포트를 불러오지 못했습니다. (${response.status})`,
  };
}

function setField(card, field, value) {
  const element = card.querySelector(`[data-field="${field}"]`);
  if (element) element.textContent = value;
}

function renderModel(card, model) {
  const badge = card.querySelector('[data-field="inferenceStatusBadge"]');
  card.classList.toggle("d-model-card--missing", !model);

  if (!model) {
    setField(card, "supplyDemandAssociationScore", "결과 없음");
    [
      "variant",
      "intercept",
      "textScore",
      "commentCountContribution",
      "recognizedFeatureCount",
      "uniqueTokenCount",
      "vocabularyCoverage",
    ].forEach((field) => setField(card, field, "—"));
    badge.textContent = "결과 없음";
    badge.className = "status-badge status-badge--muted";
    return;
  }

  setField(card, "supplyDemandAssociationScore", formatModelValue(model.supply_demand_association_score));
  setField(card, "variant", model.model_variant || "—");
  setField(card, "intercept", formatModelValue(model.intercept));
  setField(card, "textScore", formatModelValue(model.text_score));
  setField(card, "commentCountContribution", formatModelValue(model.comment_count_contribution));
  setField(card, "recognizedFeatureCount", formatCount(model.recognized_feature_count));
  setField(card, "uniqueTokenCount", formatCount(model.unique_token_count));
  setField(card, "vocabularyCoverage", formatCoverage(model.vocabulary_coverage));
  badge.textContent = analysisStatusLabel(model.inference_status);
  badge.className = `status-badge status-badge--${analysisStatusTone(model.inference_status)}`;
}

function makeKeywordRow(item, direction) {
  const row = document.createElement("div");
  row.className = "d-keyword-row";

  const word = document.createElement("span");
  word.textContent = item.keyword || "—";

  const contribution = document.createElement("strong");
  contribution.className = `d-keyword-contribution d-keyword-contribution--${direction}`;
  contribution.textContent = formatModelValue(item.contribution);
  row.append(word, contribution);
  return row;
}

function renderKeywordGroup(container, title, items, direction) {
  const group = document.createElement("section");
  group.className = "d-keyword-group";
  const heading = document.createElement("h5");
  heading.textContent = title;
  group.appendChild(heading);

  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "d-empty-state";
    empty.textContent = "저장된 표현이 없습니다.";
    group.appendChild(empty);
  } else {
    items.forEach((item) => group.appendChild(makeKeywordRow(item, direction)));
  }
  container.appendChild(group);
}

function renderKeywords(container, model) {
  container.innerHTML = "";
  if (!model) {
    renderEmptyState(container, "해당 모델의 추론 결과가 없습니다.");
    return;
  }
  renderKeywordGroup(
    container,
    "점수를 강화한 표현",
    Array.isArray(model.positive_keywords) ? model.positive_keywords : [],
    "positive",
  );
  renderKeywordGroup(
    container,
    "점수를 낮춘 표현",
    Array.isArray(model.negative_keywords) ? model.negative_keywords : [],
    "negative",
  );
}

function showLlmLoading() {
  llmStatusEl.textContent = "불러오는 중";
  llmStatusEl.className = "status-badge status-badge--muted";
  llmLoadingEl.hidden = false;
  llmEmptyEl.hidden = true;
  llmContentEl.hidden = true;
}

function showLlmState(state, message) {
  llmStatusEl.textContent = llmReportStatusLabel(state);
  llmStatusEl.className = `status-badge status-badge--${llmReportStatusTone(state)}`;
  llmLoadingEl.hidden = true;
  llmContentEl.hidden = true;
  llmEmptyEl.hidden = false;
  llmEmptyEl.textContent = message;
}

function renderLlmReport(report) {
  llmStatusEl.textContent = llmReportStatusLabel(report.status);
  llmStatusEl.className = `status-badge status-badge--${llmReportStatusTone(report.status)}`;
  llmDirectionEl.textContent = directionLabel(report.supply_direction);
  llmDirectionEl.dataset.direction = report.supply_direction || "NEUTRAL";
  llmSignalScoreEl.textContent = formatSignalScore(report.comment_signal_score);
  llmSignalLevelEl.textContent =
    report.signal_status === "ready"
      ? report.signal_level || "수준 정보 없음"
      : signalStatusLabel(report.signal_status);
  llmSummaryEl.textContent =
    report.market_commentary ||
    (report.status === "insufficient_evidence"
      ? "근거가 부족해 자세한 해설을 생성하지 않았습니다."
      : "저장된 시장 해설이 없습니다.");
  llmConclusionEl.textContent = report.conclusion || "";
  llmActualIndexEl.textContent = formatModelValue(report.actual_supply_index);
  llmSignalChangeEl.textContent = formatSigned(report.signal_change);
  llmSignalMa5El.textContent = formatSignalScore(report.signal_ma5);
  llmCommentCountEl.textContent = formatCount(report.comment_count, "건");

  llmDateEl.textContent = formatModelDate(report.model_date);
  llmSourceEl.textContent = commentarySourceLabel(report.commentary_source) || "정보 없음";
  llmSignalStatusEl.textContent = signalStatusLabel(report.signal_status);
  llmReportSupplyStatusEl.textContent = supplyDataStatusLabel(report.report_supply_data_status) || "정보 없음";
  llmReportObservedAtEl.textContent = formatObservedAt(report.report_supply_observed_at);
  llmCurrentSupplyStatusEl.textContent = supplyDataStatusLabel(report.current_supply_data_status) || "정보 없음";
  llmCurrentObservedAtEl.textContent = formatObservedAt(report.current_supply_observed_at);
  llmRefreshStatusEl.textContent = reportRefreshStatusLabel(report.report_refresh_status) || "정보 없음";
  llmNoticeEl.textContent = report.notice || "";

  if (report.report_refresh_status === "pending") {
    llmRefreshBannerEl.hidden = false;
    llmRefreshBannerEl.textContent =
      `${reportRefreshStatusLabel(report.report_refresh_status)} · ` +
      `보고서 ${supplyDataStatusLabel(report.report_supply_data_status) || "정보 없음"} → ` +
      `현재 ${supplyDataStatusLabel(report.current_supply_data_status) || "정보 없음"}`;
  } else {
    llmRefreshBannerEl.hidden = true;
    llmRefreshBannerEl.textContent = "";
  }

  llmLoadingEl.hidden = true;
  llmEmptyEl.hidden = true;
  llmContentEl.hidden = false;
}

async function loadLlmReport(modelDate) {
  const requestId = ++llmRequestId;
  if (!modelDate) {
    showLlmState("not_found", "리포트를 조회할 기준일이 없습니다.");
    return;
  }
  showLlmLoading();
  try {
    const result = await fetchLlmReport(CODE, modelDate);
    if (requestId !== llmRequestId) return;
    if (result.report) renderLlmReport(result.report);
    else showLlmState(result.state, result.message);
  } catch (error) {
    if (requestId !== llmRequestId) return;
    showLlmState("internal_error", error.message || "리포트를 불러오지 못했습니다.");
  }
}

function renderActualData(data) {
  modelDateEl.textContent = formatModelDate(data.model_date);
  commentCountEl.textContent = formatCount(data.comment_count, "개");
  actualIndexEl.textContent = formatModelValue(data.actual_supply_demand_index);
  buyVolumeEl.textContent = formatTradingVolume(data.actual_buy_volume);
  sellVolumeEl.textContent = formatTradingVolume(data.actual_sell_volume);

  const buy = data.actual_buy_volume;
  const sell = data.actual_sell_volume;
  const validVolumes =
    typeof buy === "number" && Number.isFinite(buy) && buy >= 0 &&
    typeof sell === "number" && Number.isFinite(sell) && sell >= 0 &&
    buy + sell > 0;
  const buyShare = validVolumes ? (buy / (buy + sell)) * 100 : null;
  const sellShare = validVolumes ? 100 - buyShare : null;
  buyShareEl.textContent = formatShare(buyShare);
  sellShareEl.textContent = formatShare(sellShare);
  buyShareBarEl.style.width = validVolumes ? `${buyShare}%` : "0%";

  supplyStatusEl.textContent = supplyDataStatusLabel(data.supply_data_status) || "정보 없음";
  supplyObservedAtEl.textContent = formatObservedAt(data.supply_observed_at);
  analysisStatusEl.textContent = analysisStatusLabel(data.analysis_status);
  analysisStatusEl.className = `status-badge status-badge--${analysisStatusTone(data.analysis_status)}`;
}

function updateDatePicker() {
  const entry = entries[selectedIndex];
  dateInputEl.value = entry.model_date || "";
  const dates = entries.map((item) => item.model_date).filter(Boolean);
  if (dates.length) {
    dateInputEl.min = dates[dates.length - 1];
    dateInputEl.max = dates[0];
  }
  datePrevBtn.disabled = selectedIndex >= entries.length - 1;
  dateNextBtn.disabled = selectedIndex <= 0;
  dateHintEl.textContent = `${selectedIndex + 1} / ${entries.length} · 데이터가 있는 날짜만 선택 가능`;
}

function renderSelectedEntry() {
  const data = entries[selectedIndex];
  renderActualData(data);
  renderModel(document.querySelector('[data-model-card="positive"]'), data.positive_model);
  renderModel(document.querySelector('[data-model-card="negative"]'), data.negative_model);
  renderKeywords(positiveKeywordsEl, data.positive_model);
  renderKeywords(negativeKeywordsEl, data.negative_model);
  updateDatePicker();
  loadLlmReport(data.model_date);
}

function selectEntry(index) {
  if (index < 0 || index >= entries.length) return;
  selectedIndex = index;
  renderSelectedEntry();
}

function moveDate(offset) {
  selectEntry(selectedIndex + offset);
}

datePrevBtn.addEventListener("click", () => moveDate(1));
dateNextBtn.addEventListener("click", () => moveDate(-1));
dateInputEl.addEventListener("change", () => {
  const index = entries.findIndex((entry) => entry.model_date === dateInputEl.value);
  if (index === -1) {
    dateHintEl.textContent = "선택한 날짜에는 적재된 데이터가 없습니다.";
    dateInputEl.value = entries[selectedIndex]?.model_date || "";
    return;
  }
  selectEntry(index);
});

async function load() {
  setPageState("loading");
  try {
    stockPayload = await fetchStockDetail(CODE);
    const responseStockCode = String(stockPayload.stock_code || "").padStart(6, "0");
    if (responseStockCode !== PAGE_STOCK_CODE) {
      throw new Error("상세 페이지와 조회 결과의 종목코드가 일치하지 않습니다.");
    }
    nameEl.textContent = stockPayload.stock_name || stockPayload.stock_code || CODE;
    codeEl.textContent = stockPayload.stock_code || CODE;
    chatContextNameEl.textContent = stockPayload.stock_name || stockPayload.stock_code || CODE;
    root.dataset.chatFixedStockName = stockPayload.stock_name || stockPayload.stock_code || CODE;
    renderStockLogo(PAGE_STOCK_CODE, stockPayload.stock_name);
    const history = Array.isArray(stockPayload.history) ? stockPayload.history : [];
    entries = history.length ? history : [stockPayload.latest].filter(Boolean);
    if (!entries.length) throw new Error("표시할 날짜별 데이터가 없습니다.");
    selectedIndex = 0;
    renderSelectedEntry();
    setPageState("ready");
  } catch (error) {
    setPageState("error", error.message || "종목 데이터를 불러오지 못했습니다.");
  }
}

retryBtn.addEventListener("click", load);
load();
