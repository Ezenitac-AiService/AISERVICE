# PILOS Sentiment Index

종목별 커뮤니티 댓글 표현과 실제 시장 수급의 통계적 연관성을 학습하여, 최근 댓글에서 나타나는 **매수 우세·매도 우세 언어 경향**을 종목별 심리지수로 제공하는 4인 팀 프로젝트입니다.

댓글은 형태소 분석과 TF-IDF를 통해 벡터화하고, 동일 종목·거래일의 댓글 표현을 실제 일별 매수·매도 수급 기준값과 연결하여 Ridge Regression 모델을 학습합니다.

학습된 형태소·단어별 회귀계수는 과거 시장 수급과의 연관 가중치로
사용합니다. 신규 종목·거래일별 댓글 문서에는 같은 Vectorizer와 Ridge를
적용하여 수급 연관성 점수와 주요 기여 표현을 제공합니다.

> 이 프로젝트는 일반적인 긍정·부정 감성분류, 미래 주가·수급 예측 또는 매수·매도 추천을 목적으로 하지 않습니다.

---

## 현재 구현 상태

### 서비스 기능 통합 완료

2026-08-11 `main@f80fdc2`에는 다음 서비스 기능과 실행 계약이 통합돼 있습니다.

- 댓글 백필·증분 수집과 원본 JSONL·매니페스트 관리
- 댓글 전처리·Kiwi 토큰화와 종목·거래일별 일별문서 생성
- 키움 API 기반 개인투자자 수급 추정·확정 수집과 DB 적재
- 일별문서와 같은 종목·거래일의 수급지수 연결
- Ridge와 ElasticNet 후보의 워크포워드·날짜 그룹 랜덤 비교
- Positive·Negative 모두 Ridge text-only `alpha=1` 선정
- `2025-01-02~2026-07-24` 전체 Dataset으로 모델 버전 4 재학습
- 모델 스키마 2 bundle 저장과 DB `artifacts` 등록
- 수급 데이터가 존재하는 거래일 일별문서 추론
- 방향별 점수와 상위 키워드 contribution 계산
- `sentiment_index_result` DB 적재와 중복 방지 재실행 검증
- calibration·0~100 댓글 수급 신호·`market_commentary_v13` 보고서 생성
- Flask 종목 목록·상세·저장 보고서 조회 API와 화면
- 서버 allowlist 질문 블록으로 제한한 정확 수치·저장 v13 보고서·서비스 문서 RAG 기반 챗봇
- 단일 댓글 체험, 파이프라인 상태 표시와 프론트 데이터 연결
- 댓글 수집부터 v13 보고서까지 최상위 자동화 실행기

위 항목의 “통합 완료”는 현재 코드와 기능별 테스트가 병합됐다는 뜻입니다.
2026-08-10 실제 서비스 파이프라인은 초기 증분 실행과 후속 정상 증분 실행을
모두 완료했습니다. 환경별 DB·LLM 검증 이력은 각 기능 명세에 보존합니다.

공식 날짜 그룹 랜덤 검증 평균 R²는 Positive `0.206797`, Negative
`0.221247`입니다. 이 수치는 미래 예측력이 아니라 보유 Dataset 내부의
당일 댓글 표현과 당일 수급지수 연관성 재현 지표입니다. 상세한 실험
설계·MAE·RMSE·워크포워드 한계는
[`docs/MODEL_EXPERIMENT_RESULTS.md`](docs/MODEL_EXPERIMENT_RESULTS.md)를
확인합니다.

현재 서비스 모델 v4는 `tokenizer_version=kiwi_ver1`과 확정된 TF-IDF
설정으로 재현합니다. Kiwi와 설정을 바꾸는 후속 실험은 기존 v4를
수정하지 않고 새 모델 버전으로 수행합니다.

### 발표 전 남은 확인

기능 구현과 데이터 연결은 완료됐습니다. 발표 전에는 실제 PC·모바일 브라우저의
시각 검수와 Windows 작업 스케줄러의 반복 운영 상태를 확인합니다. 또한 PR #16에서
공개 챗봇 입력이 `block_key` 방식으로 바뀐 뒤 남은 구 `message/action/metric`
테스트와 D-021 공개 계약의 차이를 해소해야 합니다. 모델 재학습은 자동 운영
파이프라인에 포함하지 않습니다.

---

## 1. 프로젝트 목표

종목별 댓글 표현과 실제 시장 수급의 연관성을 학습하여 다음 결과를 제공하는 AI 서비스를 개발합니다.

- 최근 댓글의 매수 우세·매도 우세 언어 경향
- 종목별 댓글 심리지수
- 거래일별 심리지수 변화
- 심리지수에 크게 기여한 형태소와 표현
- 단일 댓글에 대한 두 방향 모델의 텍스트 기여 반응
- 대규모 언어 모델(LLM)을 활용한 정형 일별 결과 설명

모델은 과거 시장 수급이 매수 우세였던 날과 매도 우세였던 날에 어떤 단어와 표현이 반복적으로 나타났는지를 학습합니다.

댓글이 실제 매매 행동을 일으켰다는 인과관계나 댓글 내용의 진위 여부는 판단하지 않습니다.

---

## 2. 모델 정의

### 모델이 학습하는 것

모델은 **종목·거래일별 댓글 표현**과 같은 종목·거래일의 **실제 시장 수급 기준값** 사이의 통계적 연관성을 학습합니다.

시장 수급 기준값은 일별 매수량과 매도량을 이용하여 다음 형태의 연속값으로 생성합니다.

```text
수급 기준값 = (매수량 - 매도량) / (매수량 + 매도량)
```

현재 개인투자자 확정값은 키움 `ka10060`의 매수·매도 조회 결과를 사용합니다.
매수량과 매도량이 모두 `0`이면 지수를 만들지 않고 오류로 처리합니다. 장중 추정과
장마감 확정 원천·상태의 상세 계약은 [`docs/DATA_CONTRACT.md`](docs/DATA_CONTRACT.md)를
확인합니다.

### 학습 입력과 정답

| 구분 | 정의 |
|---|---|
| 기본 입력 단위 | 동일 종목·거래일 댓글 토큰을 합친 최신 일별문서 |
| 학습 입력 X | 일별문서 `tfidf_text`의 TF-IDF 희소벡터 |
| 학습 정답 Y | 동일 종목·거래일의 실제 시장 수급 기준값 |
| 최종 서비스 모델 | 방향별 Ridge Regression, text-only, alpha=1 |
| 비교·한계 확인 | ElasticNet 후보와 워크포워드 검증 |

### 모델이 추론하는 것

현재 서비스 추론값은 종목·거래일별 일별 댓글 문서가 과거 매수 우세
또는 매도 우세 수급 국면에서 나타난 언어 패턴과 얼마나 연관되는지를
나타내는 연속값입니다. Positive와 Negative 모델이 같은 문서를 각각
분석합니다.

- **양수 방향**: 과거 매수 우세 수급과 연관된 표현 경향
- **음수 방향**: 과거 매도 우세 수급과 연관된 표현 경향
- **0 부근**: 어느 방향과도 강하게 연결되지 않은 표현 경향

이 값은 미래 시장 예측값이나 실제 매수·매도 행동 확률이 아닙니다.

---

## 3. 프로젝트가 하지 않는 것

PILOS Sentiment Index는 다음 기능을 목적으로 하지 않습니다.

- 일반적인 긍정·부정 감성분류
- 미래 주가 예측
- 미래 시장 수급 예측
- 실제 매수·매도 확률 추정
- 투자 종목 추천
- 매수·매도 시점 추천
- 댓글이 매매 행동을 발생시켰다는 인과관계 주장
- 댓글 내용의 사실 여부나 진위 판단

서비스 결과는 투자 판단을 대신하는 예측이나 권유가 아니라, 최근 댓글 표현이 과거 시장 수급과 어떤 방향으로 연관되어 나타났는지를 보여주는 분석 지표입니다.

---

## 4. 전체 처리 흐름

```text
종목별 댓글 데이터 수집
        │
        ├── 원본 보존
        │
        ▼
일별 매수·매도 수급 데이터 수집
        │
        ├── 원본 필드 검증
        │
        ▼
댓글과 수급 데이터 연결
(stock_code + trading_date)
        │
        ▼
댓글 전처리·형태소 분석
        │
        ▼
종목·거래일별 토큰 일별문서 생성
        │
        ▼
일별문서 TF-IDF 벡터화
        │
        ▼
일별 시장 수급 기준값 결합
        │
        ▼
Ridge·ElasticNet 후보 검증
        │
        ▼
Ridge text-only 최종 선정·전체 재학습
        │
        ▼
모델 bundle·artifacts 저장
        │
        ▼
신규 거래일 일별문서 방향별 추론
        │
        ├── 수급 연관성 점수
        └── 주요 단어 contribution
        │
        ▼
sentiment_index_result 저장
        │
        ▼
calibration 기반 0~100 상대 신호
        │
        ▼
v13 LLM 보고서 생성·검증·저장
        │
        ▼
Flask 웹 서비스와 질문 블록 기반 챗봇
```

---

## 5. 필수 구현 범위

1. 종목별 댓글 데이터 수집과 원본 보존
2. 종목별 일일 매수·매도 수급 데이터 수집과 원본 필드 검증
3. 댓글과 일별 수급 데이터를 `stock_code + trading_date`로 연결한 Dataset 생성
4. 댓글 전처리와 형태소 분석 파이프라인 구현
5. 종목·거래일별 댓글 토큰을 합친 일별문서 생성
6. 학습 일별문서를 기준으로 공통 TF-IDF 어휘사전과 IDF 생성
7. 일별 시장 수급 기준값 Y 생성
8. TF-IDF와 Ridge Regression 기반 Baseline 모델 학습 및 평가
9. 형태소·단어별 회귀계수와 시장 수급 연관 단어 가중치 추출
10. 신규 일별문서의 방향별 시장 수급 연관성 점수 추론
11. 일별문서 점수와 주요 단어 contribution 저장 및 조회
12. 모델 bundle과 평가·버전 메타데이터 저장 및 조회
13. Flask 기반 심리지수·주요 기여 표현·거래일별 이력 시각화
14. 대규모 언어 모델(LLM)을 활용한 결과 설명

현재 1~14와 프론트 데이터 연결·챗봇·최상위 자동화 실행기는 `main`에
통합돼 있습니다. 목표·우선순위의 최종 정본은 Notion 기획안입니다.

---

## 6. 프로젝트 구조

프로젝트는 기술 종류가 아니라 **책임**을 기준으로 분리합니다.

```text
pilos/
├── collection/
│   └── ai_clients/
├── analysis/
│   ├── modeling/
│   └── rag/
├── storage/
├── jobs/
│   └── maintenance/
├── dto/
├── service/
└── web/
tests/
└── collection/
notebooks/
├── pipeline/
└── llm/
```

### `collection`

외부 데이터 소스에서 데이터를 가져옵니다.

- 종목별 댓글 수집
- 일별 매수·매도 수급 데이터 수집
- 외부 API 요청과 응답 처리
- 원본 데이터 반환
- 실패·재시도·재수집 관리

수집 데이터를 직접 전처리하거나 저장하지 않습니다.

### `analysis`

데이터를 분석 가능한 형태로 가공하고 모델을 학습·평가·추론합니다.

- 댓글 전처리
- 형태소 분석
- 사용자 사전 적용
- TF-IDF 벡터화
- 종목·거래일별 토큰 일별문서 생성
- 시장 수급 기준값 생성
- Dataset 생성
- Ridge·ElasticNet 학습과 평가
- 단어별 회귀계수 해석
- 신규 일별문서 방향별 점수 추론
- 단어별 contribution 해석

분석 결과를 직접 저장하지 않습니다.

### `storage`

데이터와 모델 산출물의 저장·조회를 담당합니다.

- 원본 JSON
- 전처리 데이터
- 학습 Dataset
- 버전별 모델 bundle과 평가 메타데이터
- 모델 bundle에 포함된 TF-IDF 어휘사전과 IDF
- 단어별 회귀계수
- 일별문서 수급 연관성 점수와 기여 키워드
- MySQL 저장과 조회

저장 과정에서 수집·전처리·모델 추론을 수행하지 않습니다.

### `jobs`

수집·분석·저장의 실행 순서를 관리합니다.

```text
collection
    ↓
storage
    ↓
analysis
    ↓
storage
```

각 영역의 내부 구현을 대신하지 않고, 필요한 기능을 호출하여 전체 파이프라인을 구성합니다.

### `dto`

영역 사이에서 명확한 전달 계약이 필요할 때 사용합니다.

DTO는 모든 함수 사이에서 의무적으로 사용하지 않습니다. `analysis` 내부에서는 DataFrame, Series, NumPy 배열, 희소행렬 등 분석 라이브러리의 자료형을 직접 사용할 수 있습니다.

### `web`

분석 결과를 사용자에게 제공하는 Flask 서비스 영역입니다.

- 종목별 심리지수
- 거래일별 심리지수 이력
- 개인투자자 수급 추정·확정 상태와 관측 시각
- 주요 기여 표현
- 단일 댓글의 Positive·Negative 텍스트 기여 반응
- 저장된 v13 LLM 보고서
- 서버에 등록된 질문 블록 기반 분석 도우미
- 최상위 파이프라인 상태

현재 JSON API와 화면 전달 계약은
[`specs/sentiment-flask-web-integration.md`](specs/sentiment-flask-web-integration.md),
챗봇 계약은 [`specs/chatbot-service.md`](specs/chatbot-service.md)에서 확인합니다.

---

## 7. 책임 분리 원칙

```text
collection은 수집만 한다.
analysis는 분석만 한다.
storage는 저장과 조회만 담당한다.
jobs는 실행 흐름만 관리한다.
dto는 영역 경계에서만 사용한다.
web은 분석 결과를 사용자에게 제공한다.
```

구조와 의존 방향의 정본은 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)입니다.

구조를 선택한 이유와 변경 이력은 [`docs/DECISIONS.md`](docs/DECISIONS.md)에서 관리합니다.

---

## 8. 개발 환경

### 공통 환경

- Python 3.12
- `uv`
- `.venv`
- Git
- GitHub

### Windows

주로 다음 작업에 사용합니다.

- 데이터 확인과 전처리
- 소규모 모델 실험
- Flask 개발
- 화면 구현
- 저장·조회 기능
- MySQL 연동
- 발표 환경 검증

### 원격 AI 서비스

현재 v4 모델은 scikit-learn Ridge 기반이며 GPU를 요구하지 않습니다. LLM 보고서,
embedding과 reranker는 `.env`에 설정한 OpenAI 호환 원격 endpoint를 사용합니다.
특정 공급자·GPU 서버나 BERT 모델은 현재 서비스 계약으로 고정하지 않습니다.

---

## 9. 개발 환경 준비

저장소 루트에서 가상환경을 생성합니다.

```bash
uv venv --python 3.12
```

### Windows PowerShell

```powershell
.\.venv\Scripts\Activate.ps1
```

### Linux

```bash
source .venv/bin/activate
```

프로젝트 의존성이 정의된 경우 다음 명령으로 설치합니다.

```bash
uv sync
```

---

## 10. 실행 방법

저장소 루트에서 다음 명령을 실행합니다.

Flask 웹 서비스는 다음 명령으로 시작합니다.

```powershell
uv run flask --app pilos.web.app run
```

페이지 경로는 `/`, `/stocks/<stock_code>`, `/about`이며 JSON API 목록은
[`specs/sentiment-flask-web-integration.md`](specs/sentiment-flask-web-integration.md)를
확인합니다.

운영 파이프라인은 Windows 배치 파일 또는 같은 Python CLI로 실행합니다.

```powershell
.\run_service_pipeline.bat
uv run python -m pilos.jobs.run_service_pipeline --target all
```

두 진입점은 같은 최상위 실행기를 사용합니다. 최상위 실행기는 프로세스 잠금으로
중복 실행을 막고, 단계별 실패 시 뒤 단계를 중단하며, 실행 상태를
`service_pipeline_run`과 `logs/service_pipeline_YYYY-MM-DD.log`에 남깁니다.
Windows 작업 스케줄러에서는 저장소 루트의 배치 파일을 호출합니다.

기능별 확인이나 제한된 수동 운영에는 각 실행기를 독립적으로 사용할 수 있습니다.

```powershell
uv run python -m pilos.jobs.incremental_comments --target sk
uv run python -m pilos.jobs.preprocess_comments
uv run python -m pilos.jobs.tokenize_comments
uv run python -m pilos.jobs.build_daily_documents
uv run python -m pilos.jobs.collect_supply_demand --action auto
```

수급 수집은 환경설정과 키움 API·DB 연결이 필요합니다. 댓글 수집 대상은
`--target sk` 또는 `--target others`로 나눌 수 있습니다.

최종 선정 설정으로 두 방향을 반복 검증하고 전체 Dataset으로 재학습한
뒤, 모델 bundle과 DB 아티팩트를 등록합니다.

```powershell
uv run python -m pilos.jobs.train_model
```

등록된 모델 버전을 불러와 설정 기간의 거래일 일별문서를 추론하고
`sentiment_index_result`에 신규 결과만 저장합니다.

```powershell
uv run python -m pilos.jobs.predict_model
```

학습 명령은 같은 모델 버전의 파일이나 DB 행을 덮어쓰지 않습니다.
추론 명령은 같은 일별문서·아티팩트 결과가 이미 존재하면 기존 결과로
분류하고 UPDATE하지 않습니다. 실행 전 `.env`의 DB 설정과 대상 기간을
확인합니다.

댓글 수급 신호 calibration과 LLM 보고서는 별도 실행기입니다.

```powershell
uv run python -m pilos.jobs.export_ridge_v4_training_reinference
uv run python -m pilos.jobs.build_signal_calibration
uv run python -m pilos.jobs.generate_llm_reports --start-date YYYY-MM-DD --end-date YYYY-MM-DD
```

`generate_llm_reports`에는 DB, 모델과 calibration artifact가 필요합니다.
비교 이력이 없거나 신호를 계산할 수 없는 대상은 deterministic 보고서를
저장할 수 있지만, LLM 생성 대상에는 외부 LLM 서버 연결이 필요합니다.

전체 자동 테스트는 명시적으로 `tests`를 탐색해 실행합니다.

```powershell
uv run python -m unittest discover -s tests -p "test_*.py"
```

실제 Chroma·embedding·reranker·LLM을 호출하는 RAG E2E 4건은 기본 테스트에서
건너뛰며, 해당 서비스가 준비된 환경에서만 `RUN_RAG_E2E=1`로 별도 실행합니다.

2026-08-11 `main@f80fdc2` 재검증에서는 전체 437건 중 11건 실패, 88건 오류,
4건 skip이 발생했습니다. 실패·오류는 현행 `block_key` 공개 입력과 구
`message/action/metric` 챗봇 테스트의 계약 drift에 집중돼 있습니다. 같은 환경에서
파일명이 `test_chat*`인 테스트를 제외한 375건은 통과했습니다. 따라서 현재 상태를
“전체 테스트 통과”로 표현하지 않습니다.

과거 원본 파일을 처음 등록하고 미처리분을 전체 전처리하는 유지보수 명령은
일상 운영 파이프라인과 분리돼 있습니다.

```powershell
uv run python -m pilos.jobs.maintenance.initialize_comment_data
uv run python -m pilos.jobs.maintenance.rebuild_comment_manifest
```

---

## 11. 문서 정본

하나의 사실은 가능한 한 하나의 정본에서만 관리합니다.

| 확인할 내용 | 정본 |
|---|---|
| 프로젝트 목표·필수 구현 범위·우선순위·담당자 | [Notion 현재 기획](https://app.notion.com/p/3a5d365a80b481c792c0da2c1b4cdcb5) |
| 논의 중인 제안·결정 대기·적용 현황 | [Notion 결정 대기 및 적용 현황](https://app.notion.com/p/3a5d365a80b481319695f4e3579006ec) |
| 프로젝트 소개·환경 준비·검증된 실행 명령 | 이 `README.md` |
| 폴더 구조·파일 배치·의존 방향 | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| 데이터 의미·라벨·상태·필드 | [`docs/DATA_CONTRACT.md`](docs/DATA_CONTRACT.md) |
| 브랜치·커밋·PR 운영 방식 | [`docs/GIT_WORKFLOW.md`](docs/GIT_WORKFLOW.md) |
| 적용된 기술 결정과 변경 이력 | [`docs/DECISIONS.md`](docs/DECISIONS.md) |
| AI 에이전트의 작업 규칙 | [`AGENTS.md`](AGENTS.md) |

Notion은 목표, 범위, 역할, 우선순위와 의사결정 상태를 관리합니다.

저장소 문서는 현재 코드가 따라야 하는 구조, 데이터와 협업 기준을 관리합니다.

정본끼리 충돌하는 경우 임의로 내용을 섞거나 우선순위를 판단하지 않고 팀장에게 확인합니다.

---

## 12. Git 작업 방식

기본 작업 흐름은 다음과 같습니다.

```text
develop 최신화
    ↓
feature 브랜치 생성
    ↓
기능 구현 및 검증
    ↓
커밋
    ↓
원격 브랜치 push
    ↓
Pull Request
    ↓
검토 후 develop 병합
```

구체적인 브랜치, 커밋과 Pull Request 규칙은 [`docs/GIT_WORKFLOW.md`](docs/GIT_WORKFLOW.md)를 따릅니다.

---

## 13. Git에 올리지 않는 항목

다음 항목은 저장소에 커밋하지 않습니다.

- `.env`
- API Key
- DB 계정과 인증정보
- `.venv`
- Python 캐시
- 실행 로그
- 실제 원본 데이터
- 라벨링 데이터
- 학습·추론·집계 데이터
- 개인정보 또는 식별정보가 포함된 자료
- 모델 가중치
- 체크포인트
- 개인 IDE 설정

구체적인 데이터 취급 기준은 [`docs/DATA_CONTRACT.md`](docs/DATA_CONTRACT.md)와 `data/README.md`를 확인합니다.

---

## 14. AI 에이전트 사용

팀원은 Codex, Work, ChatGPT 등 AI 도구를 개발 보조 수단으로 사용할 수 있습니다.

AI 에이전트는 작업 전에 [`AGENTS.md`](AGENTS.md)와 현재 작업에 필요한 정본 문서를 먼저 확인해야 합니다.

예시:

```text
AGENTS.md와 docs/ARCHITECTURE.md를 먼저 확인한 뒤
현재 책임 구조를 유지하면서 collection 영역을 구현한다.
```

```text
AGENTS.md와 docs/DATA_CONTRACT.md를 먼저 확인한 뒤
댓글 전처리 코드가 현재 데이터 계약을 지키는지 검토한다.
```

AI는 정본에 없는 공통 규칙, 데이터 계약이나 새로운 구조를 임의로 확정해서는 안 됩니다.

---

## 15. 후속 검토 항목

다음 항목은 현재 서비스 기준선 이후 별도 결정과 검증이 필요합니다.

- 신규 미래 구간의 워크포워드 재검증과 모델 버전 비교
- 형태소 품사 조합 비교
- unigram과 unigram·bigram 조합 비교
- TF-IDF `min_df`, `max_df`, `max_features` 조정
- 종목별 개별 모델과 다종목 통합 모델 비교
- `stock_code`의 모델 Feature 사용 실험
- 일별문서 생성·집계 방식 비교
- 댓글 수 부족 구간의 신뢰도 표시
- 시장 수급 연관 단어사전 안정성 분석
- 대상 종목 확대
- 임베딩·BERT 기반 모델과 설명 가능성 비교
- 서비스 지식 문서 버전 갱신과 Chroma 재인덱싱 운영
- `block_key` 공개 계약에 맞춘 챗봇 테스트·정본 동기화
- 대화 이력을 포함한 제한형 챗봇
- 기간별 모델 성능과 단어계수 변화 보고서
