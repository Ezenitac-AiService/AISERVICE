# Implementation Plan: 043-docker-volume-ubuntu-migration-pack

**Branch**: `043-docker-volume-ubuntu-migration-pack` | **Date**: 2026-08-28 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/043-docker-volume-ubuntu-migration-pack/spec.md`

---

## Summary

AISERVICE의 전체 복합 멀티 에이전트 시스템(A-Team, B-Team, Model Gateway, Redis, Nginx 게이트웨이, DuckDNS 데몬)을 Windows 개발 환경에서 **클린 Ubuntu 24.04 LTS 서버(Intel Core i7-930 Non-AVX CPU, 24GB RAM, NVIDIA GeForce GTX 1070 8GB GPU)**로 1:1 완벽 이전하기 위한 **Zero-Configuration 원클릭 마이그레이션 팩**을 구축합니다.

주요 기술적 접근:
1. **실사용 환경 변수 100% 온전한 보존**: 루트 `.env` 및 `ddns/.env`의 모든 실사용 시크릿을 암호화 아카이브에 번들링하고 외부 보호 키를 주입하여 타겟 서버에서 사용자 수동 입력 0회(Zero-Config, 복호화 후 `chmod 600`)로 동작.
2. **클린 Ubuntu 24.04 LTS 자동 프로비저닝**: `install_prerequisites.sh`를 통해 Snap Docker를 배제하고 공식 APT Docker Engine 및 `nvidia-container-toolkit`을 `DEBIAN_FRONTEND=noninteractive` 모드로 무인 설치.
3. **하드웨어 특화 JIT 컴파일 및 VRAM 파티셔닝**: i7-930(SSE4.2, Non-AVX) CPU 크래시 방지 및 GTX 1070(Pascal `sm_61`) GPU 전용 플래그(`-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=61 -march=native`)로 `llama.cpp` JIT 자동 빌드, 8GB VRAM 내 3대 모델(Qwen 2B + BGE-M3 + Reranker) 100% GPU 가속 서빙.
4. **DBMS 및 Docker 볼륨 무손실 복원 (Mutex Strategy)**: MySQL InnoDB Dirty Page 플러시 및 ChromaDB SQLite WAL 체크포인트 기반 스냅샷 생성, 타겟 서버에서 물리 볼륨/논리 덤프 상호 배제 복원으로 테이블 충돌 방지.
5. **WSL2 Compose 정규화 및 DuckDNS 5분 크론 연동**: `/dev/dxg` 디렉티브 제거, Native Linux GPU 매핑 변환, IPv4 강제(`curl -4`) DuckDNS 5분 주기 크론 등록.
6. **11개 검사 E2E 헬스체크 게이트**: 복원 즉시 `verify_migration.py`를 통해 10개 HTTP와 Redis TCP PING을 전수 검증하고 `verification_report.json`을 발행.

---

## Technical Context

**Language/Version**: Python 3.11 / 3.12, Bash (POSIX compliant), C++17 (for llama.cpp JIT compilation)  
**Primary Dependencies**: Docker Engine 27.x, Docker Compose v2.29+, NVIDIA Container Toolkit v1.16+, CMake 3.28+, GCC/G++ 12+, `curl`, `tar` (sparse-aware), `gzip`  
**Storage**: MySQL 8.0/8.4 LTS (`pilos_v2`, `oliview_project`, Green `cosmetic_db`), ChromaDB v2 (`oliview_review_sentences_v2` with 48,210+ 1024-dim vectors), Redis 7 (AOF/RDB)
**Testing**: `pytest`, `verify_migration.py` (10 HTTP + Redis TCP PING으로 구성된 11개 검사 계약)
**Target Platform**: Ubuntu Linux 24.04 LTS (Intel Core i7-930 SSE4.2 CPU, 24GB DDR3 RAM, NVIDIA GeForce GTX 1070 8GB GDDR5 GPU)  
**Project Type**: Multi-Service System Migration & Infrastructure Automation Pack  
**Performance Goals**: 원클릭 복원 완료 시간 $\le 25$분 (클린 OS) / $\le 10$분 (사전 준비 OS), 10개 HTTP + Redis TCP PING 11개 검사 성공률 100% (11/11 Pass), LLM API 지연시간 $\le 3.0$초 (Fast SLM)
**Constraints**: Zero Manual Configuration (외부 보호 키 사전 주입을 전제로 사용자 `.env` 수동 편집 0회), No `Illegal instruction` crashes on Non-AVX i7-930 CPU, 8GB VRAM 내 100% GPU 서빙, No Snap Docker
**Scale/Scope**: 기본/Green Compose 스택의 서비스 컨테이너 inventory, 4.8만+ 벡터 임베딩, 10개 HTTP와 Redis TCP PING 1개로 구성된 11개 검증 항목, 기본 `.tar.gz` 압축 후 `.tar.gz.enc` 암호화 아카이브(선택 `.zip`, `both` 병렬 생성)

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **원칙 I (Language & Communication Policy)**: 계획서, 명세서, 주석, 가이드 문서 일체 한국어 작성 완료.
- [x] **원칙 II (Test-First & Contract Verification)**: `contracts/` 4개 명세와 11개 검사(10개 HTTP + Redis TCP PING) 계약에 대한 Red 테스트 선행 및 Green 회귀 검증을 완료함.
- [x] **원칙 III (Service Modularity & Environment Isolation)**: A-Team, B-Team, Model Gateway의 독립 볼륨 및 컨테이너 격리 보존.
- [x] **원칙 IV (Observability & Structured Logging)**: `migration_manifest.json` v2.0 및 `verification_report.json` 구조화 로깅 규격 완비.
- [x] **원칙 V (Simplicity & YAGNI)**: 복잡한 서드파티 배포 도구 대신 순수 Python/Bash 기반 경량 원클릭 부트스트랩 채택.
- [x] **원칙 VI (Dual Operating Modes & Zero Hardcoding)**: `.env` 기반 동적 설정 주입, 개발/시연 모드 1:1 무인 이전 완벽 준수.

---

## Project Structure

### Documentation (this feature)

```text
specs/043-docker-volume-ubuntu-migration-pack/
├── spec.md              # Feature specification (100% clarify & multi-persona validated)
├── plan.md              # Implementation plan (this file)
├── research.md          # Phase 0 research (Noble 24.04, i7-930/GTX 1070, Mutex DB, Snap trap)
├── data-model.md        # Phase 1 data model & state transitions
├── quickstart.md        # Phase 1 runnable quickstart validation guide
├── contracts/           # Phase 1 contracts & schemas
│   ├── migration-cli-contract.md
│   ├── bootstrap-restore-contract.md
│   ├── manifest-schema.json
│   └── verification-report-schema.json
├── checklists/
│   └── requirements.md  # Quality validation checklist (100% Pass)
└── tasks.md             # Phase 2 output (/speckit-tasks command)
```

### Source Code (repository root)

```text
c:\AISERVICE\
├── make_migration_pack.py                 # [MODIFY] 고도화된 통합 패키징 CLI v2.0
├── .env                                   # [MODIFY] 실사용 시크릿 및 DUCKDNS 설정 통합
├── docker-compose.yml                     # [MAINTAIN] 루트 멀티 컨테이너 정의
├── migration_pack/                        # [ENHANCE] 마이그레이션 전용 자산 및 스크립트
│   ├── scripts/
│   │   ├── export_databases.py            # [MODIFY] InnoDB safe flush 및 덤프 스트리밍
│   │   ├── export_docker_volumes.py       # [NEW] Docker named volume 물리 sparse 압축기
│   │   ├── install_prerequisites.sh       # [NEW] 클린 Ubuntu 24.04 Docker/GPU 무인 프로비저너
│   │   ├── normalize_compose.py           # [NEW] WSL2 디바이스 -> Linux GPU 런타임 변환기
│   │   ├── bootstrap_restore.sh           # [MODIFY] 우분투 원클릭 멱등 부트스트랩 스크립트
│   │   ├── bootstrap_restore.py           # [MODIFY] 멀티 OS 호환 복원 코어 로직
│   │   └── verify_migration.py            # [MODIFY] 10개 HTTP + Redis TCP PING 11개 검사 게이트
│   ├── database/                          # [OUTPUT] 압축된 MySQL 덤프 파일 (.sql.gz)
│   ├── volumes/                           # [OUTPUT] Docker Volume 물리 아카이브 (.tar.gz)
│   ├── config/
│   │   └── ddns.env.template              # [MAINTAIN] DuckDNS 템플릿
│   └── MIGRATION_GUIDE.md                 # [NEW] 우분투 마이그레이션 상세 매뉴얼
├── bteam/docker-compose.green.yml         # [MODIFY] Green MySQL/Chroma staged stack
├── model_gateway/
│   └── scripts/
│       ├── build_llama.sh                 # [NEW] i7-930(SSE4.2) / GTX 1070(sm_61) JIT 빌더
│       └── probe_hardware.py              # [NEW] CPU/GPU/VRAM 런타임 하드웨어 프로버
└── ddns/
    ├── duck.sh                            # [NEW] 우분투용 DuckDNS IPv4 5분 크론 갱신 스크립트
    └── .env                               # [MAINTAIN] DuckDNS 실제 토큰 보존
```

---

## Proposed Changes & Phased Implementation

### Phase 1: 패키징 파이프라인 고도화 (Packaging Pipeline v2.0)

#### 1.1 `make_migration_pack.py`
- `--include-volumes`, `--include-models`, `--target-os`, `--target-cpu`, `--target-gpu`, `--dry-run`, `--force` CLI 옵션 구현.
- `step_1_export_databases`: `export_databases.py` 호출 (InnoDB Flush).
- `step_2_export_volumes`: `export_docker_volumes.py` 호출 (Named Volume 아카이빙).
- `step_3_build_dist_bundle`: 실사용 `.env` 및 `ddns/.env`를 암호화된 아카이브에 포함하는 1:1 클린 소스 복사 (캐시/빌드 폴더 제외). 복호화 키는 아카이브 외부의 보호된 경로에서 주입.
- `step_4_generate_manifest`: `migration_manifest.json` v2.0 및 `checksums.sha256` 생성.
- `step_5_create_archive`: `--format tar.gz`를 기본으로 단일 아카이브를 생성하고, `--format zip` 또는 `--format both`로 선택/병렬 생성. 모든 배포 아카이브는 시크릿 보호 정책에 따라 암호화.

#### 1.2 `export_docker_volumes.py` [NEW]
- `ateam_db_data`, `bteam_bteam_mysql_data`, `green_mysql_data`, `green_chroma_data`, `aiservice_redis_data` 볼륨 백업.
- `bteam/docker-compose.green.yml`의 `mysql-green` 및 `chroma-green`을 staged startup/복원 대상에 포함하고 `GREEN_DB_*` 환경 변수를 사용.
- SQLite WAL 체크포인트 및 Redis BGSAVE 트리거.
- `tar --sparse -czf`를 사용하여 Sparse File 크기 최적화.

---

### Phase 2: 우분투 부트스트랩 및 인프라 프로비저닝 (Target Ubuntu Bootstrap)

#### 2.1 `install_prerequisites.sh` [NEW]
- Ubuntu 24.04 LTS 환경에서 Snap Docker 방지 및 공식 Docker APT 패키지 무인 설치 (`DEBIAN_FRONTEND=noninteractive`).
- NVIDIA GPU 감지 시 공식 `nvidia-container-toolkit` 설치 및 `/etc/docker/daemon.json` 런타임 등록, Docker 재시작.

#### 2.2 `normalize_compose.py` [NEW]
- `docker-compose.yml`에서 Windows WSL2 전용 마운트(`/dev/dxg`, `/usr/lib/wsl`)를 제거하고 Linux 표준 `nvidia` GPU 디바이스 디렉티브로 자동 변환.

#### 2.3 `bootstrap_restore.sh` & `bootstrap_restore.py`
- `.env`에 `chmod 600` 보안 권한 적용 및 스크립트 실행 권한 부여 (`chmod +x`).
- Docker 볼륨 생성 및 물리 아카이브 복원 $\rightarrow$ Mutex 규칙으로 중복 SQL 덤프 생략. Green 스택의 `mysql-green`/`chroma-green`도 동일한 복원·readiness 게이트를 적용.
- DuckDNS IPv4 갱신 (`curl -4`) 및 우분투 `crontab` 5분 주기 등록 (`ddns/duck.sh`).
- DB, Redis, Model Gateway 인프라 Healthy 상태 확인 후 애플리케이션 컨테이너 순차 기동.

---

### Phase 3: 타겟 하드웨어 적응 및 Model Gateway JIT 빌더 (Hardware Adaptation)

#### 3.1 `probe_hardware.py` [NEW]
- CPU 명령어 지원(AVX, AVX2, AVX-512, SSE4.2) 및 GPU Compute Capability, 가용 VRAM 용량 런타임 프로빙.

#### 3.2 `build_llama.sh` [NEW]
- i7-930(Nehalem, Non-AVX) CPU 감지 시 `-march=native -DGGML_AVX=OFF -DGGML_AVX2=OFF -DGGML_FMA=OFF` 플래그 적용.
- GTX 1070(Pascal) 감지 시 `-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=61` 플래그 적용하여 `llama.cpp` JIT 컴파일.

---

### Phase 4: E2E 검증 게이트 및 매뉴얼 구축 (Verification Gate & Guide)

#### 4.1 `verify_migration.py`
- 정확히 10개 HTTP 엔드포인트(Nginx 80/8080, Model Gateway 8081/8090/8091, A-Team Pilos 대시보드, B-Team Oliview UI/API/올리챗/올원챗)와 Redis TCP PING 1개를 E2E 헬스체크.
- `verification_report.json` 발행.

#### 4.2 `MIGRATION_GUIDE.md` [NEW]
- Windows $\rightarrow$ Ubuntu 24.04 LTS 마이그레이션 전주기 단계별 가이드, 하드웨어 튜닝, 트러블슈팅 문서화.

---

## Verification Plan

### Automated Tests
1. **단위/통합 테스트**:
   ```bash
   pytest tests/test_migration_pack.py -v
   ```
2. **사전 검증 시뮬레이션 (Dry-Run)**:
   ```bash
   python make_migration_pack.py --dry-run
   ```
3. **11개 검사 E2E 헬스체크(10개 HTTP + Redis TCP PING)**:
   ```bash
   python migration_pack/scripts/verify_migration.py
   ```

### Manual Verification
1. **Windows 패키징 검증**: `dist/`에 기본 `.tar.gz`(선택 `.zip`/`both`), `migration_manifest.json`, `checksums.sha256`가 생성되고 평문 시크릿이 없는지 확인.
2. **우분투 복원 검증**: Ubuntu 24.04 환경에서 외부 키 주입 후 `sudo ./bootstrap_restore.sh -y` 실행하고 기본/Green 스택의 모든 컨테이너 `Up (healthy)`를 확인.
3. **부트스트랩 SLA 검증**: 사전 준비 OS는 10분 이내, 클린 Ubuntu 24.04(드라이버·Docker 설치 포함)는 25분 이내인지 시작/완료 타임스탬프로 측정.
4. **Ubuntu 호환성 매트릭스**: 동일 팩을 Ubuntu 22.04와 24.04에서 실행하여 CRLF, 권한, Docker/GPU 런타임 차이를 기록.
5. **DuckDNS 갱신 검증**: `http://ezenitac.duckdns.org` 접속 및 `crontab -l` 5분 주기 등록 확인.
