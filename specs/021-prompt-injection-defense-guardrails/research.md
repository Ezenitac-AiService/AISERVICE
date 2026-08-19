# Phase 0: Technical Research & Security Decisions

**Feature**: `021-prompt-injection-defense-guardrails` (Oliview Chatbot A/B 다계층 프롬프트 인젝션 방어 가드레일)

## Research Topics & Architectural Decisions

### 1. 2026 LLM 보안 표준 기반 다계층 방어 (Defense-in-Depth) 구조 설계

- **Context**: 2026년 기준 LLM 보안 위협(OWASP Top 10 for LLM 2025/2026)에서 프롬프트 인젝션(Direct & Indirect), 시스템 프롬프트 유출, 탈옥 공격이 가장 주요한 위험 요소로 분류됨.
- **Decision**: 단일 방어선이 아닌 4단계 계층형 방어(Defense-in-Depth) 파이프라인 구축:
  1. **Tier 1 (Pre-Input)**: 디오브퍼스케이션(De-obfuscation) + 초고속 정규식 시그니처 필터 (<5ms)
  2. **Tier 2 (Prompt Sandboxing)**: `<user_query>`, `<reference_reviews>` XML 태그 샌드박싱 + 사용자 태그 이스케이프 + 최하단 지시문 재강화(Instruction Defense)
  3. **Tier 3 (Indirect Defense)**: RAG 검색 데이터를 비실행 수동 참조 데이터(Passive Data)로 엄격히 선언
  4. **Tier 4 (Post-Output)**: 카나리아 토큰(Canary Token) 누출 감지 및 안전 거절 응답 반환
- **Rationale**:
  - LLM 자체에만 방어를 의존할 경우 새로운 탈옥 기법에 취약해질 수 있으므로, 결정론적(Deterministic) 전처리 필터와 구조적 샌드박싱을 결합하여 100%에 가까운 신뢰성 확보.
- **Alternatives Considered**:
  - *대안 1 (모든 질의마다 LLM-as-a-Judge 실행)*: 비용 증가 및 지연시간(+300ms 이상) 발생으로 실시간 챗봇 UX를 저해하므로 기각.
  - *대안 2 (단순 금칙어 필터링)*: "무시", "지시" 등의 일반 단어가 포함된 정상 화장품 질문에 오탐(False Positive)을 유발하므로 정규화 및 맥락 결합 정규식 채택.

---

### 2. 난독화 해제(De-obfuscation) 및 ReDoS 방어 전략

- **Context**: 공격자들은 공백 사이에 제로 너비 문자(`\u200B`, `\uFEFF`)를 삽입하거나, 키릴 자모/유니코드 유사문자(Homoglyphs)를 사용하여 텍스트 필터를 우회함. 또한 과도한 역추적(Backtracking)이 발생하는 정규식은 ReDoS DoS 공격에 취약함.
- **Decision**:
  - 제로 너비 및 비가시 제어 문자 정규 제거: `re.sub(r'[\u200B-\u200D\uFEFF\u0000-\u0008\u000B\u000C\u000E-\u001F]', '', text)`
  - 유니코드 정규화(`unicodedata.normalize('NFKC', text)`) 및 기본 호모글리프 알파벳 매핑.
  - 모든 정규식 패턴은 사전 컴파일(Pre-compiled `re.compile`) 및 선형 시간 복잡도(O(N)) 비탐욕 패턴으로 한정.
- **Rationale**: 정규화 후 시그니처를 검사하면 복잡한 난독화 우회 시도를 원천 차단할 수 있으며, 1ms 이내로 안전하게 연산 완료.

---

### 3. XML 태그 샌드박싱 및 카나리아 토큰(Canary Token) 메커니즘

- **Context**: 사용자 질문이나 검색 리뷰 데이터가 시스템 프롬프트의 지시문과 섞여 실행 영역을 침범하는 것을 방어하고, 시스템 지시문 유출을 사후 검증해야 함.
- **Decision**:
  - 사용자 입력과 리뷰 데이터를 XML 태그(`<user_query>`, `<reference_reviews>`)로 감싸고, 입력 내에 포함된 태그 기호는 `&lt;` `&gt;`로 이스케이프.
  - 시스템 프롬프트 상단에 UUID 기반 세션별 `Canary Token`을 무작위 주입하고, 모델 출력 스트림에 카나리아 토큰 또는 `system_prompt` 핵심 시퀀스가 나타나면 출력을 즉시 중단하고 마스킹.
- **Rationale**: 완벽한 데이터-명령어 분리를 제공하며, 모델이 혹시라도 지시를 어기고 프롬프트를 노출하려 할 때 100% 탐지 및 차단 가능.
