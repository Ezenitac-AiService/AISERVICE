/**
 * PILOS 허용 질문 블록 분석 도우미.
 * 서버에 등록된 질문 블록만 선택하고 필요한 종목·기준일을 보충해 조회한다.
 */

(function () {
  "use strict";

  const fixedStockHost = document.querySelector("[data-chat-fixed-stock-code]");
  const inlineChatHost = document.querySelector("[data-chat-inline]");
  const IS_INLINE_MODE = Boolean(inlineChatHost);
  const configuredFixedStockCode = String(
    fixedStockHost?.dataset.chatFixedStockCode || "",
  ).trim();
  const IS_FIXED_STOCK_MODE = /^\d{1,6}$/.test(configuredFixedStockCode);
  const FIXED_STOCK_CODE = IS_FIXED_STOCK_MODE
    ? configuredFixedStockCode.padStart(6, "0")
    : null;

  function configuredFixedStockName() {
    return String(fixedStockHost?.dataset.chatFixedStockName || "").trim();
  }

  const QUESTIONS = [
    {
      key: "stock-tree",
      label: "종목별 분석 확인",
      description: IS_FIXED_STOCK_MODE
        ? "현재 종목의 날짜와 지표를 골라 확인해요"
        : "종목과 날짜를 고른 뒤 실제 데이터를 확인해요",
      navigation: true,
      nextGroup: "stockOverview",
    },
    {
      key: "service-tree",
      label: "PILOS 연구 알아보기",
      description: "서비스와 두 방향 모델의 원리를 확인해요",
      navigation: true,
      nextGroup: "serviceOverview",
    },
  ];

  const STOCK_BLOCKS = {
    summary: {
      key: "follow-summary",
      blockKey: "stock_summary",
      label: "선택한 날의 분석 요약",
      action: "stock_analysis",
      metric: null,
      needsStock: true,
      message: "선택한 날짜의 분석을 발표에서 설명할 수 있게 쉽게 요약해줘",
      nextGroup: "stockAnalysisResult",
    },
    supply: {
      key: "follow-supply",
      blockKey: "stock_supply_index",
      label: "실제 수급지수",
      action: "stock_metric",
      metric: "supply_demand_index",
      needsStock: true,
      message: "선택한 날짜의 실제 수급지수를 알려줘.",
      nextGroup: "supplyResult",
    },
    buy: {
      key: "follow-buy",
      blockKey: "stock_buy_volume",
      label: "개인 매수량",
      action: "stock_metric",
      metric: "individual_buy_volume",
      needsStock: true,
      message: "선택한 날짜의 개인 매수량을 알려줘.",
      nextGroup: "buyResult",
    },
    sell: {
      key: "follow-sell",
      blockKey: "stock_sell_volume",
      label: "개인 매도량",
      action: "stock_metric",
      metric: "individual_sell_volume",
      needsStock: true,
      message: "선택한 날짜의 개인 매도량을 알려줘.",
      nextGroup: "sellResult",
    },
  };

  const SERVICE_BLOCKS = {
    overview: {
      key: "service-overview",
      blockKey: "service_overview",
      label: "PILOS 분석 방법으로 돌아가기",
      action: "service_knowledge",
      metric: null,
      needsStock: false,
      message: "PILOS 서비스가 무엇을 연구하는지 핵심 목적만 짧게 설명해줘. 세부 모델, 데이터 항목, 해석 유의사항은 제외하고 개요만 설명해줘.",
      nextGroup: "serviceOverview",
    },
    interpretation: {
      key: "service-interpretation",
      blockKey: "service_interpretation",
      label: "분석 결과 해석",
      action: "service_knowledge",
      metric: null,
      needsStock: false,
      message: "PILOS의 분석 결과를 사용자가 어떻게 읽어야 하는지 해석 방법만 쉽게 설명해줘. 투자 추천이나 미래 예측으로 오해하지 않도록 승인된 서비스 문서 내용에만 집중해줘.",
      nextGroup: "serviceOverview",
    },
  };

  const CHAT_BLOCK_GROUPS = {
    root: {
      prompt: "먼저 확인할 범위를 골라주세요.",
      items: QUESTIONS,
    },
    stockOverview: {
      prompt: IS_FIXED_STOCK_MODE
        ? "현재 종목에서 무엇을 확인할까요?"
        : "종목별로 무엇을 확인할까요?",
      items: [
        STOCK_BLOCKS.summary,
        {
          key: "stock-supply-tree",
          label: "개인투자자 실제 수급",
          navigation: true,
          nextGroup: "stockSupply",
        },
        {
          key: "stock-overview-root",
          label: "처음 질문으로 돌아가기",
          navigation: true,
          nextGroup: "root",
        },
      ],
    },
    stockSupply: {
      prompt: "실제 수급에서 어떤 값을 확인할까요?",
      items: [
        STOCK_BLOCKS.supply,
        STOCK_BLOCKS.buy,
        STOCK_BLOCKS.sell,
        {
          key: "stock-supply-back",
          label: "종목 분석 질문으로 돌아가기",
          navigation: true,
          nextGroup: "stockOverview",
        },
      ],
    },
    serviceOverview: {
      prompt: "어떤 내용을 더 확인할까요?",
      items: [
        {
          key: "service-research-target",
          blockKey: "service_research_target",
          label: "연구 대상",
          action: "service_knowledge",
          metric: null,
          needsStock: false,
          message: "PILOS의 연구 대상만 설명해줘. 어떤 댓글 데이터와 어떤 개인투자자 수급 데이터를 연결해서 무엇을 분석하는지에 집중해줘. 다른 모델 설명이나 데이터 항목 설명은 제외해줘.",
          nextGroup: "serviceOverview",
        },
        {
          key: "service-models",
          blockKey: "service_models",
          label: "두 방향 모델",
          action: "service_knowledge",
          metric: null,
          needsStock: false,
          message: "PILOS의 Positive 모델과 Negative 모델이 각각 무엇을 의미하고 왜 두 방향으로 나누어 분석하는지 설명해줘. 두 모델 관련 내용에만 집중해줘.",
          nextGroup: "modelOverview",
        },
        SERVICE_BLOCKS.interpretation,
        {
          key: "service-columns",
          blockKey: "service_columns",
          label: "데이터 항목",
          action: "service_knowledge",
          metric: null,
          needsStock: false,
          message: "PILOS가 사용자에게 공개하는 주요 데이터 항목이 무엇인지 승인된 서비스 문서에 있는 내용만 짧게 설명해줘. 모든 항목은 한글 이름으로만 표현하고 영문 DB 컬럼명과 내부 구현용 필드는 제외해줘.",
          nextGroup: "dataColumns",
        },
        {
          key: "service-cautions",
          blockKey: "service_cautions",
          label: "분석 시 유의사항",
          action: "service_knowledge",
          metric: null,
          needsStock: false,
          message: "PILOS 분석 결과를 사용자가 해석할 때 주의해야 할 점만 설명해줘. 투자 추천이나 미래 수익 예측이 아니라는 점을 포함해 승인 문서에 있는 내용만 사용해줘.",
          nextGroup: "serviceOverview",
        },
      ],
    },
    modelOverview: {
      prompt: "두 방향 모델에서 무엇을 더 볼까요?",
      items: [
        {
          key: "service-positive-model",
          blockKey: "service_positive_model",
          label: "Positive 모델",
          action: "service_knowledge",
          metric: null,
          needsStock: false,
          message: "PILOS의 Positive 모델이 무엇인지 그 내용만 쉽게 설명해줘. Negative 모델이나 데이터 항목 설명은 제외해줘.",
          nextGroup: "modelOverview",
        },
        {
          key: "service-negative-model",
          blockKey: "service_negative_model",
          label: "Negative 모델",
          action: "service_knowledge",
          metric: null,
          needsStock: false,
          message: "PILOS의 Negative 모델이 무엇인지 그 내용만 쉽게 설명해줘. Positive 모델이나 데이터 항목 설명은 제외해줘.",
          nextGroup: "modelOverview",
        },
        {
          key: "service-model-difference",
          blockKey: "service_model_difference",
          label: "두 모델의 차이",
          action: "service_knowledge",
          metric: null,
          needsStock: false,
          message: "PILOS의 Positive 모델과 Negative 모델의 차이만 비교해서 쉽게 설명해줘. 다른 서비스 기능이나 데이터 항목 설명은 제외해줘.",
          nextGroup: "modelOverview",
        },
        {
          key: "service-score-calculation",
          blockKey: "service_score_calculation",
          label: "점수 계산 방식",
          action: "service_knowledge",
          metric: null,
          needsStock: false,
          message: "PILOS의 두 방향 모델 점수가 어떤 입력 요소를 바탕으로 계산되는지 승인된 서비스 문서 범위에서만 쉽게 설명해줘. 비공개 구현 세부정보는 제외해줘.",
          nextGroup: "modelOverview",
        },
        SERVICE_BLOCKS.overview,
      ],
    },
    dataColumns: {
      prompt: "어떤 데이터 항목을 쉽게 풀어볼까요?",
      items: [
        {
          key: "column-model-date",
          blockKey: "column_model_date",
          label: "분석 기준일",
          action: "service_knowledge",
          metric: null,
          needsStock: false,
          message: "PILOS에서 분석 기준일이 무엇을 의미하는지 그 항목만 쉽게 설명해줘. 영문 컬럼명은 표시하지 마.",
          nextGroup: "dataColumns",
        },
        {
          key: "column-text-score",
          blockKey: "column_text_score",
          label: "댓글 표현 점수",
          action: "service_knowledge",
          metric: null,
          needsStock: false,
          message: "PILOS에서 댓글 표현 점수가 무엇을 의미하는지 그 항목만 쉽게 설명해줘. 미래 예측값이나 감성 확률로 오해하지 않도록 설명하고 영문 컬럼명은 표시하지 마.",
          nextGroup: "dataColumns",
        },
        {
          key: "column-comment-count",
          blockKey: "column_comment_count",
          label: "분석 댓글 수",
          action: "service_knowledge",
          metric: null,
          needsStock: false,
          message: "PILOS에서 분석 댓글 수가 무엇을 의미하고 분석에서 어떻게 사용되는지 그 항목만 쉽게 설명해줘. 영문 컬럼명은 표시하지 마.",
          nextGroup: "dataColumns",
        },
        {
          key: "column-supply-index",
          blockKey: "column_supply_index",
          label: "수급지수",
          action: "service_knowledge",
          metric: null,
          needsStock: false,
          message: "PILOS의 수급지수가 무엇을 의미하는지 승인된 서비스 문서에 정의된 범위에서만 쉽게 설명해줘. 정본에 없는 강도 구간이나 투자 판단 기준은 만들지 마.",
          nextGroup: "dataColumns",
        },
        {
          key: "column-buy-volume",
          blockKey: "column_buy_volume",
          label: "개인 매수량",
          action: "service_knowledge",
          metric: null,
          needsStock: false,
          message: "PILOS에서 개인 매수량 데이터가 무엇을 의미하는지 그 항목만 쉽게 설명해줘.",
          nextGroup: "dataColumns",
        },
        {
          key: "column-sell-volume",
          blockKey: "column_sell_volume",
          label: "개인 매도량",
          action: "service_knowledge",
          metric: null,
          needsStock: false,
          message: "PILOS에서 개인 매도량 데이터가 무엇을 의미하는지 그 항목만 쉽게 설명해줘.",
          nextGroup: "dataColumns",
        },
        SERVICE_BLOCKS.overview,
      ],
    },
    supplyResult: {
      prompt: "다른 정보도 확인해볼까요?",
      items: [
        STOCK_BLOCKS.buy,
        STOCK_BLOCKS.sell,
        STOCK_BLOCKS.summary,
        {
          ...STOCK_BLOCKS.supply,
          key: "change-supply-context",
          label: IS_FIXED_STOCK_MODE ? "다른 날짜 확인" : "다른 종목/날짜 확인",
          resetContext: true,
        },
      ],
    },
    buyResult: {
      prompt: "같은 종목과 날짜에서 더 확인해볼까요?",
      items: [STOCK_BLOCKS.sell, STOCK_BLOCKS.supply, STOCK_BLOCKS.summary],
    },
    sellResult: {
      prompt: "같은 종목과 날짜에서 더 확인해볼까요?",
      items: [STOCK_BLOCKS.buy, STOCK_BLOCKS.supply, STOCK_BLOCKS.summary],
    },
    stockMetricResult: {
      prompt: "관련 데이터를 더 확인할까요?",
      items: [STOCK_BLOCKS.supply, STOCK_BLOCKS.buy, STOCK_BLOCKS.sell, STOCK_BLOCKS.summary],
    },
    stockAnalysisResult: {
      prompt: "관련 데이터를 더 확인할까요?",
      items: [
        STOCK_BLOCKS.supply,
        STOCK_BLOCKS.buy,
        STOCK_BLOCKS.sell,
        {
          ...SERVICE_BLOCKS.interpretation,
          key: "analysis-interpretation",
          label: "PILOS 분석 결과 해석 방법",
        },
      ],
    },
  };

  const STATUS_LABELS = {
    ready: "답변 완료",
    needs_clarification: "선택 필요",
    not_ready: "준비 중",
    not_found: "근거 없음",
    unavailable: "일시 사용 불가",
    failed: "요청 실패",
    invalid_request: "요청 오류",
  };

  const MIN_THINKING_TIME_MS = 500;

  const state = {
    question: null,
    stockCode: FIXED_STOCK_CODE,
    stockName: configuredFixedStockName() || FIXED_STOCK_CODE,
    modelDate: null,
    stocks: null,
    stocksPromise: null,
    detailCache: new Map(),
    requestedDate: null,
    lastRoute: null,
    activeBlockGroup: null,
    requestController: null,
    running: false,
  };

  function createWidget() {
    let fab = null;
    if (!IS_INLINE_MODE) {
      fab = document.createElement("button");
      fab.type = "button";
      fab.id = "chat-fab";
      fab.className = "chat-fab";
      fab.setAttribute("aria-label", "PILOS 분석 도우미 열기");
      fab.innerHTML =
        '<span class="chat-fab__icon" aria-hidden="true">' +
        '<svg viewBox="0 0 24 24" width="20" height="20" fill="none">' +
        '<path d="M4 5h16v11H8l-4 4V5Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>' +
        '<path d="M8 9h8M8 12h5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>' +
        "</svg></span>" +
        `<span class="chat-fab__label">${IS_FIXED_STOCK_MODE ? "종목 분석 도우미" : "분석 도우미"}</span>`;
      document.body.appendChild(fab);
    }

    const overlay = document.createElement("div");
    overlay.id = "chat-overlay";
    overlay.className = IS_INLINE_MODE
      ? "chat-overlay chat-overlay--inline"
      : "chat-overlay";
    overlay.hidden = !IS_INLINE_MODE;
    overlay.innerHTML = `
      <aside class="chat-panel" role="${IS_INLINE_MODE ? "region" : "dialog"}" ${IS_INLINE_MODE ? "" : 'aria-modal="true"'} aria-labelledby="chat-panel-title">
        <header class="chat-panel__head">
          <div>
            <p class="chat-panel__eyebrow">PILOS GUIDE</p>
            <h2 id="chat-panel-title">${IS_FIXED_STOCK_MODE ? "이 종목에서 무엇을 확인할까요?" : "무엇을 확인할까요?"}</h2>
          </div>
          <button type="button" id="chat-close" class="chat-panel__close" aria-label="분석 도우미 닫기" ${IS_INLINE_MODE ? "hidden" : ""}>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" aria-hidden="true">
              <path d="M6 6l12 12M18 6 6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
          </button>
        </header>

        <div class="chat-panel__body">
          <div id="chat-flow" class="chat-flow" aria-live="polite">
            <div class="chat-bubble-row chat-bubble-row--assistant">
              <span class="chat-bubble-avatar" aria-hidden="true">P</span>
              <div class="chat-bubble">
                <p id="chat-intro-message">${IS_FIXED_STOCK_MODE ? "현재 상세 종목 전용 분석 도우미입니다. 종목은 고정되어 있으며 허용된 질문과 날짜를 순서대로 골라주세요." : "안녕하세요. PILOS 분석 도우미입니다. 궁금하거나 확인하고 싶은 범위를 먼저 골라주세요."}</p>
              </div>
            </div>
            <div id="chat-question-list" class="chat-question-list" role="group" aria-label="분석 질문 선택"></div>
          </div>

          <section id="chat-context" class="chat-context" hidden aria-labelledby="chat-context-title">
            <div class="chat-context__head">
              <span>확인할 내용</span>
              <strong id="chat-context-title"></strong>
            </div>

            <div id="chat-fixed-stock" class="chat-fixed-stock" ${IS_FIXED_STOCK_MODE ? "" : "hidden"}>
              <span>고정 종목</span>
              <strong id="chat-fixed-stock-name">${FIXED_STOCK_CODE || ""}</strong>
              <small>이 상세 화면에서는 다른 종목으로 변경되지 않습니다.</small>
            </div>

            <label id="chat-stock-field" class="chat-field" for="chat-stock-input" ${IS_FIXED_STOCK_MODE ? "hidden" : ""}>
              <span>종목</span>
              <div class="chat-combo">
                <input id="chat-stock-input" type="text" autocomplete="off" placeholder="종목명 또는 코드 검색" />
                <div id="chat-stock-results" class="chat-combo__results" hidden></div>
              </div>
            </label>

            <label class="chat-field" for="chat-date-select">
              <span>분석 기준일</span>
              <select id="chat-date-select" disabled>
                <option value="">${IS_FIXED_STOCK_MODE ? "날짜를 불러오는 중…" : "종목을 먼저 선택해주세요"}</option>
              </select>
            </label>

            <button type="button" id="chat-run" class="chat-run" disabled>결과 확인하기</button>
          </section>

          <section id="chat-result" class="chat-result" hidden aria-live="polite">
            <div class="chat-result__head">
              <span id="chat-result-status" class="status-badge status-badge--muted"></span>
              <span id="chat-result-date" class="chat-result__date"></span>
            </div>
            <div id="chat-result-answer" class="chat-result__answer"></div>
            <div id="chat-result-sources" class="chat-result__sources"></div>
            <div id="chat-result-warnings" class="chat-result__warnings"></div>
            <div id="chat-result-followups" class="chat-result__followups" hidden>
              <p id="chat-result-followups-title"></p>
              <div id="chat-result-followups-list" class="chat-follow-up-list" role="group" aria-label="다음 확인 내용"></div>
            </div>
            <button type="button" id="chat-result-context" class="chat-result__context">${IS_FIXED_STOCK_MODE ? "날짜 다시 선택하기" : "종목과 날짜 다시 선택하기"}</button>
          </section>
        </div>

        <p class="chat-panel__guard">등록된 질문 블록만 선택해 조회할 수 있습니다.</p>
      </aside>`;
    (inlineChatHost || document.body).appendChild(overlay);

    return { fab, overlay };
  }

  const { fab, overlay } = createWidget();
  const panel = overlay.querySelector(".chat-panel");
  const closeButton = document.getElementById("chat-close");
  const flowEl = document.getElementById("chat-flow");
  const questionListEl = document.getElementById("chat-question-list");
  const contextEl = document.getElementById("chat-context");
  const contextTitleEl = document.getElementById("chat-context-title");
  const stockInputEl = document.getElementById("chat-stock-input");
  const stockResultsEl = document.getElementById("chat-stock-results");
  const fixedStockNameEl = document.getElementById("chat-fixed-stock-name");
  const dateSelectEl = document.getElementById("chat-date-select");
  const runButton = document.getElementById("chat-run");
  const resultEl = document.getElementById("chat-result");
  const resultStatusEl = document.getElementById("chat-result-status");
  const resultDateEl = document.getElementById("chat-result-date");
  const resultAnswerEl = document.getElementById("chat-result-answer");
  const resultSourcesEl = document.getElementById("chat-result-sources");
  const resultWarningsEl = document.getElementById("chat-result-warnings");
  const resultFollowUpsEl = document.getElementById("chat-result-followups");
  const resultFollowUpsTitleEl = document.getElementById("chat-result-followups-title");
  const resultFollowUpsListEl = document.getElementById("chat-result-followups-list");
  const resultContextButton = document.getElementById("chat-result-context");

  function openWidget() {
    if (IS_INLINE_MODE) {
      panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
      questionListEl.querySelector("button")?.focus();
      return;
    }
    overlay.hidden = false;
    questionListEl.querySelector("button")?.focus();
  }

  function closeWidget() {
    resetConversation();
    if (IS_INLINE_MODE) return;
    overlay.hidden = true;
    fab?.focus();
  }

  fab?.addEventListener("click", openWidget);
  document.querySelectorAll("[data-chat-open]").forEach((button) => {
    button.addEventListener("click", openWidget);
  });
  closeButton.addEventListener("click", closeWidget);
  overlay.addEventListener("click", (event) => {
    if (!IS_INLINE_MODE && event.target === overlay) closeWidget();
  });
  document.addEventListener("keydown", (event) => {
    if (!IS_INLINE_MODE && event.key === "Escape" && !overlay.hidden) closeWidget();
  });

  function renderQuestions() {
    questionListEl.innerHTML = "";
    QUESTIONS.forEach((question) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "chat-question";
      button.dataset.key = question.key;
      button.innerHTML =
        '<span class="chat-question__copy"><strong></strong><small></small></span>' +
        '<span class="chat-question__arrow" aria-hidden="true">→</span>';
      button.querySelector("strong").textContent = question.label;
      button.querySelector("small").textContent = question.description;
      button.addEventListener("click", () => chooseQuestion(question));
      questionListEl.appendChild(button);
    });
  }

  function appendBubble(role, message, extraClass = "") {
    const row = document.createElement("div");
    row.className = `chat-bubble-row chat-bubble-row--${role} chat-flow__transient ${extraClass}`.trim();

    if (role === "assistant") {
      const avatar = document.createElement("span");
      avatar.className = "chat-bubble-avatar";
      avatar.setAttribute("aria-hidden", "true");
      avatar.textContent = "P";
      row.appendChild(avatar);
    }

    const bubble = document.createElement("div");
    bubble.className = "chat-bubble";
    const text = document.createElement("p");
    text.textContent = message;
    bubble.appendChild(text);
    row.appendChild(bubble);
    flowEl.appendChild(row);
    scrollPanelToEnd();
    return row;
  }

  function appendNavigationGroup(groupName) {
    const group = CHAT_BLOCK_GROUPS[groupName];
    if (!group || !Array.isArray(group.items)) return;

    state.activeBlockGroup = groupName;
    const row = appendBubble("assistant", group.prompt, "chat-flow__navigation");
    const bubble = row.querySelector(".chat-bubble");
    const list = document.createElement("div");
    list.className = "chat-follow-up-list chat-navigation-list";
    list.setAttribute("role", "group");
    list.setAttribute("aria-label", group.prompt);
    group.items.forEach((block) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "chat-follow-up";
      button.innerHTML = '<span></span><span aria-hidden="true">→</span>';
      button.firstElementChild.textContent = block.label;
      button.addEventListener("click", () => chooseFollowUp(block));
      list.appendChild(button);
    });
    bubble.appendChild(list);
    scrollPanelToEnd();
  }

  function appendThinkingBubble(message) {
    const row = appendBubble("assistant", message, "chat-flow__loading");
    const text = row.querySelector(".chat-bubble p");
    const dots = document.createElement("span");
    dots.className = "chat-thinking-dots";
    dots.setAttribute("aria-label", "답변 생각 중");
    for (let index = 0; index < 3; index += 1) {
      const dot = document.createElement("span");
      dot.setAttribute("aria-hidden", "true");
      dots.appendChild(dot);
    }
    text.append(" ", dots);
    return row;
  }

  function waitForMinimumThinking(startedAt) {
    const remaining = MIN_THINKING_TIME_MS - (Date.now() - startedAt);
    if (remaining <= 0) return Promise.resolve();
    return new Promise((resolve) => window.setTimeout(resolve, remaining));
  }

  function scrollPanelToEnd() {
    window.requestAnimationFrame(() => {
      const body = panel.querySelector(".chat-panel__body");
      body.scrollTop = body.scrollHeight;
    });
  }

  function archiveCurrentResult() {
    if (resultEl.hidden) return;

    const archivedResult = resultEl.cloneNode(true);
    archivedResult.removeAttribute("id");
    archivedResult.removeAttribute("aria-live");
    archivedResult.querySelectorAll("[id]").forEach((element) => element.removeAttribute("id"));
    archivedResult.querySelector(".chat-result__followups")?.remove();
    archivedResult.querySelector(".chat-result__context")?.remove();
    archivedResult.classList.add("chat-result--history", "chat-flow__transient");
    archivedResult.hidden = false;
    flowEl.appendChild(archivedResult);
    resultEl.hidden = true;
    scrollPanelToEnd();
  }

  function stockContextPrompt() {
    return IS_FIXED_STOCK_MODE
      ? `${state.stockName || FIXED_STOCK_CODE}의 어떤 날짜를 확인해볼까요?`
      : "어떤 종목과 날짜를 확인해볼까요?";
  }

  function focusContextControl() {
    if (IS_FIXED_STOCK_MODE) {
      dateSelectEl.focus();
    } else {
      stockInputEl.focus();
    }
  }

  async function prepareFixedStockContext(options = {}) {
    if (!IS_FIXED_STOCK_MODE) return;
    await selectStock(
      {
        stock_code: FIXED_STOCK_CODE,
        stock_name: configuredFixedStockName() || state.stockName || FIXED_STOCK_CODE,
      },
      {
        preferredDate: options.preferredDate || null,
        selectFirst: options.selectFirst === true,
      },
    );
  }

  function resetStockContext() {
    state.stockCode = IS_FIXED_STOCK_MODE ? FIXED_STOCK_CODE : null;
    state.stockName = IS_FIXED_STOCK_MODE
      ? configuredFixedStockName() || state.stockName || FIXED_STOCK_CODE
      : null;
    state.modelDate = null;
    state.requestedDate = null;
    stockInputEl.value = IS_FIXED_STOCK_MODE
      ? `${state.stockName} (${FIXED_STOCK_CODE})`
      : "";
    stockResultsEl.hidden = true;
    stockResultsEl.innerHTML = "";
    dateSelectEl.disabled = true;
    dateSelectEl.innerHTML = IS_FIXED_STOCK_MODE
      ? '<option value="">날짜를 선택해주세요</option>'
      : '<option value="">종목을 먼저 선택해주세요</option>';
    if (IS_FIXED_STOCK_MODE && fixedStockNameEl) {
      fixedStockNameEl.textContent = `${state.stockName} · ${FIXED_STOCK_CODE}`;
    }
  }

  function resetConversation() {
    state.requestController?.abort();
    state.requestController = null;
    state.running = false;
    state.question = null;
    state.lastRoute = null;
    state.activeBlockGroup = null;
    resetStockContext();
    flowEl.querySelectorAll(".chat-flow__transient").forEach((element) => element.remove());
    clearResultDetails();
    resultEl.hidden = true;
    contextEl.hidden = true;
    questionListEl.querySelectorAll(".chat-question").forEach((button) => {
      button.classList.remove("chat-question--active");
    });
    runButton.textContent = "결과 확인하기";
    updateRunButton();
    panel.querySelector(".chat-panel__body").scrollTop = 0;
  }

  async function chooseQuestion(question) {
    if (state.running) return;
    archiveCurrentResult();
    state.question = question;
    contextEl.hidden = true;
    resetStockContext();
    questionListEl.querySelectorAll(".chat-question").forEach((button) => {
      button.classList.toggle("chat-question--active", button.dataset.key === question.key);
    });
    appendBubble("user", question.label);

    if (question.navigation) {
      appendNavigationGroup(question.nextGroup);
      return;
    }

    if (!question.needsStock) {
      runQuestion();
      return;
    }

    appendBubble("assistant", stockContextPrompt());
    contextTitleEl.textContent = question.label;
    contextEl.hidden = false;
    if (IS_FIXED_STOCK_MODE) {
      await prepareFixedStockContext({ selectFirst: false });
    }
    updateRunButton();
    focusContextControl();
    scrollPanelToEnd();
  }

  function ensureStocks() {
    if (state.stocks) return Promise.resolve(state.stocks);
    if (state.stocksPromise) return state.stocksPromise;
    state.stocksPromise = fetch("/api/stocks")
      .then((response) => {
        if (!response.ok) throw new Error("종목 목록을 불러오지 못했습니다.");
        return response.json();
      })
      .then((stocks) => {
        state.stocks = Array.isArray(stocks) ? stocks : [];
        return state.stocks;
      })
      .finally(() => {
        state.stocksPromise = null;
      });
    return state.stocksPromise;
  }

  function historyEntries(detail) {
    return Array.isArray(detail.history) && detail.history.length
      ? detail.history
      : [detail.latest].filter(Boolean);
  }

  function matchRequestedModelDate(history, requestedDate) {
    if (!requestedDate) return null;
    const matches = history
      .map((entry) => entry && entry.model_date)
      .filter(Boolean)
      .filter((modelDate) => {
        const [year, month, day] = modelDate.split("-").map(Number);
        return (
          month === requestedDate.month &&
          day === requestedDate.day &&
          (requestedDate.year === null || year === requestedDate.year)
        );
      });
    return matches.length === 1 ? matches[0] : null;
  }

  async function searchStocks(query) {
    const keyword = query.trim().toLowerCase();
    stockResultsEl.innerHTML = "";
    if (!keyword) {
      stockResultsEl.hidden = true;
      return;
    }

    try {
      const stocks = await ensureStocks();
      const matches = stocks
        .filter((stock) =>
          (stock.stock_name || "").toLowerCase().includes(keyword) ||
          (stock.stock_code || "").includes(keyword),
        )
        .slice(0, 7);

      if (!matches.length) {
        const empty = document.createElement("p");
        empty.className = "chat-combo__empty";
        empty.textContent = "검색 결과가 없습니다.";
        stockResultsEl.appendChild(empty);
      } else {
        matches.forEach((stock) => {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "chat-combo__item";
          const name = document.createElement("strong");
          name.textContent = stock.stock_name || stock.stock_code;
          const code = document.createElement("span");
          code.textContent = stock.stock_code;
          button.append(name, code);
          button.addEventListener("click", () =>
            selectStock(stock, { selectFirst: !state.question?.isNatural }),
          );
          stockResultsEl.appendChild(button);
        });
      }
      stockResultsEl.hidden = false;
    } catch (error) {
      const empty = document.createElement("p");
      empty.className = "chat-combo__empty";
      empty.textContent = error.message;
      stockResultsEl.appendChild(empty);
      stockResultsEl.hidden = false;
    }
  }

  async function getDetail(code) {
    if (state.detailCache.has(code)) return state.detailCache.get(code);
    const response = await fetch(`/api/stocks/${encodeURIComponent(code)}`);
    if (!response.ok) throw new Error("기준일을 불러오지 못했습니다.");
    const body = await response.json();
    state.detailCache.set(code, body);
    return body;
  }

  async function selectStock(stock, options = {}) {
    const requestedPreferredDate = options.preferredDate || null;
    const selectFirst = options.selectFirst !== false;
    state.stockCode = stock.stock_code;
    state.stockName = stock.stock_name || stock.stock_code;
    state.modelDate = null;
    stockInputEl.value = `${stock.stock_name || stock.stock_code} (${stock.stock_code})`;
    stockResultsEl.hidden = true;
    dateSelectEl.disabled = true;
    dateSelectEl.innerHTML = '<option value="">기준일을 불러오는 중…</option>';
    updateRunButton();

    try {
      const detail = await getDetail(stock.stock_code);
      state.stockName = detail.stock_name || state.stockName || stock.stock_code;
      stockInputEl.value = `${state.stockName} (${stock.stock_code})`;
      if (IS_FIXED_STOCK_MODE && fixedStockNameEl) {
        fixedStockNameEl.textContent = `${state.stockName} · ${FIXED_STOCK_CODE}`;
      }
      const history = historyEntries(detail);
      const preferredDate =
        requestedPreferredDate || matchRequestedModelDate(history, state.requestedDate);
      dateSelectEl.innerHTML = "";
      if (!selectFirst && !preferredDate) {
        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = "기준일을 선택해주세요";
        dateSelectEl.appendChild(placeholder);
      }
      history.forEach((entry) => {
        if (!entry.model_date) return;
        const option = document.createElement("option");
        option.value = entry.model_date;
        option.textContent = entry.model_date;
        dateSelectEl.appendChild(option);
      });
      const hasAvailableDate = history.some((entry) => entry && entry.model_date);
      if (hasAvailableDate) {
        dateSelectEl.disabled = false;
        if (preferredDate && Array.from(dateSelectEl.options).some((option) => option.value === preferredDate)) {
          state.modelDate = preferredDate;
          dateSelectEl.value = preferredDate;
        } else if (selectFirst) {
          state.modelDate = Array.from(dateSelectEl.options).find((option) => option.value)?.value || null;
          dateSelectEl.value = state.modelDate || "";
        }
      } else {
        dateSelectEl.innerHTML = '<option value="">조회 가능한 기준일 없음</option>';
      }
    } catch (error) {
      dateSelectEl.innerHTML = `<option value="">${error.message}</option>`;
    }
    updateRunButton();
  }

  function updateRunButton() {
    runButton.disabled =
      state.running || !state.question || !state.stockCode || !state.modelDate;
  }

  stockInputEl.addEventListener("input", () => {
    if (IS_FIXED_STOCK_MODE) return;
    state.stockCode = null;
    state.stockName = null;
    state.modelDate = null;
    dateSelectEl.disabled = true;
    dateSelectEl.innerHTML = '<option value="">종목을 먼저 선택해주세요</option>';
    updateRunButton();
    searchStocks(stockInputEl.value);
  });

  dateSelectEl.addEventListener("change", () => {
    state.modelDate = dateSelectEl.value || null;
    updateRunButton();
  });

  runButton.addEventListener("click", runQuestion);

  function clearResultDetails() {
    resultSourcesEl.innerHTML = "";
    resultWarningsEl.innerHTML = "";
    state.activeBlockGroup = null;
    resultFollowUpsEl.hidden = true;
    resultFollowUpsTitleEl.textContent = "";
    resultFollowUpsListEl.innerHTML = "";
  }

  function followUpGroupFor(body) {
    if (body.status !== "ready" || body.route === "restricted") return null;
    if (state.question?.nextGroup) return state.question.nextGroup;
    if (body.route === "general") return "root";
    if (body.route === "service_knowledge") return "serviceOverview";
    if (body.route === "stock_analysis") return "stockAnalysisResult";
    if (body.route === "stock_metric") return "stockMetricResult";
    return null;
  }

  function renderFollowUps(body) {
    const groupName = followUpGroupFor(body);
    const group = groupName ? CHAT_BLOCK_GROUPS[groupName] : null;
    if (!group || !Array.isArray(group.items) || !group.items.length) return;

    state.activeBlockGroup = groupName;
    resultFollowUpsTitleEl.textContent = group.prompt;
    group.items.forEach((block) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "chat-follow-up";
      button.innerHTML = '<span></span><span aria-hidden="true">→</span>';
      button.firstElementChild.textContent = block.label;
      button.addEventListener("click", () => chooseFollowUp(block));
      resultFollowUpsListEl.appendChild(button);
    });
    resultFollowUpsEl.hidden = false;
  }

  function statusTone(status) {
    if (status === "ready") return "success";
    if (status === "not_ready") return "pending";
    if (status === "needs_clarification" || status === "invalid_request") return "warning";
    if (status === "unavailable" || status === "failed") return "danger";
    return "muted";
  }

  function displayDate(modelDate) {
    if (typeof modelDate !== "string") return "";
    const match = modelDate.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!match) return modelDate;
    return `${Number(match[2])}월 ${Number(match[3])}일`;
  }

  function escapePattern(value) {
    return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function appendInlineMarkdown(container, value) {
    const text = String(value || "");
    const tokenPattern = /(\*\*[^*]+\*\*|`[^`]+`)/g;
    let cursor = 0;

    for (const match of text.matchAll(tokenPattern)) {
      if (match.index > cursor) {
        container.appendChild(document.createTextNode(text.slice(cursor, match.index)));
      }

      const token = match[0];
      const element = document.createElement(token.startsWith("**") ? "strong" : "code");
      element.textContent = token.startsWith("**") ? token.slice(2, -2) : token.slice(1, -1);
      container.appendChild(element);
      cursor = match.index + token.length;
    }

    if (cursor < text.length) {
      container.appendChild(document.createTextNode(text.slice(cursor)));
    }
  }

  /* ── Spec 017: CJK Korean Markdown Bold Sanitizer ──────────────── */
  function sanitizeKoreanMarkdown(md) {
    if (!md) return "";
    // Pattern 1: **"text"**조사 or **'text'**조사
    md = md.replace(/\*\*(["'])([^"'*\n]+?)\1\*\*([가-힣]+)/g, "<strong>$1$2$1</strong>$3");
    // Pattern 2: **text**조사
    md = md.replace(/\*\*([^*\n]+?)\*\*([가-힣]+)/g, "<strong>$1</strong>$2");
    return md;
  }
  /* ─────────────────────────────────────────────────────────────── */

  function renderMarkdown(container, markdown) {
    container.innerHTML = "";
    // Spec 017: Apply Korean markdown sanitization before parsing
    const sanitized = sanitizeKoreanMarkdown(String(markdown || "표시할 답변이 없습니다."));
    const lines = sanitized
      .replace(/\r\n?/g, "\n")
      .split("\n");
    let index = 0;

    while (index < lines.length) {
      const startIndex = index;
      const line = lines[index];
      if (!line.trim()) {
        index += 1;
        continue;
      }

      const heading = line.match(/^(#{1,3})\s*(.*)$/);
      if (heading) {
        const element = document.createElement(`h${heading[1].length + 2}`);
        appendInlineMarkdown(element, heading[2]);
        container.appendChild(element);
        index += 1;
        continue;
      }

      if (/^\s*([-*_])(?:\s*\1){2,}\s*$/.test(line)) {
        container.appendChild(document.createElement("hr"));
        index += 1;
        continue;
      }

      const listItem = line.match(/^\s*([-*+]|\d+\.)\s*(.*)$/);
      if (listItem) {
        const ordered = /^\d/.test(listItem[1]);
        const list = document.createElement(ordered ? "ol" : "ul");
        while (index < lines.length) {
          const current = lines[index].match(/^\s*([-*+]|\d+\.)\s*(.*)$/);
          if (!current || /^\d/.test(current[1]) !== ordered) break;
          const item = document.createElement("li");
          appendInlineMarkdown(item, current[2]);
          list.appendChild(item);
          index += 1;
        }
        container.appendChild(list);
        if (index <= startIndex) index = startIndex + 1;
        continue;
      }

      if (/^>\s?/.test(line)) {
        const quote = document.createElement("blockquote");
        const quoteLines = [];
        while (index < lines.length && /^>\s?/.test(lines[index])) {
          quoteLines.push(lines[index].replace(/^>\s?/, ""));
          index += 1;
        }
        appendInlineMarkdown(quote, quoteLines.join(" "));
        container.appendChild(quote);
        if (index <= startIndex) index = startIndex + 1;
        continue;
      }

      const paragraph = document.createElement("p");
      const paragraphLines = [];
      while (
        index < lines.length &&
        lines[index].trim() &&
        !/^(#{1,3})\s*/.test(lines[index]) &&
        !/^\s*([-*+]|\d+\.)\s*/.test(lines[index]) &&
        !/^>\s?/.test(lines[index]) &&
        !/^\s*([-*_])(?:\s*\1){2,}\s*$/.test(lines[index])
      ) {
        paragraphLines.push(lines[index].trim());
        index += 1;
      }

      if (paragraphLines.length === 0) {
        paragraphLines.push(lines[index].trim());
        index += 1;
      }

      paragraphLines.forEach((paragraphLine, lineIndex) => {
        if (lineIndex > 0) paragraph.appendChild(document.createElement("br"));
        appendInlineMarkdown(paragraph, paragraphLine);
      });
      container.appendChild(paragraph);

      if (index <= startIndex) {
        index = startIndex + 1;
      }
    }
  }

  function formatChatAnswer(answer, body) {
    let formatted = String(answer || "표시할 답변이 없습니다.");
    formatted = formatted.replace(
      /^(\d{4})-(\d{2})-(\d{2})\s+/,
      (_match, _year, month, day) => `${Number(month)}월 ${Number(day)}일 `,
    );

    const stockCode = body.stock_code || state.stockCode;
    if (stockCode && state.stockName && state.stockName !== stockCode) {
      formatted = formatted.replace(
        new RegExp(`${escapePattern(stockCode)}의`, "g"),
        `${state.stockName}의`,
      );
    }

    formatted = formatted.replace(/수급지수은/g, "수급지수는");
    formatted = formatted.replace(
      /(수급지수는\s*)([-+]?\d+(?:\.\d+)?)(입니다)/g,
      (_match, prefix, value, suffix) => {
        const numericValue = Number(value);
        if (!Number.isFinite(numericValue)) return `${prefix}${value}${suffix}`;
        return `${prefix}${numericValue.toFixed(3)}${suffix}`;
      },
    );
    return formatted;
  }

  function renderResult(body) {
    state.lastRoute = body.route || null;
    resultStatusEl.textContent = STATUS_LABELS[body.status] || body.status || "답변 완료";
    resultStatusEl.className = `status-badge status-badge--${statusTone(body.status)}`;
    resultDateEl.textContent = body.as_of ? `기준일 ${displayDate(body.as_of)}` : "";
    renderMarkdown(resultAnswerEl, formatChatAnswer(body.answer, body));
    clearResultDetails();

    if (Array.isArray(body.sources) && body.sources.length) {
      const heading = document.createElement("span");
      heading.textContent = "근거";
      resultSourcesEl.appendChild(heading);
      body.sources.forEach((source) => {
        const chip = document.createElement("span");
        chip.textContent = source.label || source.type;
        resultSourcesEl.appendChild(chip);
      });
    }

    const currentStockCode = body.stock_code || state.stockCode;
    if (currentStockCode) {
      const naverUrl = `https://finance.naver.com/item/main.naver?code=${encodeURIComponent(currentStockCode)}`;
      const dartUrl = `https://dart.fss.or.kr/dsab007/main.do?textCrpNm=${encodeURIComponent(currentStockCode)}`;
      const linkBox = document.createElement("div");
      linkBox.className = "financial-links-box";
      linkBox.style = "margin-top: 10px; display: flex; gap: 8px; flex-wrap: wrap;";
      linkBox.innerHTML = `
        <a href="${naverUrl}" target="_blank" rel="noopener noreferrer" style="display:inline-flex; align-items:center; gap:4px; padding:6px 12px; border-radius:6px; background:#03c75a; color:#fff; font-size:12px; font-weight:700; text-decoration:none;">
          📈 네이버 증권 (${currentStockCode}) ↗
        </a>
        <a href="${dartUrl}" target="_blank" rel="noopener noreferrer" style="display:inline-flex; align-items:center; gap:4px; padding:6px 12px; border-radius:6px; background:#1e3a8a; color:#fff; font-size:12px; font-weight:700; text-decoration:none;">
          🏛️ DART 전자공시 ↗
        </a>
      `;
      resultSourcesEl.appendChild(linkBox);
    }

    if (Array.isArray(body.warnings)) {
      body.warnings.forEach((warning) => {
        const text = document.createElement("p");
        text.textContent = warning;
        resultWarningsEl.appendChild(text);
      });
    }
    renderFollowUps(body);
    resultContextButton.hidden = !["stock_metric", "stock_analysis"].includes(body.route);
    resultEl.hidden = false;
    resultEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function renderFailure(message) {
    renderResult({
      status: "failed",
      answer: message || "분석 결과를 불러오지 못했습니다.",
      sources: [],
      warnings: [],
    });
  }

  async function requestChat(payload, signal, onChunk) {
    const endpoint = IS_FIXED_STOCK_MODE
      ? `/api/stocks/${encodeURIComponent(FIXED_STOCK_CODE)}/chat`
      : "/api/chat";
    const requestPayload = { ...payload, stream: true };
    const response = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
      },
      body: JSON.stringify(requestPayload),
      signal,
    });

    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new Error(
        (body && (body.error || body.message)) ||
        `분석 요청을 처리하지 못했습니다. (${response.status})`,
      );
    }

    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json") || !response.body) {
      const body = await response.json().catch(() => null);
      return body;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    let finalBody = null;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const parts = buffer.split("\n\n");
      buffer = parts.pop();

      for (const part of parts) {
        const trimmed = part.trim();
        if (!trimmed || !trimmed.startsWith("data: ")) continue;
        const dataStr = trimmed.slice(6);
        if (dataStr === "[DONE]") {
          break;
        }
        try {
          const parsed = JSON.parse(dataStr);
          if (parsed.type === "token") {
            if (onChunk && parsed.content) {
              onChunk(parsed.content);
            }
          } else if (parsed.type === "done") {
            finalBody = parsed;
          } else if (parsed.type === "error") {
            throw new Error(parsed.error || "답변 생성 중 오류가 발생했습니다.");
          }
        } catch (e) {
          if (e.name === "Error") throw e;
          console.warn("SSE 파싱 무시:", dataStr);
        }
      }
    }

    return finalBody || { status: "ready", answer: "", sources: [], warnings: [] };
  }

  function isActiveRequest(controller) {
    return state.requestController === controller;
  }

  async function runQuestion(options = {}) {
    if (!state.question || state.running) return;
    if (state.question.needsStock && (!state.stockCode || !state.modelDate)) return;

    if (state.requestController) {
      state.requestController.abort();
      state.requestController = null;
    }

    const appendContextChoice = options.appendContextChoice !== false;
    const requestController = new AbortController();
    state.requestController = requestController;

    state.running = true;
    runButton.disabled = true;
    runButton.textContent = "결과를 확인하고 있어요…";
    resultEl.hidden = true;

    if (state.question.needsStock && appendContextChoice) {
      appendBubble(
        "user",
        `${state.stockName || state.stockCode} · ${state.modelDate}`,
        "chat-flow__context-choice",
      );
      contextEl.hidden = true;
    }
    const thinkingStartedAt = Date.now();
    const loadingBubble = appendThinkingBubble("답변 생각 중");

    const payload = { block_key: state.question.blockKey };
    if (state.question.needsStock) {
      payload.stock_code = state.stockCode;
      payload.model_date = state.modelDate;
    }

    let accumulatedText = "";
    let streamStarted = false;

    const handleChunk = (chunk) => {
      if (!isActiveRequest(requestController)) return;
      accumulatedText += chunk;
      if (!streamStarted) {
        streamStarted = true;
        if (loadingBubble && loadingBubble.parentNode) {
          loadingBubble.remove();
        }
        resultTitleEl.textContent = state.question.label;
        resultBadgeEl.className = "chat-result-card__badge chat-result-card__badge--ready";
        resultBadgeEl.textContent = "작성 중…";
        resultDateEl.textContent = state.modelDate ? `기준일 ${displayDate(state.modelDate)}` : "";
        clearResultDetails();
        resultEl.hidden = false;
      }
      renderMarkdown(resultAnswerEl, accumulatedText);
    };

    try {
      const body = await requestChat(payload, requestController.signal, handleChunk);
      if (!isActiveRequest(requestController)) return;
      if (!streamStarted) {
        await waitForMinimumThinking(thinkingStartedAt);
        if (!isActiveRequest(requestController)) return;
        if (loadingBubble && loadingBubble.parentNode) {
          loadingBubble.remove();
        }
      }
      renderResult(body);
    } catch (error) {
      if (!isActiveRequest(requestController) || error.name === "AbortError") return;
      if (loadingBubble && loadingBubble.parentNode) {
        loadingBubble.remove();
      }
      renderFailure(error.message);
    } finally {
      if (!isActiveRequest(requestController)) return;
      state.requestController = null;
      state.running = false;
      runButton.textContent = "결과 확인하기";
      updateRunButton();
    }
  }

  async function chooseFollowUp(block) {
    if (state.requestController) {
      state.requestController.abort();
      state.requestController = null;
      state.running = false;
    }

    archiveCurrentResult();
    state.question = block;
    contextEl.hidden = true;
    appendBubble("user", block.label);

    if (block.navigation) {
      appendNavigationGroup(block.nextGroup);
      return;
    }

    if (block.resetContext) {
      resetStockContext();
      appendBubble("assistant", stockContextPrompt());
      contextTitleEl.textContent = block.label;
      contextEl.hidden = false;
      if (IS_FIXED_STOCK_MODE) {
        await prepareFixedStockContext({ selectFirst: false });
      }
      updateRunButton();
      focusContextControl();
      scrollPanelToEnd();
      return;
    }

    if (block.needsStock && (!state.stockCode || !state.modelDate)) {
      appendBubble("assistant", stockContextPrompt());
      contextTitleEl.textContent = block.label;
      contextEl.hidden = false;
      if (IS_FIXED_STOCK_MODE) {
        await prepareFixedStockContext({ selectFirst: false });
      }
      updateRunButton();
      focusContextControl();
      scrollPanelToEnd();
      return;
    }

    await runQuestion({ appendContextChoice: false });
  }

  resultContextButton.addEventListener("click", async () => {
    if (state.running) return;

    const currentQuestion = state.question;
    const currentRouteUsesStock =
      state.lastRoute === "stock_metric" || state.lastRoute === "stock_analysis";
    archiveCurrentResult();
    state.question = currentRouteUsesStock && currentQuestion
      ? { ...currentQuestion, needsStock: true }
      : QUESTIONS[0];
    resetStockContext();
    appendBubble("user", IS_FIXED_STOCK_MODE ? "날짜 다시 선택하기" : "종목과 날짜 다시 선택하기");
    appendBubble("assistant", stockContextPrompt());
    questionListEl.querySelectorAll(".chat-question").forEach((button) => {
      button.classList.toggle("chat-question--active", button.dataset.key === state.question.key);
    });
    contextTitleEl.textContent = state.question.label;
    contextEl.hidden = false;
    if (IS_FIXED_STOCK_MODE) {
      await prepareFixedStockContext({ selectFirst: false });
    }
    updateRunButton();
    focusContextControl();
    scrollPanelToEnd();
  });

  renderQuestions();
})();
