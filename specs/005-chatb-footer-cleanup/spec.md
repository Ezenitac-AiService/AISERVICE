# Feature Specification: 올원챗(ChatB) 푸터 클린업 및 프롬프트 고도화·한자 차단 가드레일 (005-chatb-footer-cleanup)

**Feature Branch**: `005-chatb-footer-cleanup`  
**Created**: 2026-08-17  
**Status**: Draft  
**Input**: User description: "올원챗, 하단에 주소가 노출되는데, 테스트용이 남아있는것 같아. 아울러, 챗본 대답에 한국어가 아닌 한자가 유입되었음. 프롬프트 고도화도 진행해"

---

## Clarifications

### Session 2026-08-17
- **Q**: LLM 답변 내 한자(漢字) 유입을 방지하고 전문 뷰티 가이드 답변의 완성도를 높이기 위해 어떠한 다층 가드레일 방식을 적용하시겠습니까?  
  → **A**: **Option A** — **[프롬프트 고도화 + 후처리 한자 자동 변환/정제] 이중 가드레일** 적용 (한자 유입률 0% 및 자연스러운 친절한 뷰티 가이드 톤앤매너 완성).

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 올원챗 하단 불필요 텍스트 제거 및 프로덕션 푸터 정제 (Priority: P1) 🎯 MVP

사용자가 브라우저를 통해 올원챗(ChatB) 웹 인터페이스(`https://ezenitac.duckdns.org/bteam/chatb/` 또는 `http://localhost:8080/bteam/chatb/`)에 접속했을 때, 페이지 최하단에 노출되던 개발/테스트용 잔여 주소 문자열(`# http://localhost:8000/...`)이 제거되어 깔끔하고 완성도 높은 프로덕션 화면을 볼 수 있어야 합니다.

**Why this priority**: 외부 공개 및 사용자 사용 시 개발 테스트용 주소 문자열이 화면 하단에 그대로 노출되면 서비스 완성도와 신뢰도가 저하됩니다. 즉각적인 클린업으로 전문적인 UI를 유지합니다.

**Independent Test**:
- 브라우저에서 `https://ezenitac.duckdns.org/bteam/chatb/` 접속 후 화면 최하단 스크롤 시 `© 2026 Oliview Production RAG Engine. All rights reserved.` 저작권 문구 외에 잔여 텍스트가 일체 노출되지 않는지 확인.

**Acceptance Scenarios**:

1. **Given** 올원챗 웹 인터페이스(`bteam/Oliview_chatbot_b/index.html`), **When** 사용자가 웹페이지를 조회하면, **Then** `</html>` 태그 바깥의 잔여 텍스트(`# http://localhost:8000/...`)가 렌더링되지 않고 완전히 제거된다.
2. **Given** 올원챗의 RAG 질의응답 및 검색 기능, **When** 질문을 전송하고 분석 결과를 수신하면, **Then** 하단 텍스트 제거와 무관하게 모든 AI 추천 기능과 이벤트가 100% 정상 작동한다.

---

### User Story 2 - AI 뷰티 가이드 프롬프트 고도화 및 한자(漢字) 원천 차단 (Priority: P1)

사용자가 화장품 리뷰 및 성분에 관한 자연어 질문(예: "차앤박 프로폴리스 앰플 수분감을 분석해줘")을 입력했을 때, AI가 중국어 한자(예: `結果`, `推薦`, `效果` 등)의 혼용 없이 100% 순수 현대 한국어로 작성된 친절하고 전문적인 뷰티 가이드 맞춤 솔루션을 생성해야 합니다.

**Why this priority**: 오픈소스 LLM(Qwen 등)에서 한자 표기가 한글과 섞여 출력되는 현상은 사용자 가독성을 크게 해치며 서비스 품질에 부정적인 영향을 미칩니다. 프롬프트 지시 강화와 후처리 정제 가드레일을 결합하여 완벽한 한국어 응답을 보장합니다.

**Independent Test**:
- 올원챗에서 "차앤박 프로폴리스 앰플 수분감을 분석해줘" 질의 시, LLM 응답 본문에 한자(CJK 문자)가 1자도 포함되지 않고 `결과`, `추천`, `효과` 등의 자연스러운 한글로 출력되는지 검증.

**Acceptance Scenarios**:

1. **Given** 올원챗 RAG LLM 질의 생성 파이프라인, **When** 시스템/사용자 프롬프트가 구성될 때, **Then** "100% 순수 현대 한국어(한글)로만 작성, 어떠한 한자나 외국어 불필요 혼용 금지" 지침이 강력하게 주입된다.
2. **Given** LLM이 생성한 원시 텍스트 응답, **When** 후처리 정제 함수(`clean_think_tags` / `clean_hanja_and_artifacts`)를 통과할 때, **Then** CJK 한자어가 감지되면 상응하는 한글 단어로 자동 치환되거나 불필요한 한자가 완전히 정제되어 순수 한글 문자열만 반환된다.
3. **Given** 생성된 최종 AI 답변, **When** 화면에 렌더링될 때, **Then** 사용자가 친절하고 전문적인 뷰티 전문가의 조언처럼 매끄럽게 읽을 수 있는 문장 구조를 갖춘다.

---

## Edge Cases

- **복합 한자어 유입 (예: 滋潤, 補水, 敏感肌 등)**: 화장품 도메인 전용 한자어 매핑 테이블을 갖추어 자연스러운 한글(`보습`, `수분 공급`, `민감성 피부`)로 치환하거나 한글 음으로 변환.
- **캐시된 브라우저 상태**: 사용자가 브라우저 새로고침(F5 / Ctrl+F5) 시 즉시 정제된 HTML이 로드되어야 함.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `bteam/Oliview_chatbot_b/index.html` 파일의 `</html>` 태그 뒤에 위치한 비정상 잔여 주소 텍스트(`# http://localhost:8000/...`)를 완전히 제거해야 한다.
- **FR-002**: 올원챗 HTML 문서가 유효한 HTML5 닫는 태그(`</body></html>`)로 깔끔하게 끝나야 한다.
- **FR-003**: `bteam/Oliview_chatbot_b/project_ragapi.py`의 RAG 시스템 프롬프트 및 사용자 프롬프트를 고도화하여 친절하고 전문적인 AI 뷰티 가이드 페르소나를 정립하고, 한자 사용을 엄격히 금지해야 한다.
- **FR-004**: `project_ragapi.py` 및 `common.py`에 CJK 한자 유니코드 탐지 및 한글 자동 치환/정제 후처리 함수(`clean_hanja_and_artifacts`)를 구현하여 LLM 출력 텍스트에 한자가 단 1자도 잔존하지 않도록 보장해야 한다.
- **FR-005**: 올리챗(ChatA) 및 올원챗(ChatB)의 생성 응답 정제 파이프라인에 공통으로 한자 차단 가드레일을 적용해야 한다.
- **FR-006**: RAG 검색 API(`/api/v1/search`) 및 E2E 자동화 진단 스크립트(`verify_e2e_services.ps1`)가 100% 정상 작동해야 한다.

### Key Entities

- **ChatBIndexHtml (Static UI Resource)**: 올원챗의 단독 웹 인터페이스를 렌더링하는 `bteam/Oliview_chatbot_b/index.html` 파일
- **RagPromptTemplate (AI Generation Prompt)**: 전문 뷰티 가이드 페르소나 및 순수 한글 출력 지침이 강화된 시스템/사용자 프롬프트
- **HanjaFilterPipeline (Text Guardrail)**: LLM 출력 텍스트에서 한자(CJK)를 탐지하여 한글로 치환/정제하는 후처리 가드레일

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 올원챗 페이지 최하단에서 개발/테스트용 주소 텍스트 노출률이 0%로 완벽 제거된다.
- **SC-002**: LLM 뷰티 가이드 응답 텍스트 내 한자(漢字) 잔존율이 0.0%로 완벽하게 차단된다.
- **SC-003**: 주요 한자어(例: 結果, 推薦, 效果, 保濕, 成分 등)가 자연스러운 한글로 100% 자동 치환된다.
- **SC-004**: HTML5 유효성 검사 상 `</html>` 바깥의 비표준 문자열이 존재하지 않는다 (0건).
- **SC-005**: 올원챗 RAG 검색 API(`/api/v1/search`) 및 E2E 진단(`verify_e2e_services.ps1`)이 100% PASS를 유지한다.

---

## Assumptions

- 잔여 텍스트는 개발 단계에서 메모용으로 파일 끝에 추가되었던 것으로 기능 로직과 무관함.
- CJK 한자 변환 테이블은 뷰티/화장품 및 일상 한국어에서 자주 출현하는 상용 한자어를 포괄함.
- `bteam/Oliview_chatbot_b/index.html` 및 `project_ragapi.py` 수정 후 컨테이너 핫 리로드 또는 재기동으로 즉시 반영됨.
