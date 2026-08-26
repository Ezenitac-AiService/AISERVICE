# Flask 마무리 작업 지시사항

> 현재 상태: `적용 완료`. 이 지시 범위와 후속 프론트 연결은 PR #10·#15를
> 통해 `develop@c387300`에 반영됐습니다. 현재 공개 계약은
> [`../../../specs/sentiment-flask-web-integration.md`](../../../specs/sentiment-flask-web-integration.md)를
> 사용하며, 아래 내용은 구현 과정의 확정 지시 이력입니다.

> 담당자: 미정
>
> 범위: 종목 목록·상세 조회, 저장된 LLM 보고서 API, 단일 댓글 추론 API

이 문서는 `develop`의 현재 Flask 구현을 앞 단계에서 확정한 모델·품질·수급·보고서
계약과 맞추기 위한 작업을 정리한다. 담당자가 정해질 때까지 개인 이름 문서에 포함하지
않는다. 프론트 JavaScript와 Chroma·챗봇 구현은 이 문서의 담당 범위가 아니다.

## 1. 현재 구현 요약

현재 Flask에는 다음 API가 구현돼 있다.

```http
GET /api/stocks
GET /api/stocks/<stock_code>
GET /api/stocks/<stock_code>/llm-reports?model_date=YYYY-MM-DD
POST /api/inference/single-comment
```

호출 책임은 대체로 다음 경계를 따른다.

```text
HTTP 요청
→ web/app.py route
→ service 사용 사례
→ storage DB 조회 또는 analysis 계산
→ DTO
→ jsonify 응답
```

Flask route가 SQL, 일별 모델 추론이나 LLM 호출을 직접 수행하지 않는 구조는 유지한다.

## 2. 유지할 계약

- Flask는 모델을 학습하거나 일별 문서를 추론하지 않는다.
- 저장된 Positive·Negative 결과를 하나의 감성 확률로 합치지 않는다.
- Flask는 calibration, 수급 방향, 신호 등급과 품질 임계값을 다시 계산하지 않는다.
- 생산자가 DB에 저장한 `inference_status`와 보고서 JSON을 조회·전달한다.
- 저장 JSON의 필수값 누락을 `0`, `50` 또는 빈 문자열로 채우지 않는다.
- 내부 DB ID, 입력 해시, provider 응답 ID와 토큰 사용량은 일반 화면 API에 노출하지 않는다.
- 단일 댓글 결과에 일별 `comment_signal_score`를 적용하지 않는다.
- 단일 댓글 입력과 분석 결과는 DB에 저장하지 않는다.

## 3. 공통 활성 모델 조회

현재 종목 조회 service는 다음 ID를 코드에 고정한다.

```text
Positive artifact_id = 7
Negative artifact_id = 8
```

이 값은 특정 DB의 실행 이력이지 다른 환경에서도 유지되는 계약이 아니다. 단일 댓글
service도 모델명과 모델 버전을 별도로 선언한다.

다음처럼 수정한다.

```text
공통 활성 서비스 모델 설정 조회
→ model_name, model_version, artifact_schema_version 확인
→ DB에서 정확한 Positive·Negative artifact 조회
→ 두 artifact와 로컬 bundle·tokenizer_version 호환성 검증
→ 목록·상세·단일 댓글·보고서 조회가 같은 활성 설정 사용
```

- 학습 실행기의 상수를 Flask가 가져오지 않는다.
- artifact ID를 환경변수에 새 고정값으로 옮기는 것만으로 해결하지 않는다.
- 한 방향이 누락되거나 두 방향의 모델·토큰 버전이 다르면 부분 정상으로 숨기지 않는다.

## 4. 종목 목록·상세 조회

### 현재 문제

- 목록은 고정 artifact 두 결과가 모두 존재하는 문서 중 최신 행을 선택한다.
- 더 최신 일별문서가 아직 미추론이면 이전 결과를 현재 최신처럼 보여줄 수 있다.
- 상세는 같은 거래일의 여러 일별 스냅샷을 모두 반환한다.
- 10분 주기 스냅샷이 쌓이면 화면 이력에 같은 날짜가 반복될 수 있다.
- 수급의 `data_status`, `observed_at`과 추론 `inference_status`를 반환하지 않는다.
- API JSON이 camelCase와 snake_case를 혼용한다.

### 수정 계약

- 종목·날짜별 가장 큰 `daily_document_id`를 현재 문서로 본다.
- 최신 문서가 미추론이면 과거 결과를 조용히 최신값으로 대체하지 않는다.
- 목록과 상세에 `ready`, `inference_pending`, `insufficient_features` 상태를 전달한다.
- 날짜 이력은 기본적으로 종목·날짜별 최신 스냅샷 하나만 반환한다.
- 스냅샷 전체를 제공해야 한다면 날짜뿐 아니라 `daily_document_id`와 관측 의미를 명시한다.
- `supply_data_status`, `supply_observed_at`을 응답에 포함한다.
- Positive·Negative 각각의 `inference_status`, feature 수와 coverage를 전달한다.
- JSON 필드 표기 방식은 기존 프론트 영향 확인 후 한 방식으로 고정한다.

목록에서 모든 등록 종목을 반환할지, 현재 분석 가능한 종목만 반환할지도 동일한 API
계약으로 고정한다. 현재 목록은 `LEFT JOIN`으로 등록 종목을 포함하지만 상세는 추론 결과가
없으면 404를 반환하므로 두 API의 의미가 다르다.

## 5. 저장된 LLM 보고서 조회

현재 흐름은 다음과 같다.

```text
종목·날짜의 가장 큰 daily_document_id 조회
→ 해당 문서의 최신 llm_report 조회
→ 보고서가 없으면 양방향 추론 존재 여부 확인
→ LLMReportDTO
→ v13 표시 JSON
```

### 현재 문제

- 보고서를 활성 모델·prompt·보고서 스키마 기준 없이 단순 최신 행으로 조회한다.
- 보고서가 없을 때 양방향 추론 존재 여부도 모델 버전 없이 검사한다.
- 과거 모델의 두 방향 결과만 있어도 현재 추론 완료로 오인할 수 있다.
- 추론 완료 후 보고서 생성 대기·일시 실패와 실제 보고서 부재가 모두 404가 될 수 있다.
- `supply_data_status`, `supply_observed_at`, `commentary_source`를 반환하지 않는다.
- estimated 보고서가 confirmed 기준으로 갱신 대기 중인지 표현할 수 없다.

### 수정 계약

- 공통 활성 모델과 현재 prompt·report·evidence schema에 맞는 보고서만 서비스한다.
- 현재 최신 일별문서와 정확한 Positive·Negative artifact 결과를 기준으로 준비 상태를
  판단한다.
- `supply_data_status`, `supply_observed_at`, `commentary_source`와 보고서 상태를
  표시 응답에 포함한다.
- estimated 보고서는 추정 기반임을 표시한다.
- confirmed 전환 후 보고서 갱신이 실패하면 기존 estimated 보고서의 상태를 숨기지 않는다.
- Flask가 저장 보고서의 신호나 자연어를 재계산하지 않는다.

## 6. HTTP 상태 계약

최소 다음 상태를 구분한다.

| 조건 | HTTP | 응답 상태 |
|---|---:|---|
| 요청 JSON·날짜·필드 형식 오류 | 400 | `invalid_request` |
| 종목·날짜의 일별문서 없음 | 404 | `not_found` |
| 최신 문서의 활성 모델 추론 미완료 | 202 | `inference_pending` |
| 추론 완료, 보고서 생성 대기·일시 실패 | 202 | `report_pending` |
| 현재 서비스용 보고서 존재 | 200 | 보고서의 실제 상태 |
| DB·저장 JSON·내부 계약 오류 | 500 | `internal_error` |

`not_ready` 하나에 여러 원인을 합치거나, 생성 대기를 데이터 부재 404로 반환하지 않는다.
정확한 오류 메시지는 프론트가 문자열을 분석하지 않고 `status` 값으로 분기할 수 있게 한다.

## 7. 단일 댓글 추론 API

현재 route는 JSON `comment_text`를 받고 Positive·Negative 모델의 단어 기여도를 함께
반환한다. 빈 입력·분석할 특성이 없는 입력은 400, 모델 준비와 내부 실행 실패는 500으로
구분한다. 이 기본 흐름은 유지한다.

### 필수 수정

- 배치 토큰화와 같은 품사, include POS, 불용어와 사용자 사전 설정을 명시적으로 사용한다.
- 모델 bundle의 `tokenizer_version`과 현재 단일 댓글 토큰 설정을 검증한다.
- 공통 활성 모델 설정을 사용하고 service의 모델명·버전 중복 선언을 제거한다.
- 매 요청마다 Positive·Negative bundle과 Kiwi를 다시 준비하지 않도록 안전한 지연 로드
  또는 애플리케이션 단위 캐시를 검토한다.
- 활성 모델 버전이 바뀌면 오래된 캐시를 계속 사용하지 않도록 cache identity를 둔다.
- 인식 feature가 없는 경우를 사용자 입력 400과 내부 모델 오류 500 중 현재 계약대로
  일관되게 유지한다.

단일 댓글 응답은 `text_score`, 인식 feature 수와 방향별 기여 단어만 제공한다. 모델
절편을 더한 일별 수급 연관 점수, 실제 수급 방향, calibration과 0~100 신호는 만들지 않는다.

## 8. 계층과 파일 책임

```text
web/app.py
→ HTTP 입력 파싱, 상태 코드와 jsonify

service
→ 활성 설정을 사용한 조회·분석 사용 사례 조합

storage
→ SQL, DB 행 파싱, 저장 오류 변환

analysis
→ 단일 댓글 계산과 생산자가 정의한 순수 변환

dto
→ 계층 사이 전달 구조와 상태 필드
```

- route에 SQL이나 모델 로더를 추가하지 않는다.
- storage가 수급 방향·품질 임계값을 새로 판단하지 않는다.
- service가 HTTP 응답 객체에 의존하지 않는다.
- 단순 이름 정리만을 위한 대규모 폴더 이동은 챗봇·프론트 병합 전 수행하지 않는다.

## 9. 다른 담당자와의 경계

### 이주광 영역에서 받아야 할 값

```text
활성 모델명·버전·artifact 스키마·tokenizer_version
방향별 inference_status·recognized_feature_count·vocabulary_coverage
supply_data_status·supply_observed_at
보고서 상태·commentary_source·현재 prompt·schema 버전
```

### 프론트 담당자에게 제공할 값

- 확정된 API 경로와 요청 파라미터
- 정상 응답 JSON 필드와 nullable 규칙
- HTTP 상태와 `status` 열거값
- estimated·confirmed 표시 의미
- 품질 부족과 준비 중 상태의 화면 처리 기준

### 임준화 영역과의 경계

- Flask는 Chroma에 직접 적재하지 않는다.
- 챗봇이 필요한 보고서 조회 API가 있다면 일반 화면 API와 목적을 구분한다.
- Chroma·RAG 내부 metadata와 검색 필터는 `임준화.md`에서 관리한다.

## 10. 완료 기준

1. 목록·상세·보고서·단일 댓글이 같은 활성 모델 설정을 사용한다.
2. artifact ID `7`·`8` 고정이 제거된다.
3. 종목·날짜별 최신 스냅샷과 미추론 상태가 구분된다.
4. 같은 날짜의 과거 스냅샷이 날짜 이력에 중복 노출되지 않는다.
5. 품질 상태, 수급 상태·관측 시각과 보고서 출처가 API까지 전달된다.
6. 보고서 준비 중·부재·내부 실패의 HTTP 상태가 구분된다.
7. 단일 댓글과 배치 토큰화가 같은 토큰 계약을 사용한다.
8. 단일 댓글 반복 요청에서 모델·Kiwi 로딩 정책이 명확하다.
9. Flask route가 모델 계산·LLM 호출·Chroma 적재를 직접 수행하지 않는다.
10. 현재 환경에서 수행하지 못한 DB·브라우저 검증을 완료로 표현하지 않는다.

## 11. 검증 계획

현재 로컬에서는 DB와 외부 API를 사용할 수 없으므로 이번 복기에서는 코드와 문서 계약만
확인한다. 구현 후 다음을 구분해 검증한다.

- 비DB: DTO 변환, HTTP 입력·오류 상태, 단일 댓글 token 계약
- 학원 DB: 활성 artifact 조회, 최신 스냅샷, estimated·confirmed, 보고서 상태 조회
- 브라우저: 프론트 브랜치 병합 후 실제 JSON 소비와 화면 상태
- 실행하지 못한 검증: 환경과 사유를 완료 보고에 별도 기록

## 12. 근거 파일

- [`pilos/web/app.py`](../../../pilos/web/app.py)
- [`pilos/service/sentiment_index_service.py`](../../../pilos/service/sentiment_index_service.py)
- [`pilos/service/llm_report_service.py`](../../../pilos/service/llm_report_service.py)
- [`pilos/service/single_comment_service.py`](../../../pilos/service/single_comment_service.py)
- [`pilos/storage/sentiment_index_storage.py`](../../../pilos/storage/sentiment_index_storage.py)
- [`pilos/storage/llm_report_storage.py`](../../../pilos/storage/llm_report_storage.py)
- [`pilos/dto/sentiment_index_dto.py`](../../../pilos/dto/sentiment_index_dto.py)
- [`pilos/dto/llm_report_dto.py`](../../../pilos/dto/llm_report_dto.py)
- [`pilos/dto/single_comment_inference_dto.py`](../../../pilos/dto/single_comment_inference_dto.py)
- [`specs/sentiment-flask-web-integration.md`](../../../specs/sentiment-flask-web-integration.md)
- [`docs/DATA_CONTRACT.md`](../../DATA_CONTRACT.md)
- [`docs/ARCHITECTURE.md`](../../ARCHITECTURE.md)
