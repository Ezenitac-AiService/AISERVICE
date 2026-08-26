# 수급 연관성 추론·결과 적재 기능 명세

## 상태

- 구현 상태: 활성 artifact 기준 미완료 대상 조회, 방향별 일별 추론,
  품질 상태 계산과 결과 적재 구현 완료
- 검증 상태: 기능별 자동 테스트와 실제 DB 신규 품질값 적재·멱등 대상 0건
  확인. 2026-08-11 전체 suite는 챗봇 계약 drift로 실패했지만 `test_chat*`
  제외 375개는 통과
- 통합 상태: 활성 artifact·품질 저장 운영 계약 `main@f80fdc2` 반영 완료

## 목적

DB에 등록된 정확한 Positive·Negative v4 모델로 같은 일별 문서를 각각
추론하고, 점수와 단어별 기여도를 재현 가능한 아티팩트 ID에 연결해
`sentiment_index_result`에 저장한다.

## 범위

- DB 아티팩트와 로컬 bundle 교차검증
- 수급 데이터가 존재하는 최신 일별 문서 조회
- 학습된 Vectorizer의 `transform`과 Ridge 예측
- 절편·텍스트 점수와 단어별 contribution 계산
- 입력 품질 진단 상태 계산
- 두 방향 결과의 일괄 트랜잭션 적재와 기존 결과 제외
- 대상 0건 성공 요약과 부분 실패 시 저장 금지

단일 댓글 웹 요청, Flask 조회 DTO, 화면 표시, LLM 보고서와 전체 자동화
실행기는 포함하지 않는다.

## 모델 로드 계약

추론기는 모델명 `ridge_supply`, 방향, 모델 버전 4와 bundle 스키마 2로
DB 아티팩트를 조회한다. DB의 `saved_path`는 저장소 내부 상대 경로만
허용한다.

bundle을 공개 로더로 읽은 뒤 다음 값을 DB 행과 비교한다.

```text
artifact_schema_version
model_name
model_variant
model_version
tokenizer_version
dataset_start_date
dataset_end_date
```

하나라도 다르거나 `feature_mode`가 `text_only`가 아니면 추론하지 않는다.
등록 모델 로더는 DB artifact와 bundle의 토큰 버전이 현재 서비스
`kiwi_ver1`과 같은지도 검증한다. Positive·Negative 모델을 먼저 모두
검증한 뒤 미완료 대상을 조회하므로 모델 누락을 대상 0건으로 숨기지 않는다.

## 추론 대상

- `tokenizer_version=kiwi_ver1`인 지정 기간 일별 문서를 조회한다.
- 같은 종목·날짜·토크나이저 버전에서 가장 큰 `daily_document_id`, 즉
  최신 문서만 사용한다.
- 같은 종목·날짜의 `supply_demand`가 존재하는 거래일만 포함한다.
- 현재 조회는 `supply_demand.data_status`를 필터링하지 않으므로 추정 행도
  거래일 eligibility를 만족한다.
- 실제 `supply_demand_index`는 text-only 추론 특성으로 조회하거나
  사용하지 않는다.
- 검증된 활성 Positive·Negative `artifact_id` 중 하나라도 결과가 없는
  최신 문서만 조회한다.

`run_database_inference()`는 시작일·종료일과 키워드 수를 인자로 받는다.
현재 CLI `main()`은 2026-07-25부터 실행 당일 KST까지를 운영 기간으로
사용한다. 최상위 실행기는 필요하면 같은 실행함수에 기간을 직접 전달한다.

## 계산 흐름

```text
Positive·Negative DB 아티팩트·bundle 로드와 호환성 검증
→ 미완료 일별문서 목록 1회 조회
→ Positive DB 아티팩트·bundle 사용
→ vectorizer.transform(tfidf_text)
→ Ridge 예측과 contribution 계산
→ Negative DB 아티팩트·bundle 사용
→ 같은 일별문서 transform·예측·contribution 계산
→ 두 방향 전체 성공
→ 신규 결과 일괄 INSERT
```

문서별 Ridge 예측값은 다음 관계를 검증한다.

```text
supply_demand_association_score
= intercept + text_score + comment_count_contribution
```

v4의 `comment_count_contribution`은 `0.0`이다. `text_score`는 현재
문서에서 0이 아닌 `TF-IDF × Ridge 계수`의 합이다.

키워드는 양수·음수 contribution을 각각 절댓값 방향으로 정렬한 상위
항목이며 `rank`, `word`, `tfidf`, `coefficient`, `contribution`을 가진다.

## 품질 진단

- 인식된 TF-IDF feature 수가 5개 미만이거나 vocabulary coverage가
  0.6 미만이면 `insufficient_features`로 표시한다.
- 그 외는 `ready`다.
- `recognized_feature_count`, `unique_token_count`, `vocabulary_coverage`,
  `inference_status`를 결과 행에 함께 저장한다.
- `insufficient_features`도 점수와 계산 근거를 보존한다. Flask·신호·LLM은
  자체 임계값으로 다시 판정하지 않고 DB `inference_status`를 사용한다.

## 저장과 재실행

- Positive와 Negative 추론이 모두 성공한 뒤 결과 전체를 한 번만 저장
  함수에 전달한다.
- 신규 결과는 한 트랜잭션으로 INSERT하며 하나라도 실패하면 전체 신규
  INSERT를 롤백한다.
- `(daily_document_id, artifact_id)`가 이미 존재하면 UPDATE나 Upsert하지
  않고 기존 결과로 분류한다.
- 반환값은 방향별 추론 결과와 `input_count`, `inserted_count`,
  `existing_count` 저장 요약이다.

## 실패 전달

- 모델 조회·경로 검증·bundle 로드·메타데이터 비교 오류를 호출자에게
  전달한다.
- 한 방향의 추론이 실패하면 다른 결과를 DB에 저장하지 않는다.
- 결과 저장 실패도 호출자에게 전달한다.
- 지정 기간에 추론 대상 일별 문서가 없으면 성공 0건·실패 0건으로 정상
  종료하며 Vectorizer 추론과 저장을 호출하지 않는다.

운영 최상위 실행기는 모델·추론·저장 예외를 받거나 앞 단계 일별 문서
실패 수가 0보다 큰 경우 후속 LLM 보고서 생성을 시작하지 않는다.

## 검증

비DB `unittest`에서 다음을 확인했다.

- 저장된 설정으로 fit된 Vectorizer의 `transform` 사용
- 유한한 Ridge 예측값 생성
- 양·음수 결과 전체를 저장 함수에 한 번만 전달
- 한 방향 실패 시 저장 함수 미호출
- 저장 오류의 호출자 전달

초기 검증 당시 실제 DB의 추론 결과 186행 중 신규 계약 180행은 세 품질
필드가 모두 채워졌고, 2026-07-27~2026-07-31의 기존 6행은 품질 필드가
null이었다. 기존 행은 backfill하지 않고 Flask에서 `unknown`으로 표현한다.
2026-08-10 첫 최상위 실행은 활성 모델 기준 신규 방향 결과 20행을 적재했고,
다음 실행은 미완료 대상 0건으로 정상 종료했다. 당시 artifact ID와 건수는
환경별 실행 이력이며 다른 환경의 고정 계약이 아니다.

## 후속 소비자

- Flask 기능은 저장된 결과를 서비스 DTO로 변환해 조회한다.
- LLM 기능은 저장된 점수·품질 상태와 수급 상태를 사용하며 키워드
  contribution이나 댓글 원문을 보고서 근거로 사용하지 않는다.
- 두 소비자는 모델 저장 필드의 의미를 역으로 변경하지 않는다.

## 관련 코드와 정본

- [`pilos/jobs/predict_model.py`](../pilos/jobs/predict_model.py)
- [`pilos/analysis/modeling/model_inference.py`](../pilos/analysis/modeling/model_inference.py)
- [`pilos/storage/model_artifacts.py`](../pilos/storage/model_artifacts.py)
- [`pilos/storage/model_inference_db.py`](../pilos/storage/model_inference_db.py)
- [`tests/test_analysis_pipeline.py`](../tests/test_analysis_pipeline.py)
- [`tests/test_job_execution_contracts.py`](../tests/test_job_execution_contracts.py)
- [`docs/DATA_CONTRACT.md`](../docs/DATA_CONTRACT.md)
- [`docs/DECISIONS.md`](../docs/DECISIONS.md)
