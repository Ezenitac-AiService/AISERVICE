# Research: PILOS 챗봇 로컬 GPU 지연 해소 및 스트리밍·캐시 아키텍처

## 1. 정적 서비스 지식 캐싱 전략 (Service Knowledge Caching)

### Decision
사전 등록된 15개 서비스 지식 질문 블록(`service_overview`, `service_research_target`, `service_models`, `service_interpretation`, `service_columns`, `service_cautions`, `column_*`)에 대해 서버 기동 또는 최초 요청 시 서비스 정본 마크다운(`SERVICE_KNOWLEDGE_VERSION=1.0`) 기반으로 사전 구축된 **인메모리 딕셔너리 캐시(In-Memory Dict Cache)**를 적용한다.

### Rationale
- 15개 질문 블록은 내용이 불변하는 정본 문서(Ground Truth) 안내 항목입니다.
- 매번 BM25 + 로컬 임베딩(BGE-M3) + Chroma + 리랭커(BGE-Reranker) + LLM 생성을 실행하면 GTX 1070 환경에서 25~45초가 소요되지만, 인메모리 캐시를 조회하면 **10ms 미만(초고속)**에 정확한 출처와 마크다운 서식을 반환합니다.
- YAGNI 원칙에 부합하여 Redis나 외부 캐시 서버 없이 파이썬 네이티브 메모리 캐시로 복잡도를 최소화하면서 최대의 성능 향상을 얻을 수 있습니다.

### Alternatives Considered
- **On-demand LRU Cache**: 첫 요청 시 RAG/LLM을 실행하고 결과를 캐싱하는 방식. 최초 사용자는 여전히 30초 이상의 대기를 겪으므로, 사전 워밍(Pre-warmed/Static) 방식이 더 우수하여 기각.
- **외부 Redis Cache**: 멀티 인스턴스 공유 캐시. 단일 Flask 컨테이너 구조에서 추가 컨테이너 도입은 과도한 엔지니어링이므로 기각.

---

## 2. 동적 LLM 답변 생성 스트리밍 프로토콜 (Streaming Protocol)

### Decision
동적 LLM 질문 처리(보고서 요약, 사용자 맞춤 질의 등)에 대해 **SSE(Server-Sent Events) 기반 `text/event-stream` 스트리밍 프로토콜**을 적용한다.
- 토큰 생성 중: `data: {"type": "token", "delta": "단어"}\n\n`
- 추론 완료 시: `data: {"type": "done", "status": "ready", "sources": [...], "warnings": [...], "route": "..."}\n\n`
- 스트림 종료: `data: [DONE]\n\n`

### Rationale
- HTTP POST 요청 후 `ReadableStream`(`response.body.getReader()`)을 통해 첫 토큰이 생성되는 즉시(2~4초 내) 브라우저 화면에 타이핑 효과로 렌더링됩니다.
- 주기적인 바이트 전송이 발생하므로 브라우저 및 Nginx 프록시의 유휴 소켓 타임아웃(Idle Connection Timeout)이 원천 차단됩니다.
- WebSocket 대비 단방향 응답 스트리밍에 최적화되어 별도의 소켓 서버나 복잡한 프로토콜 핸드셰이크가 필요 없습니다.

### Alternatives Considered
- **WebSocket**: 양방향 통신에 유리하나 챗봇 단방향 질의-응답 스트리밍에는 불필요하게 복잡하며 Nginx 프록시 설정 오버헤드가 큼.
- **Short Polling (작업 ID + 주기적 상태 확인)**: 백엔드에 비동기 태스크 큐(Celery/Redis)가 필요하여 구조가 지나치게 무거워짐.

---

## 3. 로컬 GPU 타임아웃 및 재시도 정책 (Local LLM Timeout & Retry Policy)

### Decision
- `CHAT_LLM_TIMEOUT_SECONDS` 및 `LLM_TIMEOUT_SECONDS` 기본값을 기존 30초에서 **120초**로 확대.
- `OpenAICompatibleLlmClient`의 무분별한 3회 연속 재시도 루프를 제거(또는 `max_retries=0` / 1회 단일 호출)하여, GPU가 연산 중일 때 중복 요청이 큐에 쌓이는 재시도 폭주(Retry Storm)를 원천 차단.
- OpenAI SDK 호출 시 `stream=True` 옵션을 적용하여 제너레이터 기반으로 토큰을 실시간 추출.

### Rationale
- GTX 1070 8GB 환경에서 긴 프롬프트(RAG 컨텍스트 포함) 추론 시 25~45초가 정상 소요됩니다.
- 기존 30초 타임아웃은 조기 종료 후 재시도를 트리거하여 GPU 큐를 마비시키는 주원인이었습니다.
- 단일 스트림 호출로 120초 한도를 부여하면 GPU가 단 하나의 작업을 온전히 끝마칠 수 있습니다.

### Alternatives Considered
- **지수 백오프 3회 재시도 유지**: 로컬 GPU는 원격 API와 달리 요청을 거절하지 않고 큐에 쌓아두므로, 재시도가 누적되면 GPU 메모리 고갈(OOM) 및 전체 지연이 가중되어 기각.

---

## 4. 프론트엔드 실시간 렌더링 및 취소 제어 (Frontend Streaming & Abort)

### Decision
`chat.js`의 `requestChat` 함수를 `fetch` + `response.body.getReader()` 기반의 스트리밍 파서로 확장하고, `AbortController`를 통해 사용자 전환/닫기 시 즉시 스트림을 차단한다.

### Rationale
- 브라우저 표준 `TextDecoder`와 `ReadableStream`을 사용하여 추가 외부 JS 라이브러리 없이 순수 바닐라 JS로 완벽히 동작합니다.
- 토큰 수신 시마다 텍스트 노드를 실시간 업데이트하고, `type: "done"` 수신 시 최종 마크다운 렌더러([renderMarkdown](file:///c:/AISERVICE/ateam/pilos-sentiment-index/pilos/web/static/js/chat.js#L991-L1067))를 호출하여 볼드체/인용구/목록 서식 및 출처 뱃지를 한 번에 확정합니다.

---

## 5. Nginx 게이트웨이 및 라우팅 정합성 (Gateway & Routing Alignment)

### Decision
- [gateway/nginx.conf](file:///c:/AISERVICE/gateway/nginx.conf)의 `/api/` 및 `/ateam/pilos/` 프록시 블록에 `proxy_buffering off;` 및 `proxy_set_header Connection '';`이 유지되는지 검증.
- 고정 종목 모드 경로 `/api/stocks/<stock_code>/chat`와 공용 경로 `/api/chat` 모두 동일한 SSE 스트리밍 및 캐시 엔드포인트 핸들러를 공유하도록 라우팅 정규화.

### Rationale
- Nginx가 응답을 버퍼링하면 SSE 스트림이 브라우저에 실시간 전달되지 않고 한꺼번에 쏟아지는 문제가 생깁니다. `proxy_buffering off;` 설정을 통해 0ms 지연 전달을 보장합니다.
