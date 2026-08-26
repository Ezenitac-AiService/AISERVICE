# 저장소 구조와 책임

> 정본 범위: 프로젝트 폴더 구조, 책임 분리, 실행 흐름과 의존 방향
>
> 상태: 현재 기준
>
> 최초 적용일: 2026-07-22
>
> 마지막 갱신: 2026-08-10

---

# 1. 설계 원칙

이 프로젝트는 **역할(Responsibility)** 중심으로 구조를 나눕니다.

각 폴더는 하나의 책임만 가지며,
새로운 기능이 추가되어도 기존 책임을 변경하지 않는 방향을 목표로 합니다.

프로젝트가 커지기 전까지는
불필요한 추상화보다 이해하기 쉬운 구조를 우선합니다.

기본 원칙은 다음과 같습니다.

- 단일 저장소를 사용합니다.
- Python 코드는 `pilos` 아래에 둡니다.
- 핵심 계산과 입출력을 분리합니다.
- 하나의 폴더는 하나의 책임만 가집니다.
- 아직 사용하지 않는 세부 폴더는 미리 만들지 않습니다.
- 실제 구현을 통해 필요성이 확인된 뒤 구조를 확장합니다.

---

# 2. 최소 구조

```text
pilos-sentiment-index/
├─ pilos/
│  ├─ collection/
│  │  └─ ai_clients/
│  ├─ analysis/
│  │  ├─ modeling/
│  │  └─ rag/
│  ├─ storage/
│  ├─ jobs/
│  │  └─ maintenance/
│  ├─ dto/
│  ├─ service/
│  └─ web/
├─ artifacts/
├─ data/
├─ docs/
├─ specs/
├─ tests/
│  └─ collection/
└─ notebooks/
   ├─ pipeline/
   └─ llm/
```

`modeling`은 모델 학습·검증·추론 계산, `rag`는 검색 조립·재순위 계산,
`ai_clients`는 외부 AI 서버 통신을 묶는다. `maintenance`는 일상 자동화에
포함하지 않는 초기 등록·보정 도구이며, 수집 계약 테스트는 공용 `tests` 아래에서
제품 코드와 분리한다. Notebook은 실행 코드가 아니라 실험 이력으로 보존한다.

`data` 하위 경로는 작업자별 로컬 데이터 확인과 실험을 위한 위치입니다. 서비스 공통 전달 계약으로 미리 확정하지 않습니다.

`artifacts`는 학습된 모델 구성요소를 보관하는 실행 산출물 경로입니다. Python 코드 계층이 아니며 Git으로 추적하지 않습니다.

---

# 3. 폴더 책임

| 폴더 | 책임 | 예시 |
|-------|------|------|
| collection | 외부 데이터를 가져옵니다. | API 호출, 크롤링, AI client |
| storage | 저장 매체와 내부 데이터 계약 사이를 변환하고 입출력합니다. | JSON, JSONL, MySQL adapter |
| analysis | 데이터를 분석합니다. | 전처리, 토큰화, 벡터화, 모델, RAG 계산 |
| jobs | 실행 순서를 조합합니다. | Pipeline, maintenance |
| dto | 영역 사이의 전달 객체를 정의합니다. | DTO |
| service | 웹 요청의 사용 사례를 조합합니다. | 추론 요청 처리 |
| web | Flask 서비스입니다. | 화면, API |
| artifacts | 재사용할 학습 산출물을 보관합니다. | 벡터라이저, Ridge 모델 |
| specs | 기능 단위 구현·검증·통합 상태를 기록합니다. | 전처리, 토큰화, 모델, 추론 명세 |

---

## collection

collection은 외부 시스템으로부터 데이터를 가져오는 책임만 가집니다.

예시

- 토스 댓글 수집
- 주가 조회
- 외부 API 호출

collection은

- JSON 저장
- DB 저장
- 모델 추론

을 직접 수행하지 않습니다.

---

## storage

storage는 단순 파일 입출력뿐 아니라 저장 매체와 내부 데이터 계약 사이의 adapter 역할을 담당할 수 있습니다.

허용되는 작업은 다음과 같습니다.

- JSON·JSONL·MySQL 읽기와 쓰기
- camelCase를 snake_case로 변환
- 식별자를 문자열로 변환
- 종목코드 문자열과 앞자리 `0` 보장
- 저장 매체에 필요한 자료형 변환
- 직렬화와 역직렬화
- 학습 산출물 저장과 로드

storage는 분석 의미를 새로 만들지 않습니다. 다음 작업은 `analysis`의 책임입니다.

- 형태소 분석과 불용어 처리
- TF-IDF
- 모델 학습·추론
- 심리지수 계산
- 분석 의미를 만드는 파생값 계산

---

## analysis

analysis는 데이터를 분석합니다.

예시

- 전처리
- 결측 처리
- 중복 제거
- 토큰화
- 사용자 사전 적용
- TF-IDF
- 벡터화
- 모델 학습
- 모델 추론
- 평가
- 심리지수 계산

analysis는

파일을 저장하거나

DB를 직접 다루지 않습니다.

분석 결과를 사람이 확인하기 위한 제한된 검수 코드는 예외적으로 로컬 검수 산출물을 직접 만들 수 있습니다. 이 예외는 서비스 저장 계층이나 정식 실행 파이프라인을 대체하지 않습니다.

---

## jobs

jobs는 프로젝트의 실행 순서를 담당합니다.

각 기능을 직접 구현하지 않고

collection

storage

analysis

를 호출하여 하나의 작업을 완성합니다.

예시

```python
raw = storage.load()

processed = analysis.preprocess(raw)

tokens = analysis.tokenize(processed)

storage.save(tokens)
```

jobs는 실행 순서를 관리하지만

전처리나 모델 계산을 직접 구현하지 않습니다.

배치 수집, 모델 학습, 일별 집계 추론처럼 명령이나 스케줄에 따라 시작되는 작업을 조합합니다.

---

## dto

DTO는 서로 다른 담당 영역이
같은 데이터를 전달해야 할 때만 사용합니다.

분석 내부에서는

DataFrame

dict

list

등을 자유롭게 사용할 수 있습니다.

DTO는

저장 방식

모델 구조

DB

를 알지 않습니다.

---

## service

service는 Flask route가 무거워지지 않도록 웹 요청 단위의 사용 사례를 조합합니다.

예시

- 단일 댓글 추론 요청 처리
- 저장된 일별 추론 결과 조회
- 분석 결과를 DTO로 변환하여 반환

service는 HTTP 요청 파싱, 응답 렌더링, 모델 계산과 저장 입출력을 직접 구현하지 않습니다. 필요한 작업을 `storage`, `analysis`, `dto`에 위임합니다.

`jobs`가 배치·CLI 실행을 조합한다면 `service`는 요청·응답 흐름을 조합합니다.

---

## web

Flask 화면과 API를 담당합니다.

예시

- HTML
- CSS
- JavaScript
- API 응답
- 화면 렌더링

복잡한 분석·조회 흐름은 직접 구현하지 않고 `service`를 호출합니다.

---

## artifacts

artifacts는 학습 후 다시 사용할 모델 구성요소를 보관합니다.

서비스 모델 v4의 현재 대상은 다음과 같습니다.

- TF-IDF 벡터라이저
- Ridge 회귀 모델

댓글 수 특성 스케일러는 이전 bundle 계약에는 있었지만 text-only v4에는
포함하지 않습니다. 모델 버전마다 bundle 스키마와 입력 특성을 함께
검증합니다.

`artifacts/calibration`은 방향별 Ridge 출력 분포를 백분위로 보관하는 신호
calibration JSON을 둡니다. 재추론 원본이 아니라 모델 artifact 성격의
메타데이터이므로 운영 DB에 적재하지 않고 이 경로에 보관합니다. 기존
`.pkl` bundle 계약은 변경하지 않고 별도 파일로 분리합니다.

`artifacts/rag_chroma`는 승인된 서비스 설명 문서를 검색하는 챗봇용 로컬
Chroma 영속 디렉터리입니다. 모델 추론 결과나 LLM 보고서를 저장하는 곳이
아니며, `storage.vector_storage`와 `service.rag_service`를 통해서만 접근합니다.

artifacts에는 소스 코드나 계산 로직을 두지 않습니다. 직렬화와 역직렬화는 `storage`, 학습·추론 실행 조합은 `jobs` 또는 `service`가 담당합니다.

`analysis`와 `web`은 `.pkl` 파일을 직접 열지 않습니다.

---

## specs

specs는 하나의 기능이 여러 코드 영역을 사용할 때 입력·출력, 실행 흐름,
실패·재실행 계약과 검증 상태를 기능 단위로 기록합니다.

`docs`가 프로젝트 공통 구조·데이터 의미·Git 규칙·효력이 생긴 기술 결정을
관리하는 정본이라면, `specs`는 구현과 함께 갱신하는 기능 명세와 이력입니다.
기능 명세가 공통 계약을 새로 결정하거나 정본을 대체하지 않습니다. 공통
기준으로 확정된 내용은 팀장이 해당 `docs` 정본에 반영합니다.

---

# 4. 실행 흐름

배치·CLI 흐름의 실행 순서는 `jobs`가 담당합니다.

현재 병합된 댓글 처리 실행 기준선

```text
jobs가 백필 또는 증분 댓글 수집을 시작
→ collection이 토스 댓글 API를 호출
→ storage가 원본 JSONL과 수집 매니페스트를 저장
→ jobs가 source_comment_file의 미처리 원본 JSONL 조회
→ storage가 원본을 읽고 저장 경계 자료형 정규화
→ analysis가 댓글을 평탄화·전처리
→ storage가 preprocessed_comment에 적재
→ jobs가 미토큰화 댓글을 배치 조회
→ analysis가 Kiwi 토큰화
→ storage가 tokenized_comment에 적재
→ jobs가 미생성 종목·날짜 대상을 조회
→ analysis가 장 마감 전 댓글을 일별 문서로 집계
→ storage가 daily_document와 daily_document_comment를 한 트랜잭션으로 적재
```

전처리·토큰화·일별 문서 생성은 각각 독립 실행기로도 사용할 수 있습니다.
서비스 운영에서는 `pilos.jobs.run_service_pipeline`이 아래 단계를 Python
`run_*` 함수로 순차 호출합니다.

```text
증분 댓글 수집
→ 이번 실행이 기록한 원본 파일 전처리
→ 미토큰화 댓글 토큰화
→ 장 마감 전 댓글의 일별 문서 생성
→ 개인 수급 장중 추정 또는 장마감 확정 수집
→ 활성 Positive·Negative artifact 기준 미완료 문서 추론
→ v13 보고서 신규 생성 또는 허용된 수급 상태 갱신
```

Windows 작업 스케줄러는 저장소 루트의 `run_service_pipeline.bat`를 호출합니다.
최상위 실행기는 프로세스 잠금으로 중복 실행을 차단하고, 실행 시작·종료를
`service_pipeline_run`에 기록하며, 자체 단계 요약만 `logs/service_pipeline_*.log`에
남깁니다. 모델 학습과 calibration 생성은 이 자동 운영 흐름에 포함하지 않습니다.

개인투자자 수급 수집은 댓글 흐름과 별도 실행기에서 수행합니다.

```text
jobs가 KST 시각과 실행 모드 판정
→ collection이 키움 API의 장중 추정 또는 장마감 확정 데이터를 수집
→ analysis가 개인 매수·매도량과 수급지수를 계산·검증
→ storage가 supply_demand의 추정·확정 이력을 보존하며 현재값을 갱신
```

장중 추정값이 이미 확정된 행을 다시 추정 상태로 낮추지 않습니다. 학습은
확정 수급만 사용합니다. 추론과 v13 보고서는 현재 관측 상태를 함께 전달하고,
같은 v13 보고서는 `estimated→confirmed` 또는 더 최신 estimated 관측에만
제한적으로 갱신합니다. 웹은 두 상태와 갱신 대기를 구분해 표시합니다.

모델 학습

```text
jobs
→ storage가 DB에서 최신 일별문서와 수급지수 조회
→ analysis가 양·음수 공통 월별 층화 날짜 그룹 생성
→ analysis가 시드 42~46 반복 검증
→ analysis가 전체 Dataset으로 TF-IDF와 Ridge를 최종 재학습
→ storage가 스키마 2 bundle을 파일로 저장·재로드 검증
→ storage가 DB artifacts에 모델 정보와 평가 지표 등록
```

일별 집계 추론

```text
jobs
→ storage가 DB artifacts와 로컬 v4 bundle을 교차검증·로드
→ storage가 수급 데이터가 존재하는 최신 거래일 일별문서 조회
→ analysis가 양·음수 일별 추론과 feature 기여도 계산
→ storage가 sentiment_index_result에 신규 결과 일괄 저장
```

반복 검증의 임시 모델은 최종 서비스 객체로 재사용하지 않습니다. 두
방향 추론이 모두 성공한 뒤 한 트랜잭션으로 저장하며 같은 일별문서·
아티팩트 결과는 덮어쓰지 않습니다.

신호 calibration 생성

```text
jobs
→ storage가 DB artifacts와 로컬 v4 bundle을 교차검증·로드
→ analysis가 학습 범위 재추론과 raw 점수 계산
→ storage가 재추론 CSV를 로컬 검수 산출물로 저장
→ analysis가 방향별 백분위 기준 생성
→ storage가 calibration JSON을 artifacts 경로에 저장
```

일별 댓글 수급 신호와 LLM 브리핑

```text
jobs
→ storage가 calibration JSON 로드
→ storage가 최신 일별문서·추론 결과·실제 수급 조회
→ storage가 비교용 과거 추론 결과 조회
→ analysis가 방향 판정·백분위 변환·비교값 계산
→ analysis가 정형 수치 근거와 프롬프트 조립
→ collection이 LLM 호출 또는 jobs가 deterministic 요약 사용
→ storage가 llm_report에 신규 결과 저장
```

LLM은 분석기가 아니라 이미 계산된 정형 수치를 자연어로 정리하는 편집자
역할만 담당합니다. 모델 feature의 의미 해석은 `collection`에 위임하지
않습니다.

모델 학습은 자동 운영 파이프라인에 포함하지 않습니다. 재학습이나 다른
로컬 환경에서 v4 모델 객체를 생성할 때 별도 실행합니다.

단일 댓글 요청

```text
web
→ service가 요청 사용 사례 조합
→ storage가 모델 구성요소 로드
→ analysis가 전처리·토큰화·추론·feature 기여도 계산
→ dto가 영역 간 반환 구조 제공
→ web이 API 응답 또는 화면 렌더링
```

저장된 일별 결과 조회

```text
web
→ service가 조회 사용 사례 조합
→ storage가 추론 결과 로드
→ dto가 영역 간 반환 구조 제공
→ web이 API 응답 또는 화면 렌더링
```

근거 기반 챗봇 요청

```text
web이 서버 allowlist의 block_key와 선택한 종목·기준일을 파싱
→ web이 block_key를 서버 정의의 action·metric·message로 변환
→ service가 stock_metric / stock_analysis / service_knowledge 경로 실행
→ storage가 MySQL 확정 수치·저장 v13 보고서 또는 Chroma 문서 근거 조회
→ 필요한 경로에서만 collection의 embedding·reranker·LLM client 사용
→ dto가 공개 출처·경고를 포함한 응답 제공
→ web과 chat.js가 상태별로 표시
```

공용 화면은 `POST /api/chat`, 종목 상세 화면은 URL의 종목을 고정하는
`POST /api/stocks/<stock_code>/chat`을 사용합니다. 공개 요청은 임의
`message`·`action`·`metric`을 받지 않습니다. 코드에 남은 자유문장 분류,
`general`·`restricted` 처리와 수급 순위 handler는 현재 공개 질문 블록에서
도달할 수 없습니다.

챗봇은 미래 전망·투자 지시를 입력받는 자유 대화 UI를 제공하지 않으며, 내부
Chroma 경로·검색 점수·프롬프트·비밀정보를 공개하지 않습니다.

---

# 5. 의존 방향

Python 호출 책임과 데이터 흐름을 구분합니다.

호출 책임

```text
배치·CLI: jobs → collection / storage / analysis / dto
웹 요청: web → service → storage / analysis / dto
```

데이터 흐름

```text
collection 또는 기존 원본
→ storage
→ analysis
→ storage
```

`analysis`는 `collection`이나 `storage`를 호출하지 않고, `collection`도 `analysis`를 호출하지 않습니다. 여러 영역의 정식 실행 순서는 `jobs`가 조합합니다.

`service`는 HTTP 표현을 알지 않고 `web`은 저장 형식과 모델 계산을 직접 다루지 않습니다.

> **CONFLICT — 2026-08-11 구현 감사:** 위 의존 규칙과 다른 직접 import가 현재
> `main@f80fdc2`에 존재합니다. `service/rag_service.py`는 외부 AI client를 위해
> `collection.ai_clients`를 호출하고, `collection/comment_crawler.py`는
> `storage`를, `collection/kiwoom_supply_demand.py`는 `analysis`를 호출합니다.
> 이 문서는 규칙을 코드에 맞춰 완화하지 않았습니다. 계층 규칙을 변경할지 구현을
> 재배치할지는 별도 기술 결정이 필요합니다.

`artifacts`는 호출 주체가 아닌 저장 위치입니다. 코드에서는 `storage`를 통해 접근합니다.

`pilos/analysis/review.py`는 일별 TF-IDF 입력·feature·IDF·점수를 사람이 확인하는 분석 검수 코드입니다. 로컬 검수 CSV를 직접 생성하지만 서비스 운영 파이프라인은 아닙니다.

---

# 6. 분석 검수와 Notebook

분석 검수 코드는 다음 목적으로 사용할 수 있습니다.

- TF-IDF 입력 확인
- feature와 IDF 검수
- 일별 문서의 상위 TF-IDF 점수 확인
- 일별 문서의 원문·토큰 표본 확인
- 분석 결과 CSV 생성

Notebook은 원본·분포 확인, 결과 비교, 시각화, 일부 로직과 파라미터 검증을 위한 실험 도구입니다. Notebook과 검수 산출물은 현재 운영 코드나 서비스 계약의 정본이 아닙니다.

현재 규모에서는 검수 CSV만을 위한 별도 저장 인터페이스, `experiments` 계층, Notebook 관리 시스템을 만들지 않습니다.

---

# 7. 새 파일 위치를 판단하는 기준

새 파일을 만들기 전에 다음 질문을 확인합니다.

1. 이 파일의 책임은 무엇인가?
2. 어떤 입력을 받는가?
3. 어떤 출력을 만드는가?
4. 다른 영역을 알아야 하는가?
5. 다른 폴더가 더 적절하지 않은가?

한 문장으로 설명하기 어렵다면
새로운 폴더를 만들기 전에 팀장과 먼저 논의합니다.

---

# 8. DTO를 만드는 기준

DTO는 다음 조건이 모두 만족될 때만 추가합니다.

- 생산자가 명확하다.
- 소비자가 명확하다.
- 전달되는 필드가 합의되었다.
- 두 영역 이상이 같은 구조를 사용한다.

분석 내부에서는 DTO를 강제하지 않습니다.

---

# 9. 실행 방식

실행은 저장소 루트에서 수행합니다. 팀 공통 명령은 해당 코드가 `develop`에 병합되고 팀 환경에서 검증된 뒤 README에 기록합니다. 현재 배포 기준은 `main`입니다.

배치·자동 실행은 jobs에서 관리하며

웹 요청 사용 사례는 service

핵심 계산은 analysis

입출력은 storage

역할을 유지합니다.

---

# 10. 현재 구현 상태

2026-08-11 `main@f80fdc2` 기준은 다음과 같습니다.

| 범위 | 상태 |
|---|---|
| 분석 실행 기준선 | PR #3. 전처리·토큰화·일별 문서·TF-IDF·Ridge 학습·평가·추론·결과 적재 통합 완료 |
| Flask 조회와 화면 | PR #4·#10·#15·#16. 종목 목록·상세·v13 보고서·단일 댓글 API와 현재 snake_case 화면 계약 통합 완료 |
| 댓글 수집 | PR #5. 백필·증분 수집과 최상위 수집→전처리 연결 완료 |
| 개인 수급 수집 | PR #6. 키움 장중 추정·장마감 확정·백필과 DB 적재 통합 완료 |
| 댓글 수급 신호와 LLM | PR #7 이후 마무리. calibration, v13 정형 근거, DB 품질 상태, deterministic fallback과 허용된 수급 상태 갱신 통합 완료 |
| 서비스 모델 | 두 방향 Ridge text-only alpha=1, v4 전체 재학습과 기존 DB 적재 이력 확인 |
| Flask 데이터 계약 | 활성 모델 동적 조회, 품질·수급 상태, v13 보고서 갱신 대기와 HTTP 상태 계약 적용 완료 |
| 단일 댓글 웹 기능 | `POST /api/inference/single-comment`와 상세 화면 체험 UI 연결 완료 |
| 최상위 실행기 | PR #14. 배치·CLI, 중복 잠금, 단계 중단, 파일 로그와 DB 실행 상태 기록 적용 완료 |
| 전체 수직 통합 | 2026-08-10 실제 실행 ID 1 완료(34분 43초 초기 증분), ID 2 완료(95초 정상 증분). 최신 실행 전 단계 실패 0건 |
| 챗봇 | PR #12·#15·#16. 정확 수치·저장 v13 분석·서비스 문서 RAG와 서버 allowlist 질문 블록 적용 완료. D-021의 `action/metric` 공개 계약과 현행 `block_key` 구현은 충돌 상태 |
| 프론트 | PR #15·#16. 검색·최근 조회·목록·상세·v13·단일 댓글·질문 트리·파이프라인 상태 polling 연결 완료 |
| 자동 테스트 | 2026-08-11 전체 437건: 11 failures, 88 errors, 4 skips. 구 챗봇 입력 계약 테스트가 현행 `block_key` 구현과 불일치. `test_chat*` 제외 375건 통과 |

기능 구현과 코드 통합은 완료됐습니다. 발표 전 남은 확인은 실제 PC·모바일
브라우저의 시각 검수와 Windows 스케줄러의 반복 운영 관찰입니다. 모델 재학습은
자동 운영 흐름에 넣지 않습니다.

---

# 11. 구조 변경

큰 구조를 변경하는 경우에는

팀장이 문서를 먼저 갱신합니다.

문서가 최신 기준이 된 이후

기능 구현을 진행합니다.

구조 변경 이유는

DECISIONS.md

에 기록합니다.
