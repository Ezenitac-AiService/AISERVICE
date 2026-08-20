# Feature Specification: 028-cross-platform-migration-pack

**Feature Branch**: `028-cross-platform-migration-pack`  
**Created**: 2026-08-20  
**Status**: Draft  
**Input**: User description: "컨테이너 내부의 데이터베이스 정보까지 포함한 이 폴더의 모든 프로젝트를 다른 플렛폼에 마이그레이션 하기 위해, 마이그레이션 팩을 만들기 위한 조사를 시작하고, 분석해서 스펙을 작성해줘"

---

## Clarifications

### Session 2026-08-20
- Q: 마이그레이션 팩의 최종 배포 산출물 포맷을 어떤 방식으로 패키징할까요? → A: **하이브리드 지원** (기본 `migration_pack/` 디렉터리 구축 + 원클릭 단일 아카이브 압축 도구 `pack_archive.sh/.bat` 동시 제공)
- Q: 수 GB에 달하는 AI 모델 가중치(Qwen3.5 LLM, BGE-M3 임베딩, BGE-Reranker, Prompt-Guard-86M)의 이전 및 동기화 전략을 어떻게 구성할까요? → A: **경량 팩 + 선택적 오프라인 번들러** (기본 팩은 DB 덤프와 설정 중심 약 500MB 미만으로 유지하고, 폐쇄망용 오프라인 가중치 아카이브 도구 `export_offline_models.sh/.bat` 별도 제공)
- Q: 타겟 서버에서 데이터베이스(`pilos_v2`, `oliview_project`) 복원 시 기존 데이터 충돌 방지 및 안전 정책을 어떻게 처리할까요? → A: **안전 자동 감지 모드** (신규 DB는 무인 자동 복원, 기존 DB 발견 시 안전 확인 또는 `--force`/`--yes` 플래그로 무인 덮어쓰기 지원)

---

## 1. 개요 및 비즈니스 배경 (Overview & Business Context)

AISERVICE는 A-Team(Pilos 주식 감정지수 및 LLM 시장 보고서), B-Team(Oliview 올리브영 화장품 리뷰 RAG 및 챗봇), Model Gateway(vLLM/Qwen LLM, BGE-M3 임베딩, BGE-Reranker, Prompt Guard 86M), Redis 세션 인프라, 통합 Nginx 게이트웨이 및 2개의 대규모 MySQL 데이터베이스(`pilos_v2`, `oliview_project`)가 유기적으로 연동된 복합 멀티 에이전트 AI 서비스 생태계입니다.

현재 서비스 환경(Windows Docker 호스트)에서 타 플랫폼(Linux Ubuntu/Debian/RHEL, AWS EC2, GCP Compute Engine, On-Premise GPU 서버 또는 신규 Windows/WSL2 호스트)으로 서비스 전체를 **무손실, 최소 다운타임, 원클릭 무결성 복원**이 가능하도록 완벽한 **마이그레이션 팩(Migration Pack)**을 패키징하고 자동화하는 사양을 정의합니다.

---

## 2. 사용자 시나리오 및 인수 테스트 (User Scenarios & Testing)

### User Story 1 - 원클릭 데이터베이스 무손실 백업 및 덤프 생성 (Priority: P1)
시스템 관리자 또는 배포 엔지니어는 단일 마이그레이션 백업 명령을 실행하여 컨테이너 내부의 `pilos_v2`(약 3.4GB, 430만 건의 토큰화 및 시계열 댓글 데이터)와 `oliview_project`(약 950MB, 5.7만 건의 1024차원 BGE-M3 임베딩 벡터 및 리뷰 데이터)를 구조(Schema), 데이터(Data), 뷰(View), 트리거(Trigger)의 누락 없이 압축 덤프(`.sql.gz`) 및 SHA-256 체크섬으로 추출할 수 있어야 합니다.

- **Why this priority**: 데이터베이스 내의 1024차원 벡터 및 형태소 분석 시계열 데이터가 손실되면 수주 간의 크롤링 및 임베딩 재작업이 발생하므로 데이터 무손실 백업이 마이그레이션의 최우선 핵심입니다.
- **Independent Test**: 백업 스크립트 실행 후 `migration_pack/database/` 경로에 `pilos_v2.sql.gz`, `oliview_project.sql.gz` 및 `checksums.sha256` 파일이 생성되고 데이터 무결성 검증을 통과해야 합니다.
- **Acceptance Scenarios**:
  1. **Given** `pilos-db` 및 `bteam_db` 컨테이너가 가동 중인 상태에서, **When** `export_databases` 도구를 실행하면, **Then** 2개 DB 전체 테이블/뷰가 `utf8mb4` 인코딩으로 오류 없이 덤프 압축되고 해시 체크섬이 생성된다.
  2. **Given** 덤프 생성 완료 후, **When** 체크섬 검증 루틴을 실행하면, **Then** 모든 덤프 파일의 바이트 무결성이 100% 일치함이 확인된다.

---

### User Story 2 - 플랫폼 독립적 환경 설정 및 시크릿 번들링 (Priority: P2)
새로운 환경에 배포할 때 IP 주소, 도메인, GPU 유무, 포트 매핑 등이 변경될 수 있으므로, 시스템은 민감한 비밀키를 안전하게 템플릿화하고 새 환경에 맞춰 손쉽게 주입할 수 있는 환경 변수 매트릭스 번들(`.env.template` 및 설정 프로파일)을 제공해야 합니다.

- **Why this priority**: 타 플랫폼 환경(클라우드 Linux vs 로컬 WSL2 vs 온프레미스)에 따라 GPU 아키텍처 및 네트워크 포트가 상이하므로 설정 자동화가 필수적입니다.
- **Independent Test**: 환경 설정 번들러를 통해 신규 호스트 환경에 맞는 `.env`가 자동 생성되고 모든 서브프로젝트에 정확히 전파되는지 확인합니다.
- **Acceptance Scenarios**:
  1. **Given** 타 플랫폼 환경 정보(도메인/포트/GPU 여부)가 주어졌을 때, **When** `configure_environment`를 실행하면, **Then** 루트 `.env`, `ateam/.env`, `bteam/.env`, `model_gateway/.env`가 일관되게 생성된다.
  2. **Given** 신규 `.env`가 생성되었을 때, **When** 필수 환경 변수(DB 계정, LLM URL, 게이트웨이 포트 등) 검증을 수행하면, **Then** 누락된 키가 0건으로 통과된다.

---

### User Story 3 - 타 플랫폼 원클릭 복원 및 자동 부트스트랩 (Priority: P3)
새로운 타겟 서버(Linux 또는 Windows)에서 단일 실행 스크립트(`bootstrap_restore.sh` 또는 `bootstrap_restore.bat`)를 실행하면, 디렉터리 준비 -> DB 볼륨 생성 및 덤프 복원(안전 모드 자동 감지) -> 모델 및 컨테이너 빌드/기동 -> 11개 엔드포인트 헬스체크까지 완전 자동화되어 서비스가 즉시 정상 가동되어야 합니다.

- **Why this priority**: 타 플랫폼 이전 시 엔지니어의 수동 개입 및 설정 실수를 원천 차단하고 서비스 복구 시간(RTO)을 15분 이내로 단축하기 위함입니다.
- **Independent Test**: 깨끗한 신규 Docker 호스트 환경에서 `bootstrap_restore.sh`를 실행하여 11개 전 엔드포인트가 HTTP 200 OK를 반환하는지 검증합니다.
- **Acceptance Scenarios**:
  1. **Given** 신규 타겟 서버에 마이그레이션 팩이 전달된 상태에서, **When** 부트스트랩 스크립트를 실행하면, **Then** DB가 자동 복원되고 Docker Compose 전체 컨테이너(10개)가 Healthy 상태로 기동된다.
  2. **Given** 기존 DB가 존재하는 타겟 서버에서, **When** `--force` 플래그 없이 실행하면 덮어쓰기 확인 프롬프트가 표시되고, `--force` 지정 시 무인 덮어쓰기 복원이 수행된다.
  3. **Given** 서비스 기동 완료 후, **When** 통합 헬스체크 및 E2E 회귀 테스트를 실행하면, **Then** Gateway, A-Team Pilos, B-Team Oliview, Model Gateway 등 11개 전 엔드포인트가 Pass된다.

---

### User Story 4 - 모델 가중치 오프라인 캐시 및 온디맨드 다운로더 (Priority: P4)
폐쇄망(인터넷 제한 환경) 또는 대역폭 제한 환경으로의 이전을 위해, 필수 AI 모델(Qwen3.5 LLM, BGE-M3 임베딩, BGE-Reranker, Prompt Guard 86M)의 가중치 볼륨을 오프라인 아카이브로 내보내거나 타겟 서버에서 자동 동기화할 수 있는 모델 패키징 전략을 제공해야 합니다.

- **Why this priority**: AI 서비스의 특성상 모델 가중치(수 GB) 다운로드 실패나 버전 불일치가 발생하지 않도록 보장하기 위함입니다.
- **Independent Test**: 모델 다운로드/검증 스크립트를 실행하여 모델 캐시 경로에 필수 모델 가중치가 완전히 준비되었는지 확인합니다.
- **Acceptance Scenarios**:
  1. **Given** 마이그레이션 팩 내의 `export_offline_models.sh/.bat`를 실행했을 때, **When** 모델 캐시 무결성을 검사하면, **Then** 4종의 필수 모델 가중치 파일(Qwen, BGE-M3, Reranker, Prompt-Guard)이 완벽히 식별된다.

---

## 3. 엣지 케이스 및 예외 처리 (Edge Cases)

- **EC-001 (대용량 덤프 중단 및 메모리 부족)**: 3.4GB DB 덤프/복구 시 단일 트랜잭션 메모리 초과를 방지하기 위해 `--single-transaction`, `--quick`, `--max_allowed_packet=512M` 옵션 및 스트리밍 파이프라인 적용.
- **EC-002 (타겟 플랫폼 아키텍처 상이 - GPU vs CPU 모드)**: 타겟 호스트에 NVIDIA GPU가 없거나 드라이버가 미설치된 경우, Model Gateway가 자동으로 경량 CPU/양자화 모드로 안전 전환(Graceful Degradation) 안내.
- **EC-003 (포트 충돌 및 방화벽)**: 타겟 서버의 기존 80/8080 포트 점유 시 `.env`의 `GATEWAY_PORT` 변경만으로 Nginx 및 내부 프록시가 자동 정렬되도록 완전 파라미터화.
- **EC-004 (MySQL 문자셋 및 타임존 불일치)**: MySQL 덤프 생성 및 복원 시 `utf8mb4_unicode_ci` 및 `KST (Asia/Seoul)` 타임존을 강제 지정하여 한글 깨짐 및 시계열 데이터 왜곡 방지.
- **EC-005 (기존 DB 충돌)**: 타겟 서버에 동일한 데이터베이스가 이미 존재할 때 대화형 환경에서는 확인을 요청하고, CI/CD 자동화 환경에서는 `--force` 또는 `--yes` 플래그로 무인 덮어쓰기 지원.

---

## 4. 기능 요구사항 (Functional Requirements)

- **FR-001**: 시스템은 `pilos_v2` 및 `bteam_db`(`oliview_project`)의 전체 테이블, 인덱스, 뷰, 트리거를 포함하는 무손실 압축 덤프(`.sql.gz`) 생성 도구(`export_databases.sh/.bat`)를 제공해야 한다.
- **FR-002**: 시스템은 생성된 모든 백업 파일에 대한 SHA-256 해시 체크섬 매니페스트(`checksums.sha256`)를 자동 발행하고 검증할 수 있어야 한다.
- **FR-003**: 마이그레이션 팩은 소스 코드, Docker Compose 설정, Nginx 게이트웨이 설정, DDNS 설정, 문서 일체를 독립적인 아카이브 구조(`migration_pack/`)로 조직화해야 한다.
- **FR-004**: 시스템은 원클릭 단일 아카이브 압축 도구(`pack_archive.sh/.bat`)를 제공하여 전체 팩을 단일 `.tar.gz` 또는 `.zip`으로 즉시 묶을 수 있어야 한다.
- **FR-005**: 시스템은 폐쇄망 배포를 지원하기 위해 모델 가중치를 선택적으로 내보내는 `export_offline_models.sh/.bat` 도구를 제공해야 한다.
- **FR-006**: 시스템은 Linux(Bash) 및 Windows(PowerShell/Batch) 환경을 모두 지원하는 원클릭 복원 부트스트랩 스크립트(`bootstrap_restore.sh/.bat`)를 제공해야 한다.
- **FR-007**: 부트스트랩 스크립트는 신규 환경에서 Docker 볼륨 초기화, MySQL 데이터베이스 프로비저닝, 덤프 복원, 컨테이너 빌드 및 오케스트레이션을 안전 자동 감지 모드로 순차 무인 실행해야 한다.
- **FR-008**: 시스템은 마이그레이션 완료 후 즉시 11개 주요 서비스 엔드포인트(80/8080 게이트웨이, 8081 LLM, 8090 임베딩, 8091 리랭커, 5000 Pilos Web, 5050 Oliview Backend, 5173 Oliview Frontend, 8501 올리챗 A, 8002 올리뷰챗 B, 6379 Redis)의 정상 동작을 판정하는 자동화 검증 스크립트(`verify_migration.py`)를 제공해야 한다.
- **FR-009**: 시스템은 마이그레이션 절차, 전제조건(Docker, Docker Compose, GPU 요구사항), 문제 해결(Troubleshooting) 가이드를 담은 `MIGRATION_GUIDE.md` 문서를 포함해야 한다.

---

## 5. 핵심 엔티티 및 패키지 구조 (Key Entities & Package Structure)

### 마이그레이션 팩 디렉터리 레이아웃 (`migration_pack/`)
```text
migration_pack/
├── database/                   # 압축된 DB 백업 및 복원 스크립트
│   ├── pilos_v2.sql.gz         # A-Team Pilos MySQL 8.0 데이터베이스 덤프 (~3.4GB 원본)
│   ├── oliview_project.sql.gz  # B-Team Oliview MySQL 8.0 데이터베이스 덤프 (~950MB 원본)
│   └── checksums.sha256        # 무결성 검증용 SHA-256 체크섬
├── scripts/                    # 자동화 도구 스크립트
│   ├── export_databases.sh     # [소스 호스트] DB 덤프 및 해시 생성 스크립트 (Linux/WSL)
│   ├── export_databases.bat    # [소스 호스트] DB 덤프 및 해시 생성 스크립트 (Windows)
│   ├── export_offline_models.sh# [소스 호스트] 폐쇄망용 모델 가중치 오프라인 번들러 (선택)
│   ├── export_offline_models.bat# [소스 호스트] 폐쇄망용 모델 가중치 오프라인 번들러 (선택)
│   ├── pack_archive.sh         # [소스 호스트] 단일 압축본 패키징 도구 (Linux/WSL)
│   ├── pack_archive.bat        # [소스 호스트] 단일 압축본 패키징 도구 (Windows)
│   ├── bootstrap_restore.sh    # [타겟 호스트] 원클릭 DB 복원 및 서비스 기동 (Linux)
│   ├── bootstrap_restore.bat   # [타겟 호스트] 원클릭 DB 복원 및 서비스 기동 (Windows)
│   └── verify_migration.py     # [타겟 호스트] 11개 엔드포인트 E2E 자동 검증기
├── config/                     # 환경 변수 템플릿 및 Nginx/Redis 설정
│   ├── .env.migration.template # 통합 환경 변수 템플릿
│   └── nginx.conf              # 게이트웨이 프록시 설정
├── docker-compose.yml          # 다중 플랫폼 호환 Docker Compose 매니페스트
└── MIGRATION_GUIDE.md          # 마이그레이션 실행 매뉴얼
```

---

## 6. 성공 기준 (Success Criteria)

- **SC-001 (데이터 무손실률 100%)**: `pilos_v2`(11개 테이블, 1,280만+ 행) 및 `oliview_project`(22개 테이블, 17만+ 행)의 테이블 레코드 수 및 1024차원 임베딩 벡터가 타겟 플랫폼에 100% 오차 없이 복원된다.
- **SC-002 (원클릭 자동화 복구 시간 15분 이내)**: 타겟 호스트에서 부트스트랩 스크립트 실행 후 서비스 전체가 가동되기까지의 소요 시간이 15분 이내여야 한다.
- **SC-003 (11개 엔드포인트 100% 패스)**: 마이그레이션 완료 후 검증 스크립트 실행 시 11개 서비스 엔드포인트 전수 검사에서 오류율 0% (11/11 Pass)를 달성한다.
- **SC-004 (플랫폼 이식성)**: Linux(Ubuntu 22.04/24.04), Windows 10/11(Docker Desktop/WSL2) 및 주요 클라우드 환경에서 추가 코드 수정 없이 즉시 배포 가능하다.

---

## 7. 가정 및 제약사항 (Assumptions & Constraints)

- **타겟 호스트 전제조건**: 타겟 서버에 Docker Engine 24.0+ 및 Docker Compose v2(또는 Docker Desktop)가 사전 설치되어 있어야 합니다.
- **GPU 환경 가속**: NVIDIA GPU 환경에서는 `nvidia-container-toolkit`이 활성화되어 있어야 최적의 vLLM 가속(Qwen 4B/2B, BGE-M3)이 지원되며, 미지원 환경에서는 안내에 따라 CPU 폴백 설정을 적용합니다.
- **스토리지 여유 공간**: 덤프 생성 및 복원 작업을 위해 소스 및 타겟 호스트에 최소 15GB 이상의 디스크 여유 공간이 확보되어 있어야 합니다.
- **시크릿 보안**: 마이그레이션 팩 전송 시 외부 네트워크 노출을 방지하기 위해 SSH/SCP 또는 보안 스토리지(S3 프라이빗 버킷 등)를 통해 전송하는 것을 권장합니다.
