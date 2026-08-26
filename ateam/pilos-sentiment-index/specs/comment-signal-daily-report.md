# 댓글 수급 신호와 일별 LLM 브리핑 기능 명세

## 상태

- 구현 상태: calibration 계산·저장·로딩, 일별 댓글 수급 신호 계산,
  정형 수치 근거 기반 `market_commentary_v13` 프롬프트와 DTO,
  deterministic 요약, DB 품질 상태 재사용, 수급 상태 갱신과 단일 댓글
  분석 실행 경로 구현 완료
- 표현 계약 상태: v13 적용 완료. **`main@f80fdc2` 서비스 baseline이다.**
  페르소나는 데이터 해설자이고, 수급 방향은 `현재는 개인투자자의 매도가
  더 많습니다`처럼 현재형으로, 등급은 `높은 편`·`보통 수준`처럼
  자연어로 쓴다. `강세`·`약세`·`유지`·`상회`는 단어만으로 reject하지
  않으며, evidence와 대조 가능한 사실 모순만 hard reject한다
- 비DB 검증 상태: 2026-08-10 기준 전체 394개 실행, 390개 통과·RAG E2E
  환경 의존 테스트 4개 skip 이력. 2026-08-11 전체 suite는 구 챗봇 계약
  테스트 때문에 실패했으며, `test_chat*` 제외 375개는 통과.
  calibration 방향·범위·clamp, no-feature, neutral, LLM DTO,
  단일 댓글, 표현 계약 회귀, 기존 추론 regression 포함
- calibration 생성 상태: 실제 v4 calibration artifact와 당시 Positive 7·
  Negative 8 DB artifact/bundle 전체 identity 검증 완료. ID는 환경별 이력이며
  서비스 코드는 방향·버전 identity로 활성 artifact를 조회
- 학원 서버 호환성 검증 상태: `market_commentary_v13` 90행 실적재 완료.
  ready 79행, deterministic 11행이며 저장 보고서 90행 재검증에서 계약
  위반이 없었다
- DB 통합 검증 상태: 초기 품질 필드 신규 결과 180행, v13 90행과 미완료
  대상 0건 확인. 기존 품질 필드 null 6행은 backfill하지 않고 유지한다.
  이후 최상위 실행에서 추론 20행과 v13 20행을 신규 적재했고 재실행 대상
  0건 계약을 확인했다
- DDL 변경 상태: `sentiment_index_result` 품질 3필드와 `llm_report` 수급
  상태·관측 시각·갱신 시각 컬럼 적용 완료
- 통합 상태: v13 품질·수급 갱신 운영 계약 `main@f80fdc2` 반영 완료
- 웹 소비 상태: v13 API와 JavaScript 상세 화면 연결 완료. 수급 상태·관측
  시각·품질 상태·브리핑을 현재 공개 계약으로 표시

## 목적

기존 TF-IDF·Ridge v4 추론 결과를 사용자에게 이해 가능한 수치로
표현한다.

Ridge의 raw 출력값을 같은 모델의 과거 출력 분포에 상대화하여 0~100
`comment_signal_score`로 변환하고, LLM은 이미 계산된 정형 수치를 짧은
한국어 브리핑으로 요약만 한다.

이 기능은 예측력을 새로 주장하지 않는다. 기존 모델이 학습한 같은 날짜
댓글과 같은 날짜 수급 사이의 관계를 더 안정적으로 표현하는 것이 목적이다.

## 포함 범위와 제외 범위

### 포함 범위

- 재추론 결과에서 방향별 백분위 calibration artifact 생성
- calibration과 모델 artifact identity 교차검증
- 일별 `comment_signal_score`, `signal_level`, `signal_status` 계산
- 직전 거래일 신호와 이동평균 비교값 계산
- 정형 수치만 사용하는 LLM 프롬프트와 응답 검증
- LLM 없이 동작하는 deterministic 요약
- estimated·confirmed 수급 상태에 따른 같은 v13 보고서 제한적 갱신
- Flask 전달용 완성 응답 조립
- 단일 댓글 분석 실행 경로

### 제외 범위

- TF-IDF·Kiwi·Ridge 학습과 추론 로직 변경
- Positive/Negative 모델 통합
- 재추론 전체 행의 운영 DB 적재
- calibration 전용 DB 테이블
- 신규 DDL과 backfill
- 대표 댓글 선택, 기여 키워드 해석, LLM 근거 evidence
- standalone preview 실행기

## 핵심 도메인 의미

`comment_signal_score`는 다음이 **아니다.**

- 댓글 긍정도·부정도
- 감성 확률
- 주가 상승·하락 확률
- 미래 수급 예측값

의미는 다음과 같다.

> 온라인 투자자 댓글의 언어 패턴과 실제 개인투자자 수급 사이에서 학습된
> 관계를 기반으로, 현재 댓글에 대한 모델 반응이 과거 동일 수급 방향
> 대비 어느 정도 수준인지 0~100으로 수치화한 값이다.

`50`은 감성 중립이 아니라 과거 동일 모델 출력 분포의 중간 수준이다.

방향 판단은 신호가 하지 않는다. 실제 개인투자자 수급 데이터가 결정한
`supply_direction`이 담당한다.

## 입력과 출력

### calibration 입력

`pilos/jobs/export_ridge_v4_training_reinference.py`가 만드는 재추론
CSV를 사용한다. 다음 컬럼이 모두 필요하다.

```text
artifact_id
artifact_type
model_name
model_variant
model_version
artifact_schema_version
tokenizer_version
vectorizer_name
scaler_name
dataset_start_date
dataset_end_date
predicted_score
source_scope
```

컬럼명은 `artifacts` 테이블의 실제 컬럼과 같습니다. 테이블에 없는
`vectorizer_version`, `architecture_version`, `training_data_version`은
사용하지 않습니다.

방향별로 `artifact_id`가 하나여야 하고, 모델 identity 컬럼은 CSV 전체에서
값이 하나여야 한다. 조건을 만족하지 않으면 오류로 중단한다.

### calibration artifact

```text
artifacts/calibration/<model_name>_v<model_version>_signal_calibration.json
```

`artifacts`는 Git 비추적 실행 산출물 경로다. calibration은 재추론 원본이
아니라 모델 artifact 성격의 메타데이터이므로 운영 DB에 적재하지 않는다.

논리 구조는 다음과 같다.

| 필드 | 설명 |
|---|---|
| calibration_schema_version | 현재 `1` |
| generated_at | 생성 시각 (Asia/Seoul ISO 8601) |
| source_scope | 재추론 CSV의 `source_scope` |
| source_row_count | 재추론 CSV 행 수 |
| model_name / model_version | 모델 identity |
| artifact_type / artifact_schema_version | 모델 identity |
| tokenizer_version / vectorizer_name / scaler_name | 모델 identity |
| dataset_start_date / dataset_end_date | 학습 Dataset 기간 |
| variants.positive / variants.negative | 방향별 백분위 |

방향별 항목은 다음을 가진다.

| 필드 | 설명 |
|---|---|
| artifact_id | 해당 방향 재추론에 사용한 정확한 artifact |
| sample_count | 재추론 표본 수 |
| quantile_levels | `0`부터 `100`까지 1단위 백분위 지점 101개 |
| quantile_scores | 각 지점의 실제 `predicted_score` |

`quantile_scores`는 비내림차순이어야 한다. 로딩 시 길이와 단조성을
검증한다.

### 일별 신호 입력

기존 `sentiment_index_result`의 저장된 값을 그대로 사용한다. 신규
테이블을 만들지 않는다.

| 사용 값 | 출처 |
|---|---|
| supply_demand_association_score | `sentiment_index_result` |
| artifact_id | `sentiment_index_result` |
| recognized_feature_count | `sentiment_index_result` |
| unique_token_count / vocabulary_coverage | `sentiment_index_result` |
| inference_status | `sentiment_index_result` |
| supply_demand_index | `supply_demand` |
| data_status / observed_at | `supply_demand` |
| comment_count / model_date | `daily_document` |

`positive_contribution_keywords`와 `negative_contribution_keywords`는
이 기능에서 조회하지 않는다. 두 컬럼은 추론 검수와 단일 댓글 기능을
위해 DB에 그대로 보존한다.

### 일별 신호 출력

`DailyCommentSignal`의 논리 계약은 다음과 같다.

| 필드 | 자료형 | 설명 |
|---|---|---|
| stock_id / stock_code / stock_name | - | 종목 식별 |
| model_date | date | 거래일 |
| daily_document_id | integer | 최신 일별문서 |
| comment_count | integer | 이날 집계된 댓글 수 |
| actual_supply_index | float | 실제 개인 수급지수 |
| supply_direction | `BUY`/`SELL`/`NEUTRAL` | 실제 수급 방향 |
| active_model_variant | `positive`/`negative`/null | 사용한 Ridge |
| active_result_id / active_artifact_id | integer/null | 사용한 추론 행 |
| predicted_score | float/null | Ridge raw 출력값 |
| recognized_feature_count | integer/null | 활성 모델 인식 특성 수 |
| unique_token_count | integer/null | 활성 결과의 고유 토큰 수 |
| vocabulary_coverage | float/null | 활성 결과의 vocabulary 포함 비율 |
| inference_status | `ready`/`insufficient_features`/null | DB 저장 품질 상태 |
| supply_data_status | `estimated`/`confirmed` | 수급 관측 상태 |
| supply_observed_at | datetime | 수급 관측 시각 |
| comment_signal_score | integer 0~100/null | 상대 신호 |
| signal_level | string/null | 상대 강도 문구 |
| signal_status | `ready`/`insufficient_features`/`no_direction` | 계산 상태 |
| model/artifact/calibration 버전 | - | 재현 정보 |

`predicted_score`는 내부 추적·검증용으로 유지하며 Flask 응답에는 넣지
않는다.

## 실행 흐름

```text
jobs가 calibration과 Positive·Negative DB artifact/bundle 전체 identity 검증
→ storage가 기간 내 최신 일별문서·추론 결과·실제 수급 조회
→ storage가 비교용 과거 추론 결과 조회
→ analysis가 방향 판정과 백분위 변환으로 일별 신호 계산
→ analysis가 직전 거래일·이동평균 비교값 계산
→ analysis가 정형 수치 근거와 프롬프트 조립
→ deterministic 대상은 client 없이 jobs가 요약 저장
→ 실제 LLM 대상이 처음 나타날 때 collection client 생성·재사용
→ analysis가 화면·API용 JSON 조립
→ storage가 llm_report에 신규 INSERT 또는 허용된 수급 변화 UPDATE
```

## 핵심 처리 규칙

### 백분위 변환

```text
percentile = quantile_scores 배열에 대한 predicted_score의 선형 보간 위치
```

분포 최솟값보다 작으면 `0`, 최댓값보다 크면 `100`으로 clamp한다.

```text
positive → signal_score = percentile
negative → signal_score = 100 - percentile
```

negative 모델은 더 강한 음수가 해당 방향의 강한 반응이므로 백분위 방향을
뒤집는다.

최종 값은 항상 `0 <= score <= 100`이며 단조성을 유지하는 반올림을
사용한다.

### signal level

| 구간 | 문구 |
|---|---|
| 0 ~ 19 | 매우 낮음 |
| 20 ~ 39 | 낮음 |
| 40 ~ 59 | 보통 |
| 60 ~ 79 | 높음 |
| 80 ~ 100 | 매우 높음 |

`긍정`, `부정` 계열 표현을 사용하지 않는다. 방향은 `supply_direction`이
담당한다.

### 예외 처리

| 조건 | signal_status | comment_signal_score |
|---|---|---|
| `actual_supply_index == 0` | `no_direction` | null |
| 활성 결과의 DB `inference_status == insufficient_features` | `insufficient_features` | null |
| 그 외 | `ready` | 0~100 |

수급지수가 0일 때 positive/negative 중 하나를 임의로 선택하지 않는다.

품질 상태는 추론기가 저장한 DB `inference_status`만 사용한다. 신호와 LLM은
`recognized_feature_count`나 coverage 임계값으로 상태를 다시 판정하지 않는다.

비활성 방향의 인식 특성 수는 신호 계산을 막지 않는다.

### 비교값

`previous_signal_score`는 당일보다 앞선 거래일 중 가장 최근의 `ready`
신호다.

`signal_ma5`는 **당일을 제외한** 직전 최대 5거래일 `ready` 신호의
평균이다. 당일 값을 포함하지 않으므로 당일 신호와 비교하는 기준선으로
사용할 수 있다.

`signal_change`는 `comment_signal_score - previous_signal_score`다.

신호가 계산되지 않은 날은 평균과 직전 값 계산에서 제외한다. 없는 값을
만들어 채우지 않는다. 비교 가능한 과거 신호가 없으면 세 값 모두 null이다.

과거 신호는 재추론 CSV가 아니라 DB에 이미 저장된 raw 점수에 같은
calibration을 적용해 계산한다.

### calibration 일치 검증

다음이 하나라도 다르면 신호를 만들지 않고 오류로 중단한다.

- `model_name`, `model_version`, `artifact_type`, `artifact_schema_version`
- `tokenizer_version`, `vectorizer_name`, `scaler_name`
- `dataset_start_date`, `dataset_end_date`
- 방향별 `artifact_id`

### LLM 호출 판정

LLM은 다음 조건을 모두 만족할 때만 호출한다.

1. `signal_status == "ready"`
2. `previous_signal_score` 또는 `signal_ma5` 중 하나 이상 존재

수급 방향과 당일 신호만 있는 경우는 deterministic 코드로 처리한다.

### LLM 입력 근거

`LlmSignalEvidence`가 전달하는 값은 다음뿐이다.

```text
actual_supply_index
supply_direction
signal_status
comment_signal_score
signal_level
comment_count
previous_signal_score   (있을 때만)
signal_change           (있을 때만)
signal_ma5              (있을 때만)
```

값이 없는 비교 항목은 프롬프트에 키 자체를 넣지 않는다. null을 넣으면
LLM이 없는 값을 설명하려 시도할 수 있다.

키워드, 대표 댓글, 댓글 원문, 기여도는 프롬프트에 넣지 않는다.

### 표현 계약

LLM은 이미 계산된 값의 의미를 바꾸지 않는다. 다음 세 값은 서로 다른
의미이며 하나로 합치지 않는다.

| 값 | 의미 | 유일한 표현 |
|---|---|---|
| `previous_signal_score` | 직전 거래일 신호 | 직전 거래일 |
| `signal_change` | 현재 신호 − 직전 거래일 신호 | 직전 거래일보다 N포인트 상승·하락 |
| `signal_ma5` | 당일 제외 직전 5거래일 평균 | 직전 5거래일 평균 |

전일 비교와 5거래일 평균 비교는 독립된 관계다. 직전 거래일보다 올랐어도
5거래일 평균보다 낮을 수 있으므로 `강화됐다`, `약화됐다` 하나로 합치지
않는다.

`signal_level`은 코드가 결정한 값이며 LLM의 판단 대상이 아니다.
`낮음`을 `매우 낮음`으로, `보통`을 `중립`으로 바꾸지 않는다.

프롬프트는 비교 **사실**만 제시하고 문장 구성은 LLM이 정한다. LLM이
`현재 − 전일`이나 `현재 − 평균`을 새로 계산하지 않게 하되, 어떤 관계를
어떻게 묶을지는 맡긴다.

```text
- 어제(직전 거래일)와 비교: 30점 높아짐 (어제 9점)
- 최근 5일 평균과 비교: 현재가 더 낮음 (평균 55점)
- 종합하면: 어제보다는 올라왔지만 최근 5일 평균보다는 아직 낮은 상태
```

`describe_signal_pattern`이 네 가지 교차 관계를 미리 이름 붙인다.

| 조건 | 관계 |
|---|---|
| 현재 > 전일, 현재 > 평균 | 어제보다도 최근 5일 평균보다도 높은 상태 |
| 현재 < 전일, 현재 < 평균 | 어제보다도 최근 5일 평균보다도 낮은 상태 |
| 현재 > 전일, 현재 < 평균 | 어제보다는 올라왔지만 최근 5일 평균보다는 아직 낮은 상태 |
| 현재 < 전일, 현재 > 평균 | 어제보다는 낮아졌지만 최근 5일 평균보다는 여전히 높은 상태 |

방향이 엇갈리는 두 관계를 `강화됐다`, `약화됐다` 하나로 합치지 않는다.

문장 구조는 고정하지 않는다. 2~4문장 범위에서 어떤 수치를 먼저 말할지,
무엇을 생략할지는 LLM이 고른다. 변화량으로 관계가 드러나면 직전 거래일의
절대 점수는 생략해도 된다.

`강해졌다`, `약해졌다`, `회복했다` 같은 변화 표현은 숫자 관계가
뒷받침하면 허용한다. 단 대상은 반드시 댓글 수급 신호여야 한다.

### LLM 응답 검증

응답 계약은 `market_commentary`와 `conclusion` 두 필드뿐이다.
`conclusion`도 `market_commentary`와 같은 사실 계약을 적용한다.

검증 목적은 문체 강제가 아니라 evidence와의 모순 차단이다. 다음만
hard reject한다.

| 검증 | 내용 |
|---|---|
| 입력에 없는 숫자 | 근거 값·0~100 척도·날짜 구성요소 외 정수, 소수, `%` |
| 수급 방향 오류 | BUY인데 `매도 우위`·`매도가 더 많다`, SELL인데 그 반대, NEUTRAL인데 방향 명시 |
| 지표 혼동 | `매도 우위가 62점`처럼 수급 방향에 신호 점수를 붙임 |
| 변화량 값 오류 | `N포인트`, `어제보다 N점`의 N이 `signal_change` 절댓값과 다름 |
| 변화량 방향 오류 | 상승인데 하락 서술, 하락인데 상승 서술 |
| 변화량 기준 오류 | 변화량 바로 앞에 `signal_ma5` 값을 기준으로 제시 |
| 평균 비교 방향 오류 | 현재 > 평균인데 `못 미친다`, 현재 < 평균인데 `웃돈다` |
| 평균 명칭 왜곡 | `과거 평균`, `과거 분포`, `중간 수준`, `이동평균`, `직전 거래일 평균` |
| 평균 시계열 주장 | `평균도 상승했다` — 평균의 변화는 evidence에 없음 |
| 등급 재분류 | 입력 `signal_level`과 어긋나는 등급으로 서술. `매우`를 뗀 표현은 허용 |
| 주가·시장 방향 | 주가·시장을 대상으로 한 방향 서술, `상승 신호`, `하락 신호` |
| 투자 권유 | `매수 추천`, `매수 신호`, `목표가`, `손절` 등 |
| 미래 전망 | `향후`, `예상됩니다`, `이어질`, `가능성이 높` 등 |
| 원인 추론 | `때문`, `덕분`, `영향으로`, `기대감에` 등 |
| 변화 표현 대상 오류 | `매수세가 강해졌다`처럼 시계열이 없는 대상에 변화 서술 |
| 숫자 동일 주장 | 점수가 실제로 변했는데 `점수가 그대로`, `어제와 같은 점수`, `변화가 없` |
| 전환 주장 | `매수로 전환`, `매도로 돌아섰다`, `등급 전환` — 직전 값이 evidence에 없음 |
| 수급 강도 변화 | `매도 압력이 커졌다`, `매수세가 강화됐다` — 강도 시계열이 evidence에 없음 |
| 평균 비교 주어 역전 | `평균 81점이 현재보다 낮다` — 실제 관계와 반대 |
| 숫자 역할 혼동 | 변화량을 직전 거래일 점수 자리에 적음 |
| 직접 인과 | 수급·댓글과 주가 사이의 인과 서술 |

다음은 hard reject하지 않는다. 문체 문제이지 사실 문제가 아니다.

- `signal_level` 생략, 점수와 떨어진 위치에서 서술
- 문장 순서와 개수, 어미와 어순
- 중복되는 숫자 생략
- `최근 5거래일 평균`, `직전 5일 평균`, 문맥이 분명한 `최근 평균`
- 댓글 수급 신호를 대상으로 한 `상승세`, `하락세`, `강화`, `약화`,
  `회복`
- `관측됩니다`, `설정되어 있습니다` 같은 기계적 표현
- 수급 강도를 강조하는 `강한`, `뚜렷한` 같은 수식어

변화 표현은 대상으로 판정한다. `댓글 수급 신호가 상승세`는 통과하고
`주가 상승세`, `매수세가 강해졌다`는 차단한다. 대상이 명시되지 않은
경우는 사실을 반증할 수 없으므로 막지 않는다.

검증에 두 번 실패하면 검증된 정형 근거로 deterministic fallback을 저장하고
`commentary_source=deterministic`으로 구분한다. 연결·HTTP 실패는 저장하지
않아 재실행 대상으로 남긴다.

### deterministic 요약

LLM을 호출하지 않는 경우 정형 값만으로 한국어 요약을 만든다.

| 상태 | 내용 |
|---|---|
| `no_direction` | 수급 균형이며 신호를 계산하지 않았음을 설명 |
| `insufficient_features` | 인식 특성이 없어 신호를 계산하지 않았음을 설명 |
| `ready` | 방향, 점수, 강도, 있을 때 비교값과 댓글 수를 나열 |

deterministic 요약은 원인이나 전망을 만들지 않는다.

### 버전

| 항목 | v7 | v8 | v9~v12 | v13 |
|---|---|---|---|---|
| prompt_version | `market_commentary_v7` | `market_commentary_v8` | `market_commentary_v9`~`v12` | `market_commentary_v13` |
| report_schema_version | `4` | `5` | `5` | `5` |
| evidence_schema_version | `2` | `3` | `3` | `3` |
| calibration_schema_version | 없음 | `1` | `1` | `1` |

v9~v13은 프롬프트 표현 계약과 응답 검증만 바꿨다. 전달 필드와 저장
구조가 v8과 같으므로 `report_schema_version`과
`evidence_schema_version`은 올리지 않는다.

`llm_report` 고유키에 `prompt_version`이 들어 있으므로 프롬프트 계약이
바뀌면 `prompt_version`만 올려도 기존 행을 덮어쓰지 않고 새로 적재된다.
구조가 그대로인데 schema 버전을 올리면 Flask 영역과 검수 노트북에
구조가 바뀌었다는 잘못된 신호를 준다.

v11의 원칙은 **표현 자유도는 높이고 사실 자유도는 높이지 않는다**이다.
검증의 목적은 문체 강제가 아니라 evidence와의 모순 차단이다.

v12는 그 원칙을 유지하면서 기본 문체를 사용자 쪽으로 옮겼다. 24개
고정 케이스 프롬프트 실험에서 페르소나를 넓게 열면 수급 방향 반전과
입력에 없는 해석이 늘어난다는 것이 확인됐으므로, 새로운 해석 자유를
주는 대신 **이미 확정된 사실을 더 자연스럽게 설명할 자유**만 준다.

또한 v11에서 문체 단어 하나 때문에 사실이 정확한 보고서가 폐기되던
문제를 없앴다. `강세`, `약세`, `회복세`, `유지`, `상회`, `하회`는
hard rejection 대상에서 제외했고, `유지`는 직전 거래일 점수의 등급
구간이 실제로 같은지 확인해 판정한다.

`evidence_schema_version`은 키워드 evidence 전용 번호가 아니다. 근거의
종류가 키워드·대표 댓글에서 정형 수치로 바뀌었으므로 같은 버전 축을
계속 사용하되 번호를 올린다.

v2~v12는 덮어쓰거나 수정하지 않는다. v13은 같은 생성키에서
`estimated→confirmed` 또는 더 최신 `estimated→estimated` 관측만 같은 행을
UPDATE한다. confirmed를 estimated로 낮추지 않으며 그 외 hash 변경은 오류다.

### 저장 상태

| status | 의미 |
|---|---|
| `ready` | LLM이 생성하고 검증을 통과한 브리핑 |
| `insufficient_evidence` | LLM을 호출하지 않고 deterministic 요약을 저장 |

LLM 연결·HTTP 호출 자체가 실패하면 저장하지 않고 실행 요약에서 `failed`로
집계한다. 응답 계약 검증 2회 실패는 deterministic fallback으로 저장한다.

## Flask 전달 계약

Flask 영역은 백분위, 모델 방향 판단, signal level, artifact 해석을
직접 계산하지 않는다.

```json
{
  "stock_code": "000660",
  "stock_name": "SK하이닉스",
  "model_date": "2026-08-07",
  "supply_direction": "BUY",
  "actual_supply_index": 0.1951,
  "comment_signal_score": 84,
  "signal_level": "매우 높음",
  "signal_status": "ready",
  "signal_change": 27,
  "signal_ma5": 50,
  "comment_count": 1830,
  "market_commentary": "...",
  "conclusion": "...",
  "notice": "..."
}
```

`signal_status`가 `ready`가 아니면 `comment_signal_score`,
`signal_level`, `signal_change`, `signal_ma5`는 `null`이다.

## 단일 댓글 분석

일별 시장 분석과 단일 댓글 분석은 서로 다른 기능이다.

```text
사용자 입력
→ preprocess_comment_text
→ tokenize_comment (Kiwi)
→ tokens_to_tfidf_text
→ positive vectorizer.transform → analyze_text_contributions
→ negative vectorizer.transform → analyze_text_contributions
```

`analyze_text_contributions`는 일별 추론과 같은 함수이므로
`TF-IDF × coefficient` 계산 규칙이 두 기능에서 동일하다.

단일 댓글 결과에는 일별 calibration을 적용하지 않는다. Ridge는 일별
댓글 집합(document) 단위로 학습됐으므로 단일 댓글 결과를 0~100 신호로
바꾸어 보여주면 안 된다.

방향별 결과는 기존 `SingleCommentInferenceDTO` 계약을 그대로 따른다.
`docs/DATA_CONTRACT.md` §18에 따라 모델 절편과 전체 수급지수 예측값을
단일 댓글 결과인 것처럼 합산하지 않고 `text_score`만 제공한다.

전처리 또는 토큰화 후 분석할 문자열이 없으면 결과 대신 오류로 처리한다.

## calibration 생성 전제

`build_signal_calibration`은 실제 재추론 결과에서만 값을 만든다. 예시값과
합성값을 production calibration으로 사용하지 않는다.

실행에는 다음이 모두 필요하다.

1. MySQL 접속 (`artifacts`, `daily_document`, `supply_demand` 조회)
2. `artifacts` 경로의 실제 모델 `.pkl` bundle 2개
3. 위 둘로 생성한 재추론 CSV

실행 순서는 다음과 같다.

```bash
uv run python -m pilos.jobs.export_ridge_v4_training_reinference

uv run python -m pilos.jobs.build_signal_calibration

uv run python -m pilos.jobs.generate_llm_reports \
  --start-date 2026-08-07 --end-date 2026-08-07
```

## 실패와 재실행 계약

- calibration artifact가 없으면 보고서 생성을 시작하지 않는다
- calibration과 Positive·Negative DB artifact/bundle identity가 다르면 대상
  조회·처리 전에 전체 실행을 중단한다
- 같은 방향의 추론 결과가 둘 이상이면 해당 대상만 실패로 처리하고 전체
  실행을 중단하지 않는다
- 같은 생성 고유키의 hash가 같으면 기존 보고서를 재사용한다
- hash가 달라도 estimated→confirmed 또는 더 최신 estimated 관측이면 기존
  v13을 UPDATE하고, 그 외 변경은 오류로 처리한다
- confirmed 보고서를 estimated 입력으로 낮추지 않는다
- 과거 이력 조회에서 판정할 수 없는 날은 비교 대상에서 제외한다
- 대상 0건은 성공 0건·실패 0건으로 종료하며 LLM client를 만들지 않는다
- 모든 대상이 deterministic이면 API Key 검증과 외부 client 생성을 하지
  않는다. 첫 실제 LLM 대상에서 한 번 생성한 client를 이후 재사용한다
- 독립 CLI는 `failed_count`를 출력한다. 운영 최상위 실행기는 반환된
  `failed_count`를 직접 검사해 전체 실행 성공·실패를 판정한다

## 검증 내용과 검증하지 않은 내용

### 검증한 내용

```bash
uv run python -m unittest \
  tests.test_analysis_pipeline \
  tests.test_build_signal_calibration_job \
  tests.test_job_execution_contracts \
  tests.test_llm_capability \
  tests.test_llm_report_analysis \
  tests.test_llm_report_client \
  tests.test_llm_report_generation_job \
  tests.test_ridge_training_reinference_export \
  tests.test_signal_calibration \
  tests.test_single_comment_inference
```

초기 v8 계약 시점에는 아래 명령 범위 122개가 통과했다. 2026-08-10 현재
전체 회귀 검증은 394개를 실행해 390개가 통과했고 RAG E2E 4개가 skip됐다.

- positive 신호 단조성, negative 방향 반전, 0~100 범위, 분포 밖 clamp,
  중앙값 부근 50
- `no_direction`, `insufficient_features` null 처리
- 비교값 창 크기와 신호 없는 날 제외
- calibration artifact 왕복 저장·로딩과 단조성 손상 탐지
- calibration·artifact identity 불일치 차단
- 프롬프트와 저장 JSON에 키워드·대표 댓글 근거 부재
- LLM 응답의 인과·확률·백분율·소수·미입력 숫자 차단
- 주가 방향·투자 판단 어휘 차단과 수급 방향 표현 허용
- `signal_level` 재분류 차단과 비교 문장 오탐 방지
- `signal_ma5` 별칭 차단과 명칭 강제
- 변화량을 5거래일 평균에 결합하는 오류 차단
- v8 실출력 10종목 fixture 회귀와 deterministic 출력 표현 계약
- deterministic 요약이 자체 응답 검증을 통과
- 단일 댓글 두 모델 실행, 기여도 합과 `text_score` 일치
- 기존 추론 pipeline regression
- DB `inference_status` 단일 품질 판정과 품질 3필드 조회·저장
- 대상 0건과 deterministic-only client 미생성
- estimated→confirmed, 최신 estimated 갱신, 역방향 강등 금지
- 같은 input hash 멱등성과 허용되지 않은 hash 변경 차단
- 응답 검증 2회 실패 deterministic fallback 저장

### 검증하지 않은 내용

- 실제 DB의 estimated v13을 더 최신 estimated로 UPDATE하는 운영 실행
- 학습 대상 v5 bundle·DB artifact·calibration 생성과 활성 전환
- 기존 품질 필드 null 6행 backfill

후속 v9~v12는 학원 LLM 서버와 실제 DB에서 검토됐다. v13은 10종목의
2026-07-27~2026-08-06 기간 보고서 90행(LLM ready 79, deterministic 11)을
실제 DB에 저장했고, production 검증기로 90행을 복원·재검증해 계약 위반
없음을 확인했다. 상세 검수 근거는 실행된 `05_llm_report.ipynb`와 v13 평가
자료에 남아 있다.

## 후속 소비자와 영향

- Flask API는 `build_flask_daily_signal_response` 결과를 그대로 전달한다
- 단일 댓글 API는 두 방향 모델 결과를 함께 전달하고 일별 신호 필드를
  만들지 않는다
- 화면은 `84 / 100`을 감성 긍정 84점으로 표시하지 않는다. 설명이
  필요하면 `notice` 문구를 사용한다
- `sentiment_index_result`는 기존 점수와 함께 품질 3필드를 저장하며,
  과거 null 6행은 신규 INSERT 계약과 분리된 migration 대상이다

## 관련 코드와 정본

- [`pilos/analysis/signal_calibration.py`](../pilos/analysis/signal_calibration.py)
- [`pilos/analysis/llm_report.py`](../pilos/analysis/llm_report.py)
- [`pilos/analysis/single_comment_inference.py`](../pilos/analysis/single_comment_inference.py)
- [`pilos/dto/comment_signal_dto.py`](../pilos/dto/comment_signal_dto.py)
- [`pilos/dto/llm_report_dto.py`](../pilos/dto/llm_report_dto.py)
- [`pilos/dto/single_comment_inference_dto.py`](../pilos/dto/single_comment_inference_dto.py)
- [`pilos/collection/ai_clients/llm_report_client.py`](../pilos/collection/ai_clients/llm_report_client.py)
- [`pilos/storage/signal_calibration_store.py`](../pilos/storage/signal_calibration_store.py)
- [`pilos/storage/llm_report_db.py`](../pilos/storage/llm_report_db.py)
- [`pilos/jobs/build_signal_calibration.py`](../pilos/jobs/build_signal_calibration.py)
- [`pilos/jobs/generate_llm_reports.py`](../pilos/jobs/generate_llm_reports.py)
- [`pilos/jobs/analyze_single_comment.py`](../pilos/jobs/analyze_single_comment.py)
- [`docs/DATA_CONTRACT.md`](../docs/DATA_CONTRACT.md)
- [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md)

## v13 — 현재 서비스 baseline

v13은 실험 버전이 아니라 `main@f80fdc2` 서비스 연동용 기준선이다. v12 실적재 결과를
읽고 확인된 두 가지를 반영했다.

**문체**

| 항목 | v12 | v13 |
|---|---|---|
| 수급 방향 | `오늘은 개인투자자의 매도가 더 많았습니다` | `현재는 개인투자자의 매도가 더 많습니다` |
| 등급 | `70점으로 높음 편` | `70점으로 높은 편` |

수급 방향은 해당 거래일의 현재 상태를 보고하는 값인데 과거형은 이미
끝난 사건처럼 읽힌다. 등급 label(`높음`)은 DB 저장값이므로 그대로 두고
자연어 본문에서만 `높은 편`으로 푼다.

**검증**

완화 — v12 실적재에서 정상 보고서가 걸린 두 규칙을 좁혔다.

- `유지`는 더 이상 단어나 등급 구간으로 판정하지 않는다. `높은 수준을
  유지하고 있습니다` 같은 상태 서술은 허용하고, `점수가 그대로다`처럼
  숫자가 동일하다는 주장만 `signal_change`와 대조한다
- 변화량의 기준 검사가 앞뒤 절을 넘지 않는다. `평균 52점보다는 낮지만
  어제보다 11점 높아졌습니다`가 오탐되지 않는다

강화 — v12가 통과시킨 의미 오류를 막는다.

- 수급 강도 변화 생성 (`매도 압력이 커졌다`)
- 평균 비교 주어 역전 (`평균 81점이 현재보다 낮다`)
- 숫자 역할 혼동 (변화량을 직전 거래일 점수 자리에 적음)

후속 LLM 변경은 별도 feature 브랜치에서 진행하고, 그때 다시
`prompt_version`을 올린다.
