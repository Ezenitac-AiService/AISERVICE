# Flask·프론트엔드 서비스 연동 기능 명세

## 상태

- 구현 상태: 종목 검색·최근 조회·전체 목록·상세 이력·v13 보고서·단일 댓글
  분석·질문 블록 챗봇·파이프라인 상태 표시 구현 완료
- 통합 상태: `main@f80fdc2` 반영 완료(PR #4, #10, #15, #16, #17)
- 검증 상태: 2026-08-11 전체 437개 실행, 11 failures, 88 errors,
  RAG 환경 의존 테스트 4개 skip. 구 챗봇 입력 테스트가 현행 `block_key`
  구현과 불일치하며, `test_chat*` 제외 375개는 통과
- 실제 데이터 확인 이력: 10종목 목록, SK하이닉스 580개 이력, v13
  `ready`·`report_pending`·`insufficient_evidence` 응답 확인
- 남은 확인: 운영 브라우저의 최종 시각 배치와 반응형 디자인

## 목적

DB에 저장된 수급 추론, 개인 수급, v13 보고서와 파이프라인 실행 상태를
Flask API로 제공하고 화면에서 같은 계약으로 표시한다. Flask 요청 중 모델
학습·일별 추론·LLM 보고서 생성을 실행하지 않는다.

챗봇의 별도 계약은 [`chatbot-service.md`](chatbot-service.md), 자동화 실행
상태의 생산 계약은 [`service-pipeline-automation.md`](service-pipeline-automation.md)를
따른다.

## 공개 API

```http
GET  /api/stocks
GET  /api/stocks/<stock_code>
GET  /api/stocks/<stock_code>/llm-reports?model_date=YYYY-MM-DD
POST /api/inference/single-comment
POST /api/chat
POST /api/stocks/<stock_code>/chat
GET  /api/pipeline/status
```

- 종목 목록은 등록 종목과 선택된 활성 Positive·Negative 결과의 최신 상태를
  반환한다.
- 상세는 `model_date DESC, daily_document_id DESC` 순 이력과 최신 v13
  보고서 표시 정보를 반환한다.
- 보고서는 같은 종목·날짜의 최신 일별 문서와 최신 v13 행을 선택한다.
- 날짜 누락·형식 오류는 400, 준비되지 않은 보고서는 202, 없는 자원은 404,
  내부 조회 실패는 500으로 구분한다.
- 파이프라인 상태는 이력이 없으면 200과 `not_started`, 있으면 최신 실행의
  공개 필드만 반환한다.
- 공용 챗봇은 `block_key`와 필요한 종목·날짜를 받고, 종목 상세 챗봇은 URL의
  종목코드를 고정한다. 임의 `message`·`action`·`metric`은 받지 않는다.

## 수급 추론 표시 계약

`SentimentIndexDTO`는 다음 공통 값을 가진다.

```text
stock_code, stock_name, model_date, comment_count
actual_supply_demand_index, actual_buy_volume, actual_sell_volume
analysis_status, supply_data_status, supply_observed_at
positive_model, negative_model
```

방향별 결과는 점수·절편·텍스트 점수·기여 키워드와 함께 다음 품질 필드를
전달한다.

```text
inference_status
recognized_feature_count
unique_token_count
vocabulary_coverage
```

활성 artifact는 모델명·버전·방향·토크나이저 identity로 DB에서 조회한다.
특정 환경에서 관측된 ID `7`·`8`을 서비스 계약으로 고정하지 않는다. 기존
DB의 `inference_status IS NULL`은 변경하지 않고 API에서 `unknown`으로 표현한다.
화면은 Positive·Negative 점수를 감성 확률 하나로 합치지 않는다.

## v13 보고서 표시 계약

공개 응답은 다음 사용자용 필드를 중심으로 구성한다.

```text
stock_code, stock_name, model_date
supply_direction, supply_data_status, supply_observed_at
current_supply_data_status, current_supply_observed_at, report_refresh_status
actual_supply_index, comment_signal_score, signal_level, signal_status
signal_change, signal_ma5, comment_count
market_commentary, conclusion, notice
```

- `ready`는 수치·브리핑을 표시한다.
- `insufficient_evidence`는 점수 대신 근거 부족 상태를 표시한다.
- 최신 문서의 보고서가 아직 없으면 `report_pending`으로 표시한다.
- `estimated`와 `confirmed`를 구분하며 확정값을 추정값으로 강등하지 않는다.
- 내부 DB ID, input hash, provider 응답 ID와 토큰 수는 공개하지 않는다.

## 단일 댓글 계약

`POST /api/inference/single-comment`는 `comment_text`를 전처리한 뒤 등록된
Positive·Negative v4 모델을 각각 적용한다.

정상 응답은 `comment_text`, `processed_text`, `token_count`, `positive_model`,
`negative_model`, `notice`를 반환한다. 각 방향 결과에는 `text_score`,
`recognized_feature_count`, 양·음수 기여 키워드가 포함된다.

- 정상은 두 방향 결과와 품질 정보를 함께 반환한다.
- 빈 요청·빈 문자열·분석할 특성이 없는 입력은 400이다.
- 모델 등록 또는 bundle 준비 실패는 500이다.
- 일별 수급 방향·calibration 신호·미래 예측을 만들지 않는다.
- 요청과 결과를 DB에 저장하지 않는다.

## 화면 동작

- 메인: 종목 검색, 최근 조회, 전체 목록, 최상위 파이프라인 상태를 표시한다.
- 상세: 날짜별 수급·품질·v13 브리핑과 단일 댓글 분석을 표시한다.
- 챗봇 위젯: 서버 allowlist 질문 트리, 근거 출처와 답변을 표시한다. 메인은
  종목을 선택하고 상세는 현재 URL 종목을 고정한다.
- 파이프라인 상태는 30초마다 polling하며 진행 중·완료·실패를 구분한다.
- 모든 API 필드는 `snake_case`를 사용한다.

## 표시 제한

- `comment_signal_score`는 감성 확률, 미래 수급 또는 주가 예측값이 아니다.
- 실제 수급 방향은 `supply_direction`이 결정한다.
- 근거 부족 값을 `0`이나 `50`으로 임의 대체하지 않는다.
- `recognized_feature_count`를 댓글 수로 표시하지 않는다.
- `notice`로 투자 권고가 아니라는 점을 고지한다.

## 실패와 재실행

웹 조회는 DB를 변경하지 않는다. API별 예외는 JSON 오류 응답으로 변환하고,
화면은 HTTP 성공 여부만이 아니라 응답의 업무 상태를 표시한다. 파이프라인
상태 조회 실패가 다른 종목 조회를 실행시키거나 자동화 실행을 재시작하지 않는다.

## 제외 범위

- HTTP 요청 중 모델 학습·일별 배치 추론·LLM 보고서 생성
- 인증·권한·CORS와 운영 배포 인프라
- 투자 주문과 미래 주가·수급 예측
- 최종 디자인 브랜치의 색상·타이포그래피 조정

## 관련 코드와 정본

- [`pilos/web/app.py`](../pilos/web/app.py)
- [`pilos/web/static/js`](../pilos/web/static/js)
- [`pilos/service`](../pilos/service)
- [`pilos/storage`](../pilos/storage)
- [`docs/DATA_CONTRACT.md`](../docs/DATA_CONTRACT.md)
- [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md)
- [`docs/DECISIONS.md`](../docs/DECISIONS.md)
