# Research & Technical Decisions: 047-fix-chata-synthesis-and-entity-naming

## 1. Target Entity vs Product Name Decoupling Architecture

- **Context**: 카테고리 발굴(`FEATURE_DISCOVERY`) 질문(예: *"스킨케어에서 수분감 좋은 인기 앰플 추천해줘"*, *"여름철 기름기 잡고 모공 커버 잘되는 매트한 파운데이션"*) 인입 시, 의도 라우터가 질문 문자열을 `TargetEntity.target_name`으로 설정한 뒤, 검색 및 오케스트레이터가 실제 DB의 상품명 대신 질문 문장을 상품명으로 취급하여 인용 태그 및 올리브영 검색 URL 파라미터를 오염시키는 결함.
- **Decision**: `TargetEntity`의 `target_name`(라우팅/검색용 쿼리 식별자)과 실제 검색된 리뷰 레코드의 `product_name` / `clean_product_name`(단일 진실 공급원)을 엄격히 분리한다. `search_node` 및 `graph_orchestrator`는 검색 풀에서 반환된 실제 MySQL/Chroma 메타데이터의 `product_name`을 인용 뱃지(`[제품명 리뷰 N]`), 아코디언 카드 타이틀, 올리브영 검색 링크 파라미터의 최우선 SSOT로 결속한다.
- **Rationale**: 사용자 질문 문장은 검색 가이드일 뿐 상품명이 아니며, 실제 DB에서 발굴된 화장품 실명(예: `차앤박 뮤제너 피토 수딩 앰플 35ml`, `브링그린 알로에 97% 수딩젤`)이 사용자의 인용 근거와 구매 링크에 정확히 연결되어야 한다.
- **Alternatives Considered**:
  - *질문 문자열에서 상품명을 LLM으로 재추출*: 불필요한 LLM 왕복 지연(500ms+) 및 환각 위험 발생. 검색된 리뷰의 DB 메타데이터를 직접 사용하는 것이 0ms 지연 및 100% 사실 정합성을 보장함.

---

## 2. Multi-Product Dynamic Grouping in Discovery Pool

- **Context**: 단일 검색 풀(`discovery_pool`)에 여러 서로 다른 상품(예: 차앤박 앰플, 브링그린 세럼 등)의 리뷰가 섞여 들어왔을 때, 이를 단일 타겟으로 취급하면 인용 태그가 뒤섞이거나 엉뚱한 번호가 부여되는 문제.
- **Decision**: `rerank_node` 및 `context_node`에서 후보 문서를 실제 `product_name`별로 자동 그룹화(Partitioning)하여, 각 상품별로 독립된 네임스페이스(`[제품A 리뷰 1]`, `[제품B 리뷰 1]`)를 부여하고 올리브영 링크도 개별 상품별로 1:1 매핑한다.
- **Rationale**: 2026년 Agentic RAG 표준에 따라 다중 상품 추천 시 각 제품별 독립 근거 결속(Namespace Isolation)이 필수적이다.
- **Alternatives Considered**:
  - *전체 통합 `[리뷰 1]`, `[리뷰 2]` 단일 번호 체계*: 추천 모드에서 사용자가 어느 제품의 후기인지 식별하기 어려움.

---

## 3. Gated Write-Back Poison Cache Defense in Redis L5

- **Context**: `synthesis_node`에서 LLM 생성 도중 타임아웃이나 연결 실패가 발생했을 때, 방출된 에러 메시지(`[답변 생성 오류: timed out]`)가 비어있지 않은 문자열이라는 이유로 Redis L5 응답 캐시에 12시간 동안 영구 저장되어 에러가 반복 재생되는 결함 (OWASP LLM08 Cache Poisoning).
- **Decision**: `is_valid_synthesis_response()` 복합 유효성 검증 게이트를 신설하여 다음 조건 중 하나라도 해당할 경우 L5 캐시 저장을 100% 차단(Bypass)한다:
  1. 에러 키워드 감지 (`"[답변 생성 오류:"`, `"timed out"`, `"Error:"`, `"Exception:"`, `"traceback"`, `"유출 감지"`)
  2. 최소 완결 텍스트 길이 미달 (`len(response_text.strip()) < 80`)
  3. 인라인 인용 태그(`[... 리뷰 \d+]`) 부재
  4. 기존 오염된 Redis L5 키 패턴(`l5:*`, `chata:l5:*`, `chatb:l5:*`)에 대해 기동 시 또는 명시적 호출 시 일괄 Eviction 지원.
- **Rationale**: 불완전하거나 실패한 응답이 캐시되는 것을 원천 차단하여 시스템 신뢰성을 복구한다.
- **Alternatives Considered**:
  - *L5 캐시 완전 비활성화*: 정상 응답 시의 0.1초 즉시 응답 이점(SLA)을 상실하므로, 게이트 검증을 통한 선별 캐싱이 최적.

---

## 4. Resilient LLM Streaming Timeout Configuration

- **Context**: 공유 GPU/CPU 환경에서 vLLM 초기 추론 및 큐 대기 시간(30~40초) 동안 `AiGatewayClient`의 `inactivity_timeout_s`가 만료되어 `ReadTimeout` 에러가 발생하는 문제.
- **Decision**: AISERVICE 헌법 제6조(시연 모드 지연 허용)에 따라 `APP_RUN_MODE=DEMO` 및 `development` 모드에서 `inactivity_timeout_s=180.0`, `timeout_llm_sec=180.0`으로 넉넉한 타임아웃 예산을 확보하고, 브라우저 스트림 유휴 방지를 위한 5초 주기 단계 업데이트를 유지한다.
- **Rationale**: 실증 환경의 GPU 자원 제약을 안정적으로 수용하면서 Nginx 게이트웨이 타임아웃(300초) 이내에 온전한 토큰 스트리밍 완주를 보장한다.
- **Alternatives Considered**:
  - *동기 블로킹 호출로 전환*: 스트리밍 실시간 사용자 경험이 파괴되므로 SSE 스트리밍 유지 필수.

---

## 5. Regex-based Leading Bracket & Category Delimiter Stripper

- **Context**: 리뷰 원문에 남아있는 `[기획세트]` 태그나 짝이 맞지 않는 선행 닫는 괄호(`]`) 파편이 `clean_text` 앞에 노출되는 문제.
- **Decision**: `re.sub(r'^\s*\[[^\]]*\]\s*', '', text)` 및 `re.sub(r'^\s*\]\s*', '', text)` 정규식을 공용 코어(`sanitizer.py` / `graph_orchestrator.py`)에 표준화하여 선행 대괄호 파편을 완벽히 정제하고, 텍스트가 과도하게 짧아지면 원본을 안전 복원한다.
- **Rationale**: 구매자 리뷰의 가독성을 극대화하고 UI에 지저분한 문장 파편이 노출되지 않도록 보장한다.

---

## 6. 3-Way Single-Master Core Synchronization via `bteam/sync_core.py`

- **Context**: `bteam/oliview_core`(마스터), `bteam/Oliview_chatbot_a/oliview_core`(ChatA), `bteam/Oliview_chatbot_b/oliview_core`(ChatB) 3개 복제본 간의 코드 불일치(Desync) 위험.
- **Decision**: 마스터 코어(`bteam/oliview_core`)를 단일 진실 공급원(SSOT)으로 하여 모든 코어 로직을 작성/수정한 후, `python bteam/sync_core.py`를 실행하여 3개 디렉터리를 100% 바이트 단위로 동기화하고 테스트에서 `--verify` 검증을 통과시킨다.
- **Rationale**: 헌법 제3조(서비스 모듈화 및 격리)를 준수하면서 중복 관리 부채를 완전히 해소한다.
