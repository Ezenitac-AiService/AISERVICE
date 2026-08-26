# 근거 기반 챗봇 서비스 기능 명세

## 상태

- 구현 상태: 서버 allowlist 질문 블록, MySQL 확정 지표 조회, 저장 v13 보고서
  조회, 서비스 지식 RAG와 공용·종목 상세 질문 UI 구현 완료
- 통합 상태: `main@f80fdc2` 반영 완료(PR #12, #15, #16, #17)
- 검증 상태: 2026-08-11 전체 437개 실행 결과 11 failures, 88 errors,
  RAG E2E 4개 skip. 구 `message/action/metric` 챗봇 테스트가 현행
  `block_key` 계약을 기대하지 않아 전체 suite는 실패 상태다. `test_chat*`
  파일을 제외한 375개는 통과했고, 현행 block API test-client smoke 6개는 통과했다
- 계약 상태: D-021과 `docs/DATA_CONTRACT.md`는 화면이 `action`·`metric`을
  전달하도록 정했으나 현재 공개 코드는 `block_key`만 받는다. 이 명세는 실제
  동작을 기록하며, 정본 계약을 대체하지 않는다

## 목적

PILOS가 보유한 confirmed 수급·저장된 v13 보고서·승인 서비스 설명 문서 안에서만
사용자가 선택한 질문에 답한다. 현재 UI는 범용 자유입력 챗봇이 아니라 서버가
관리하는 질문 트리다. 미래 전망, 투자 추천과 임의 명령 실행은 제공하지 않는다.

## 공개 API

공용 화면은 다음 endpoint를 사용한다.

```http
POST /api/chat
Content-Type: application/json

{"block_key":"stock_supply_index","stock_code":"000660","model_date":"2026-08-05"}
```

종목 상세 화면은 URL의 종목코드를 고정한다.

```http
POST /api/stocks/000660/chat
Content-Type: application/json

{"block_key":"stock_summary","model_date":"2026-08-05"}
```

허용 body 필드는 다음과 같다.

| 필드 | 필수 | 규칙 |
|---|---:|---|
| `block_key` | 필수 | 서버 `CHAT_BLOCK_DEFINITIONS`에 등록된 문자열 |
| `session_id` | 선택 | 문자열. 응답 상관관계용이며 대화 이력을 저장하지 않음 |
| `stock_code` | 조건부 | 공용 endpoint의 종목 블록에서 최대 6자리 숫자 문자열 |
| `model_date` | 조건부 | 종목 블록에서 `YYYY-MM-DD` |

임의 `message`, `action`, `metric`과 그 밖의 필드를 보내면 400
`invalid_request`다. 종목 상세 endpoint에서는 URL의 종목코드가 요청 대상을
결정한다. 종목 블록에서 종목이나 날짜가 빠져도 service의 clarification으로 넘기지
않고 Flask 입력 경계에서 400으로 거절한다.

## 질문 블록과 근거

서버는 `block_key`를 내부 `action`·`metric`·고정 `message`로 변환한다.

| 공개 블록 | 내부 route | 근거 |
|---|---|---|
| `stock_summary` | `stock_analysis` | 저장된 현재 v13 보고서 |
| `stock_supply_index` | `stock_metric` | MySQL confirmed 수급지수 |
| `stock_buy_volume` | `stock_metric` | MySQL confirmed 개인 매수량 |
| `stock_sell_volume` | `stock_metric` | MySQL confirmed 개인 매도량 |
| `service_*`, `column_*` | `service_knowledge` | 승인 서비스 문서 Chroma RAG |

서비스 설명 블록은 개요·연구 대상·두 방향 모델·해석·공개 데이터 항목·주의사항과
각 모델·점수·주요 공개 컬럼 설명으로 제한된다. 정확한 목록과 문구의 서버 정본은
`CHAT_BLOCK_DEFINITIONS`다. `chat.js`의 질문 트리도 같은 block key를 전송한다.

코드에는 자유문장용 `classify_chat_route()`, `general`·`restricted` 응답과 수급
순위 handler가 남아 있다. 그러나 이 기능에 대응하는 공개 block key가 없으므로 현재
UI와 공개 API의 정상 요청으로는 도달할 수 없다. 따라서 제한 질문 차단·일반 대화·
임의 종목 순위를 현재 제공 기능으로 소개하지 않는다.

## 응답·상태·출처

정상 Chat 응답은 다음 필드를 제공한다.

```text
status, answer, route, session_id, stock_code, as_of, sources, warnings
```

공개 상태는 `ready`, `needs_clarification`, `not_ready`, `not_found`,
`unavailable`, `failed` 중 하나다. 현재 공개 블록 경로에서 주로 사용하는 의미는
다음과 같다.

| 상황 | 상태 또는 HTTP |
|---|---|
| 확정 수급·저장 보고서·문서 답변 성공 | `ready`, HTTP 200 |
| confirmed 수급이 아직 없음 | `not_ready`, HTTP 200 |
| 저장 보고서가 없거나 준비되지 않음 | `not_found` 또는 `not_ready`, HTTP 200 |
| RAG·DB 등 의존 경계 사용 불가 | `unavailable`, HTTP 200 |
| JSON·필드·block·종목·날짜 검증 실패 | `invalid_request`, HTTP 400 |
| service의 `RuntimeError`·`ValueError` | HTTP 503 오류 JSON |
| 예상하지 못한 내부 오류 | HTTP 500 오류 JSON |

출처 type은 `mysql_metric`, `llm_report`, `service_document`만 공개한다. 내부
Chroma 경로·chunk ID·거리·검색 점수·프롬프트·DB ID·비밀 설정은 노출하지 않는다.

## RAG 흐름

서비스 지식 블록만 외부 AI client를 사용한다.

```text
승인 완료·문서 버전 일치 chunk 로드
→ Kiwi BM25 top 10
→ embedding vector top 10
→ RRF(k=60) top 10
→ reranker top 5
→ 검색 근거만 포함한 Chat LLM 응답
```

- 기본 영속 경로는 `artifacts/rag_chroma`다.
- 검색 자원은 문서 버전·collection identity별로 프로세스에서 재사용한다.
- 검색 결과가 없으면 LLM을 호출하지 않고 `not_found`를 반환한다.
- embedding·reranker·Chat LLM 실패 단계는 `unavailable`로 구분한다.
- RAG가 없어도 확정 수급과 저장 보고서 경로는 각 DB 준비 상태에 따라 독립적으로
  동작한다.

## 실패와 재실행

챗봇 요청은 DB를 변경하지 않는다. `session_id`를 저장하거나 이전 답변을 다음 요청에
주입하지 않는다. `stock_analysis`는 새 LLM 호출 없이 저장된
`market_commentary`, `conclusion`, `notice`를 결합하며, 누락된 내용을 일반 지식으로
보완하지 않는다.

## 확인이 필요한 충돌

1. D-021과 `docs/DATA_CONTRACT.md`의 `action`·`metric` 공개 계약을 현행
   `block_key` 계약으로 대체할지 결정이 필요하다.
2. 현행 block 계약에 맞게 `test_chat_api.py`, `test_chat_dto.py`,
   `test_chatbot_question_catalog.py`, `test_chatbot_service.py` 등을 갱신해야 전체
   suite의 현재 상태를 검증할 수 있다.
3. 공개 block이 없는 `restricted`·`general`·ranking 코드를 유지할지 제거할지 결정이
   필요하다. 문서 수정만으로 기능 범위를 확장하지 않는다.

## 관련 코드와 정본

- [`pilos/web/app.py`](../pilos/web/app.py)
- [`pilos/web/static/js/chat.js`](../pilos/web/static/js/chat.js)
- [`pilos/dto/chat_dto.py`](../pilos/dto/chat_dto.py)
- [`pilos/service/chatbot_service.py`](../pilos/service/chatbot_service.py)
- [`pilos/service/rag_service.py`](../pilos/service/rag_service.py)
- [`pilos/storage/vector_storage.py`](../pilos/storage/vector_storage.py)
- [`pilos/analysis/rag`](../pilos/analysis/rag)
- [`docs/DATA_CONTRACT.md`](../docs/DATA_CONTRACT.md)
- [`docs/DECISIONS.md`](../docs/DECISIONS.md)
