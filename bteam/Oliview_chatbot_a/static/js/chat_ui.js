/**
 * Oliview ChatA - UI Components, Markdown Parser & Bottom Sheet Manager (Spec 038)
 */

// 카테고리별 주요 속성 및 1-클릭 질문 예시 데이터
const CATEGORY_DATA = {
  "스킨케어": {
    attributes: ["✨ 수분감/보습력", "🌸 자극성/순함", "🌿 기능/효과", "🍃 사용감/제형", "💧 트러블/진정"],
    examples: [
      { label: "차앤박 앰플 수분감", query: "차앤박 프로폴리스 앰플 수분감과 흡수력 알려줘" },
      { label: "식물나라 토너 자극성", query: "식물나라 토너 자극성과 기능/효과 분석해줘" },
      { label: "브링그린 세럼 진정", query: "브링그린 티트리 세럼 진정 효과와 사용감 어때?" },
      { label: "스킨케어 수분 앰플", query: "스킨케어에서 수분감 좋은 인기 앰플 추천해줘" },
    ]
  },
  "클렌징": {
    attributes: ["🫧 세정력/세안력", "🌸 저자극/순함", "✨ 수분감/당김", "🍃 거품력/사용감", "🌿 모공/피지관리"],
    examples: [
      { label: "식물나라 클렌징 세정력", query: "식물나라 클렌징폼 세정력과 거품력 어때?" },
      { label: "순한 클렌징폼 추천", query: "자극 없이 순한 클렌징 제품 분석해줘" },
      { label: "브링그린 딥클렌징", query: "브링그린 클렌징 제품 모공 세정 효과 알려줘" },
      { label: "클렌징 수분감/당김", query: "세안 후 당김 없는 클렌징폼 추천해줘" },
    ]
  },
  "선케어": {
    attributes: ["☀️ 자외선차단/지속", "🌸 눈시림/순함", "✨ 백탁/톤업", "🍃 발림성/끈적임", "💧 수분감/촉촉함"],
    examples: [
      { label: "식물나라 선크림 백탁", query: "식물나라 선크림 백탁현상과 발림성 알려줘" },
      { label: "눈시림 없는 선크림", query: "눈시림 없고 순한 선케어 제품 추천해줘" },
      { label: "헤라 선크림 톤업", query: "헤라 선크림 톤업효과와 지속력 분석해줘" },
      { label: "브링그린 선세럼 촉촉함", query: "브링그린 선세럼 백탁 없이 촉촉한지 알려줘" },
    ]
  },
  "립메이크업": {
    attributes: ["💄 발색력/착색력", "💧 촉촉함/보습감", "⏱️ 지속력/밀착력", "✨ 각질부각/주름부각", "🍃 제형/끈적임"],
    examples: [
      { label: "헤라 센슈얼 립 분석", query: "헤라 센슈얼 립 촉촉함과 각질부각 분석해줘" },
      { label: "롬앤 틴트 지속력", query: "롬앤 쥬시 래스팅 틴트 지속력과 착색력 알려줘" },
      { label: "컬러그램 꿀로스 광택", query: "컬러그램 탕후루 탱글 꿀로스 광택감과 끈적임 어때?" },
      { label: "각질부각 없는 립밤", query: "각질부각 없고 촉촉한 립메이크업 제품 추천해줘" },
    ]
  },
  "베이스메이크업": {
    attributes: ["🎭 커버력/결보정", "⏱️ 지속력/다크닝", "💧 밀착력/들뜸", "✨ 유분기/무너짐", "🍃 발림성/무게감"],
    examples: [
      { label: "헤라 블랙쿠션 커버력", query: "헤라 블랙쿠션 커버력과 다크닝 분석해줘" },
      { label: "다크닝 없는 쿠션", query: "시간 지나도 다크닝 없는 베이스 쿠션 추천해줘" },
      { label: "들뜸 없는 파데", query: "들뜸과 밀림 없이 밀착력 좋은 베이스 알려줘" },
      { label: "촉촉한 베이스 메이크업", query: "건성 피부에 좋은 촉촉한 베이스 제품 분석해줘" },
    ]
  }
};

let currentReferenceReviews = [];

/**
 * 카테고리 패널 업데이트 함수
 */
function updateCategoryPanel(categoryName) {
  const data = CATEGORY_DATA[categoryName] || CATEGORY_DATA["스킨케어"];

  // 속성 카드 업데이트
  const cardTitle = document.getElementById("attributeCardTitle");
  if (cardTitle) cardTitle.textContent = `${categoryName} 주요 분석 속성`;

  const attrBox = document.getElementById("attributeBox");
  if (attrBox) {
    attrBox.innerHTML = data.attributes
      .map(attr => `<span class="attribute-chip">${attr}</span>`)
      .join("");
  }

  // 1-클릭 질문 예시 버튼 업데이트
  const exampleContainer = document.getElementById("exampleQueries");
  if (exampleContainer) {
    exampleContainer.innerHTML = data.examples
      .map(ex => `<button type="button" class="btn-example" data-query="${ex.query}"><strong>${ex.label}</strong><br><span style="font-size:11.5px;color:#5A7060;">"${ex.query}"</span></button>`)
      .join("");

    // 예시 버튼 클릭 이벤트 바인딩
    exampleContainer.querySelectorAll(".btn-example").forEach(btn => {
      btn.addEventListener("click", () => {
        const query = btn.getAttribute("data-query");
        const input = document.getElementById("chatInput");
        if (input) {
          input.value = query;
          document.getElementById("chatForm").dispatchEvent(new Event("submit"));
        }
      });
    });
  }
}

/**
 * GFM 테이블 파서 (Markdown Tables -> HTML Table)
 */
function parseMarkdownTables(text) {
  const lines = text.split("\n");
  const output = [];
  let i = 0;

  while (i < lines.length) {
    const rawLine = lines[i];
    const line = rawLine.trim();

    // 테이블 시작 후보 감지: '|'로 시작하고 끝나는 라인
    if (line.startsWith("|") && line.endsWith("|") && i + 1 < lines.length) {
      const nextRaw = lines[i + 1];
      const nextLine = nextRaw.trim();

      // 구분선 라인 확인: | :--- | :--- | 또는 |---|---|
      const isSep = /^\|(?:\s*:?-{2,}:?\s*\|)+$/.test(nextLine);
      if (isSep) {
        const tableRows = [line, nextLine];
        let j = i + 2;
        while (j < lines.length) {
          const rowLine = lines[j].trim();
          if (rowLine.startsWith("|") && rowLine.endsWith("|")) {
            tableRows.push(rowLine);
            j++;
          } else {
            break;
          }
        }

        // HTML 테이블 변환
        const htmlTable = convertTableRowsToHtml(tableRows);
        output.push(htmlTable);
        i = j;
        continue;
      }
    }

    output.push(rawLine);
    i++;
  }

  return output.join("\n");
}

function convertTableRowsToHtml(rows) {
  if (rows.length < 2) return rows.join("\n");

  const headerCells = splitTableRowCells(rows[0]);
  const sepCells = splitTableRowCells(rows[1]);

  const alignments = sepCells.map(c => {
    const s = c.trim();
    if (s.startsWith(":") && s.endsWith(":")) return "center";
    if (s.endsWith(":")) return "right";
    return "left";
  });

  let thead = "<thead><tr>";
  headerCells.forEach((cell, idx) => {
    const align = alignments[idx] || "left";
    thead += `<th style="text-align:${align};">${cell.trim()}</th>`;
  });
  thead += "</tr></thead>";

  let tbody = "<tbody>";
  for (let r = 2; r < rows.length; r++) {
    const dataCells = splitTableRowCells(rows[r]);
    tbody += "<tr>";
    headerCells.forEach((_, idx) => {
      const cellText = (dataCells[idx] !== undefined ? dataCells[idx] : "").trim();
      const align = alignments[idx] || "left";
      tbody += `<td style="text-align:${align};">${cellText}</td>`;
    });
    tbody += "</tr>";
  }
  tbody += "</tbody>";

  return `<div class="table-responsive"><table class="markdown-table">${thead}${tbody}</table></div>`;
}

function splitTableRowCells(row) {
  let content = row.trim();
  if (content.startsWith("|")) content = content.substring(1);
  if (content.endsWith("|")) content = content.substring(0, content.length - 1);
  return content.split("|");
}

/**
 * 마크다운 렌더링 & 인라인 [리뷰 N] 인용 뱃지 변환
 */
function renderMarkdownWithCitations(rawMarkdown) {
  if (!rawMarkdown) return "";

  // 1. 인용 부호 주변의 백틱 사전 제거: `[제품명 리뷰 1]` -> [제품명 리뷰 1]
  let html = rawMarkdown.replace(/`(\[[^`\]\n]+?리뷰\s+\d+\])`/g, '$1');

  // 2. GFM 마크다운 테이블 변환
  html = parseMarkdownTables(html);

  // 3. 수평선 변환 (---, ***, ___)
  html = html.replace(/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/gm, '<hr class="markdown-hr">');

  // 4. 헤딩 변환 (###, ##, #)
  html = html.replace(/^### (.*$)/gm, '<h3 class="markdown-h3">$1</h3>');
  html = html.replace(/^## (.*$)/gm, '<h2 class="markdown-h2">$1</h2>');
  html = html.replace(/^# (.*$)/gm, '<h1 class="markdown-h1">$1</h1>');

  // 5. 코드 블록 및 인라인 코드
  html = html.replace(/```([\s\S]*?)```/g, '<pre class="markdown-pre"><code>$1</code></pre>');
  html = html.replace(/`([^`\n]+)`/g, '<code class="markdown-code">$1</code>');

  // 6. 볼드체 (**text**) 및 이탤릭 (*text*)
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>');

  // 7. 리스트 변환 (순서 없는 리스트 및 순서 있는 리스트)
  html = html.replace(/^\s*[-*+]\s+(.*$)/gm, '<li class="markdown-li">$1</li>');
  html = html.replace(/^\s*(\d+)\.\s+(.*$)/gm, '<li class="markdown-li markdown-oli"><span class="oli-num">$1.</span> $2</li>');

  // 8. 인라인 인용 태그 변환: [제품명 리뷰 N] 또는 [리뷰 N]
  html = html.replace(/\[([^\s\]]+(?:\s+[^\s\]]+)*\s+리뷰\s+\d+)\]/g, '<span class="citation-badge" data-citation="[$1]" title="참조 리뷰 보기">[$1]</span>');
  html = html.replace(/\[리뷰\s+(\d+)\]/g, '<span class="citation-badge" data-citation="[리뷰 $1]" title="참조 리뷰 보기">[리뷰 $1]</span>');

  // 9. 줄바꿈 정제
  const blockTags = ["div", "table", "thead", "tbody", "tr", "th", "td", "hr", "h1", "h2", "h3", "li", "pre", "code"];
  const lines = html.split("\n");
  const processed = [];

  for (let idx = 0; idx < lines.length; idx++) {
    const l = lines[idx];
    const trimmed = l.trim();
    if (!trimmed) {
      const prev = idx > 0 ? lines[idx - 1].trim() : "";
      const next = idx + 1 < lines.length ? lines[idx + 1].trim() : "";
      const isPrevBlock = blockTags.some(tag => prev.endsWith(`</${tag}>`) || prev.startsWith(`<${tag}`));
      const isNextBlock = blockTags.some(tag => next.startsWith(`<${tag}`));
      if (!isPrevBlock && !isNextBlock && prev && next) {
        processed.push("<br>");
      }
      continue;
    }

    const isBlock = blockTags.some(tag => trimmed.startsWith(`<${tag}`) || trimmed.endsWith(`</${tag}>`));
    if (isBlock) {
      processed.push(l);
    } else {
      processed.push(l + "<br>");
    }
  }

  html = processed.join("\n");
  html = html.replace(/(?:<br>\s*){3,}/g, '<br><br>');
  html = html.replace(/<\/li><br>/g, '</li>');
  html = html.replace(/<\/h[1-3]><br>/g, '</h$1>');
  html = html.replace(/<\/div><br>/g, '</div>');
  html = html.replace(/<hr class="markdown-hr"><br>/g, '<hr class="markdown-hr">');

  return html;
}

/**
 * 바텀 시트 열기
 */
function openBottomSheet(title, contentHtml) {
  const overlay = document.getElementById("bottomSheetOverlay");
  const titleElem = document.getElementById("bottomSheetTitle");
  const bodyElem = document.getElementById("bottomSheetBody");

  if (titleElem) titleElem.textContent = title;
  if (bodyElem) bodyElem.innerHTML = contentHtml;

  if (overlay) {
    overlay.classList.add("open");
    document.body.style.overflow = "hidden"; // 배경 스크롤 방지
  }
}

/**
 * 바텀 시트 닫기
 */
function closeBottomSheet() {
  const overlay = document.getElementById("bottomSheetOverlay");
  if (overlay) {
    overlay.classList.remove("open");
    document.body.style.overflow = "";
  }
}

/**
 * 인라인 인용 뱃지 클릭 핸들러 초기화
 */
function attachCitationClickHandlers(container) {
  container.querySelectorAll(".citation-badge").forEach(badge => {
    badge.addEventListener("click", () => {
      const citationTag = badge.getAttribute("data-citation");
      handleCitationClick(citationTag);
    });
  });
}

function handleCitationClick(citationTag) {
  // 매칭되는 리뷰 찾기
  let matchedReview = null;
  if (currentReferenceReviews && currentReferenceReviews.length > 0) {
    const numMatch = citationTag.match(/(\d+)/);
    const targetRank = numMatch ? parseInt(numMatch[1], 10) : 1;

    const cleanTag = citationTag.replace(/[\[\]]/g, "");
    matchedReview = currentReferenceReviews.find(r => 
      cleanTag.includes(r.product_name) || r.rank === targetRank
    ) || currentReferenceReviews[0];
  }

  if (matchedReview) {
    const stars = "⭐".repeat(Math.round(matchedReview.review_score || 5));
    const content = `
      <div class="bottom-sheet-review">
        <div style="margin-bottom:8px;">
          <span style="font-size:14px;font-weight:700;color:#238035;">${matchedReview.product_name}</span>
          <span style="float:right;color:#F59E0B;font-size:13px;">${stars} ${matchedReview.review_score}점</span>
        </div>
        <div style="font-size:13.5px;color:#2C4233;background:#F7FAF8;padding:12px;border-radius:8px;border:1px solid #E0EBE3;line-height:1.6;">
          "${matchedReview.clean_text || matchedReview.separated_sentence}"
        </div>
        <div style="margin-top:14px;text-align:right;">
          <a href="${matchedReview.product_url || matchedReview.oliveyoung_search_url}" target="_blank" class="btn-send" style="display:inline-block;text-decoration:none;font-size:13px;padding:8px 16px;">
            올리브영 공식몰에서 보기 ↗
          </a>
        </div>
      </div>
    `;
    openBottomSheet(`📚 ${citationTag} 상세 원문`, content);
  } else {
    openBottomSheet("📚 참조 리뷰", `<p style="font-size:13px;color:#5A7060;">선택하신 인용(${citationTag})의 상세 원문을 확인하고 있습니다.</p>`);
  }
}

// Global Event Listeners Setup
document.addEventListener("DOMContentLoaded", () => {
  // 카테고리 알약 버튼 클릭 이벤트
  const catPills = document.querySelectorAll(".cat-pill");
  catPills.forEach(pill => {
    pill.addEventListener("click", () => {
      catPills.forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      const cat = pill.getAttribute("data-cat");
      updateCategoryPanel(cat);
    });
  });

  // 브랜드 칩 클릭 시 입력창 자동 채우기
  document.querySelectorAll(".brand-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      const brand = chip.getAttribute("data-brand");
      const input = document.getElementById("chatInput");
      if (input) {
        input.value = `${brand} 인기 제품 분석해줘`;
        input.focus();
      }
    });
  });

  // 바텀 시트 닫기 이벤트
  const closeBtn = document.getElementById("bottomSheetClose");
  const overlay = document.getElementById("bottomSheetOverlay");
  if (closeBtn) closeBtn.addEventListener("click", closeBottomSheet);
  if (overlay) {
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closeBottomSheet();
    });
  }

  // 초기 스킨케어 패널 로드
  updateCategoryPanel("스킨케어");
});
