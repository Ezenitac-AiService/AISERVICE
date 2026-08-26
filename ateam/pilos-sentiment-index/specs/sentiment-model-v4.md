# 수급 연관성 모델 v4 기능 명세

## 상태

- 구현 상태: 방향별 Ridge text-only v4 구현·학습 완료
- 검증 상태: 워크포워드와 월별 층화 날짜 그룹 반복 검증 완료
- 통합 상태: `main@f80fdc2` 반영 완료 (PR #3, #17)

## 목적

종목·거래일별 댓글 표현과 같은 날 개인투자자 수급지수의 통계적 연관성을
학습한다. 결과는 미래 수급·주가 예측이나 매수·매도 추천이 아니라 당일
댓글 표현이 과거 수급 국면과 보인 연관성으로 해석한다.

## 범위와 실행 시점

- Positive와 Negative 수급 방향별 학습 Dataset 조회
- 공통 날짜 분할을 사용한 반복 검증
- 선정 모델을 전체 Dataset으로 새로 학습
- Vectorizer와 Ridge를 스키마 2 bundle로 저장·재로드 검증
- 모델 메타데이터와 검증 지표를 DB `artifacts`에 등록

학습은 자동 운영 파이프라인에 포함하지 않는다. 재학습이 필요하거나 다른
로컬 환경에서 모델 객체를 생성할 때 별도 실행한다.

## 학습 Dataset

한 행은 최신 `daily_document`와 같은 종목·거래일의 `supply_demand`를
결합한 결과다. 입력 컬럼은 다음과 같다.

```text
daily_document_id
stock_code
model_date
tfidf_text
comment_count
supply_demand_index
```

Positive는 수급지수가 0보다 큰 행, Negative는 0보다 작은 행을 사용한다.
학습 조회는 `supply_demand.data_status='confirmed'`인 행만 사용한다.
서비스 v4 입력 특성은 `tfidf_text`의 TF-IDF 희소행렬뿐이다.
`stock_code`, 날짜, 댓글 수와 실제 수급지수는 모델 특성에 넣지 않는다.

## 서비스 모델 설정

현재 활성 서비스 모델은 v4다. `pilos.model_config`의
`ACTIVE_SERVICE_MODEL_VERSION`을 추론·단일 댓글·calibration·LLM이
공유한다. 학습 실행기에는 별도 `TRAINING_TARGET_MODEL_VERSION=5`가 있으며,
새 모델 학습 준비가 현재 v4 서비스 식별값을 바꾸지 않는다. v5는 학습 대상
설정일 뿐 현재 활성 artifact나 calibration으로 전환된 상태가 아니다.

| 항목 | 값 |
|---|---|
| 모델명 | `ridge_supply` |
| 방향 | `positive`, `negative` |
| 모델 버전 | `4` |
| 특성 모드 | `text_only` |
| 토크나이저 | `kiwi_ver1` |
| Ridge alpha | `1.0` |
| Ridge solver | `lsqr` |
| ngram | `(1, 1)` |
| `min_df` | `5` |
| `max_df` | `0.95` |
| `max_features` | `None` |
| `sublinear_tf` | `True` |
| `lowercase` | `True` |

댓글 수 Scaler는 사용하지 않으며 DB 메타데이터에는 `not_used`로 기록한다.

## 검증과 최종 학습

- 전체 관측 날짜를 월별로 층화해 약 80:20으로 나눈다.
- Positive와 Negative는 같은 날짜 분할을 공유한다.
- 시드 42~46의 각 분할에서 새 Vectorizer와 Ridge를 학습한다.
- 훈련에는 `fit_transform`, 검증에는 해당 임시 Vectorizer의 `transform`을
  사용한다.
- 공식 검증 지표는 다섯 검증 결과의 평균이다.
- 후보 선정 후 임시 객체를 재사용하지 않고 2026-07-24까지 전체
  Dataset으로 Vectorizer와 Ridge를 처음부터 다시 학습한다.

상세 지표와 후보 비교 결과는
[`docs/MODEL_EXPERIMENT_RESULTS.md`](../docs/MODEL_EXPERIMENT_RESULTS.md)를
참조한다.

## bundle 계약

스키마 버전은 `2`이며 다음 필드만 허용한다.

```text
artifact_schema_version
model_name
model_variant
model_version
feature_mode
tokenizer_version
dataset_start_date
dataset_end_date
vectorizer
ridge_model
```

Vectorizer는 학습된 vocabulary를 가져야 하고 Ridge는 계수와 절편을
가져야 한다. feature 수와 Ridge 계수 수, 계수·절편의 유한값 여부를
저장 전과 로드 후 검증한다.

현재 활성 서비스 파일은 다음과 같다.

```text
artifacts/ridge_supply_positive_text_only_v4.pkl
artifacts/ridge_supply_negative_text_only_v4.pkl
```

파일은 Git 추적 대상이 아니다. 기존 파일이나 같은 모델명·방향·버전의
DB 행을 덮어쓰지 않는다. 기존 검증 환경의 artifact ID 7·8은 실행 이력
식별자이며 다른 환경에서 고정값으로 가정하지 않는다.

## 실패와 재실행

- 방향별 학습 데이터가 없거나 목표값이 결측·비유한이면 중단한다.
- 동일 버전의 DB 아티팩트나 로컬 파일이 있으면 덮어쓰지 않고 중단한다.
- 저장한 bundle을 공개 로더로 다시 읽어 전체 Dataset 예측이 저장 전과
  일치하는지 확인한다.
- 현재 흐름은 파일 저장 후 DB 아티팩트를 등록한다. DB 등록이 실패해
  파일만 남으면 자동 복구하지 않으므로 원인을 확인한 뒤 새 버전 또는
  승인된 수동 정리가 필요하다.
- 두 방향은 순서대로 생성하므로 한 방향 완료 후 다른 방향이 실패할 수
  있다. 자동 운영 실행에 포함하지 않는 이유 중 하나다.

## 검증 근거와 한계

- 로컬 Positive·Negative v4 bundle의 스키마·버전·TF-IDF 설정·Ridge
  alpha와 `transform`·예측을 비DB 스모크 검증했다.
- 랜덤 검증은 보유 Dataset 내부의 동시점 연관성 재현이며 미래 성능을
  증명하지 않는다.
- 모델 파라미터나 토큰 계약을 변경하면 기존 v4를 수정하지 않고 새 모델
  버전으로 재학습한다.
- 학습 대상 버전을 바꿔도 활성 서비스 버전은 자동으로 바뀌지 않는다.
  새 bundle·DB artifact·calibration 검증 후 별도로 활성 버전을 전환한다.

## 관련 코드와 정본

- [`pilos/jobs/train_model.py`](../pilos/jobs/train_model.py)
- [`pilos/analysis/vectorizer.py`](../pilos/analysis/vectorizer.py)
- [`pilos/analysis/modeling/model_train.py`](../pilos/analysis/modeling/model_train.py)
- [`pilos/analysis/modeling/model_validation.py`](../pilos/analysis/modeling/model_validation.py)
- [`pilos/analysis/modeling/ridge_model.py`](../pilos/analysis/modeling/ridge_model.py)
- [`pilos/storage/model_artifacts.py`](../pilos/storage/model_artifacts.py)
- [`docs/DECISIONS.md`](../docs/DECISIONS.md)
- [`docs/MODEL_EXPERIMENT_RESULTS.md`](../docs/MODEL_EXPERIMENT_RESULTS.md)
