/**
 * Oliview ChatA - SSE Streaming Client & Pipeline Controller (Spec 038)
 */

let currentAbortController = null;

document.addEventListener("DOMContentLoaded", () => {
  const chatForm = document.getElementById("chatForm");
  const chatInput = document.getElementById("chatInput");
  const chatMessages = document.getElementById("chatMessages");
  const chatContainer = document.getElementById("chatContainer");
  const sendBtn = document.getElementById("sendBtn");
  const stopBtn = document.getElementById("stopBtn");

  // Textarea 자동 줄바꿈 조절
  chatInput.addEventListener("input", () => {
    chatInput.style.height = "auto";
    chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + "px";
  });

  // Enter키 전송 (Shift+Enter는 줄바꿈)
  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      chatForm.dispatchEvent(new Event("submit"));
    }
  });

  // 폼 제출 이벤트
  chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const query = chatInput.value.trim();
    if (!query) return;

    // 1. 유저 메시지 렌더링
    appendUserMessage(query);
    chatInput.value = "";
    chatInput.style.height = "auto";

    // 2. 어시스턴트 메시지 버블 및 상태 박스 생성
    const assistantBubbleContext = createAssistantMessageBubble();
    scrollToBottom();

    // 3. SSE 스트리밍 시작
    await startChatStream(query, assistantBubbleContext);
  });

  // 생성 중단 버튼 이벤트 (AbortController)
  stopBtn.addEventListener("click", () => {
    if (currentAbortController) {
      currentAbortController.abort();
      currentAbortController = null;
      setGeneratingState(false);
      console.log("[Client] Stream generation aborted by user.");
    }
  });

  function setGeneratingState(isGenerating) {
    if (isGenerating) {
      sendBtn.classList.add("hidden");
      stopBtn.classList.remove("hidden");
      chatInput.disabled = true;
    } else {
      sendBtn.classList.remove("hidden");
      stopBtn.classList.add("hidden");
      chatInput.disabled = false;
      chatInput.focus();
    }
  }

  function appendUserMessage(text) {
    const wrapper = document.createElement("div");
    wrapper.className = "message-wrapper user-wrapper";
    wrapper.innerHTML = `
      <div class="avatar user-avatar">👤</div>
      <div class="message-bubble user-bubble">${escapeHtml(text)}</div>
    `;
    chatMessages.appendChild(wrapper);
  }

  function createAssistantMessageBubble() {
    const wrapper = document.createElement("div");
    wrapper.className = "message-wrapper assistant-wrapper";

    const bubbleId = "bubble_" + Date.now();
    wrapper.innerHTML = `
      <div class="avatar assistant-avatar">🌿</div>
      <div class="message-bubble assistant-bubble" id="${bubbleId}">
        <div class="status-box" id="status_${bubbleId}">
          <div class="status-step running" id="step_intent_${bubbleId}">
            <span class="status-spinner"></span>
            <span>🔍 1. 의도 분석 및 라인명 매칭 중...</span>
          </div>
        </div>
        <div class="message-content" id="content_${bubbleId}"></div>
      </div>
    `;
    chatMessages.appendChild(wrapper);

    return {
      bubble: document.getElementById(bubbleId),
      statusBox: document.getElementById(`status_${bubbleId}`),
      contentElem: document.getElementById(`content_${bubbleId}`),
      id: bubbleId,
    };
  }

  // Session ID 관리 (새로고침 시 유지)
  let currentSessionId = sessionStorage.getItem("oliview_chata_session_id");
  if (!currentSessionId) {
    currentSessionId = "sess_" + Date.now() + "_" + Math.random().toString(36).substring(2, 8);
    sessionStorage.setItem("oliview_chata_session_id", currentSessionId);
  }

  // 이전 세션 대화 내역 복원
  restoreSessionHistory();

  async function restoreSessionHistory() {
    try {
      const resp = await fetch(`api/v1/chat/history/${currentSessionId}`);
      if (!resp.ok) return;
      const data = await resp.json();
      if (data.messages && data.messages.length > 0) {
        for (const msg of data.messages) {
          if (msg.role === "user") {
            appendUserMessage(msg.content);
          } else if (msg.role === "assistant") {
            const context = createAssistantMessageBubble();
            if (context.statusBox) context.statusBox.remove();
            context.contentElem.innerHTML = renderMarkdownWithCitations(msg.content);
            attachCitationClickHandlers(context.contentElem);
          }
        }
        scrollToBottom();
      }
    } catch (e) {
      console.warn("Session history restoration skipped:", e);
    }
  }

  async function startChatStream(query, context) {
    setGeneratingState(true);
    currentAbortController = new AbortController();

    let fullMarkdownText = "";
    const activeCategory = document.querySelector(".cat-pill.active")?.getAttribute("data-cat") || null;

    try {
      const response = await fetch("api/v1/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: query,
          session_id: currentSessionId,
          category_hint: activeCategory,
          bypass_cache: false,
        }),
        signal: currentAbortController.signal,
      });

      if (!response.ok) {
        throw new Error(`서버 응답 오류: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop(); // 잔여 미완성 청크 보관

        for (const block of lines) {
          if (!block.trim()) continue;

          let eventType = "message";
          let dataStr = "";

          const blockLines = block.split("\n");
          for (const line of blockLines) {
            if (line.startsWith("event:")) {
              eventType = line.replace("event:", "").trim();
            } else if (line.startsWith("data:")) {
              dataStr = line.replace("data:", "").trim();
            }
          }

          if (!dataStr) continue;

          try {
            const data = JSON.parse(dataStr);

            if (eventType === "step_update" || data.event_type === "step_update") {
              updateStatusBox(context.statusBox, data);
            } else if (eventType === "token" || eventType === "token_chunk" || data.event_type === "token" || data.event_type === "token_chunk") {
              const token = data.content !== undefined ? data.content : (data.token || "");
              fullMarkdownText += token;
              context.contentElem.innerHTML = renderMarkdownWithCitations(fullMarkdownText);
              attachCitationClickHandlers(context.contentElem);
              scrollToBottom();
            } else if (eventType === "complete" || eventType === "final_result" || data.event_type === "complete" || data.event_type === "final_result") {
              finalizeStatusAndAccordion(context, data, fullMarkdownText);
            } else if (eventType === "error" || data.event_type === "error") {
              context.contentElem.innerHTML += `<p style="color:#EF4444;margin-top:8px;">⚠️ 오류: ${data.error_message}</p>`;
            }
          } catch (e) {
            console.error("SSE parse error:", e, block);
          }
        }
      }
    } catch (err) {
      if (err.name === "AbortError") {
        context.contentElem.innerHTML += `<p style="color:#EF4444;font-size:13px;margin-top:6px;">⏹️ 사용자에 의해 생성이 중단되었습니다.</p>`;
      } else {
        context.contentElem.innerHTML += `<p style="color:#EF4444;font-size:13px;margin-top:6px;">⚠️ 연결 오류가 발생했습니다: ${err.message}</p>`;
      }
    } finally {
      setGeneratingState(false);
      currentAbortController = null;
      scrollToBottom();
    }
  }

  function updateStatusBox(statusBox, eventData) {
    if (!statusBox) return;

    const stepId = eventData.step_id || eventData.node_id || "STEP";
    const stepName = eventData.step_name || eventData.title || stepId;
    const status = eventData.status || "running";

    let stepElem = statusBox.querySelector(`[data-step="${stepId}"]`);
    if (!stepElem) {
      stepElem = document.createElement("div");
      stepElem.className = `status-step ${status}`;
      stepElem.setAttribute("data-step", stepId);
      statusBox.appendChild(stepElem);
    }

    if (status === "running") {
      stepElem.className = "status-step running";
      stepElem.innerHTML = `<span class="status-spinner"></span><span>${stepName}...</span>`;
    } else {
      stepElem.className = "status-step complete";
      const elapsed = eventData.elapsed_ms ? ` (${(eventData.elapsed_ms / 1000).toFixed(1)}s)` : "";
      stepElem.innerHTML = `<span>✓ ${stepName}${elapsed}</span>`;
    }
  }

  function finalizeStatusAndAccordion(context, completeData, fullMarkdownText) {
    const { statusBox, contentElem, bubble } = context;

    // 1. 상태 박스 완료 표기
    const latency = completeData.total_latency_sec || 1.2;
    const reviewCount = completeData.selected_review_count || 0;
    const cachedBadge = completeData.is_cached ? " ⚡ (L5 캐시)" : "";

    if (statusBox) {
      statusBox.innerHTML = `
        <div class="status-step complete" style="font-weight:700;color:#2B6E3F;">
          ✅ 리뷰 분석 완료 (${latency}초, ${reviewCount}건 선별)${cachedBadge}
        </div>
      `;
    }

    // 2. 최종 마크다운 인라인 인용 뱃지 재바인딩
    contentElem.innerHTML = renderMarkdownWithCitations(fullMarkdownText);
    attachCitationClickHandlers(contentElem);

    // 3. 하단 참조 리뷰 원문 아코디언 렌더링
    const reviews = completeData.reference_reviews || [];
    currentReferenceReviews = reviews;

    if (reviews.length > 0) {
      const accordionWrapper = document.createElement("div");
      accordionWrapper.className = "accordion-wrapper";

      const header = document.createElement("div");
      header.className = "accordion-header";
      header.innerHTML = `
        <span>📚 참조 리뷰 원문 (${reviews.length}건 선별)</span>
        <span class="accordion-arrow">▼</span>
      `;

      const body = document.createElement("div");
      body.className = "accordion-body";

      body.innerHTML = reviews.map((r, idx) => {
        const stars = "⭐".repeat(Math.round(r.review_score || 5));
        const cleanProduct = r.clean_product_name || r.product_name;
        const tag = `[${cleanProduct} 리뷰 ${r.rank || idx + 1}]`;
        return `
          <div class="review-item" data-rank="${r.rank || idx + 1}">
            <div class="review-item-header">
              <span class="review-product-name">${tag} ${cleanProduct}</span>
              <span class="review-rating">${stars} ${r.review_score}점</span>
            </div>
            <div class="review-text">"${r.clean_text || r.separated_sentence}"</div>
            <a href="${r.product_url || r.oliveyoung_search_url}" target="_blank" class="btn-oy-link">
              올리브영 공식몰 상품 보기 ↗
            </a>
          </div>
        `;
      }).join("");

      header.addEventListener("click", () => {
        const isOpen = body.classList.toggle("open");
        header.querySelector(".accordion-arrow").textContent = isOpen ? "▲" : "▼";
      });

      accordionWrapper.appendChild(header);
      accordionWrapper.appendChild(body);
      bubble.appendChild(accordionWrapper);
    }
  }

  function scrollToBottom() {
    window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
  }

  function escapeHtml(str) {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
});
