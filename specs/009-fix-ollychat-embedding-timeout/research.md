# Research: 올리챗·올원챗 임베딩 타임아웃 해소, 순차 대기 큐 및 3대 챗봇 통합 회귀 검증 (009-fix-ollychat-embedding-timeout)

## 1. 장애 원인 분석 및 기술적 의사결정

### Decision 1: Model Gateway 보조 프로세스(포트 8090/8091) I/O 파이프 데드락 해소
- **문제 진단**: `vllm-serv-gateway`에서 `bge-m3` 임베딩(8090) 및 `bge-reranker-v2-m3` 리랭커(8091)를 `python -m llama_cpp.server` 서브프로세스로 구동할 때, `stdout=asyncio.subprocess.PIPE`로 생성됨. 이 서브프로세스의 로그를 비동기로 읽는 `_drain_stdout` 태스크가 중단되거나 지연되면서 Linux 커널 레벨에서 64KB 파이프 버퍼가 가득 차 서브프로세스가 `anon_pipe_write` 상태로 영구 정지(Hang)됨.
- **선택된 해결책**:
  - 서브프로세스 생성 시 `stdout`/`stderr`를 `asyncio.subprocess.PIPE` 대신 회전 로그 파일(`open(bench_log_path, "a")`) 또는 `/dev/null` 파일 디스크립터로 직접 리다이렉션(`stdout=log_fd`, `stderr=subprocess.STDOUT`).
  - 파이프 버퍼를 거치지 않고 OS 커널이 디스크 파일로 직접 쓰도록 하여 I/O 데드락 원천 차단.
- **대안 비교**:
  - *대안 A: `_drain_stdout` 코루틴을 더 적극적으로 폴링*: 파이썬 이벤트 루프 부하 시 여전히 버퍼 오버플로우 위험 잔존 (기각).
  - *대안 B: 파일 디스크립터 직접 리다이렉션*: 파이썬 런타임 간섭 없이 OS 커널이 100% 안전하게 디스크에 기록 (채택).

---

### Decision 2: 단일 GPU 자원 경합 시 스트리밍 킵얼라이브 순차 대기 큐 (Option A)
- **문제 진단**: 단일 NVIDIA GTX 1070 (8GB VRAM) 환경에서 2개 이상의 챗봇(PILOS, 올리챗, 올원챗)이 동시에 무거운 LLM 생성을 요청하면 GPU OOM 또는 동시 추론 연산 지연으로 인해 Nginx/브라우저 유휴 소켓 타임아웃(30~60초) 단절 발생.
- **선택된 해결책**:
  - `vllm-serv-gateway`의 메인 LLM 엔드포인트(`/v1/chat/completions`)에 `asyncio.Lock` 기반 FIFO 순차 대기 큐 구현.
  - 요청 진입 즉시 락이 획득되지 않고 대기해야 하는 경우, 스트리밍 클라이언트에게 `"type": "status"`, `"content": "LLM 서버가 다른 질문을 처리 중입니다. 순서를 기다리고 있습니다..."` 킵얼라이브 패킷을 즉각 전송하여 소켓 연결 유지.
  - 이전 작업 완료로 락 획득 시 즉시 실제 토큰 스트리밍 시작.
- **대안 비교**:
  - *대안 A: HTTP 429 Retry-After 반환*: 클라이언트가 폴링 로직을 구현해야 하며 UX가 분절됨 (기각).
  - *대안 B: 단순 백엔드 블로킹*: 클라이언트 소켓이 30초 유휴 상태로 대기하다가 타임아웃 종료됨 (기각).
  - *대안 C: 스트리밍 킵얼라이브 순차 큐 (Option A)*: 연결 유지 및 실시간 안내 완벽 지원 (채택).

---

### Decision 3: 클라이언트 레벨 타임아웃 현실화 (120초)
- **적용 대상**:
  - `bteam/Oliview_chatbot_a/common/embedding_client.py`: `timeout: float = 120.0`
  - `bteam/Oliview_chatbot_b/`: 타임아웃 기본값 120초 구성
- **효과**: 일시적인 큐 대기나 대용량 텍스트 임베딩 시 60초 조기 단절 방지.

---

### Decision 4: 3대 챗봇 통합 자동화 회귀 테스트 스위트
- **대상 엔드포인트 및 검증 항목**:
  1. **A-Team PILOS**:
     - 정본 지식 캐시 조회 (< 50ms, GPU 0%)
     - 동적 종목 분석 스트리밍 (200 OK)
  2. **B-Team 올리챗 (Streamlit / 8501)**:
     - BGE-M3 임베딩 호출 (< 5초)
     - 하이브리드 RAG 리뷰 분석 파이프라인 (200 OK)
  3. **B-Team 올원챗 (FastAPI / 8002)**:
     - `/analyze` 엔드포인트 상품별 맞춤 솔루션 생성 (200 OK)
- **테스트 스위트 위치**: `tests/test_multi_chatbot_regression.py`
