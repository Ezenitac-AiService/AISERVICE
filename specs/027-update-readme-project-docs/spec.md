# Feature Specification: 027-update-readme-project-docs

**Feature Name**: `027-update-readme-project-docs`  
**Created**: 2026-08-20  
**Status**: APPROVED  
**Target**: `README.md` 및 `docs/` 하위 모듈 문서화 체계 구축

---

## Clarifications

### Session 2026-08-20
- **Q**: 메인 `README.md`와 하위 세부 기술 문서의 역할 분담 및 라이센스 정책은 어떻게 구성하는가?  
  → **A**: 메인 `README.md`는 **개요, 전체 아키텍처 다이어그램, 서비스 URL 맵, 1-Click 빠른 시작, 상세설명 목차 및 링크, 라이센스(MIT)**로 간결하고 명확하게 구성하고, 각 서브모듈 및 도메인별 심층 기술 문서는 `docs/` 디렉토리 하위의 독립 마크다운 문서(`docs/architecture.md`, `docs/model_gateway.md`, `docs/bteam_oliview.md`, `docs/ateam_pilos.md`, `docs/security_guardrails.md`)로 분리하여 모듈형 문서 체계를 구축한다.

---

## 1. Overview & Business Value

AISERVICE 프로젝트는 A-Team(Pilos 주식 수급 감정지수 플랫폼), B-Team(Oliview 뷰티 리뷰 감정 분석 & 챗봇 A/B), Model Gateway(vLLM/llama.cpp GPU 서빙 게이트웨이), Redis L2/L3 캐싱 및 4단계 보안 가드레일 등으로 구성된 대규모 분산 AI 플랫폼입니다.

본 명세는 메인 `README.md`를 **프로젝트 개요, 통합 아키텍처, 서비스 진입 라우팅 맵, 원클릭 실행 가이드, 상세 기술문서 목차/링크, MIT 라이센스**로 재구성하고, 서브모듈별 세부 구현 내역을 `docs/` 하위 전용 문서로 모듈화하여 단일 진입점과 체계적 심층 문서화를 동시에 달성하는 것을 목표로 합니다.

---

## 2. User Stories & Acceptance Scenarios

### User Story 1: 총괄 개요 및 서비스 라우팅 맵 파악 (Priority: P1) 🎯 MVP
**As a** 시스템 운영자, 개발자 또는 비즈니스 이해관계자  
**I want to** 메인 `README.md`를 통해 전체 서비스 개요, 통합 아키텍처 다이어그램, 4대 서비스 바로가기 링크 및 빠른 시작법을 한눈에 파악하고 싶다.  
**So that** 서비스의 전체 구성을 명확히 이해하고 원하는 서비스나 문서로 즉시 이동할 수 있다.

#### Acceptance Scenarios:
- **AC1.1**: 공인 DDNS HTTPS 진입점(`https://ezenitac.duckdns.org`), Nginx 포털, Traefik 인그레스, A/B-Team/Gateway 연결 구조가 다이어그램으로 제공된다.
- **AC1.2**: 4대 주요 서비스(통합 포털, Oliview 대시보드, 올리챗 A, 올원챗 B, Pilos 대시보드)의 공인 URL, 기술 스택, 설명이 표로 정리된다.
- **AC1.3**: 프로젝트 라이센스(MIT License)가 메인 `README.md`에 명시된다.

---

### User Story 2: 상세 서브 도메인별 전용 기술 문서 탐색 (Priority: P2)
**As a** 도메인별 개발자 또는 아키텍트  
**I want to** `README.md`의 목차 링크를 통해 관심 있는 하위 시스템의 상세 마크다운 문서를 열람하고 싶다.  
**So that** 게이트웨이 GPU 토폴로지, 보안 가드레일, A-Team 파이프라인, B-Team RAG 구조를 깊이 있게 파악할 수 있다.

#### Acceptance Scenarios:
- **AC2.1**: `docs/architecture.md` (전체 시스템 및 네트워크 격리 구조) 문서가 제공되고 링크된다.
- **AC2.2**: `docs/model_gateway.md` (2B 상주 서빙, SINGLE_MODEL_MODE, 16K 컨텍스트, VRAM 토폴로지) 문서가 제공되고 링크된다.
- **AC2.3**: `docs/bteam_oliview.md` (화장품 감정분석, 챗봇 A Streamlit, 챗봇 B FastAPI RAG) 문서가 제공되고 링크된다.
- **AC2.4**: `docs/ateam_pilos.md` (주식 종토방 크롤링, Ridge v4 수급 감정지수, 7단계 배치 데몬) 문서가 제공되고 링크된다.
- **AC2.5**: `docs/security_guardrails.md` (4단계 보안 가드레일, 토큰 예산 정책, Let's Encrypt HTTPS) 문서가 제공되고 링크된다.

---

### User Story 3: 1-Click 원클릭 기동 및 헬스체크 검증 (Priority: P3)
**As a** 엔지니어 또는 평가자  
**I want to** Windows 및 Linux 환경에서 10개 컨테이너를 원클릭으로 기동하고 즉시 상태를 검증하는 명령어를 확인하고 싶다.  
**So that** 셋업 착오 없이 누구나 시스템을 완벽하게 재현 및 실행할 수 있다.

#### Acceptance Scenarios:
- **AC3.1**: `run_all_services.bat up` 및 `./run_all_services.sh up` 실행 가이드가 명시된다.
- **AC3.2**: 각 서비스별 헬스체크 및 Pilos 파이프라인 수동 트리거 명령어가 포함된다.

---

## 3. Functional Requirements

- **FR-001**: 메인 `README.md`는 **개요(Overview), 통합 아키텍처(Architecture), 서비스 라우팅 맵(Service Map), 빠른 시작(Quickstart), 상세설명 목차 및 링크(Detailed Documentation TOC), 라이센스(MIT)**의 6대 핵심 섹션으로 구성되어야 한다.
- **FR-002**: `docs/` 디렉토리를 생성하고 5개의 세부 기술 문서를 표준 마크다운 형식으로 작성해야 한다:
  1. `docs/architecture.md`: K8s/Docker 통합 네트워크 및 프록시 아키텍처
  2. `docs/model_gateway.md`: LLM GPU 서빙 게이트웨이, 2B 상주 서빙, 16K 컨텍스트, `SINGLE_MODEL_MODE`
  3. `docs/bteam_oliview.md`: Oliview 뷰티 리뷰 분석 대시보드 및 챗봇 A/B 구조
  4. `docs/ateam_pilos.md`: Pilos 주식 수급 감정지수 분석 플랫폼 및 워커 데몬
  5. `docs/security_guardrails.md`: 4단계 CPU 가드레일 및 3단계 하이브리드 토큰 정책
- **FR-003**: 메인 `README.md` 내의 모든 세부 기술 문서 링크는 클릭 가능한 표준 GitHub 마크다운 상대 링크(`[제목](docs/파일명.md)`)로 연결되어야 한다.
- **FR-004**: GPU VRAM 실측 수치(~4.1GB / 8.0GB), 3개 모델 상주(`bge-m3`, `reranker`, `qwen3.5-2b`), 4단계 가드레일, 3단계 토큰 예산이 최신 실측 상태와 100% 일치해야 한다.
- **FR-005**: 프로젝트 라이센스를 `MIT License`로 명시하고 루트에 `LICENSE` 파일이 필요시 포함되도록 한다.

---

## 4. Success Criteria

- **SC-001**: `README.md`의 길이가 120줄 내외로 간결하게 유지되면서도 전체 청사진과 핵심 정보가 완벽히 전달됨.
- **SC-002**: `README.md`에 포함된 모든 `docs/*.md` 링크가 깨짐(Broken link) 없이 100% 정상 연결됨.
- **SC-003**: 5개의 상세 기술 문서가 각 도메인의 최신 구현 현황(2B 통일, 가드레일 정밀화 등)을 100% 반영함.
- **SC-004**: MIT 라이센스 고지가 표준 양식으로 정확히 반영됨.

---

## 5. Scope & Directory Structure

```text
c:/AISERVICE/
├── README.md                  # [MODIFY] 메인 총괄 대시보드 문서 (개요, 아키텍처, 맵, 시작법, 목차링크, MIT)
├── LICENSE                    # [NEW] MIT 라이센스 전문 파일
└── docs/                      # [NEW] 서브 도메인별 심층 상세 기술문서 디렉토리
    ├── architecture.md        # 통합 인프라, K8s Ingress, Nginx 게이트웨이, 네트워크 격리
    ├── model_gateway.md       # vLLM/llama.cpp 서빙, 2B 상주, SINGLE_MODEL_MODE, 16K ctx
    ├── bteam_oliview.md       # Oliview React/Flask 플랫폼, 챗봇 A(Streamlit), 챗봇 B(FastAPI RAG)
    ├── ateam_pilos.md         # Pilos 주식 수급 감정분석, 7단계 배치 워커 데몬, 대시보드
    └── security_guardrails.md # 4단계 CPU 보안 가드레일, 3단계 하이브리드 토큰 정책
```
