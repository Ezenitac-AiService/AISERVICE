# PILOS 발표용 기능 설명 기준서

> 문서 상태: `main@f80fdc2` 구현 기준 최신화
>
> 기준일: 2026-08-11
>
> 용도: 발표 슬라이드·시연 대본·질의응답의 공통 근거

## 1. 한 문장 소개

PILOS는 온라인 종목 댓글을 수집·정제하고, 같은 날 개인투자자 수급과의
통계적 연관성을 방향별 Ridge 모델로 계산한 뒤, 정형 신호·LLM 브리핑·근거
기반 챗봇으로 설명하는 서비스입니다.

이 서비스는 댓글 감성 확률, 주가 전망, 미래 수급 예측 또는 투자 추천을
제공하지 않습니다.

## 2. 발표에서 보여줄 전체 흐름

```text
토스 종목 댓글 증분 수집
→ 비식별화·전처리·중복 제거
→ Kiwi 토큰화
→ 종목·날짜별 장 마감 전 댓글 일별 문서
→ 키움 개인 수급 장중 추정·장마감 확정
→ Positive·Negative Ridge v4 추론과 품질 진단
→ calibration 기반 0~100 댓글 수급 신호
→ 정형 근거 기반 v13 LLM 브리핑
→ Flask 목록·상세·단일 댓글·챗봇 화면
```

Windows 작업 스케줄러는 `run_service_pipeline.bat`를 10분마다 호출합니다.
최상위 실행기는 각 단계의 Python `run_*` 함수를 순차 호출하고, 이전 실행이
끝나지 않았으면 프로세스 잠금으로 중복 실행을 차단합니다.

## 3. 최종 구현 상태

| 기능 | 현재 상태 | 발표 근거 |
|---|---|---|
| 댓글 백필·증분 수집 | 적용 완료 | 작성일별 JSONL, 매니페스트·파일 경계, 종목별 실패 격리 |
| 전처리 | 적용 완료 | 원문 추적, 비식별화, 표준 컬럼, 중복 제거, DB 증분 적재 |
| Kiwi 토큰화 | 적용 완료 | `kiwi_ver1`, 미토큰화 대상만 적재 |
| 일별 문서 | 적용 완료 | 종목·날짜·토큰 버전별 15:30 이전 댓글 스냅샷 |
| 개인 수급 | 적용 완료 | 장중 estimated, 장마감 confirmed, 강등 금지 |
| Ridge v4 | 적용 완료 | Positive·Negative text-only 방향별 모델 |
| DB 추론 | 적용 완료 | 활성 artifact 기준 미완료 대상, 품질 3필드, 원자적 INSERT |
| 댓글 수급 신호 | 적용 완료 | 실제 수급 방향 + 방향별 calibration 0~100 상대 신호 |
| v13 LLM 보고서 | 적용 완료 | 정형 근거, validator, deterministic fallback, 제한적 수급 갱신 |
| Flask·프론트 | 적용 완료 | 목록·상세·이력·단일 댓글·챗봇·파이프라인 상태 |
| 근거 기반 챗봇 | 적용 완료 | MySQL 확정 수치, 저장 v13, 서비스 문서 RAG |
| 최상위 자동화 | 적용 완료 | 배치·CLI, 중복 잠금, 단계 중단, 로그와 DB 상태 |

## 4. 댓글 수집과 전처리

### 해결한 문제

한 번의 대량 수집이 중단되거나 10분 주기로 반복 실행되어도 빠진 구간과
중복을 통제해야 했습니다. 또한 원본을 보존하면서 분석용 표준 데이터만 DB에
적재해야 했습니다.

### 구현 방식

- 원본 댓글은 수정하지 않고 `data/raw`의 JSONL에 append합니다.
- 백필은 페이지 커서를, 증분은 최신 댓글 ID 경계를 매니페스트로 관리합니다.
- 증분 경계는 정상 종료했을 때만 앞으로 이동합니다.
- 원본 파일의 `raw_line_number`를 watermark로 사용해 새 줄만 전처리합니다.
- 비식별화 솔트는 저장소 루트 `.env`를 최상위 실행기가 단계 import 전에 읽습니다.
- 전처리는 필수값·빈 텍스트 제거, 종목코드·시각 정규화, 제목·본문 결합,
  소셜 표현 정규화와 `comment_id` 중복 제거를 수행합니다.
- 한 종목 또는 한 파일 실패는 요약에 남기며, 부분 실패가 있으면 후속 토큰화
  이후 단계는 시작하지 않습니다.

### 발표 표현

> 원본은 append-only로 보존하고, 처리 위치와 최신 댓글 경계를 별도로 기록해
> 중단 후에도 이어서 수집하고 전처리할 수 있게 했습니다.

## 5. 토큰화와 일별 문서

- 현재 서비스 토큰 계약은 `kiwi_ver1`입니다.
- 토큰의 `form`만 TF-IDF 입력으로 사용하며 복합 표현 내부 공백은 `_`로 보존합니다.
- 토큰화 결과는 `(preprocessed_comment_id, tokenizer_version)` 기준으로 멱등 적재합니다.
- 일별 문서는 같은 종목·날짜에서 15:30 이전 댓글만 사용합니다.
- 문서 내용·댓글 수·구성 댓글 ID를 포함한 SHA-256 `document_hash`로 스냅샷을
  식별합니다.
- 신규 댓글이 장 마감 이후 작성됐다면 토큰화까지는 되지만 당일 일별 문서를
  다시 만들지 않습니다.

### 발표 표현

> 댓글 하나를 바로 예측하는 대신, 거래일과 종목 단위로 댓글을 묶어 같은 날
> 수급과 비교할 수 있는 재현 가능한 분석 문서를 만듭니다.

## 6. 개인투자자 수급

### 장중 추정

키움 `ka10063`의 외국인·기관·기타법인 매수·매도량을 전체 누적 거래량에서
제외한 잔차로 개인 수급을 추정합니다. 원천 거래량의 차이와 품질 진단값을 함께
보존합니다.

### 장마감 확정

키움 `ka10060`의 개인 매수·매도량을 사용합니다. 확정값이 적재되면 current
값을 교체하지만 estimated 원천 이력은 보존합니다. confirmed 행을 이후 estimated
실행으로 낮추지 않습니다.

```text
supply_demand_index = (buy_volume - sell_volume) / (buy_volume + sell_volume)
```

### 발표 표현

> 장중에는 추정값으로 현재 상황을 보여주고, 장마감 후에는 확정값으로 승격합니다.
> 모델 학습 라벨은 confirmed 데이터만 사용합니다.

## 7. 방향별 Ridge v4 모델

- 모델명: `ridge_supply`
- 모델 버전: `4`
- 방향: `positive`, `negative`
- 입력: 일별 문서의 TF-IDF text-only 희소행렬
- 알고리즘: Ridge, `alpha=1.0`, `solver=lsqr`
- 모델 bundle: 학습된 Vectorizer와 Ridge를 스키마 2로 함께 저장

Positive 모델은 실제 개인 수급지수가 양수인 국면, Negative 모델은 음수인
국면에서 댓글 표현과 수급지수의 관계를 각각 학습합니다. 실제 수급지수,
종목코드, 날짜와 댓글 수는 v4 입력 특성에 넣지 않습니다.

공식 내부 검증은 월별 층화 날짜 그룹 80:20 분할을 시드 42~46에서 반복했고,
최종 서비스 bundle은 2026-07-24까지 전체 Dataset으로 다시 학습했습니다.

### 발표 표현

> 단어가 각 수급 방향의 과거 국면과 어느 정도 연관됐는지 설명할 수 있도록
> 해석 가능한 선형 Ridge 모델을 선택했습니다.

## 8. 추론 품질과 저장

운영 대상은 2026-07-25부터 실행 당일 KST까지입니다. 서비스 버전과 방향으로
DB artifact를 조회한 뒤 로컬 bundle의 전체 identity를 검증합니다. artifact ID
7·8은 기존 환경의 실행 이력일 뿐 코드에 고정하지 않습니다.

신규 결과에는 다음 품질값을 저장합니다.

```text
recognized_feature_count
unique_token_count
vocabulary_coverage
inference_status = ready | insufficient_features
```

두 방향 중 하나라도 활성 artifact 결과가 없는 최신 일별문서만 처리합니다.
Positive·Negative 전체 계산이 성공한 뒤 한 트랜잭션으로 INSERT하며,
`(daily_document_id, artifact_id)` 기존 결과는 UPDATE하지 않습니다. 대상 0건은
오류가 아니라 정상 성공입니다.

### 발표 표현

> 단순히 점수만 저장하지 않고 현재 문서가 모델 어휘를 얼마나 인식했는지 함께
> 기록해, 근거가 부족한 결과를 정상 결과와 구분합니다.

## 9. 댓글 수급 신호와 v13 브리핑

Ridge raw 점수는 같은 방향 모델의 과거 재추론 분포와 비교해 0~100으로
calibration합니다.

```text
Positive 방향: percentile
Negative 방향: 100 - percentile
```

실제 수급 부호가 BUY·SELL·NEUTRAL 방향을 결정하며, 신호 점수는 방향을
결정하지 않습니다. `50`은 감성 중립이 아니라 과거 동일 방향 출력 분포의
중간 수준입니다.

v13 LLM은 다음 정형 근거만 설명합니다.

- 실제 개인 수급 방향과 수급지수
- 댓글 수급 신호 점수와 등급
- 직전 거래일 대비 변화
- 직전 최대 5거래일 평균
- 댓글 수와 수급 관측 상태

LLM 응답은 수치·등급·비교 방향·전망·투자 권유 금지 계약을 검증합니다.
응답 검증 2회 실패 시 deterministic fallback을 저장하고, 실제 LLM 호출 자체가
실패한 대상은 저장하지 않습니다. 기존 v2~v12 보고서는 수정하지 않습니다.

같은 v13은 `estimated→confirmed` 또는 더 최신 estimated 관측에만 UPDATE하고,
confirmed를 estimated로 낮추지 않습니다.

### 발표 검증 근거

- v13 기준 검수 90행: LLM 79행, deterministic 11행
- validator가 잘못된 LLM 출력 7건을 저장 전에 차단
- 최종 90행의 수급 방향·모델 방향·비교 수치 계약 위반 0건

## 10. Flask와 사용자 화면

### API

```text
GET  /api/stocks
GET  /api/stocks/<stock_code>
GET  /api/stocks/<stock_code>/llm-reports?model_date=YYYY-MM-DD
POST /api/inference/single-comment
POST /api/chat
POST /api/stocks/<stock_code>/chat
GET  /api/pipeline/status
```

### 화면

- 종목명·코드 검색, 최근 조회, 전체 목록 정렬·필터
- 최신 수급·두 방향 모델 점수·품질·estimated/confirmed 상태
- 날짜별 상세 이력과 기여 키워드
- v13 신호·해설·결론·주의 문구와 보고서 갱신 대기
- 단일 댓글의 Positive·Negative text score와 기여 표현
- 챗봇 질문 블록·종목·기준일 선택, 답변·출처·warning
- 최상위 파이프라인 최신 상태를 30초마다 polling

단일 댓글 결과에는 일별 calibration을 적용하지 않으며 0~100 공식 신호처럼
표시하지 않습니다.

## 11. 근거 기반 챗봇

| 질문 종류 | 근거 | 외부 LLM 사용 |
|---|---|---|
| 정확 수치 | MySQL confirmed 수급 | 사용하지 않음 |
| 종목 분석 | 저장된 현재 v13 보고서 | 새 호출 없이 저장 결과 사용 |
| 서비스 설명 | 승인 Markdown의 Chroma RAG | embedding·reranker·LLM 사용 |

공개 응답은 답변과 함께 근거 type·label·version·기준일 및 warning을 제공합니다.
내부 chunk ID, 검색 점수, Chroma 경로와 비밀 설정은 표시하지 않습니다.

현재 공개 UI는 자유문장을 받지 않고 서버에 등록된 `block_key`만 선택합니다.
공용 화면은 `/api/chat`, 종목 상세 화면은 URL의 종목코드를 고정하는
`/api/stocks/<stock_code>/chat`을 사용합니다. 임의 `message`, `action`, `metric`은
400으로 거절됩니다. 따라서 코드에 남은 `general`·`restricted` 분기와 종목 순위
handler는 현재 시연 가능한 공개 질문 경로가 아닙니다.

현재 로컬 `artifacts/rag_chroma`에는 활성 서비스 문서 버전의 completed chunk가
존재하며, 별도 실행한 실제 RAG E2E 4개가 통과한 이력이 있습니다. 기본 비DB
테스트에서는 외부 호출 방지를 위해 이 4개를 skip합니다.

## 12. 최상위 자동화와 운영 상태

실행 명령은 다음 두 방식입니다.

```powershell
run_service_pipeline.bat

.\.venv\Scripts\python.exe -m pilos.jobs.run_service_pipeline --target all
```

`--target`은 `all`, `sk`, `others`를 허용합니다. Windows 작업 스케줄러에서는
프로그램에 `run_service_pipeline.bat` 절대경로를 지정하고 시작 위치에 저장소
루트를 지정합니다. 작업이 이미 실행 중이면 새 인스턴스를 시작하지 않도록 설정합니다.

### 2026-08-10 실제 실행

| 실행 | 결과 | 주요 내용 |
|---|---|---|
| 실행 ID 1 | completed, 2,083초 | 댓글 15,283건 수집, 전처리·토큰화 14,227건, 문서 10건, 추론 20건, 보고서 신규 20건 |
| 실행 ID 2 | completed, 95초 | 댓글 438건 수집, 전처리·토큰화 384건, 수급 already_confirmed, 추론 0건, 보고서 기존 100건 |

두 번째 정상 증분 실행은 10분 주기 안에 완료됐습니다. 첫 대량 실행이 10분을
넘는 동안 다음 스케줄 실행이 겹쳐 시작되지 않았고, 완료 후 다음 주기에 다시
정상 실행됐습니다.

## 13. 검증 현황

- 2026-08-11 전체 테스트: 437개 실행, 11 failures, 88 errors, RAG E2E 4개 skip
- `test_chat*` 제외: 375개 통과
- 현행 질문 블록 API test-client smoke: 6개 통과
- 실패 범위: 구 `message/action/metric` 챗봇 테스트와 현행 `block_key` 구현의 계약 drift
- 2026-08-10 과거 기준: 394개 실행, 390개 통과, RAG E2E 4개 skip
- 실제 RAG E2E: 별도 환경에서 4개 통과 이력
- 실제 DB 읽기 전용 `/api/stocks`: 10종목 HTTP 200
- 실제 종목 상세: HTTP 200, 품질 필드·날짜 이력 확인
- 실제 v13 보고서: ready·insufficient_evidence·inference_pending·report_pending 확인
- 실제 최상위 파이프라인: 실행 ID 1·2 completed
- JavaScript 4개 파일 문법 검사 통과
- 브라우저 PC·모바일 시각 검수: 발표 환경에서 최종 확인 필요

테스트 로그의 의도된 mock 예외는 실제 운영 장애로 해석하지 않습니다.

## 14. 시연 권장 순서

1. 메인 화면에서 파이프라인 `갱신 완료` 상태와 전체 종목을 보여줍니다.
2. 종목을 검색하고 상세 화면으로 이동합니다.
3. 실제 수급, Positive·Negative 결과, 품질 상태를 설명합니다.
4. v13 `ready` 날짜를 선택해 신호·전일 대비·5거래일 평균·해설을 보여줍니다.
5. 단일 댓글 체험에서 두 방향 모델 반응이 다름을 보여줍니다.
6. 질문 트리에서 확정 수급지수, 저장 분석, 서비스 설명 블록을 각각 선택합니다.
7. 상세 화면에서는 종목이 URL 문맥으로 고정되고 날짜만 선택하는 동작을 보여줍니다.

최신 날짜가 `report_pending`일 수 있으므로 시연 전에 `ready` 날짜를 확인합니다.
2026-08-05 SK하이닉스는 실제 조회에서 `ready`였고, 2026-08-06은
`insufficient_evidence` 상태 확인에 사용할 수 있습니다.

## 15. 발표에서 지켜야 할 표현

### 사용

- 댓글 기반 수급 연계 신호
- 같은 날 댓글 표현과 개인 수급의 통계적 연관성
- 과거 동일 방향 모델 출력 분포 대비 상대 수준
- 저장된 수치와 승인 문서를 근거로 한 설명
- 장중 추정과 장마감 확정

### 사용하지 않음

- 긍정·부정 감성 확률
- 주가 상승·하락 예측
- 미래 개인 수급 예측
- 매수·매도 추천
- LLM이 시장 원인을 분석했다
- 모든 실행이 항상 10분 이내 완료된다

## 16. 현재 한계와 발표 이후 과제

- 첫 대량 증분 수집은 10분을 넘을 수 있으며 종목별 수집량에 영향을 받습니다.
- 매니페스트 날짜 공백은 경고만 제공하고 자동 재수집하지 않습니다.
- 원본 watermark는 JSONL append-only 전제에 의존합니다.
- 과거 품질 필드 NULL 행은 운영 backfill하지 않았습니다.
- v13 자연어의 의미 확장·문체 반복은 별도 검토 문서의 발표 이후 개선사항입니다.
- 장기 대화 기억, 임의 종목 순위, 미래 전망 챗봇은 구현하지 않았습니다.
- 구 챗봇 테스트·D-021 계약과 현재 `block_key` 공개 입력 사이의 drift가 남아 있습니다.
- 운영 배포·인증·권한·HTTPS는 현재 발표용 로컬 서비스 범위 밖입니다.
- PC·모바일 브라우저의 최종 디자인·시각 검수는 아직 완료 근거가 없습니다.

## 17. 근거 문서

- [`../ARCHITECTURE.md`](../ARCHITECTURE.md)
- [`../DATA_CONTRACT.md`](../DATA_CONTRACT.md)
- [`../DECISIONS.md`](../DECISIONS.md)
- [`../../specs/README.md`](../../specs/README.md)
- [`../../specs/service-pipeline-automation.md`](../../specs/service-pipeline-automation.md)
- [`../../specs/sentiment-flask-web-integration.md`](../../specs/sentiment-flask-web-integration.md)
- [`../../specs/chatbot-service.md`](../../specs/chatbot-service.md)
- [`../v13_LLM_보고서_검토_및_향후_개선사항.docx`](../v13_LLM_보고서_검토_및_향후_개선사항.docx)
