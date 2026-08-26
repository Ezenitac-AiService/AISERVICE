/**
 * common.js — 여러 페이지(index, detail, 단일 댓글 등)에서 공통으로 쓰는 표시 유틸
 *
 * 모듈 시스템을 쓰지 않으므로(전역 스크립트) 이 파일을 페이지별 스크립트보다
 * 먼저 <script>로 불러와야 합니다.
 *
 * 필드/상태값은 손성욱.md(§5 확정 Flask API 계약) 기준 snake_case를 그대로
 * 사용합니다. 과거 camelCase 별칭(positiveModel, artifactId 등)은 여기서
 * 만들지 않습니다.
 */

/* ---------------- 숫자·시각 표시 ---------------- */

function formatTradingVolume(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "—";
  }

  return `${Math.trunc(value).toLocaleString("ko-KR")}주`;
}

/**
 * ISO 시각 문자열을 "3분 전", "어제" 같은 상대 시간 문구로 변환합니다.
 */
function formatRelativeTime(isoString) {
  if (!isoString) return "—";
  const then = new Date(isoString).getTime();
  const now = Date.now();
  const diffMin = Math.max(0, Math.round((now - then) / 60000));

  if (diffMin < 1) return "방금 전";
  if (diffMin < 60) return `${diffMin}분 전`;

  const diffHour = Math.round(diffMin / 60);
  if (diffHour < 24) return `${diffHour}시간 전`;

  const diffDay = Math.round(diffHour / 24);
  if (diffDay === 1) return "어제";
  return `${diffDay}일 전`;
}

function formatModelValue(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return value.toLocaleString("ko-KR", { maximumFractionDigits: 6 });
}

function formatModelDate(value) {
  if (!value) return "기준일 없음";
  return value;
}

/**
 * 0~1 사이 비율값(vocabulary_coverage 등)을 퍼센트 문자열로 표시합니다.
 * null/undefined/NaN은 "—"로 표시하고 임의로 0%로 바꾸지 않습니다.
 */
function formatCoverage(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return `${(value * 100).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}%`;
}

/* ---------------- 모델 결과 존재 여부 ----------------
 * positive_model / negative_model 자체가 null인지 여부만 봅니다.
 * "결과가 정상인지"는 별개로 analysis_status가 판단하므로 섞지 않습니다. */

function hasModelResult(stock) {
  return Boolean(stock && (stock.positive_model || stock.negative_model));
}

/* ---------------- analysis_status 표시 ----------------
 * 손성욱.md §5.4 우선순위:
 * not_found → inference_pending → no_direction → unknown →
 * insufficient_features → ready
 * 프론트는 이 값을 그대로 사용하고 다른 규칙으로 재판정하지 않습니다. */

const ANALYSIS_STATUS_META = {
  not_found: { label: "일별문서 없음", tone: "muted" },
  inference_pending: { label: "추론 대기 중", tone: "pending" },
  no_direction: { label: "실제 수급 방향 없음", tone: "neutral" },
  unknown: { label: "상태 확인 불가", tone: "muted" },
  insufficient_features: { label: "분석 근거 부족", tone: "warning" },
  ready: { label: "정상 분석 완료", tone: "success" },
};

function analysisStatusLabel(status) {
  return ANALYSIS_STATUS_META[status]?.label ?? "상태 정보 없음";
}

/**
 * CSS 배지 클래스에 붙일 톤 키워드입니다. (예: `model-status--${tone}`)
 * index.css/detail.css에 톤별 색상 정의가 필요합니다.
 */
function analysisStatusTone(status) {
  return ANALYSIS_STATUS_META[status]?.tone ?? "muted";
}

/* ---------------- supply_data_status 표시 ----------------
 * estimated(장중 추정) / confirmed(장마감 확정) / null(값 없음)을 구분합니다.
 * null을 "확정"이나 다른 상태로 임의로 채우지 않습니다. */

const SUPPLY_DATA_STATUS_META = {
  estimated: { label: "장중 추정", tone: "pending" },
  confirmed: { label: "장마감 확정", tone: "success" },
};

function supplyDataStatusLabel(status) {
  if (!status) return null;
  return SUPPLY_DATA_STATUS_META[status]?.label ?? status;
}

function supplyDataStatusTone(status) {
  return SUPPLY_DATA_STATUS_META[status]?.tone ?? "muted";
}

/* ---------------- LLM 보고서 조회 상태 표시 ----------------
 * 손성욱.md §5.6 HTTP 상태·status 값 표를 그대로 반영합니다.
 * 메시지 문자열로 상태를 다시 판정하지 않고 status 값만 사용합니다. */

const LLM_REPORT_STATUS_META = {
  invalid_request: { label: "요청 오류", tone: "warning" },
  not_found: { label: "보고서 없음", tone: "muted" },
  inference_pending: { label: "추론 대기 중", tone: "pending" },
  report_pending: { label: "보고서 생성 대기 중", tone: "pending" },
  ready: { label: "분석 완료", tone: "success" },
  insufficient_evidence: { label: "근거 부족", tone: "warning" },
  internal_error: { label: "서버 오류", tone: "danger" },
};

function llmReportStatusLabel(status) {
  return LLM_REPORT_STATUS_META[status]?.label ?? "조회 실패";
}

function llmReportStatusTone(status) {
  return LLM_REPORT_STATUS_META[status]?.tone ?? "muted";
}

/**
 * commentary_source: "llm" 또는 "deterministic".
 * deterministic을 실패한 LLM 응답처럼 보이지 않게 별도 문구로 표시합니다. (§7.3)
 */
function commentarySourceLabel(source) {
  if (source === "llm") return "LLM 생성 해설";
  if (source === "deterministic") return "정형 근거 기반 자동 요약";
  return "—";
}

/**
 * report_refresh_status: "pending" 또는 "current".
 * estimated 보고서가 confirmed 수급 반영을 기다리는 중인지 표시합니다. (§5.5/§7.3)
 */
function reportRefreshStatusLabel(status) {
  if (status === "pending") return "확정 수급 반영 대기";
  if (status === "current") return "현재 수급 상태 반영됨";
  return null;
}

/* ---------------- 종목 로고 이미지 로드 실패 시 동적 아바타 폴백 ---------------- */

/**
 * 종목명 첫 글자 기반의 고유한 배경색을 가진 SVG 원형 아바타 Data URL을 생성합니다.
 * @param {string} stockName - 종목명 (예: "삼성전자", "SK하이닉스")
 * @returns {string} SVG Data URL
 */
function createStockInitialAvatar(stockName) {
  const initial = (stockName && stockName.trim().length > 0) ? stockName.trim()[0] : "종";
  
  let hash = 0;
  for (let i = 0; i < (stockName || "").length; i++) {
    hash = stockName.charCodeAt(i) + ((hash << 5) - hash);
  }
  const h = Math.abs(hash) % 360;
  const s = 65; // 채도
  const l = 45; // 명도

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
    <rect width="64" height="64" rx="32" fill="hsl(${h}, ${s}%, ${l}%)"/>
    <text x="50%" y="54%" font-family="Pretendard, -apple-system, sans-serif" font-size="28" font-weight="700" fill="#ffffff" text-anchor="middle" dominant-baseline="middle">${initial}</text>
  </svg>`;

  return "data:image/svg+xml;utf8," + encodeURIComponent(svg);
}

/**
 * 이미지 onerror 이벤트 발생 시 동적 아바타로 안전하게 교체합니다.
 * @param {HTMLImageElement} imgElement
 * @param {string} [stockName]
 */
function handleStockLogoError(imgElement, stockName) {
  if (!imgElement || imgElement.dataset.fallbackApplied) return;
  imgElement.dataset.fallbackApplied = "true";
  const name = stockName || imgElement.alt || imgElement.getAttribute("data-stock-name") || "종목";
  imgElement.src = createStockInitialAvatar(name);
}

// DOM 로드 완료 시 모든 stock-logo 이미지에 onerror 자동 바인딩
if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", function() {
    document.querySelectorAll("img.stock-logo, img[src*='stock-logos']").forEach(function(img) {
      img.addEventListener("error", function() {
        handleStockLogoError(img);
      });
    });
  });
}