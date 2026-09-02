# Feature Specification: 048-anti-fictional-user-and-citation-fidelity

**Feature Branch**: `048-anti-fictional-user-and-citation-fidelity`

**Created**: 2026-09-02

**Status**: Draft

**Input**: User description: ""진정 효과 좋은지 모르겠어요"라는 리뷰를 인용하면서, 진정 효과가 좋다고 분석하고, 가상의 사용자를 생성하고, 없는 리뷰를 만들어냄, 저 브링그린 리뷰 1,2,3,4,5,6 전부 같은 리뷰임 '진정 효과 좋은지 모르겠어요'였음. 최종 답변에서 가상 사용자 생성하지 않는다는 제약을 걸겠다는 내용이 기존 spec에 있을건데, 검토해봐. 코어는 통합하되, chatA와 chatB를 차별화 하여, 각각의 다른 성격의 챗봇이 되도록하는 방안을 검토하고 제안해줘. 메인 포털에도 설명 추가 및 하단 최신순 릴리즈 변경점 타임라인 구축. 카카오톡-모바일-스마트폰 트래픽 최적화 반응형 웹 도입 및 정식 출시 전 알파(v0.X.X-alpha)/베타(v0.X.X-beta) 라이프사이클 체계 적용. 메인 포털 2x1 히어로 벤또 카드 및 전용 이력 페이지(changelog.html) 구축. 다중 페르소나 심층 검토 및 2026년 9월 웹 트렌드(Liquid Glass, dvh+svh 하이브리드, 스트리밍 토큰 인터셉터) 전면 반영"

---

## Clarifications

### Session 2026-09-02
- **Q1 (다중 방어 아키텍처 & 스트리밍 토큰 인터셉터)**: ChatA 및 ChatB의 가상 사용자 날조, 인용 번호 초과($N > K$), 스트리밍 중 가상 라벨 깜빡임(Flicker)을 어떻게 방어할 것인가?
  → **A**: **3단계 다중 방어 아키텍처 + 스트림 경계 안전 인터셉터 채택**. (1) 프롬프트 제약(가상 페르소나 금지 & $K$건 상한 명시) + (2) 컨텍스트 유효 인용 태그 레지스트리 바인딩 + (3) `synthesis_node.py`에서 UTF-8로 디코딩된 SSE 텍스트 조각을 검사하고, 등록된 금지 패턴의 최대 접두어 길이 이상을 미방출 상태로 유지하는 동적 carry buffer와 배치 `GroundednessSanitizer` 검증. 모델 토큰 수나 SSE 이벤트 경계를 보안 경계로 간주하지 않는다.
- **Q2 (사실 감성 극성 일치 및 제로 서치 기권)**: 수집된 리뷰가 소수(1~2건)이면서 부정·의구심(예: '진정 효과 좋은지 모르겠어요') 피드백일 때, 요약표 및 답변 결론의 감성 극성을 어떻게 처리할까요?
  → **A**: **사실 감성 극성 일치(Fact Polarity Alignment)**. 긍정으로 왜곡하지 않고 "실제 수집된 리뷰에서 진정 효과에 대한 체감이 부족하다는 의견이 확인되었습니다"와 같이 솔직한 피드백으로 분류하고, 요약표에도 과장 없는 객관적 평을 반영. $K=0$인 경우 모델 호출 없이 즉각 하드 기권(Abstention) 카드로 안내.
- **Q3 (2단계 Document Top-P 연동 & 컨텍스트 고갈 방어)**: Document Top-P로 선별된 유효 리뷰 개수($K$)를 프롬프트 및 검증에 어떻게 연계할 것인가?
  → **A**: 컨텍스트에 엄선된 $K$건의 인용 태그 목록(`[제품명 리뷰 1]` ~ `[제품명 리뷰 K]`)을 명시하고, $K=1$인 경우 복수 사용자 일반화 서술을 방지하는 **적응형 프롬프트(Adaptive Prompting)**를 적용. `0.60` 절대 점수와 `0.25` 절벽 차이는 초기 후보 기본값이며, 고정 평가 코퍼스의 검색 정밀도·재현율·근거 충실도 결과로 보정한 뒤 운영 기본값으로 승인한다.
- **Q4 (프롬프트 SSOT 일원화)**: ChatA와 ChatB에 산재된 하드코딩 프롬프트(ChatB의 레거시 IT 어시스턴트 포함)를 어떻게 통합 관리할 것인가?
  → **A**: `bteam/oliview_core/prompts.py`를 단일 진실 공급원(SSOT)으로 신설하여 ChatA와 ChatB가 100% 동일한 무환각 뷰티 프롬프트 모듈을 호출하도록 일원화.
- **Q5 (ChatA vs ChatB 2-Track 차별화 전략)**: 코어는 통합하되 두 챗봇의 성격과 UI를 어떻게 차별화할 것인가?
  → **A**: **2-Track 차별화 전략 확정**.
  - **ChatA (올리뷰 컨시어지 - C-End)**: 일반 소비자용 친절·공감 뷰티 쇼핑 큐레이터 (모바일 퍼스트 1열 채팅, 썸존 스와이프 칩바, 뷰티 케어 루틴 제안).
  - **ChatB (올리뷰 애널리스트 - B-End/Pro)**: 올리브영 MD/기획자용 객관적 데이터 분석관 (모바일 드로어/데스크탑 2열 프로 대시보드, 동적 브랜드/감성 필터, Document Top-P 제어 슬라이더, BGE-Reranker 점수 분포 및 파이프라인 관측성 시각화).
- **Q6 (2026 UI/UX & 모바일 카카오톡 최적화)**: 접속 트래픽의 대다수를 차지하는 스마트폰/카카오톡 환경을 어떻게 지원할 것인가?
  → **A**: **하이브리드 뷰포트(`100dvh` 레이아웃 + `85svh` 바텀시트), `visualViewport` 가상 키보드 방어, 하단 40% 썸존(Thumb Zone) 액션바, 테이블 우측 그라데이션 페이드 스크롤 인디케이터**를 전면 적용.
- **Q7 (서브시스템 라이프사이클 분화 - Alpha vs Beta)**: 시스템 구성 요소별 성숙도를 어떻게 구분하여 반영할 것인가?
  → **A**: **인프라/게이트웨이는 Beta 🏆, 지능화/UX 계층은 Alpha 🌱로 분화**.
    - **`Model Gateway`**: `v0.9.0-beta` 🏆 (VRAM 100% 온로드 상시 서빙, OpenAI 호환 API, OOM 가드레일 완성)
    - **`Nginx Gateway`**: `v0.8.5-beta` 🏆 (단일 진입점 라우팅, SSE 버퍼링 제어, DuckDNS 게이트웨이 확립)
    - **`PILOS`**: `v0.8.0-beta` 🏆 (A-Team 뉴스 수급 감정 지수 및 AI 요약 리포트 완성)
    - **`Oliview Web`**: `v0.8.0-beta` 🏆 (B-Team 5.7만 건 리뷰 속성 통계 및 React/Flask 풀스택 대시보드)
    - **`Core/Gateway`**: `v0.7.0-alpha` 🌱 (3단계 무환각 방어, SSOT 프롬프트 레지스트리 구축)
    - **`ChatA`**: `v0.5.2-alpha` 🌱 (올리뷰 컨시어지: 썸존 스와이프 칩바 & 모바일 100dvh 바텀시트)
    - **`ChatB`**: `v0.4.1-alpha` 🌱 (올리뷰 애널리스트: 2열 프로 RAG 관측 대시보드 & Document Top-P 제어)
- **Q8 (메인 포털 2x1 히어로 벤또 카드 & 전용 이력 페이지)**: 릴리즈 히스토리를 메인 화면에 어떻게 배치할 것인가?
  → **A**: **메인 포털 2x1 와이드 히어로 벤또 카드 ➔ 전용 이력 페이지(`gateway/html/changelog.html`) 링크 구조 확정**. 메인 포털에는 Liquid Glass 스타일의 2x1 히어로 벤또 위젯을 배치하고, 전용 페이지에서 서브시스템별 탭 필터링 및 7대 마일스톤 상세 엔지니어링 카드를 제공.
- **Q9 (64K/32K 컨텍스트 및 4슬롯 Continuous Batching VRAM 수용성)**: GTX 1070 8GB VRAM에서 다중 슬롯 동시 요청 처리가 가능한가?
  → **A**: **실측 전에는 확정하지 않는다.** `64K context pool`은 슬롯당 64K가 아니라 서버 전체 context allocation을 뜻하며, 4슬롯 사용 시 슬롯별 가용 context는 요청 구성에 따라 분할된다. 모델 해시, GGUF 양자화, KV cache 형식, 드라이버, prompt/output 길이를 고정한 재현 가능한 benchmark에서 VRAM·TTFT·처리량·OOM 여부를 측정한 뒤 승인한다.
- **Q10 (대상 하드웨어 플랫폼 - RTX 2080 8GB & RTX 3060 12GB 최적화)**: 향후 배포 대상인 RTX 2080 및 RTX 3060 12GB 플랫폼에서 본 전략의 유효성과 vLLM 적용 타당성은?
  → **A**: **하드웨어 적응형 하이브리드 게이트웨이 전략 확정**.
    - **GTX 1070 (sm_61)**: 현재 vLLM CUDA 최소 compute capability를 충족하지 않으므로 `llama-server` 후보만 benchmark한다.
    - **RTX 2080/RTX 3060 (sm_75/sm_86)**: `llama-server`와 Linux 기반 vLLM을 동일 workload로 비교하여 latency·throughput·VRAM·안정성 기준으로 선택한다. `-fa`는 하드웨어/빌드별 `auto` 결과를 우선 검증하며 강제 활성화를 기본값으로 가정하지 않는다.

---

## 1. 문제 분석 및 배경 (Problem Analysis & Context)

올리뷰 챗봇(ChatA, ChatB)에서 제품 속성 및 비교 분석 질의(예: *"브링그린 티트리 세럼 진정 효과와 사용감 어때?"*)를 수행할 때, **실제 수집된 리뷰가 단 1건(부정적 의구심: `"진정 효과 좋은지 모르겠어요"`)에 불과함에도 불구하고 LLM이 다음과 같은 심각한 환각(Hallucination) 및 사실 왜곡 결함을 발생**시키고 있습니다.

```
[데이터베이스/RAG 컨텍스트]
 ➔ 단 1건의 리뷰만 존재: [브링그린 리뷰 1] "진정 효과 좋은지 모르겠어요" (부정/회의적 반응)
       │
       ▼ (LLM 합성 시 환각 발생)
[결함 1. 가상 사용자(Persona) 및 허위 인용구 날조]
 ➔ '사용자 A', '사용자 B', '사용자 C', '사용자 D', '사용자 E', '사용자 F' 가상 인물 창작
 ➔ "피부염이 심해서 너무 불안했는데 진정 효과가 정말 좋았어요" 등 데이터에 없는 허위 문장 날조

[결함 2. 감성/극성 왜곡 (Polarity Inversion)]
 ➔ "진정 효과 좋은지 모르겠어요"라는 부정적 리뷰를 근거로 들면서 "1. 진정 효과에 대한 긍정적 평가: 피부가 안정적"으로 정반대 해석

[결함 3. 존재하지 않는 초과 인용 태그 날조 (Citation Index Overflow)]
 ➔ 컨텍스트에는 [브링그린 리뷰 1]만 존재함에도 불구하고 [브링그린 리뷰 2] ~ [브링그린 리뷰 6]까지 허위 태그 무단 생성

[결함 4. ChatB 프롬프트 분절 및 레거시 UI 불일치]
 ➔ ChatB 스트리밍 시 "당신은 IT 및 AI 기술 전문 어시스턴트입니다"라는 레거시 프롬프트 누출
 ➔ ChatB UI에 2026 Document Top-P와 불일치하는 레거시 Top-K(fetch_k=20, top_n=3) 슬라이더 잔존

[결함 5. 모바일/카카오톡 인앱 환경 UX 미흡]
 ➔ 스마트폰/카카오톡 접속 시 상하단 툴바 및 가상 키보드 가림 현상, 한 손 조작 썸존 칩 부재
```

이는 대한민국 헌법 제6조(100% 무환각 및 실존 리뷰 인라인 인용 결속 절대 원칙) 및 Spec 038/039의 가상 사용자(사용자 A/B/C) 발생률 0.0% 원칙을 정면으로 위반하는 치명적인 신뢰성 결함입니다.

---

## 2. User Scenarios & Testing *(mandatory)*

### User Story 1 - 가상 사용자(사용자 A/B/C) 및 허위 후기 날조 원천 차단 (Priority: P1) 🎯 MVP

사용자가 특정 제품의 속성이나 효능을 질문했을 때, 시스템은 '사용자 A', '사용자 B', '고객 1'과 같은 임의의 가상 인물 라벨이나 날조된 대화체 인용구를 일체 생성하지 않고, **실제 데이터베이스에 존재하는 리뷰 원문 사실만을 객관적이고 담백하게 요약·분석**해야 한다.

**Why this priority**: 가짜 인물과 가짜 대화체를 지어내는 것은 서비스의 진실성과 데이터 신뢰도를 근본적으로 파괴하는 최우선 결함이다.

**Independent Test**:
- *"브링그린 티트리 세럼 진정 효과와 사용감 어때?"* 질의 시, 답변 본문에 '사용자 A', '사용자 B', '고객 1', '익명의 구매자' 등의 가상 페르소나 및 따옴표 대화체가 단 1회도 발생하지 않는지 검증.

**Acceptance Scenarios**:
1. **Given** 실제 리뷰가 제공되었을 때, **When** LLM이 분석 답변을 생성하면, **Then** 가상 사용자 라벨('사용자 A/B/C' 등)을 사용하지 않고 속성별/문맥별 사실 요약 문장으로만 답변을 구성해야 한다.
2. **Given** 리뷰 텍스트에 없는 주장을 작성하려 할 때, **When** Groundedness 가드레일 및 스트리밍 토큰 인터셉터가 감지하면, **Then** 허위 날조 문장을 즉각 차단 및 정제해야 한다.

---

### User Story 2 - 컨텍스트 리뷰 수 초과 인용 태그 날조 방지 및 사실 극성 보존 (Priority: P1)

사용자가 적은 수(예: 1~2건)의 리뷰만 존재하는 제품을 질문했을 때, 시스템은 **제공된 실제 리뷰 개수 $K$를 초과하는 허위 인용 태그(`[리뷰 N]`, where $N > K$)를 생성하지 않아야 하며**, 리뷰가 부정적이거나 의구심을 표할 경우 이를 억지로 긍정으로 왜곡하지 않고 실제 반응 그대로 전달해야 한다.

**Why this priority**: 실제 1건뿐인 부정 리뷰를 6건의 긍정 리뷰로 둔갑시키는 것은 심각한 소비자 기만이자 알고리즘 왜곡이다.

**Independent Test**:
- 실제 리뷰가 1건(`"진정 효과 좋은지 모르겠어요"`)만 전달된 환경에서, 답변에 `[리뷰 2]`, `[리뷰 3]` 등의 초과 태그가 0건이며, 진정 효과에 대해 "진정 효과에 대한 체감이 부족하다는 의견이 있습니다"와 같이 실제 감성 극성을 사실대로 반영하는지 검증.

**Acceptance Scenarios**:
1. **Given** 컨텍스트에 $K$개의 리뷰가 주어졌을 때, **When** 인라인 인용 태그가 생성되면, **Then** 오직 $1 \le N \le K$ 범위의 인용 태그만 허용되어야 한다.
2. **Given** 리뷰가 부정적 속성(`"좋은지 모르겠어요"`, `"트러블 발생"`)을 언급할 때, **When** 요약 및 장단점을 도출하면, **Then** 긍정 장점으로 왜곡하지 않고 주의점/회의적 피드백으로 분류해야 한다.

---

### User Story 3 - SSOT 프롬프트 레지스트리 및 스트리밍 토큰 인터셉터 (Priority: P2)

프롬프트 지침뿐만 아니라 `bteam/oliview_core/prompts.py`를 신설하여 ChatA와 ChatB의 시스템 프롬프트를 완전 일원화하고, SSE 스트리밍 도중 가상 인물 라벨이 찰나에 노출되는 현상을 슬라이딩 윈도우 토큰 인터셉터로 원천 차단해야 한다.

**Why this priority**: 소형 모델(Qwen 2B)의 경우 프롬프트만으로는 환각을 100% 억제하기 어려우므로 스트리밍 토큰 버퍼와 결정론적 가드레일 방어선이 필수적이다.

**Independent Test**:
- 모델이 스트리밍 중 '사용자 A: "..."' 토큰을 방출하려 할 때, 슬라이딩 윈도우 인터셉터가 이를 감지하여 브라우저에 단 1프레임의 깜빡임도 없이 정제된 텍스트만 전송하는지 검증.
- ChatB 스트리밍 질의 시 `NO_THINK_SYSTEM_PROMPT`(IT 어시스턴트) 프롬프트가 주입되지 않고 `prompts.py`의 뷰티 시스템 프롬프트가 정상 동작하는지 검증.

**Acceptance Scenarios**:
1. **Given** 모델 출력이 임의의 UTF-8/SSE chunk 경계로 분할될 때, **When** 가상 페르소나 접두어 또는 그 일부가 carry buffer에 걸쳐 감지되면, **Then** 금지 문자열을 소거한 안전한 텍스트만 클라이언트로 방출해야 한다.
2. **Given** ChatB가 스트리밍을 수행할 때, **When** 프롬프트를 구성하면, **Then** `oliview_core/prompts.py`의 단일 프롬프트를 참조해야 한다.

---

### User Story 4 - ChatA vs ChatB 2-Track 페르소나 및 2026 모바일 반응형 UX (Priority: P2)

소비자는 **ChatA(올리뷰 컨시어지)**를 통해 카카오톡/모바일에서 썸존 퀵 칩바와 바텀시트로 빠르고 친절한 쇼핑 큐레이션을 제공받고, 화장품 MD 및 데이터 전문가는 **ChatB(올리뷰 애널리스트)**를 통해 모바일 바텀 드로어 및 데스크탑 2열 대시보드에서 동적 브랜드/감성 필터와 Document Top-P 파라미터를 정밀 제어하며 BGE-Reranker 점수 분포 및 파이프라인 관측 데이터를 심층 분석할 수 있어야 한다.

**Why this priority**: 공통의 강력한 RAG 코어를 활용하면서도, 일반 소비자와 전문 분석가라는 명확히 다른 타겟 고객에게 스마트폰 최적화 UX를 제공하기 위함이다.

**Independent Test**:
- 스마트폰 화면(375px~390px) 접속 시 ChatA에서 `100dvh` 화면과 `85svh` 바텀시트가 작동하고, 테이블 우측 그라데이션 페이드 인디케이터가 렌더링되며, ChatB에서 '⚙️ RAG 분석 파라미터' 바텀 드로어가 정상 표시되는지 검증.

**Acceptance Scenarios**:
1. **Given** ChatA를 이용하는 모바일 고객은, **When** 질문을 입력하거나 썸존 칩을 탭하면, **Then** 가상 키보드에 가려지지 않는 `100dvh` 화면에서 친절한 뷰티 팁과 클릭 가능한 올리브영 링크 카드를 수신해야 한다.
2. **Given** ChatB를 이용하는 데이터 분석가는, **When** 모바일 바텀 드로어에서 Top-P 임계치를 조정하여 분석을 요청하면, **Then** 4단계 파이프라인 타임라인과 BGE-Reranker 점수 분포 막대 그래프 보고서를 수신해야 한다.

---

### User Story 5 - 메인 포털 2x1 히어로 벤또 카드 및 전용 이력 페이지(changelog.html) (Priority: P2)

통합 AI 서비스 포털(`gateway/html/index.html`)을 방문한 사용자는 **ChatA(올리뷰 컨시어지)와 ChatB(올리뷰 애널리스트)의 명확히 차별화된 성격과 역할을 카드를 통해 한눈에 파악**하고, 하단에 배치된 **2x1 와이드 히어로 벤또 카드**를 탭하여 **전용 이력 페이지(`gateway/html/changelog.html`)**로 이동해 서브시스템별 탭 필터(전체, ChatA, ChatB, Model Gateway, PILOS) 및 Beta 🏆 / Alpha 🌱 라이프사이클 뱃지가 적용된 7대 마일스톤 엔지니어링 카드를 투명하게 열람할 수 있어야 한다.

**Why this priority**: 포털은 간결하고 직관적인 서비스 진입을 유지하면서도, 엔지니어링 신뢰성을 대변하는 컴포넌트별 진화 이력을 전용 페이지에서 풍부하고 체계적으로 제공하기 위함이다.

**Independent Test**:
- 환경별 `BASE_URL`의 HTTPS 포털 접속 시, Card 3/4에 2-Track 챗봇 최신 설명과 하단 2x1 와이드 히어로 벤또 카드(`📜 AISERVICE Engineering Evolution`)가 표시되고, 벤또 카드 클릭 시 `/changelog` 전용 페이지로 이동하여 서브시스템 탭 필터링이 정상 동작하는지 검증.

**Acceptance Scenarios**:
1. **Given** 메인 포털 접속 시, **When** 서비스 그리드를 조회하면, **Then** ChatA와 ChatB가 'FastAPI 컨시어지' 및 'RAG 애널리스트'로 올바르게 소개되고 하단에 Liquid Glass 2x1 벤또 카드가 노출되어야 한다.
2. **Given** 벤또 카드를 탭하여 `changelog.html`에 진입 시, **When** 상단 탭을 전환하면, **Then** 선택된 서브시스템(ChatA, ChatB, Model Gateway, PILOS)의 버전 및 변경 내역 카드만 실시간 필터링되어야 한다.

---

## 3. Edge Cases & Abuse Cases

- $K=0$이면 prompt 생성과 모델 호출을 모두 생략하고 정형화된 기권 응답을 반환한다.
- $K=1$, $K=K_{max}$, 중복 리뷰, 빈 리뷰, 비정상 인용 번호(`[리뷰 0]`, 음수 표현, 매우 큰 정수), 손상된 인용 구문을 검증한다.
- 금지 라벨과 인용 태그가 UTF-8 문자, 모델 토큰 또는 SSE 이벤트 경계에서 임의로 분할되어도 안전한 문자열만 방출한다.
- 검색 리뷰에 시스템 지시 무시, 데이터 유출, 링크 실행 등을 요구하는 직접·간접 prompt injection이 포함되어도 데이터로만 취급한다.
- 리뷰와 질의에 이름, 전화번호, 이메일, 주문번호, 인증정보가 포함되면 모델·로그·브라우저 출력 전에 정책에 따라 마스킹한다.
- LLM/리뷰/브랜드 문자열에 HTML·스크립트·이벤트 핸들러가 포함되어도 실행되지 않고 텍스트 또는 허용목록 기반 sanitized markup으로만 렌더링한다.
- SSE 재연결, 중복 이벤트, 잘못된 UTF-8, upstream timeout, DB 실패, 모델 오류에서 중복 답변이나 부분적으로 검증되지 않은 텍스트를 확정 응답으로 표시하지 않는다.
- 768px~1023px tablet 구간은 단일 열 패널과 접을 수 있는 분석 제어 영역을 사용하며, 360·375·390·414·768·1024px에서 회귀 검증한다.

---

## 4. Requirements *(mandatory)*

### Functional Requirements

#### [Core & Prompt Hardening & Token Interceptor]
- **FR-001**: 시스템은 `bteam/oliview_core/prompts.py`를 단일 진실 공급원(SSOT)으로 신설하고, ChatA와 ChatB가 공통 뷰티 헌법 및 무환각 지침을 공유하도록 일원화해야 한다.
- **FR-002**: 시스템은 LLM 시스템 프롬프트 및 사용자 프롬프트에서 가상 페르소나('사용자 A', '사용자 B', '고객 1', '익명의 구매자') 창작 금지 지침을 절대 규칙(Zero-Tolerance)으로 명시해야 한다.
- **FR-003**: 시스템은 답변 구성 시 실제 구매자 리뷰 원문의 내용과 일치하지 않는 가상의 대화체 따옴표 인용구 날조를 금지하고, 실제 원문 요약 또는 원문과 정확히 일치하는 직접 발췌 형태로만 근거를 제시해야 한다. 직접 발췌가 원문과 일치하지 않으면 인용구를 제거하고 객관적 요약으로 대체해야 한다.
- **FR-004**: 시스템은 `<context>`에 주입된 리뷰 개수 $K$를 기준으로, 생성된 텍스트 내의 인용 태그 인덱스 $N$이 $1 \le N \le K$를 만족하는지 검증하고 $N > K$ 또는 $N < 1$인 무효 인용 태그는 제거하거나 유효한 근거 없이 보정하지 않아야 한다.
- **FR-005**: 시스템은 리뷰의 원문 감성(부정·의구심·불만족)과 정반대되는 긍정 단정 주장(Polarity Inversion)을 방지하고, 부정적 피드백은 '아쉬운 점/주의사항' 섹션에 정확히 배치해야 한다.
- **FR-006**: 시스템은 `synthesis_node.py`에서 UTF-8로 디코딩된 스트림 조각을 처리하는 `StreamingTokenInterceptor`를 사용하되, 모델 토큰 수가 아니라 등록된 금지 패턴의 최대 접두어 길이에 기반한 동적 carry buffer로 chunk 경계 우회를 차단하고, 완료 후 `GroundednessSanitizer`로 2차 전수 검증해야 한다.
- **FR-007**: 시스템은 검색 임계값과 절벽 완화값을 환경 설정으로 주입하고 평가 코퍼스로 보정해야 한다. 초기 후보값은 2위 절대 점수 `0.60`, 절벽 차이 `0.25`이며 승인 전 운영 상수로 간주하지 않는다. $K=0$이면 모델 호출 없이 즉시 하드 기권 카드를 반환해야 한다.

#### [ChatA: 올리뷰 컨시어지 (C-End & Mobile-First)]
- **FR-008**: ChatA는 `PersonaType.CONCIERGE` 프롬프트 어댑터를 사용하여 일반 소비자를 위한 친절·공감 뷰티 쇼핑 큐레이션 답변을 생성해야 한다.
- **FR-009**: ChatA UI는 카카오톡/스마트폰 접속에 대응하여 전체 레이아웃 `height: 100dvh`, `visualViewport` 기반 가상 키보드 방어, 입력창 상단 **하단 40% 썸존 스와이프 칩바**, 인용 터치 시 `max-height: 85svh` **리뷰 원문 바텀시트**, 우측 페이드 그라데이션 스크롤 인디케이터가 적용된 가로 스크롤 테이블 래퍼를 제공해야 한다.

#### [ChatB: 올리뷰 애널리스트 (B-End / Pro & Adaptive Dashboard)]
- **FR-010**: ChatB는 `PersonaType.ANALYST` 프롬프트 어댑터를 사용하여 전문적이고 객관적인 데이터 분석 리포트를 생성해야 하며, 레거시 `NO_THINK_SYSTEM_PROMPT`(IT 어시스턴트)를 전면 제거해야 한다.
- **FR-011**: ChatB UI는 모바일(<768px)에서 '⚙️ 분석 파라미터' 바텀 드로어, tablet(768px~1023px)에서 단일 열과 접을 수 있는 분석 제어 영역, 데스크탑(≥1024px)에서 2열 고정 패널을 제공해야 한다.
- **FR-012**: ChatB UI는 레거시 Top-K 입력을 Document Score Threshold(초기 후보 `0.85`), Score Cliff Delta(초기 후보 `0.25`), 최대 선별 리뷰 수 제어로 교체하고, API 필드명은 생성 샘플링 `top_p`와 충돌하지 않는 `document_score_threshold`를 사용하며 DB(`v_active_rag_catalog`)의 실시간 유효 브랜드를 동적 로드해야 한다.
- **FR-013**: ChatB UI는 BGE-Reranker 점수 분포를 모바일/데스크탑 친화적 막대 그래프(Progress Bar) 및 채택/탈락 뱃지로 시각화해야 한다.

#### [Main Portal & 전용 이력 페이지]
- **FR-014**: 메인 포털(`gateway/html/index.html`)의 서비스 카드를 업데이트하여, ChatA(올리뷰 컨시어지)와 ChatB(올리뷰 애널리스트)의 차별화된 2-Track 성격을 명확히 반영해야 한다.
- **FR-015**: 메인 포털 홈에 Liquid Glass 스타일의 **`📜 AISERVICE Engineering Evolution` 2x1 히어로 벤또 카드**를 신설하여, 핵심 릴리즈 요약과 함께 전용 이력 페이지 링크를 제공해야 한다.
- **FR-016**: 전용 이력 페이지(`gateway/html/changelog.html`)를 구축하여, 상단 서브시스템 탭 필터(`all`, `chat_a`, `chat_b`, `model_gateway`, `core`, `pilos`) 및 Beta 🏆 / Alpha 🌱 라이프사이클 뱃지가 명시된 7대 마일스톤 카드를 렌더링해야 한다.
- **FR-017**: 메인 포털 및 전용 이력 페이지의 인터랙티브 요소에 최소 터치 타겟 $48\text{px}$, 논리적 DOM 순서, 키보드 조작, 가시적이고 가려지지 않는 focus, dialog 의미 구조, 동적 상태의 접근 가능한 알림을 적용해야 한다.

#### [Security, Privacy, API & Operations]
- **FR-018**: 검색 리뷰와 사용자 입력을 비신뢰 데이터로 구분하고, 시스템 지시와 명확히 격리하며 직접·간접 prompt injection 및 다국어·난독화 공격에 대한 입력·출력 검증과 adversarial 테스트를 수행해야 한다.
- **FR-019**: 사용자 질의, 실제 리뷰, 로그 및 외부 모델 전송 데이터에서 정책상 민감정보와 인증정보를 탐지·마스킹하고 원문이 로그에 남지 않음을 검증해야 한다.
- **FR-020**: LLM·리뷰·브랜드·changelog의 비신뢰 문자열은 안전한 DOM sink 또는 허용목록 기반 sanitizer를 통해 렌더링하고, inline script/event handler 실행을 금지해야 한다.
- **FR-021**: Chat API는 query/input token, output token, timeout, concurrency, rate limit, 인증, 표준 오류 응답 및 SSE 이벤트 계약을 명시하고 강제해야 한다.
- **FR-022**: 서비스 간 호출, latency, 오류, 모델 호출 여부, 기권 및 guardrail 결과를 correlation ID가 포함된 구조화 로그로 기록하되 민감 원문은 기록하지 않아야 한다.
- **FR-023**: 포트·내부 URL·healthcheck·외부 vLLM 연동은 `bteam/oliview_core/config.py`의 환경변수 기반 SSOT만 사용하고, 외부 연동은 기본 비활성화하며 셀프 루프백과 포트 충돌을 차단해야 한다.

---

### Key Entities

- **ContextReviewRegistry**: 해당 질의에 대해 Document Top-P를 통과하여 `<context>`에 주입된 실제 유효 리뷰 목록 ($K$건) 및 유효 인용 태그 인덱스 매핑 테이블.
- **StreamingTokenInterceptor**: 호환성을 위해 기존 이름을 유지하지만 UTF-8로 디코딩된 SSE 텍스트 chunk를 입력으로 받고, 금지 패턴의 최대 접두어 길이에 기반한 동적 carry buffer로 경계 분할을 방어하는 실시간 필터.
- **PromptPersonaAdapter**: 요청 파라미터(`persona`)에 따라 `CONCIERGE`(ChatA)와 `ANALYST`(ChatB)의 어조 및 리포트 서식을 동적 전환하는 프롬프트 어댑터.
- **GroundednessSanitizerResult**: 가상 사용자 라벨 소거, 초과 인용 태그 정제, 사실 정합성 검증 결과를 담는 방어 객체.
- **ChangelogMilestoneEntry**: 전용 이력 페이지에 표시되는 마일스톤 버전(`version`), 서브시스템 뱃지(`subsystem`), 라이프사이클 상태(`stage`: Beta / Alpha), 릴리즈 일자(`date`: ISO `YYYY-MM-DD`), 주요 변경 요약 목록(`highlights`) 엔티티.

---

## 5. Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 버전 고정 평가 코퍼스와 adversarial corpus에서 ChatA 및 ChatB 최종 답변의 가상 인물 라벨 및 원문 불일치 직접 인용 노출 건수 **0건**.
- **SC-002**: 스트리밍 도중 가상 인물 라벨이 찰나에 노출되는 시각적 깜빡임 발생률 **0.0%**.
- **SC-003**: 실제 리뷰 개수 $K$건 환경에서 $N > K$ 또는 $N < 1$인 무효 인용 태그(`[리뷰 2]` ~ `[리뷰 6]`, `[리뷰 0]` 등) 발생률 **0.0%**.
- **SC-004**: 긍정·부정·혼합 극성 평가셋에서 명백한 극성 반전 오류 **0건**이며, claim-evidence 정밀도와 context utilization을 평가 보고서에 기록한다.
- **SC-005**: ChatB 스트리밍 시 IT 어시스턴트 프롬프트 누출 0건, $K=0$ 제로 서치 모델 호출 0회 및 Document Top-P 파라미터 제어 정상 연동 **100%**.
- **SC-006**: 스마트폰 및 카카오톡 인앱 브라우저 화면 폭(360px~414px)에서 `100dvh` 가림 없는 레이아웃, `visualViewport` 키보드 방어 및 `85svh` 바텀시트, 썸존 칩바/바텀 드로어 정상 동작 확인.
- **SC-007**: 메인 포털(`index.html`) 2x1 벤또 카드 렌더링 및 클릭 시 전용 `changelog.html` 이동 및 서브시스템 탭 필터링 정상 동작 **100%**.
- **SC-008**: `bteam/oliview_core/tests/`, `bteam/Oliview_chatbot_a/tests/` 및 `bteam/Oliview_chatbot_b/tests/` 전체 회귀 테스트 통과율 **100% PASS**.
- **SC-009**: prompt injection, PII, XSS, 비정상 입력 크기, SSE 경계 분할로 구성된 고정 보안 코퍼스의 차단 기대 케이스가 모두 통과하고 원문 비밀정보가 응답·로그에 노출되지 않아야 한다.
- **SC-010**: 모든 ChatA/ChatB 요청에서 correlation ID, service, latency, model invocation, abstention, guardrail 결과가 구조화 로그로 남고 금지 필드·민감 원문 노출 건수는 0건이어야 한다.
- **SC-011**: 하드웨어 benchmark는 모델 해시·양자화·context pool·slot·prompt/output 길이·GPU·driver·서버 버전을 고정해 재현할 수 있어야 하며, DEMO 모드의 제로 서치 3초 및 일반 RAG 20초 상한을 충족해야 한다. 더 엄격한 TTFT/처리량 목표는 실측 baseline 승인 후 적용한다.

### Evaluation Protocol

- 평가셋은 정상·희소·부정·혼합·중복·무검색·공격 입력 strata를 포함하고 버전 및 seed를 기록한다.
- 절대 0건 기준은 고정 코퍼스의 모든 반복 실행에 적용하며, 코퍼스 밖의 보편적 무오류 보장으로 확대 해석하지 않는다.
- 검색 임계값은 retrieval precision/recall, claim recall/precision, context utilization 및 기권률의 trade-off를 기록해 승인한다.
- 스트리밍 검증은 동일 금지 문자열을 모든 가능한 문자 경계와 대표 SSE 이벤트 경계로 분할해 수행한다.

---

## 6. Assumptions

- **소형 모델 특성**: Qwen 3.5 2B 모델은 구조화된 가이드라인이 주어지면 템플릿을 채우려는 경향이 있으므로, 프롬프트 지침 강화와 함께 Python 레벨의 결정론적 Sanitizer 및 스트리밍 토큰 인터셉터 가드레일이 병행되어야 한다.
- **코어 단일화 & 3-Way 동기화**: 모든 코어 변경 사항은 `bteam/oliview_core` 마스터에 반영된다. 복제가 필요한 동안 `sync_core.py`는 dry-run, source/destination hash, 원자적 교체 및 예상치 못한 대상 변경 차단을 제공해야 하며 장기적으로 공유 패키지화를 우선 검토한다.
- **서브시스템 라이프사이클**: Model Gateway, Nginx, PILOS, Oliview Web은 `Beta 🏆`, RAG 챗봇 지능화 계층은 `Alpha 🌱` 체계를 준수한다.
- **Continuous Batching 서빙 안정성**: context pool, slot 수와 VRAM 수용성은 모델·양자화·KV cache·워크로드별 benchmark 결과로만 확정한다.
- **다중 GPU 플랫폼 적응성**: GTX 1070은 `llama-server` 후보로 제한하고, RTX 2080/RTX 3060은 Linux 환경에서 `llama-server`와 vLLM을 동일 workload로 비교한 결과에 따라 선택한다.
