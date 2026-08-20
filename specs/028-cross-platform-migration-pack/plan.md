# Implementation Plan: 028-cross-platform-migration-pack

**Branch**: `028-cross-platform-migration-pack` | **Date**: 2026-08-20 | **Spec**: [spec.md](file:///c:/AISERVICE/specs/028-cross-platform-migration-pack/spec.md)

**Input**: Feature specification from `specs/028-cross-platform-migration-pack/spec.md`

---

## 1. Summary

컨테이너 내부의 대규모 데이터베이스(`pilos_v2` 3.4GB, `oliview_project` 950MB) 및 멀티 에이전트 서비스 생태계(Model Gateway, Redis, Pilos, Oliview, Chatbot A/B, Nginx)를 다른 플랫폼(Linux, AWS, GCP, On-Premise GPU 서버 등)으로 무손실, 최소 다운타임, 원클릭 무결성 복원할 수 있도록 **완전 자동화된 크로스 플랫폼 마이그레이션 팩(Migration Pack)**을 패키징하고 배포 스크립트를 구현합니다.

---

## 2. Technical Context

- **언어 및 런타임 (Language/Version)**: POSIX Shell (Bash), Windows Batch/PowerShell, Python 3.10+ (표준 라이브러리 기반 무의존성 검증 엔진)
- **주요 의존성 (Primary Dependencies)**: Docker Engine 24.0+, Docker Compose v2, MySQL 8.0 Client/Dump Tools (`mysqldump`, `gzip`), Nginx, Redis 7
- **스토리지 및 데이터 (Storage)**:
  - MySQL 8.0 (`pilos-db:3306`, `bteam_db:3306`) - 4.35GB 원본 데이터 → `gzip -9` 압축 시 약 460MB
  - AI 모델 가중치 (Qwen3.5 LLM, BGE-M3, BGE-Reranker, Prompt-Guard-86M)
- **테스트 및 검증 (Testing)**: `verify_migration.py` (11개 전 엔드포인트 E2E 헬스체크 및 DB 레코드 일치율 전수 검사)
- **대상 플랫폼 (Target Platform)**: Linux (Ubuntu 22.04/24.04 LTS, Debian, RHEL), Windows 10/11 (Docker Desktop / WSL2), AWS EC2, GCP Compute Engine
- **성능 목표 (Performance Goals)**:
  - 데이터 무손실률: **100%**
  - DB 덤프 압축 소요 시간: 3분 이내
  - 타겟 호스트 복구 및 부트스트랩 완료 시간 (RTO): **15분 이내**
  - 마이그레이션 팩 기본 크기: **500MB 미만** (경량 팩)
- **보안 및 제약사항 (Security & Constraints)**: 민감 시크릿 키 분리 및 `.env` 템플릿화, SHA-256 비트 무결성 체크섬 매니페스트.

---

## 3. Constitution Check

*GATE: AISERVICE 거버넌스 헌법(Constitution v1.0.0) 준수 검토.*

| 헌법 원칙 (Principle) | 준수 여부 (Status) | 검증 내용 및 근거 |
| :--- | :---: | :--- |
| **I. 언어 및 커뮤니케이션 정책** | **PASS** | 모든 대화, 명세서, 계획서, 가이드라인 문서를 한국어로 작성하고 영어 원어를 명확히 병기함. |
| **II. TDD 및 계약 검증** | **PASS** | `verify_migration.py`를 통해 11개 엔드포인트 및 DB 데이터 무결성에 대한 자동화된 계약 검증 스위트를 선행 정의함. |
| **III. 서비스 모듈화 및 환경 격리** | **PASS** | A-Team, B-Team, Model Gateway, DB 간의 격리된 컨테이너 구조를 완벽히 보존하며 비파괴적 덤프 방식을 적용함. |
| **IV. 관측 가능성 및 보안** | **PASS** | 마이그레이션 매니페스트 및 SHA-256 체크섬 발행, 민감 키 마스킹 템플릿(`.env.migration.template`) 적용. |
| **V. 단순성 및 점진적 진화 (YAGNI)** | **PASS** | 복잡한 서드파티 백업 툴 없이 Docker/MySQL 표준 내장 도구 및 표준 라이브러리 스크립트로 가장 직관적이고 견고한 파이프라인 구축. |

---

## 4. Project Structure

### Documentation & Specifications
```text
specs/028-cross-platform-migration-pack/
├── spec.md                          # 기능 명세서
├── checklists/requirements.md       # 사양 품질 체크리스트 (16/16 Pass)
├── plan.md                          # 본 구현 계획서
├── research.md                      # Phase 0 연구 결과 (덤프, 스크립트, 모델 전략)
├── data-model.md                    # Phase 1 데이터베이스 및 매니페스트 스키마
├── contracts/
│   └── migration-cli-contracts.md  # Phase 1 CLI 도구 및 엔드포인트 계약
└── quickstart.md                    # Phase 1 원클릭 실행 및 검증 가이드
```

### Delivered Source Layout (`migration_pack/`)
```text
migration_pack/
├── database/                        # 압축된 DB 백업 및 체크섬
│   ├── pilos_v2.sql.gz              # A-Team Pilos MySQL 덤프 (~3.4GB 원본)
│   ├── oliview_project.sql.gz       # B-Team Oliview MySQL 덤프 (~950MB 원본)
│   └── checksums.sha256             # SHA-256 무결성 해시 매니페스트
├── scripts/                         # 원클릭 자동화 스크립트
│   ├── export_databases.sh          # [소스 호스트] DB 덤프 및 해시 생성 (Linux/WSL2)
│   ├── export_databases.bat         # [소스 호스트] DB 덤프 및 해시 생성 (Windows)
│   ├── export_offline_models.sh     # [소스 호스트] 폐쇄망용 오프라인 모델 번들러 (선택)
│   ├── export_offline_models.bat    # [소스 호스트] 폐쇄망용 오프라인 모델 번들러 (선택)
│   ├── pack_archive.sh              # [소스 호스트] 단일 압축본 패키징 도구 (Linux)
│   ├── pack_archive.bat             # [소스 호스트] 단일 압축본 패키징 도구 (Windows)
│   ├── bootstrap_restore.sh         # [타겟 호스트] 원클릭 DB 복원 및 서비스 기동 (Linux)
│   ├── bootstrap_restore.bat        # [타겟 호스트] 원클릭 DB 복원 및 서비스 기동 (Windows)
│   └── verify_migration.py          # [타겟 호스트] 11개 엔드포인트 E2E 자동 검증기
├── config/                          # 환경 설정 템플릿 및 인프라 설정
│   ├── .env.migration.template      # 통합 환경 변수 주입 템플릿
│   └── nginx.conf                   # 게이트웨이 프록시 설정
├── docker-compose.yml               # 다중 플랫폼 호환 Compose 매니페스트
└── MIGRATION_GUIDE.md               # 플랫폼별 상세 이전 매뉴얼
```

---

## 5. Complexity Tracking

헌법 및 설계 상의 복잡도 위반 사항 없음 (No Violations).
모든 컴포넌트가 표준 Docker Compose 및 MySQL 클라이언트 생태계와 100% 일치하도록 설계되었습니다.
