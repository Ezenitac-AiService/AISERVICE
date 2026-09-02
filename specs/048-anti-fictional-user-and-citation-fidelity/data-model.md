# Phase 1: Data Model (048-anti-fictional-user-and-citation-fidelity)

**Date**: 2026-09-02
**Feature**: [spec.md](file:///c:/AISERVICE/specs/048-anti-fictional-user-and-citation-fidelity/spec.md)
**Status**: Completed

---

## 1. Domain Entities & Class Models

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Feature 048 Domain Data Model                         │
└─────────────────────────────────────────────────────────────────────────────┘
  ContextReviewRegistry
   ├── count: int (K건, 0 <= K <= configured_max <= 20)
   ├── reviews: List[ReviewItem]
   └── valid_citation_tags: List[str]  # e.g., ["[브링그린 리뷰 1]"]

  PromptPersonaAdapter
   ├── persona: PersonaType (CONCIERGE | ANALYST)
   ├── source: ServiceIdentity (CHAT_A | CHAT_B, client override 금지)
   ├── get_system_prompt() -> str
   └── format_user_prompt(query, context, registry) -> str

  StreamingTokenInterceptor
   ├── carry: str (금지 패턴 최대 접두어 길이 기반 동적 suffix buffer)
   ├── registered_k: int
   ├── process_chunk(chunk: str) -> Optional[str]
   └── flush() -> str

  CitationView
   ├── review_index: int (1 <= N <= K)
   ├── review_id: str
   ├── display_quote: str (안전한 원문 substring 또는 동일 정책으로 redaction한 표시 문자열)
   └── quote_redacted: bool

  ProductLinkCard
   ├── label: str
   ├── url: str (HTTPS, allowlisted Olive Young host)
   └── host_validated: Literal[True]

  PipelineStageEvent
   ├── stage: PipelineStage (SEARCH | RERANK | GROUNDING | SYNTHESIS)
   ├── status: StageStatus (PENDING | RUNNING | COMPLETED | SKIPPED | FAILED)
   └── latency_ms: int

  AuthPrincipalContext
   ├── principal_id: str (로그에는 비가역 상관 식별자만 사용)
   ├── service_id: ServiceIdentity
   ├── auth_method: AuthMethod (BEARER | BROWSER_SESSION)
   └── csrf_verified: bool

  GroundednessSanitizerResult
   ├── sanitized_text: str
   ├── persona_removed_count: int
   ├── citations_removed_count: int
   ├── claims_removed_count: int
   ├── citations: List[CitationView]
   └── is_grounded: bool

  ChangelogMilestoneEntry
   ├── version: str (e.g., "v0.7.0-alpha", "v0.9.0-beta")
   ├── subsystem: SubsystemType (CHAT_A | CHAT_B | MODEL_GATEWAY | NGINX_GATEWAY | OLIVIEW_WEB | CORE | PILOS)
   ├── stage: StageType (BETA_TROPHY | ALPHA_SPROUT)
   ├── release_date: str (ISO YYYY-MM-DD)
  └── highlights: List[str]

  StructuredLogEvent
   ├── correlation_id: UUID
   ├── service: str
   ├── event: str
   ├── latency_ms: int
   ├── model_invoked: bool
   ├── abstained: bool
   ├── guardrail_counts: Dict[str, int]
   └── redaction_applied: bool
```

---

## 2. Entity Specifications

### 1) `ContextReviewRegistry`
- **책임**: Document Score Threshold를 통과하여 컨텍스트에 주입된 유효 리뷰 목록 및 인용 인덱스 상한($K$) 관리.
- **Attributes**:
  - `reviews: List[Dict[str, Any]]`: 선별된 실존 리뷰 객체 리스트.
  - `k_bound: int`: 유효 리뷰 개수 (`0 <= K <= configured_max_selected_reviews <= 20`). 기본 최대값 후보는 6이며 설정으로 주입한다.
  - `allowed_tags: Set[str]`: 허용된 인용 태그 집합 (예: `{"[브링그린 리뷰 1]"}`).
  - `is_sparse: bool`: $K \le 1$ 여부 (True일 경우 단일 리뷰 적응형 프롬프트 활성화).

### 2) `StreamingTokenInterceptor`
- **책임**: 호환성을 위해 이름은 유지하지만 UTF-8로 디코딩된 SSE text chunk를 처리한다. tokenizer token이나 SSE 이벤트 경계를 신뢰하지 않고 가상 인물 라벨 및 금지 패턴의 경계 분할을 차단한다.
- **Attributes**:
  - `carry: str`: 현재 보유 중인 미방출 suffix 문자열.
  - `carry_length: int`: 등록된 금지 패턴의 최대 부분 접두어를 안전하게 보유할 수 있도록 계산된 길이. 고정 token count를 사용하지 않는다.
  - `persona_regex: Pattern`: `r'사용자\s*[A-Z가-힣0-9]|고객\s*[0-9]|익명의\s*구매자'`
  - `overflow_citation_regex: Pattern`: `r'\[([^\]]+리뷰\s*([0-9]+))\]'` (where index $> K$ or index $< 1$)
- **Methods**:
  - `feed(chunk: str) -> str`: UTF-8 디코딩 완료 text chunk를 결합하고 안전한 접두어만 방출.
  - `finalize() -> str`: 잔여 버퍼 정제 후 최종 방출.

### 3) `PromptPersonaAdapter`
- **책임**: 단일 SSOT 프롬프트 모듈(`bteam/oliview_core/prompts.py`)의 공통 integrity base prompt를 공유하고, 2-Track 페르소나별 어조와 텍스트 서식만 조합.
- **Attributes**:
  - `PersonaType`: `Enum("PersonaType", ["CONCIERGE", "ANALYST"])`
  - `ServiceIdentity`: ChatA는 `CONCIERGE`, ChatB는 `ANALYST`로 서버에서 고정하며 client payload의 persona override를 허용하지 않음.
- **Functions**:
  - `build_beauty_system_prompt(persona: PersonaType, k_bound: int) -> str`
  - `build_rag_user_prompt(query: str, context: str, registry: ContextReviewRegistry) -> str`

### 4) `ChangelogMilestoneEntry`
- **책임**: canonical URL `/changelog`에서 `gateway/html/changelog.html`로 렌더링되는 서브시스템별 릴리즈 이력 데이터 구조.
- **Attributes**:
  - `version: str`: 버전 문자열 (예: `"v0.7.0-alpha"`, `"v0.9.0-beta"`).
  - `subsystem: str`: `"chat_a"` | `"chat_b"` | `"model_gateway"` | `"nginx_gateway"` | `"oliview_web"` | `"core"` | `"pilos"`. `"all"`은 UI filter state이며 저장 엔티티 값이 아니다.
  - `stage: str`: `"beta"` (Beta 🏆) | `"alpha"` (Alpha 🌱).
  - `date: str`: ISO 날짜 `"2026-09-02"`.
  - `title: str`: 릴리즈 타이틀.
  - `highlights: List[str]`: 주요 성과 불릿 목록.
  - `spec_ref: Optional[str]`: 관련 스펙 경로.

### 5) `StructuredLogEvent`
- **책임**: 서비스 호출과 guardrail 결과를 민감 원문 없이 추적한다.
- **Required Attributes**:
  - `timestamp`: UTC ISO 8601 timestamp.
  - `correlation_id`: 요청 전 구간에서 유지되는 UUID.
  - `service`, `event`, `latency_ms`, `model_invoked`, `abstained`, `redaction_applied`.
  - `guardrail_counts`: persona/quote/citation/polarity/injection/redaction 처리 개수.
- **Prohibited Raw Fields**: `query`, `review_text`, `system_prompt`, `context`, `token`, API key 및 인증 토큰 원문.
