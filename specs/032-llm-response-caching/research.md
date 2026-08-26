# Research & Technical Decisions: 032-llm-response-caching

**Feature**: `032-llm-response-caching`  
**Date**: 2026-08-26  
**Status**: Completed  

---

## 1. Research Topics & Decisions

### Decision 1: L5 캐시 키 생성 및 탈맥락화 정규화 기법
* **선택**: `SHA256(NFKC(rewritten_query) + sorted_doc_ids_hash + prompt_version_hash + model_id + tenant_id)`
* **선택 근거**:
  * **멀티턴 맥락 오염(Context Contamination) 방지**: 사용자가 대명사("이거 얼마야?", "다른 색상은?")를 사용할 때 raw query를 캐싱하면 이전 대화의 엉뚱한 제품 답변이 반환될 위험이 있습니다. 따라서 `QueryRewriterNode`가 생성한 탈맥락화 독립 질의(`rewritten_query`)를 캐시 키 입력으로 사용합니다.
  * **정규화(Normalization)**: Unicode NFKC, 다중 공백 단일화, 소문자화 전처리를 적용하여 띄어쓰기 1개 차이나 문장 부호로 인한 불필요한 캐시 미스를 방지합니다.
  * **데이터 무결성(Context Invalidation)**: RAG 검색/리랭커가 반환한 상위 문서 ID들의 정렬 해시(`doc_ids_hash`)를 결합하여, 크롤러/분석 배치가 돌아 상품 정보나 리뷰가 바뀌면 자동으로 캐시 미스가 발생하도록 보장합니다.
* **대안 비교**:
  * *대안 A (Raw 질문만 해싱)*: 구현은 간단하나 멀티턴 대명사 질의 시 치명적인 맥락 왜곡 발생 및 DB 데이터 갱신 시 Stale 데이터 노출 위험으로 기각.
  * *대안 B (벡터 유사도 기반 Semantic Cache)*: 0.90 이상의 유사도 매칭 시 미세한 뉘앙스 차이(예: 21호 vs 23호)에서 오답을 낼 위험이 있어, 1단계로는 100% 결정론적인 Exact Match Cache를 우선 채택.

---

### Decision 2: Cache Stampede (Thundering Herd) 방어 메커니즘
* **선택**: `SingleFlightLock` (Redis 분산 락) + `TTL Jitter (12시간 ± 1시간)`
* **선택 근거**:
  * 인기 상품 질의의 캐시가 만료되는 순간 다수의 동시 요청이 유입될 때 모두 캐시 미스로 판정되어 단일 GPU 슬롯 큐를 일시에 폭파시키는 현상을 방지합니다.
  * `redis_pool.py`의 `SingleFlightLock`(`SET lock_key val NX PX 5000`)을 활용하여 최초 1개 요청만 GPU 추론을 수행하고, 나머지 요청은 0.1초 간격으로 캐시 생성을 대기(Poll) 후 즉시 공유합니다.
  * 기본 12시간(`redis_ttl_llm_response = 43200`초) 만료 시간에 무작위 ±3600초 Jitter를 부여하여 대량 엔트리의 동시 만료를 분산합니다.
* **대안 비교**:
  * *대안 A (락 없는 단순 캐싱)*: 인기 상품 질의 만료 시 GPU 큐 병목 발생으로 기각.
  * *대안 B (Background Probabilistic Recomputation)*: 백그라운드 워커가 불필요하게 GPU 슬롯을 사전 소모하므로 단일 GPU 환경에 부적합하여 기각.

---

### Decision 3: Word-Boundary Streaming Cache Replay 엔진
* **선택**: 단어 경계 단위(Word Boundary, 청크당 4~10자 / 20~30ms 간격) 고속 스트리밍 Replay
* **선택 근거**:
  * **UX 호환성**: 캐시 히트 시 수천 자의 JSON 전문을 한 번에 덤프하면 클라이언트(Chat A, Chat B)의 SSE 파서, 마크다운 렌더러 및 타이핑 인터랙션이 깨지거나 부자연스러워집니다.
  * **DOM 렌더링 최적화**: 1글자/10ms 단위는 브라우저 DOM 재렌더링 과부하(CPU 스파이크)를 유발하므로, 단어/공백 단위(4~10자)로 20~30ms마다 전송하여 60fps의 부드러운 타이핑 효과를 보장합니다.
  * **메타데이터 전달**: SSE 스트림 최초 이벤트 또는 응답 헤더에 `x-cache: HIT`, `is_cached: true`, `latency_saved_s` 메타데이터를 전송하여 프론트엔드 및 APM 관측성을 확보합니다.
* **대안 비교**:
  * *대안 A (Non-streaming 단일 블록 반환)*: 기존 스트리밍 인터페이스 규격과 충돌하고 프론트엔드 코드 분기를 강제하므로 기각.
  * *대안 B (1글자 단위 10ms 스트리밍)*: 클라이언트 브라우저 렌더링 과부하 유발로 기각.

---

### Decision 4: Cache Poisoning 방지 (Deny-List Policy)
* **선택**: 안전성 가드레일 거부 문구, 에러성 답변, 20자 미만 답변의 캐시 적재 차단 (Deny-List Guard)
* **선택 근거**:
  * 시스템 프롬프트 탈취/탈옥 시도에 대한 거부 응답이나 LLM 생성 오류 문구가 캐시에 저장될 경우, 정상 사용자에게 오염된 답변이 영구 전파되는 보안 사고를 방지합니다.
  * `len(response_text) >= 20` 및 에러 키워드("죄송합니다", "답변할 수 없습니다", "일시적인 오류") 검증 후 안전한 뷰티 분석 답변만 Redis L5에 커밋합니다.
* **대안 비교**:
  * *대안 A (모든 200 OK 응답 무조건 캐싱)*: 에러 및 거부 문구까지 캐싱되어 서비스 품질 저하를 유발하므로 기각.

---

### Decision 5: Fail-Fast 격리 및 테넌트 네임스페이스
* **선택**: Redis 소켓 타임아웃 0.2초 Fail-Fast + `olliview:l5:{tenant_id}:{hash}` 네임스페이스 격리
* **선택 근거**:
  * Redis 서버 장애 또는 네트워크 지연 시 전체 RAG 파이프라인이 멈추지 않고 즉시 캐시 미스로 판정하여 GPU 직접 추론으로 자동 Fallback(회복 탄력성 100%).
  * Chat A(Streamlit)와 Chat B(Web UI) 간의 마크다운 서식 및 UI 페르소나 차이를 네임스페이스 레벨에서 완벽히 격리.
