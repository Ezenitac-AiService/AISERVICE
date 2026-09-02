# Interface Contracts: Oliview RAG 파이프라인 및 백엔드 인터페이스 규약 (Feature 045)

**Feature Branch**: `045-fix-bteam-rag-zero-search`
**Date**: 2026-09-02
**Status**: Completed

## 1. Chatbot A Streamlit / Core Pipeline Interface

- **함수 시그니처**:
  ```python
  def run_pipeline(
      question: str,
      selected_category: Optional[str] = None,
      callback: Optional[StepCallbackProtocol] = None,
      trace_id: Optional[str] = None,
  ) -> Tuple[Iterator[str], RagExecutionMetadata]:
  ```
- **반환 규약**:
  - `Iterator[str]`: 실시간 스트리밍 생성 토큰 시퀀스
  - `RagExecutionMetadata`: 총 소요시간, 검색/리랭킹 지연시간, 선별된 참고 리뷰 목록(`reference_reviews: List[ReferenceReview]`), 모델명, 폴백 사용 여부.

---

## 2. Chatbot B FastAPI Endpoint (`POST /api/v1/search/stream`)

- **요청 Body**:
  ```json
  {
    "question": "여름철 기름기 잡고 모공 커버 잘되는 매트한 파운데이션 추천해줘",
    "category": "메이크업",
    "brand_filter": null,
    "sentiment_filter": null,
    "top_k": 20,
    "rerank_top_n": 3
  }
  ```
- **응답 (SSE Streaming Response)**:
  - `event: step` (`StepEvent` 진행 상태)
  - `event: token` (LLM 생성 텍스트 청크)
  - `event: done` (`RagExecutionMetadata` 및 참고 리뷰 데이터)
