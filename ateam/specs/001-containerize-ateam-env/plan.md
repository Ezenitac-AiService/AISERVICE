# Implementation Plan: A-Team 컨테이너 기반 개발 및 서비스 환경 구축 (Containerize A-Team Environment)

**Branch**: `001-containerize-ateam-env` | **Date**: 2026-08-17 | **Spec**: [`specs/001-containerize-ateam-env/spec.md`](spec.md)

**Input**: Feature specification from `/specs/001-containerize-ateam-env/spec.md`

## Summary

마이그레이션된 소스 코드(`pilos-sentiment-index/`)와 대용량 SQL 덤프(`pilos_v2.sql`, 약 2.69GB)를 Windows 11 + WSL2 + Rancher Desktop 환경에서 Docker 컨테이너(`python:3.12-slim` Web + `mysql:8.0` DBMS + Docker Named Volume)로 패키징하고, 공통 Docker 네트워크(`aiservice-network`)를 통해 기존 LLM 컨테이너와 연결하며, B-Team과의 포트 충돌을 방지하기 위해 A-Team 전용 포트(Web `8080`, DB `3307`)로 격리 서비스하도록 인프라 구성을 수립합니다.

## Technical Context

**Language/Version**: Python 3.12 (`python:3.12-slim` 베이스 이미지)

**Primary Dependencies**: Flask 3.1.3, Gunicorn, SQLAlchemy 2.0.51, PyMySQL 1.2.0, OpenAI SDK 1.0.0+, ChromaDB 1.5.9, KiwiPiePy 0.23.2, Scikit-learn 1.9.0, Pandas 3.0.5

**Storage**: MySQL 8.0 (`ateam_db_data` Docker Named Volume, `pilos_v2.sql` 2.69GB 덤프 마이그레이션 적재)

**Testing**: curl 기반 엔드투엔드 시나리오 검증, Docker Healthcheck, Pytest

**Target Platform**: Windows 11 + WSL2 + Rancher Desktop (Docker Engine / Compose v2 규격)

**Project Type**: 컨테이너 기반 웹 서비스 및 관계형 데이터베이스 시스템

**Performance Goals**: 웹 대시보드 렌더링 < 3초, LLM 질의 첫 응답 < 5초, 컨테이너 재기동 후 데이터 보존율 100%

**Constraints**: B-Team 포트 충돌 방지(Web `8080`, DB `3307` 고정 및 `.env` 오버라이드 지원), 2.69GB 덤프 복원 안정성 확보(1회성 워크플로우 분리), 보안 준수(`.env` 기반 비밀번호 및 키 주입)

**Scale/Scope**: 2개 컨테이너(Web, DB) + 1개 공통 브리지 네트워크 + 1개 영속 볼륨

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 헌장 원칙 (Constitution Gate) | 준수 여부 | 설명 |
|---|---|---|
| **I. Language Governance** | **PASS** | 모든 설계 산출물 및 공식 문서를 한국어로 작성하며 내부 추론은 영어로 수행 |
| **II. Canonical Authority** | **PASS** | `docs/ARCHITECTURE.md`, `docs/DATA_CONTRACT.md` 및 팀장 지시 우선순위 준수 |
| **III. Contract-First & Simplicity** | **PASS** | YAGNI 원칙에 따라 불필요한 프록시나 복잡한 레이어 배제, 표준 Docker Compose 채택 |
| **IV. Test-First & Empirical Validation** | **PASS** | `quickstart.md`에 실증 가능한 엔드투엔드 검증 시나리오 및 헬스체크 정의 |
| **V. Strict Security & Privacy Compliance** | **PASS** | 하드코딩 없이 `.env` 및 Docker 환경 변수를 통해 자격증명 관리 |

## Project Structure

### Documentation (this feature)

```text
specs/001-containerize-ateam-env/
├── spec.md                  # 기능 명세서
├── plan.md                  # 본 구현 계획서
├── research.md              # Phase 0 기술 연구 및 의사결정 결과
├── data-model.md            # Phase 1 엔티티, 아키텍처 및 상태 모델
├── quickstart.md            # Phase 1 실행 및 검증 가이드
├── contracts/               # Phase 1 인터페이스 계약
│   ├── docker-compose-contract.md
│   └── env-variables-contract.md
└── checklists/
    └── requirements.md      # 명세 품질 검증 체크리스트
```

### Source Code (repository layout)

```text
C:\AISERVICE\ateam\
├── docker-compose.yml                      # 루트 Docker Compose 오케스트레이션 정의
├── pilos_v2.sql                            # 마이그레이션된 2.69GB DB 덤프 파일
├── pilos-sentiment-index/
│   ├── Dockerfile                          # Python 3.12 Web 애플리케이션 컨테이너 빌드 파일
│   ├── .dockerignore                       # 불필요한 빌드 파일 제외 목록
│   ├── .env.example                        # 환경 변수 템플릿
│   ├── .env                                # 로컬 컨테이너 환경 설정 (Git 미추적)
│   ├── pyproject.toml                      # Python 의존성 정의
│   ├── pilos/
│   │   ├── web/                            # Flask 웹 라우트 및 정적 템플릿
│   │   ├── service/                        # 비즈니스 로직 및 LLM/챗봇 서비스
│   │   ├── storage/                        # MySQL 및 벡터 저장소 연결
│   │   └── ...
│   └── tests/                              # 단위 및 통합 테스트
```

**Structure Decision**: A-Team 프로젝트 소스(`pilos-sentiment-index/`) 내부에 애플리케이션 전용 `Dockerfile`을 배치하고, 프로젝트 루트에 전체 인프라를 오케스트레이션하는 `docker-compose.yml`을 배치하여 루트 디렉터리의 `pilos_v2.sql`과 유기적으로 연동되는 단일 진입점 구조를 확립합니다.

## Complexity Tracking

> **Constitution Check 결과 위반 사항이 없으므로 추가 복잡도 승인 불필요 (No Violations)**
