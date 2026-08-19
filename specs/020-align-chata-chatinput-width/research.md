# Phase 0: Technical Research & Architectural Decisions

**Feature**: `020-align-chata-chatinput-width` (Oliview Chatbot A 대화 입력창 가로 너비 정렬 최적화)

## Research Topics & Findings

### 1. Streamlit `st.chat_input` DOM 구조 및 하단 고정 래퍼 분석

- **Context**: Streamlit(`layout="wide"`) 환경에서 메인 컨텐츠 영역은 `.block-container`의 `max-width: 1200px !important;`에 의해 중앙 정렬되지만, `st.chat_input` 위젯은 독립된 하단 고정 DOM 트리(`[data-testid="stBottom"]`, `[data-testid="stBottomBlockContainer"]`)로 분리되어 렌더링됨.
- **Decision**: Streamlit의 공식 하단 고정 셀렉터인 `[data-testid="stBottomBlockContainer"]`, `.stBottomBlockContainer`, `[data-testid="stChatInput"]` 및 `[data-testid="stBottom"]`을 타깃으로 `max-width: 1200px !important; margin: 0 auto !important;` CSS를 주입.
- **Rationale**:
  - `stBottomBlockContainer`는 하단 입력창을 감싸는 최상위 컨테이너로, 이 요소의 `max-width`와 `margin: 0 auto`를 메인 본문 `.block-container`와 동일하게 지정하면 1200px 이상의 와이드 해상도에서 완벽한 수직 정렬이 달성됨.
  - 구버전/신버전 Streamlit 클래스 및 testid를 함께 포함하여 렌더링 엔진 호환성 보장.
- **Alternatives Considered**:
  - *대안 1 (st.text_input으로 대체)*: 채팅 UX 저하 및 실시간 스트리밍 인터랙션과 불일치하므로 기각.
  - *대안 2 (Streamlit 기본 centered 레이아웃으로 변경)*: 상단 2열(분석 설정 1.6 : 질문 예시 1.4) 그리드 비율이 좁아져 버튼 줄바꿈 및 정보 밀도가 훼손되므로 기각.

---

### 2. 하단 고정 바(Bottom Bar) 스크롤 겹침 방지 및 블러 배경 설계

- **Context**: 대화가 누적되어 스크롤이 발생할 때, 하단 입력창 뒤로 지나가는 긴 텍스트와 참조 리뷰 내용이 겹쳐 보여 가독성이 떨어지는 문제를 방지해야 함 (Spec Clarification Option A 채택).
- **Decision**: `[data-testid="stBottom"]` 영역에 반투명 글래스모피즘 스타일 적용.
  ```css
  [data-testid="stBottom"] {
      background: rgba(255, 255, 255, 0.88) !important;
      backdrop-filter: blur(12px) !important;
      -webkit-backdrop-filter: blur(12px) !important;
      border-top: 1px solid rgba(220, 232, 224, 0.6) !important;
  }
  ```
- **Rationale**:
  - 불투명 흰색보다 자연스럽게 웹앱 본문과 융합되며, 스크롤되는 텍스트를 부드럽게 블러 처리하여 시각적 완성도(Premium UX) 제공.
  - 올리브영 테마 컬러 계열의 은은한 상단 보더라인을 더해 경계 구분을 명확히 함.

---

### 3. 멀티 해상도 반응형(Responsive) 및 모바일/태블릿 적응 전략

- **Context**: 1920px(FHD), 2560px(QHD/4K) 와이드 모니터뿐만 아니라 768px(태블릿), 360px~480px(모바일) 화면에서도 좌우 여백과 패딩이 동일하게 반응해야 함.
- **Decision**:
  - `padding-left: 1rem !important; padding-right: 1rem !important; width: 100% !important; box-sizing: border-box !important;` 적용.
  - 미디어 쿼리를 통한 모바일 패딩 최적화 (`@media (max-width: 768px)`).
- **Rationale**: 화면 폭이 1200px 미만으로 줄어들면 자동으로 뷰포트 너비 100%에 맞춰지며, 상단 본문 좌우 여백(1rem)과 완전히 일치하여 잘림이나 가로 스크롤 현상이 발생하지 않음.
