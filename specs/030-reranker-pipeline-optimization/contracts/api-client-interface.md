# API Client & Component Interface Contracts

## 1. `AiGatewayClient` (공통 AI 게이트웨이 클라이언트)

`oliview_core/client.py`에서 제공하며 Chatbot A(Streamlit)와 Chatbot B(FastAPI)가 공통으로 사용하는 인터페이스.

```python
class AiGatewayClient:
    async def embed(self, texts: list[str], trace_id: str = "") -> list[list[float]]:
        """
        BGE-M3 (Port 8090) 임베딩 벡터 생성.
        - L2 Redis 캐시 (emb:bge-m3:{hash}) 우선 조회 (0.5ms)
        - Cache miss 시 8090 호출 후 Redis 7일 캐시 저장
        """
        ...

    async def rerank(
        self, 
        query: str, 
        docs: list[str], 
        timeout: float = 5.0, 
        trace_id: str = ""
    ) -> list[float] | None:
        """
        BGE-Reranker-v2-M3 (Port 8091) 통합 단일 배치 리랭킹 점수 계산.
        - L3 Redis 캐시 (rerank:{q_hash}:{docs_hash}) 우선 조회 (0.8ms)
        - 5.0초 단일 타임아웃 적용 (초과 시 None 반환하여 안전 폴백)
        - 로컬 CPU cross_encoder 폴백 제거 (0ms 1차 유사도 순위 유지)
        """
        ...

    async def generate_stream(
        self, 
        messages: list[dict], 
        max_tokens: int = 4096, 
        trace_id: str = ""
    ) -> AsyncGenerator[str, None]:
        """
        Qwen 3.5 2B (Port 8081/8089) 16K 컨텍스트 실시간 토큰 스트리밍.
        - GPU Concurrency Semaphore(3) 적용
        - FlashAttention 가속 & Tier 4 카나리아 토큰 실시간 스트림 감사
        """
        ...
```

---

## 2. `MultiTargetGraphOrchestrator` (LangGraph 오케스트레이터)

`oliview_core/graph_orchestrator.py`에서 제공하는 상태 머신 엔진.

```python
class MultiTargetGraphOrchestrator:
    async def astream_rag(
        self,
        query: str,
        session_id: str,
        user_id: str | None = None,
        trace_id: str | None = None
    ) -> AsyncGenerator[dict, None]:
        """
        LangGraph StateGraph 실행 및 계층형 SSE 이벤트 스트리밍.
        - Events emitted:
          1. event: step_update (INTENT -> SEARCH -> RERANK -> SYNTHESIS)
          2. event: token (생성 토큰 스트림)
          3. event: complete (최종 메트릭 및 인용 리뷰 목록)
          4. event: fallback_alert (리랭커 타임아웃 시 ⚡ 신속 모드 알림)
        """
        ...
```

---

## 3. `StreamlitGraphAdapter` (Streamlit 동기 제너레이터 래퍼)

`bteam/Oliview_chatbot_a/graph_adapter.py`에서 제공.

```python
class StreamlitGraphAdapter:
    @staticmethod
    def run_sync_stream(
        orchestrator: MultiTargetGraphOrchestrator,
        query: str,
        session_id: str,
        status_box: any,
        substep_container: any
    ) -> Generator[str, None, None]:
        """
        LangGraph의 비동기 astream_rag를 Streamlit 메인 스레드에 안전하게 동기 래핑.
        - status_box 및 substep_container를 실시간 write() 갱신
        - st.write_stream()으로 전달할 토큰 제너레이터 반환
        """
        ...
```
