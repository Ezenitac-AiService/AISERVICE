# Feature Specification: Oliview B-Team 전주기 데이터 및 서비스 파이프라인 통합 재구성

**Feature Branch**: `041-bteam-unified-pipeline-restructure`  
**Created**: 2026-08-26  
**Status**: Clarified & Fully Hardened (Round 3 Final Approved)  
**Input**: User description: "C:\AISERVICE\bteam 폴더에 있는 하위 프로젝트들의 구조 검토와 재구성을 위한 리서치를 진행해서 스펙 작성. 올리브영 사이트에서 타겟 제품의 리뷰를 수집 -> 감성분석 -> 개선제안 보고서 생성. 리뷰 분석 정보를 바탕으로 챗봇 운영의 구조인데, 각 프로젝트들이 폴더별로 개별 구현되어있어서 통합 재구성해야 할것 같음"

---

## Clarification & Design Decisions *(speckit-clarify & Round 3 Multi-Persona Hardening)*

- **Q1 (디렉토리 재구성 및 마이그레이션 전략)**: B팀 하위 프로젝트들의 디렉토리 재구성 및 마이그레이션 전략을 어떻게 진행할 것인가?
  - **결정**: **표준 3계층(`packages/core`, `pipelines/`, `services/`) 물리적 이동 및 레거시 분산 폴더 완전 정리** 채택. 래퍼나 심볼릭 링크 같은 임시 방편을 배제하고 단일하고 깔끔한 모노레포 구조로 진정한 파일 재구성 단행.
- **Q2 (전주기 파이프라인 오케스트레이션 방식)**: 전주기 파이프라인(크롤링 $\rightarrow$ 감성분석 $\rightarrow$ 보고서생성 $\rightarrow$ 벡터인덱싱) 오케스트레이션 방식을 어떻게 구현할 것인가?
  - **결정**: **통합 CLI 오케스트레이터 (`pipeline_runner.py`) + 단계별 독립 실행 모드 (`--step crawl|split|sentiment|report|index|all`) + 체크포인트 재개(Resume)** 지원. 전체 E2E 자동 실행과 특정 단계 디버깅/재시도를 모두 지원.
- **Q3 (ChromaDB 벡터 인덱스 동기화 방식)**: 수집/분석된 신규 리뷰 데이터의 ChromaDB 벡터 인덱스 동기화 방식을 어떻게 처리할 것인가?
  - **결정**: **증분 동기화 (Incremental Sync)** 채택. MySQL `review.vector_indexed` 플래그를 통해 새로 수집 및 감성 분석 완료된 리뷰만 식별하여 ChromaDB에 실시간 Upsert하여 대화형 챗봇에서 즉시 인용 가능하도록 구성.
- **Q4 (LLM 개선 제안 보고서 연동 범위)**: 생성된 '제품별 LLM 개선 제안 보고서'의 서비스 연동 범위를 어떻게 설정할 것인가?
  - **결정**: **MySQL `product_report` 테이블에 정형 JSON/Markdown으로 저장하여 웹 대시보드(React/Flask) 및 챗봇(ChatA/ChatB) 양쪽에서 즉시 열람/인용 연동** 지원.
- **Q5 (패키지 및 가상환경 관리 전략)**: Python 패키지 및 가상환경(UV) 관리 전략을 어떻게 구성할 것인가?
  - **결정**: **`bteam` 루트의 단일 `pyproject.toml` 기반 `uv workspace`로 의존성 및 패키지 관리 완전 일원화** 채택.
- **Q6 (머신러닝 모델 가중치 파일 저장 위치)**: 문장분리 및 감성분석 모델 가중치(Weights) 파일들의 저장 위치를 어떻게 구성할 것인가?
  - **결정**: **공통 `models/` 폴더(`bteam/models/sentence_split`, `bteam/models/sentiment`)로 모델 가중치 파일 일괄 통합** 채택.
- **Q7 (컨테이너 이름 및 게이트웨이 연동 호환성)**: 통합 `docker-compose.yml`의 컨테이너 이름 및 게이트웨이(Nginx) 연동 호환성을 어떻게 처리할 것인가?
  - **결정**: **새로운 서비스 폴더명에 맞춰 컨테이너 이름 일치 변경 (`bteam_db`, `bteam_dashboard_backend`, `bteam_dashboard_frontend`, `bteam_chatbot_a`, `bteam_chatbot_b`) 및 Gateway Nginx 동기화** 채택.
- **Q8 (MySQL 보고서 스키마 관리)**: LLM 제품 보고서 저장을 위한 `product_report` 테이블 스키마 관리를 어떻게 처리할 것인가?
  - **결정**: **파이프라인 초기화 시 `product_report` 및 메타데이터 테이블이 없으면 자동 생성(`CREATE TABLE IF NOT EXISTS`)하는 내장 자동 마이그레이션** 적용.
- **Q9 (오케스트레이터 스케줄링 옵션)**: `pipeline_runner.py` 오케스트레이터의 실행 및 스케줄링 방식을 어떻게 구성할 것인가?
  - **결정**: **온디맨드 CLI 실행 중심 + 백그라운드 주기 실행을 위한 단순 주기 파라미터(`--interval-hours`) 옵션 제공** 채택.

---

## 1. Executive Summary & Problem Definition

### 1.1 현상 및 문제점 (Current State & Pain Points)
현재 `C:\AISERVICE\bteam` 하위 프로젝트는 다음과 같이 6개 이상의 폴더로 분산 격리(Siloed)되어 있습니다:
1. `Oliview_Project`: 올리브영 크롤러 모음 + Flask 백엔드 + React Vite 프론트엔드
2. `Oliview_aspect_sentence_split`: 리뷰 문장 분리 스크립트 및 모델
3. `Oliview_aspect_sentiment`: 속성별 감성 분석(긍정/부정/중립) 스크립트 및 모델
4. `Oliview_LLM`: 단일/전체 제품 대상 LLM 개선 제안 보고서 생성 스크립트
5. `Oliview_chatbot_a`: Streamlit 기반 RAG 챗봇
6. `Oliview_chatbot_b`: FastAPI 기반 하이브리드 RAG 챗봇

**핵심 결함**:
- **파이프라인 단절**: "크롤링 $\rightarrow$ 문장 분리 $\rightarrow$ 감성 분석 $\rightarrow$ LLM 보고서 생성 $\rightarrow$ 챗봇 RAG 서빙 $\rightarrow$ 대시보드 표출"의 핵심 가치 사슬이 하나의 통합 파이프라인으로 연결되어 있지 않고 개별 스크립트 수동 실행에 의존.
- **코드 및 설정 중복**: 각 폴더마다 독립된 `.env`, `pyproject.toml`, `common.py`, DB 연결 코드, LLM Gateway 호출 코드가 분산되어 있어 동기화 불일치 및 유지보수 비용 발생.
- **배포 및 패키지 관리 비효율**: 6개의 가상환경과 도커 컨테이너 설정이 분절되어 있어 데이터 변경 시 서비스 즉각 반영(End-to-End Reactive Refresh)이 불가능.

---

## 2. 통합 시스템 아키텍처 (Target Architecture)

```mermaid
flowchart TD
    subgraph Data_Pipeline["1. 통합 데이터 & AI 파이프라인 (Pipelines Layer)"]
        Crawler["1) OliveYoung Review Crawler\n(타겟 제품/리뷰 수집 & Master Upsert)"]
        Splitter["2) Aspect Sentence Splitter\n(6대 화장품 속성별 문장 분리 & PII 마스킹)"]
        Sentiment["3) Aspect Sentiment Classifier\n(긍정 / 부정 / 중립 분류)"]
        Reporter["4) LLM Report Generator\n(제품별 개선 제안 보고서 자동 생성, Throttling)"]
        Indexer["5) ChromaDB Vector Indexer\n(신규 리뷰 증분 벡터화 & SQLite 락 방어 & Redis Purge)"]
        Orchestrator["6) Unified Pipeline Orchestrator (pipeline_runner.py)\n(E2E 원클릭 실행 & 단계별 제어 & 주기 실행 & 체크포인팅)"]

        Crawler -->|원문 리뷰 저장 (500 청크 커밋)| DB[(MySQL cosmetic_db)]
        DB -->|미분석 리뷰 추출| Splitter
        Splitter -->|속성 분리 문장| Sentiment
        Sentiment -->|감성 라벨 적재| DB
        DB -->|감성 통계 집계| Reporter
        Reporter -->|개선제안서 저장| DB
        DB -->|신규 분석 리뷰 증분 추출 (vector_indexed=0)| Indexer
        Indexer -->|임베딩 Upsert & vector_indexed=1| VectorDB[("ChromaDB Vector Store")]
        Indexer -.->|캐시 즉시 무효화| Cache[(Redis L1~L5 Cache)]

        Orchestrator -.->|E2E / Step-by-Step / Retry / Chunking| Crawler
        Orchestrator -.-> Splitter
        Orchestrator -.-> Sentiment
        Orchestrator -.-> Reporter
        Orchestrator -.-> Indexer
    end

    subgraph Core_Layer["2. 공통 코어 계층 (Shared Core Package)"]
        CoreDB["Database Manager (MySQL Connection Pool & Auto Migration & Chunk Commit)"]
        CoreLLM["LLM / Embedding / Reranker Client (vLLM Throttling)"]
        CoreCache["Redis L1~L5 Cache Manager (Auto Invalidation)"]
        CoreGuard["Domain Guardrails & Sanitizer (PII Masking)"]
    end

    subgraph Service_Layer["3. 서비스 서빙 계층 (Serving & Delivery Layer)"]
        ChatA["ChatA: Streamlit 챗봇\n(/bteam/chata/)"]
        ChatB["ChatB: FastAPI 챗봇\n(/bteam/chatb/)"]
        DashboardBE["Oliview Backend API\n(Flask /api)"]
        DashboardFE["Oliview Frontend UI\n(React 19 + Vite)"]

        VectorDB --> ChatA
        VectorDB --> ChatB
        DB --> DashboardBE
        DashboardBE --> DashboardFE
        DB -.->|보고서 직접 인용| ChatA
        DB -.->|보고서 직접 인용| ChatB
    end

    Core_Layer -.-> Data_Pipeline
    Core_Layer -.-> Service_Layer
```

---

## 3. 재구성 디렉토리 표준 구조 (Target Directory Layout)

```text
bteam/
├── packages/
│   └── core/                           # [공통 모듈] DB, Gateway, Redis, 프롬프트, 가드레일
│       ├── pyproject.toml
│       └── oliview_core/
│           ├── db/                     # MySQL 커넥션 풀, ORM 모델, 자동 마이그레이션, 청크 커밋
│           ├── gateway/                # vLLM Gateway 클라이언트 (LLM, Embedding, Reranker, Throttling)
│           ├── cache/                  # Redis 캐시 계층 (L1~L5 & Auto Invalidation)
│           ├── guardrails/             # 브랜드 검증, 무환각 새니타이저, PII 마스킹
│           └── models/                 # 공통 Pydantic 데이터 모델
├── models/                             # [공통 ML 모델 가중치 저장소] (.dockerignore로 빌드 격리)
│   ├── sentence_split/                 # 문장분리 KoBERT/HuggingFace 가중치
│   └── sentiment/                      # 속성 감성분석 가중치
├── pipelines/                          # [데이터 & 분석 파이프라인]
│   ├── crawler/                        # 올리브영 타겟 제품 및 리뷰 크롤러 (Master Product Upsert)
│   ├── sentence_split/                 # 리뷰 문장 분리 모델 & 프로세서 (PII 마스킹)
│   ├── sentiment/                      # 6대 속성 기반 감성 분석 분류기
│   ├── report_generator/               # LLM 기반 제품별 개선 제안 보고서 생성기 (GPU Throttling)
│   ├── vector_indexer/                 # MySQL -> ChromaDB 벡터 인덱싱 동기화 (SQLite 락 방어 & Redis Purge)
│   └── pipeline_runner.py              # E2E 전주기 원클릭 오케스트레이터 CLI (--interval-hours 지원)
├── services/                           # [서빙 서비스]
│   ├── dashboard_backend/              # Flask 메인 REST API (구 Oliview_Project/backend)
│   ├── dashboard_frontend/             # React 19 Vite 웹 대시보드 (구 Oliview_Project/frontend)
│   ├── chatbot_a/                      # Streamlit 대화형 RAG 챗봇 (구 Oliview_chatbot_a)
│   └── chatbot_b/                      # FastAPI 하이브리드 RAG 챗봇 (구 Oliview_chatbot_b)
├── docker-compose.yml                  # 통합 서비스 오케스트레이션 (표준 서비스명 매핑)
├── .dockerignore                       # 2GB models/ 빌드 컨텍스트 격리
├── pyproject.toml                      # 루트 uv 워크스페이스 통합 설정
└── README.md                           # 전주기 통합 운영 가이드
```

---

## 4. User Scenarios & Testing *(mandatory)*

### User Story 1 - E2E 전주기 데이터 파이프라인 원클릭 실행 (Priority: P1) 🎯 MVP

데이터 엔지니어/운영자는 `pipeline_runner.py` 단일 명령을 통해 특정 타겟 제품(예: "컬러그램 탕후루 꿀로스")의 리뷰 수집 $\rightarrow$ 문장 분리 $\rightarrow$ 감성 분석 $\rightarrow$ LLM 개선제안 보고서 생성 $\rightarrow$ 벡터 인덱스 갱신까지 중단 없이 완전 자동화된 파이프라인을 구동할 수 있어야 한다.

**Why this priority**: 현재 수동으로 4~5개 폴더의 스크립트를 개별 실행해야 하는 운영 단절을 근본적으로 제거하기 위함.

**Independent Test**:
```bash
uv run python pipelines/pipeline_runner.py --product-id 12345 --steps all
```
실행 후 MySQL 테이블(`review`, `review_sentence`, `sentiment_analysis`, `product_report`)과 ChromaDB 인덱스가 모두 정상 갱신되는지 확인.

---

### User Story 2 - 공통 코어 패키지(`packages/core`) 단일화 및 코드 중복 제거 (Priority: P1)

모든 서비스(`services/`)와 파이프라인(`pipelines/`)이 분산된 `common.py` 및 중복 DB 설정 대신 `oliview_core` 패키지를 직접 import하여 사용하며, 단 하나의 통일된 설정 파일(`.env`)로 시스템 전체 환경변수를 제어한다.

**Why this priority**: 코드 중복으로 인한 버그와 설정 불일치를 원천 차단.

**Independent Test**: 각 서비스 및 파이프라인에서 `from oliview_core.db import get_db_pool`, `from oliview_core.gateway import LLMGatewayClient`로 공통 임포트 실행 및 정상 동작 확인.

---

### User Story 3 - 챗봇 및 대시보드 실시간 연동 무결성 보장 (Priority: P2)

새롭게 수집/분석된 리뷰 데이터와 LLM 개선제안 보고서가 즉시 대시보드(React/Flask)와 챗봇(ChatA/ChatB)의 RAG 검색 풀에 반영되어야 한다.

**Why this priority**: 리뷰 분석의 최종 목적은 대시보드 시각화와 챗봇 질의응답을 통한 비즈니스 가치 창출이기 때문.

**Independent Test**: 신규 리뷰 적재 후 ChatA/ChatB에서 해당 리뷰 내용이 인용 문서로 즉시 검색되는지 확인.

---

### User Story 4 - 도커 빌드 격리 및 게이트웨이 무중단 서빙 보장 (Priority: P3)

컨테이너명 개편(`bteam_dashboard_backend`, `bteam_chatbot_a`, etc.)과 빌드 격리(`.dockerignore`)를 적용하여 2GB 가중치 파일 유입 없이 빠르고 가볍게 빌드되며, Gateway Nginx를 통해 0초 무중단 프록시 서비스를 유지한다.

**Why this priority**: 인프라 변경 시 발생할 수 있는 서비스 중단(502 Bad Gateway) 및 빌드 실패를 원천 방어.

**Independent Test**: `docker compose up -d --build` 실행 후 `https://ezenitac.duckdns.org/bteam/chata/`, `/bteam/chatb/`, `/bteam/oliview/` 접속 시 HTTP 200 OK 확인.

---

## 5. Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 시스템은 `bteam/` 하위 프로젝트를 `packages/core`, `models/`, `pipelines/`, `services/`의 표준 계층으로 명확히 물리적 재구성하고 단일 `uv workspace`로 패키지 의존성을 통합 관리해야 한다.
- **FR-002**: 시스템은 `pipelines/pipeline_runner.py`를 구현하여 `[crawler] -> [sentence_split] -> [sentiment] -> [report_generator] -> [vector_indexer]`의 5단계 파이프라인을 단일 제품/전체 제품 단위로 실행(`--steps`)하고, 주기적 백그라운드 실행(`--interval-hours`) 및 장애 시 재개(Resume)를 지원해야 한다.
- **FR-003**: 시스템은 `packages/core`에 통일된 MySQL 데이터베이스 연결 풀, `product_report` 자동 마이그레이션, Model Gateway 클라이언트(LLM/임베딩/리랭커), Redis 캐싱, 가드레일 모듈을 제공하여 모든 하위 모듈이 공유하도록 해야 한다.
- **FR-004**: 시스템은 `docker-compose.yml`을 신규 디렉토리 구조(`services/`) 및 표준 컨테이너명(`bteam_db`, `bteam_dashboard_backend`, `bteam_dashboard_frontend`, `bteam_chatbot_a`, `bteam_chatbot_b`)으로 갱신하고, Gateway Nginx의 프록시 라우팅을 함께 동기화해야 한다.
- **FR-005**: 시스템은 기존의 소스 코드 기능(Flask API, React 대시보드, Streamlit ChatA, FastAPI ChatB, 머신러닝 감성 분류기, LLM 프롬프트)의 비즈니스 로직을 100% 보존하면서 구조적 재구성만 수행해야 한다.
- **FR-006 (파이프라인 멱등성 & 체크포인팅)**: `pipeline_runner.py`는 단계별 완료 상태를 DB 플래그로 기록하고, 장애 발생 시 실패 지점부터 재개(Resume)하는 멱등 실행을 보장해야 한다.
- **FR-007 (증분 인덱싱 플래그 및 메타데이터 정합성)**: MySQL `review.vector_indexed` 컬럼을 기반으로 미색인 리뷰만 추출하여 ChromaDB에 실시간 Upsert해야 한다.
- **FR-008 (도커 빌드 격리 & 가중치 볼륨 마운트)**: `.dockerignore`를 통해 빌드 컨텍스트에서 `models/`를 제외하고 읽기 전용 볼륨으로 컨테이너에 주입하여 빌드 속도를 최적화해야 한다.
- **FR-009 (Gateway Nginx 무중단 동기화)**: 컨테이너명 변경에 따른 `gateway/nginx.conf` 업스트림 프록시를 동시 갱신하여 0초 다운타임을 보장해야 한다.
- **FR-010 (MySQL 배치 청크 커밋 & 락 격리)**: `pipeline_runner`의 모든 대량 DB 쓰기 작업은 500건 단위 청크 트랜잭션(`batch_size=500, autocommit=False`) 및 `READ COMMITTED` 격리 수준을 적용하여 실시간 챗봇/대시보드 조회 쿼리와의 락 경합을 방지해야 한다.
- **FR-011 (ChromaDB 안전 동기화 & 재시도 백오프)**: `vector_indexer`는 동시 쓰기-읽기 충돌 방지를 위해 일괄 Upsert 후 플러시를 수행하고, `OperationalError(database is locked)` 발생 시 최대 3회 지수 백오프 재시도 로직을 적용해야 한다.
- **FR-012 (LLM GPU 추론 큐 부하 분산 & Throttling)**: `report_generator`는 실시간 챗봇(ChatA/ChatB)의 SLA를 보장하기 위해 LLM 요청 동시성을 `max_concurrency=1~2`로 제어하고 요청 간 0.5초 딜레이(Throttling)를 적용해야 한다.
- **FR-013 (도커 멀티 패키징 & 프론트엔드 환경변수 일치화)**: 각 `services/*` Dockerfile에서 `packages/core`를 표준 설치(`pip install -e /app/packages/core`)하고, React 대시보드는 Nginx 리버스 프록시 상대 경로(`/bteam/oliview/api`)를 적용해야 한다.
- **FR-014 (마스터 상품 카탈로그 자동 Upsert & 데이터 정합성)**: 크롤러는 리뷰 수집 전 제품 메타데이터(`goodsNo`, `brand_name`, `category`)를 `product` 테이블에 먼저 `INSERT ... ON DUPLICATE KEY UPDATE`하여 외래키 무결성을 보장해야 한다.
- **FR-015 (파이프라인 완료 시 Redis 캐시 자동 무효화)**: `pipeline_runner`의 벡터 인덱싱 및 보고서 생성이 완료되면, 해당 제품의 Redis 캐시 키(`oliview:rag:*`, `oliview:report:*`)를 자동으로 Flush/Invalidate하여 실시간 최신성을 즉시 반영해야 한다.
- **FR-016 (리뷰 PII 개인정보 마스킹 새니타이저)**: 문장 분리 및 벡터화 단계에서 작성자 개인정보(연락처, 계좌, 주민번호, 노골적 개인 식별자)를 `packages/core/guardrails` 정규식 필터로 자동 마스킹(`[개인정보]`)해야 한다.
- **FR-017 (원자적 단계별 마이그레이션 및 롤백 안전장치)**: 대규모 리팩토링을 5단계 원자적 Git 체크포인트(`core 생성` $\rightarrow$ `models 통합` $\rightarrow$ `pipelines 구성` $\rightarrow$ `services 전환` $\rightarrow$ `docker-compose 갱신`)로 분할 실행하여 무중단 롤백 가능성을 확보해야 한다.

---

## 6. Success Criteria *(mandatory)*

- **SC-001**: 6개로 파편화되어 있던 하위 프로젝트 폴더가 `packages/`, `models/`, `pipelines/`, `services/`의 단일 표준 워크스페이스 구조로 100% 통합 재구성되어야 한다.
- **SC-002**: `pipeline_runner.py` 1회 실행으로 크롤링부터 보고서 생성 및 ChromaDB 갱신까지 E2E 자동 실행이 성공해야 한다.
- **SC-003**: 4개 메인 서비스(`bteam_dashboard_backend`, `bteam_dashboard_frontend`, `bteam_chatbot_a`, `bteam_chatbot_b`)가 Docker Compose 환경에서 무중단 정상 기동(Health 200 OK)되어야 한다.
- **SC-004**: 중복 파일(`common.py`, 레거시 백업 스크립트 등)이 80% 이상 제거되고 코드베이스 유지보수성이 극대화되어야 한다.
- **SC-005**: 도커 빌드 시 2GB 가중치 파일의 불필요한 컨텍스트 전송이 0MB로 완벽히 격리되어야 한다.
- **SC-006**: 파이프라인 중간 오류 발생 시 기존 처리 데이터 유실 없이 실패 단계부터 재개(Resume)되어야 한다.
- **SC-007**: 대량 리뷰 DB 쓰기 및 ChromaDB 동기화 중에도 실시간 챗봇 질의 쿼리가 데드락이나 DB 락 에러 없이 100% 정상 응답해야 한다.
- **SC-008**: LLM 대량 보고서 생성 중에도 실시간 챗봇 P95 응답 지연시간이 5초 이내를 유지해야 한다.
- **SC-009**: 신규 제품 리뷰 수집 시 마스터 상품 테이블 외래키 에러 0건 및 Redis 캐시 유령 데이터 잔존 0건이어야 한다.
- **SC-010**: 개인정보(전화번호, 계좌 등)의 벡터 DB 및 LLM 프롬프트 무단 유입이 0건이어야 한다.
