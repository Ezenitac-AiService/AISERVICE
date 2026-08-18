# Feature Specification: 올리챗·올원챗 임베딩 타임아웃 해소, 순차 대기 큐 및 3대 챗봇 통합 회귀 검증 (009-fix-ollychat-embedding-timeout)

**Feature Branch**: `009-fix-ollychat-embedding-timeout`  
**Created**: 2026-08-18  
**Status**: Draft  
**Input**: User description: "pilos 챗봇 수정시 다른 챗봇 기능이 망가지면 안된다고 했지? 차앤박 프로폴리스 앰플 수분감을 분석해줘 -> Model Gateway 임베딩 서버(http://vllm-serv-gateway:8090/v1/embeddings) 호출 실패: Read timed out. 올리챗에 타임아웃이야. 올원챗도 마찬가지임. 작업 마지막에, 회귀 테스트를 넣어. 하드웨어 성능상, 3개의 챗봇이 독립 공존을 하지 못한다면, 차라리 'llm 서버가 다른 질문을 처리중입니다. 순서를 기다리고 있습니다.'라고 표시하고 순차적으로 처리하던지"

---

## Clarifications

### Session 2026-08-18

- **Q: 올원챗(FastAPI / 8002)의 RAG API 500 에러도 동일한 Model Gateway 임베딩 서버(8090) 파이프 블로킹이 원인인가?**  
  → **A: 예**, 올원챗(`bteam/chatb/`)의 RAG API 또한 동일한 Model Gateway 포트 8090(`bge-m3`) 임베딩 타임아웃으로 인해 HTTP 500 서버 장애를 일으키므로 올리챗과 함께 최우선 해결 대상에 포함한다.
- **Q: 단일 GPU(GTX 1070 8GB) 하드웨어 환경에서 3개 챗봇의 동시 LLM 요청 경합 시 어떻게 처리할 것인가?**  
  → **A: 순차 대기 큐(Sequential Queue) 및 스트리밍 킵얼라이브 안내 (Option A)**: 3개 챗봇이 동시에 무거운 LLM 생성을 요청할 경우 연결을 끊거나 타임아웃을 내지 않고, 큐 진입 즉시 `"LLM 서버가 다른 질문을 처리 중입니다. 순서를 기다리고 있습니다..."` 상태 이벤트를 수신하여 화면에 표시하고 소켓 유휴 타임아웃을 차단하며, 차례 도달 시 자연스럽게 답변 스트리밍으로 전환하여 순차 완결한다.
- **Q: 구현 작업의 최종 검증 단계에 어떤 테스트를 배치할 것인가?**  
  → **A: 3대 챗봇(PILOS, 올리챗, 올원챗) 통합 E2E 회귀 테스트**를 구현 마지막 단계에 필수로 추가하여 3개 챗봇의 모든 질의·검색·응답이 상호 간섭 없이 100% 정상 작동함을 자동 검증한다.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 올리챗(Streamlit) 리뷰 분석 질의 시 임베딩 RAG 검색 정상 완료 (Priority: P1) 🎯 MVP

사용자가 올리챗(Oliview Chatbot A, Streamlit)에서 상품 리뷰 분석 질문(예: "차앤박 프로폴리스 앰플 수분감을 분석해줘")을 입력했을 때, Model Gateway 임베딩 서버(포트 8090)가 파이프 버퍼 블로킹 없이 즉각 임베딩 벡터를 반환하여 60초 타임아웃 오류 없이 리뷰 근거 기반의 정확한 답변을 정상 수신한다.

**Why this priority**:
올리챗의 핵심 기능인 하이브리드 RAG 검색(ChromaDB 벡터 검색 + BM25 + 리랭킹)이 임베딩 서버 블로킹으로 완전히 중단(RuntimeError 500)되어 서비스 불능 상태이므로 최우선 해결되어야 한다.

**Independent Test**:
- 올리챗 UI 및 백엔드 파이프라인에서 "차앤박 프로폴리스 앰플 수분감을 분석해줘" 질의 시, `vllm-serv-gateway:8090/v1/embeddings` 호출이 타임아웃 없이 수 초 내에 완료되고 리뷰 분석 답변이 정상 출력되는지 검증.

**Acceptance Scenarios**:
1. **Given** 올리챗이 실행 중인 상태에서, **When** 사용자가 "차앤박 프로폴리스 앰플 수분감을 분석해줘"를 질문하면, **Then** 임베딩 서버(8090)가 5초 이내에 정상 응답하고 올리챗이 수분감 관련 리뷰 요약 답변을 렌더링한다.
2. **Given** Model Gateway 컨테이너가 장시간 기동 중인 상태에서, **When** 다수의 임베딩 요청이 발생하더라도, **Then** 서브프로세스 표준 출력(stdout/stderr) 파이프가 가득 차서 블로킹(`anon_pipe_write` 대기)되지 않고 지속적으로 정상 서빙한다.

---

### User Story 2 - 올원챗(FastAPI) RAG API 엔드포인트 500 통신 장애 해소 (Priority: P1)

사용자가 올원챗(Oliview Chatbot B, FastAPI 포트 8002) 웹 UI에서 상품 리뷰 분석을 요청했을 때, "RAG API 통신 장애: HTTP 통신 실패 서버 오류 (상태코드: 500)"가 발생하지 않고 임베딩 및 생성 답변이 정상 수신된다.

**Why this priority**:
올원챗 역시 동일한 8090 포트 임베딩 게이트웨이에 의존하므로, 백엔드 API 정상화를 통해 웹 UI 솔루션 카드가 정상 노출되어야 한다.

**Independent Test**:
- 올원챗 API(`/bteam/chatb/` 또는 `http://localhost:8002/analyze`)로 "차앤박 프로폴리스 앰플 수분감을 분석해줘" 요청 전송 시 HTTP 200 응답과 상품별 감성 솔루션이 정상 반환되는지 확인.

**Acceptance Scenarios**:
1. **Given** 올원챗 웹 UI에서, **When** "차앤박 프로폴리스 앰플 수분감을 분석해줘"를 검색하면, **Then** 500 에러 카드 대신 "AI 전문 뷰티 가이드의 맞춤 솔루션"과 추천 상품 3종 카드가 정상 표시된다.

---

### User Story 3 - 동시 LLM 요청 시 스트리밍 킵얼라이브 순차 대기 큐 및 안내 (Priority: P1)

단일 로컬 GPU에서 2개 이상의 챗봇이 동시에 무거운 LLM 생성을 요청할 경우, Model Gateway가 요청을 충돌/드롭하지 않고 안전한 순차 큐(FIFO / Concurrency Lock)로 대기시키며, 클라이언트 UI에 "LLM 서버가 다른 질문을 처리 중입니다. 순서를 기다리고 있습니다..." 상태 이벤트를 즉각 방출(Keep-Alive)한 후 차례 도달 시 매끄럽게 답변 스트리밍으로 전환하여 완료한다.

**Why this priority**:
하드웨어 한계(8GB VRAM 단일 GPU) 내에서 3대 챗봇이 메모리 부족(OOM)이나 소켓 타임아웃 없이 안전하고 질서 있게 공존하기 위한 핵심 메커니즘이다.

**Independent Test**:
- PILOS 챗봇과 올리챗에서 동시에 긴 답변 생성을 요청했을 때, 두 요청 모두 실패하지 않고 큐에 진입한 요청이 "순서를 기다리고 있습니다" 상태를 띄운 뒤 앞선 작업 종료 즉시 정상 완료되는지 확인.

**Acceptance Scenarios**:
1. **Given** Model Gateway에서 이전 질의 추론이 진행 중일 때, **When** 다른 챗봇에서 새로운 질의를 요청하면, **Then** 요청이 거절되지 않고 큐에 진입하여 스트리밍 킵얼라이브 상태("순서를 기다리고 있습니다...")를 표시한 뒤 이전 작업 종료 즉시 순차 처리된다.

---

### User Story 4 - Model Gateway 보조 프로세스(임베딩·리랭커) I/O 데드락 원천 차단 (Priority: P1)

Model Gateway(`vllm-serv-gateway`) 내부에서 실행되는 보조 서브프로세스(포트 8090 `bge-m3` 임베딩, 포트 8091 `bge-reranker-v2-m3` 리랭커)의 표준 입출력 파이프라인이 OS 파이프 버퍼 한계(64KB)로 인해 블로킹되지 않도록 파일 디스크립터 직접 리다이렉션 또는 비차단 로깅 구조로 개선한다.

**Why this priority**:
임베딩/리랭커 서브프로세스가 I/O 버퍼 고갈로 인해 Linux 커널 레벨에서 `anon_pipe_write` 영구 대기(Deadlock)에 빠지는 근본 원인을 제거해야 챗봇 전체의 안정성이 보장된다.

**Independent Test**:
- `http://vllm-serv-gateway:8090/v1/embeddings` 및 `http://vllm-serv-gateway:8091/v1/rerank`에 연속 50회 이상의 임베딩/리랭킹 요청을 전송하여 단 한 번의 타임아웃 없이 모두 200 OK를 반환하는지 검증.

**Acceptance Scenarios**:
1. **Given** Model Gateway가 부팅된 상태에서, **When** 임베딩(8090) 및 리랭커(8091) 프로세스 상태를 조회하면, **Then** 프로세스가 `anon_pipe_write` 대기 없이 `do_epoll_wait` 활성 수신 대기 상태를 유지한다.
2. **Given** 서브프로세스가 장시간 로그를 대량 출력하더라도, **When** 메모리 및 파이프 상태를 모니터링하면, **Then** 로그 파일로 안전하게 기록되고 버퍼 포화로 인한 프로세스 프리징이 발생하지 않는다.

---

### User Story 5 - 3대 챗봇(PILOS, 올리챗, 올원챗) 통합 E2E 회귀 테스트 구축 및 전원 합격 (Priority: P1)

작업 최종 단계에 3대 챗봇(A-Team PILOS, B-Team 올리챗, B-Team 올원챗)의 모든 핵심 유즈케이스를 순차/동시 검증하는 통합 자동화 회귀 테스트를 구축하고 100% 통과를 확인한다.

**Why this priority**:
어느 한 챗봇의 수정이 다른 챗봇에 부정적 영향을 미치지 않았음을 최종적으로 보증하는 품질 게이트이다.

**Independent Test**:
- 통합 회귀 테스트 스크립트 실행 시 PILOS, 올리챗, 올원챗 3개 챗봇의 API 및 핵심 응답이 모두 HTTP 200과 유효한 답변을 반환하는지 자동 검증.

**Acceptance Scenarios**:
1. **Given** 전체 서비스가 기동 중일 때, **When** 3대 챗봇 통합 회귀 테스트 스위트를 실행하면, **Then** PILOS(캐시 10ms + 스트리밍), 올리챗(Chroma RAG), 올원챗(FastAPI 솔루션) 모두 에러 0건으로 전원 통과한다.

---

## Edge Cases

- **대용량 텍스트 임베딩 요청**: 500자 이상의 긴 리뷰나 여러 문장이 포함된 배치 임베딩 요청 시 컨텍스트 초과 오류 없이 안정적으로 청크 처리되어야 함.
- **클라이언트 타임아웃 임계치**: 올리챗 클라이언트(`embedding_client.py`) 및 올원챗 클라이언트의 기본 타임아웃을 120초로 현실화하여 일시적 큐잉 대기를 안전하게 수용함.
- **비정상 서브프로세스 감지 시 자동 복구**: 임베딩/리랭커 프로세스에 이상이 발생할 경우 `AuxiliaryModelManager`의 헬스체크가 감지하여 자동으로 서브프로세스를 재기동함.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Model Gateway(`vllm-serv-gateway`)의 `ProcessManager`는 보조 서브프로세스(포트 8090 임베딩, 포트 8091 리랭커) 구동 시 표준 출력/에러 파이프 버퍼 포화로 인한 커널 레벨 블로킹(`anon_pipe_write`)이 발생하지 않도록 I/O 스트림을 안전하게 파일로 직접 리다이렉션해야 한다 (MUST).
- **FR-002**: `vllm-serv-gateway:8090/v1/embeddings` 엔드포인트는 올리챗 및 올원챗의 임베딩 요청에 대해 5초 이내(최대 10초 이내)에 정확한 임베딩 벡터를 반환해야 한다 (MUST).
- **FR-003**: 올리챗(`bteam/Oliview_chatbot_a/common/embedding_client.py`) 및 올원챗(`bteam/Oliview_chatbot_b/`)은 임베딩 타임아웃을 120초로 현실화하여 일시적 GPU/CPU 부하 시 조기 단절을 방지해야 한다 (SHOULD).
- **FR-004**: 올리챗의 05.chatbot RAG 파이프라인("차앤박 프로폴리스 앰플 수분감을 분석해줘") 실행 시 ChromaDB 벡터 검색, BM25, Cross-Encoder 리랭킹이 순차적으로 정상 완료되어 최종 리뷰 요약 답변을 제공해야 한다 (MUST).
- **FR-005**: 올원챗의 RAG API(`http://localhost:8002/analyze`)는 HTTP 500 통신 장애 없이 추천 리뷰 카드와 뷰티 가이드 솔루션을 정상 반환해야 한다 (MUST).
- **FR-006**: GPU 추론 동시 요청 발생 시 Model Gateway 및 클라이언트는 스트리밍 킵얼라이브 패킷(`"LLM 서버가 다른 질문을 처리 중입니다. 순서를 기다리고 있습니다..."`)을 방출하여 유휴 소켓 타임아웃을 방지하고 순차 대기 큐로 완료해야 한다 (MUST).
- **FR-007**: 작업 완료 단계에 3대 챗봇(A-Team PILOS, B-Team 올리챗, B-Team 올원챗)의 무결성과 비간섭을 검증하는 통합 자동화 회귀 테스트를 구축하고 100% 통과해야 한다 (MUST).

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 올리챗 및 올원챗에서 "차앤박 프로폴리스 앰플 수분감을 분석해줘" 질의 시 타임아웃(Read timed out) 및 500 통신 장애 발생률 0% 달성.
- **SC-002**: Model Gateway 임베딩 서버(`vllm-serv-gateway:8090`)의 단일 쿼리 임베딩 처리 시간 5초 이내 달성.
- **SC-003**: 연속 50회 임베딩 요청 시 I/O 데드락(`anon_pipe_write`) 발생 0건 및 100% 정상 응답.
- **SC-004**: 동시 다중 질의 요청 시 OOM/소켓 타임아웃 없이 100% 순차 대기 완결 처리.
- **SC-005**: 3대 챗봇(PILOS, 올리챗, 올원챗) 통합 회귀 테스트 스위트 100% PASS.

---

## Assumptions

- 로컬 NVIDIA GTX 1070 (8GB VRAM) 환경에서 메인 생성 모델(Qwen 4B)은 GPU에 상주하며, 보조 모델(BGE-M3 임베딩, BGE-Reranker 리랭커)은 CPU 멀티스레드로 구동된다.
- 임베딩 서버는 `bge-m3-q8_0.gguf` 모델을 사용하여 1024차원 고밀도 벡터를 산출한다.
- 올리챗 및 올원챗의 ChromaDB 및 DB 인덱스는 기 구축된 데이터를 재사용한다.
