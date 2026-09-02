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
**Testing**: `pytest`, `verify_migration.py` (10 HTTP + Redis TCP PING으로 구성된 11개 검사 계약; Gateway 포트는 CLI 인자 > 환경 변수 > 기본값 순서)
**Normative Source**: 타겟 하드웨어, GPU/CPU fallback, 시크릿 보호 및 archive 판정은 `spec.md` §7.1과 FR/SC를 기준으로 하며, 본 계획서의 반복 내용은 구현 요약으로 취급한다.
**Target Platform**: Ubuntu Linux 24.04 LTS (Intel Core i7-930 SSE4.2 CPU, 24GB DDR3 RAM, NVIDIA GeForce GTX 1070 8GB GDDR5 GPU)  
**Project Type**: Multi-Service System Migration & Infrastructure Automation Pack  
**Performance Goals**: 원클릭 복원 완료 시간 $\le 25$분 (클린 OS) / $\le 10$분 (사전 준비 OS), 10개 HTTP + Redis TCP PING 11개 검사 성공률 100% (11/11 Pass), LLM API 지연시간 $\le 3.0$초 (Fast SLM)
**Constraints**: Zero Manual Configuration (외부 보호 키 사전 주입을 전제로 사용자 `.env` 수동 편집 0회), No `Illegal instruction` crashes on Non-AVX i7-930 CPU, 정상 GTX 1070 경로에서 8GB VRAM 내 100% GPU 서빙, `--skip-gpu` 시 CPU-only 전환, No Snap Docker
**Scale/Scope**: 기본/Green Compose 스택의 서비스 컨테이너 inventory, 4.8만+ 벡터 임베딩, 10개 HTTP와 Redis TCP PING 1개로 구성된 11개 검증 항목, 기본 `.tar.gz.enc`와 선택 `.zip.enc`를 생성하며 `both`는 동일 내용의 두 암호화 아카이브를 생성

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **원칙 I (Language & Communication Policy)**: 계획서, 명세서, 주석, 가이드 문서 일체 한국어 작성 완료.
- [x] **원칙 II (Test-First & Contract Verification)**: `contracts/` 4개 명세와 11개 검사(10개 HTTP + Redis TCP PING) 계약 및 Phase 21–22(T097–T102)의 archive 경계·Green resolver·CPU-only 전환·JIT·모델 포함 옵션을 테스트 우선으로 검증했다. 관련 회귀 스위트는 49개 테스트가 통과했다.
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
│   ├── checksums.sha256                    # [OUTPUT] clean source bundle 전체 파일 inventory 체크섬
│   ├── database/                          # [OUTPUT] 압축된 MySQL 덤프 파일 (.sql.gz)
│   │   └── checksums.sha256                # [OUTPUT] DB dump/volume 산출물 전용 체크섬
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
- `--include-volumes`, `--include-models`, `--target-os`, `--target-cpu`, `--target-gpu`, `--dry-run`, `--skip-gpu`, `--force` CLI 옵션 구현. `--include-models`는 설정된 모델 루트·파일 크기·SHA-256을 manifest/checksum에 기록하고 복원 시 동일 경로에 배치한다.
- `step_1_export_databases`: `export_databases.py` 호출 (InnoDB Flush).
- `step_2_export_volumes`: `export_docker_volumes.py` 호출 (Named Volume 아카이빙).
- `step_3_build_dist_bundle`: 실사용 `.env` 및 `ddns/.env`를 암호화된 아카이브에 포함하는 1:1 클린 소스 복사 (캐시/빌드 폴더 제외). 복호화 키는 아카이브 외부의 보호된 경로에서 주입.
- `step_4_generate_manifest`: `migration_manifest.json` v2.0 및 `checksums.sha256` 생성.
- `step_5_create_archive`: `--format tar.gz`는 `*.tar.gz.enc`, `--format zip`은 `*.zip.enc`를 생성하고, `--format both`는 동일 manifest/checksum을 포함한 두 개의 독립 아카이브를 생성한다. 병렬 생성은 선택 사항이며 모든 배포 아카이브는 외부 키 기반으로 암호화한다.

#### 1.2 `export_docker_volumes.py` [NEW]
- `ateam_db_data`, `bteam_bteam_mysql_data`, `green_mysql_data`, `green_chroma_data`, `aiservice_redis_data` 볼륨 백업.
- `bteam/docker-compose.green.yml`의 `mysql-green` 및 `chroma-green`을 staged startup/복원 대상에 포함하고 `GREEN_DB_*` 환경 변수를 사용.
- Green MySQL 논리 덤프는 `migration_pack/database/cosmetic_db.sql.gz`로 패키징하고 DB checksum/manifest에 포함.
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
- GPU 없음, `--skip-gpu`, 또는 GPU 호환성 실패 시 Compose GPU 설정을 제거하고 CPU fallback chain으로 readiness를 통과시키며, 보고서에는 `DEGRADED` 상태를 기록한다. 정상 GTX 1070 GPU 경로만 SC-003 PASS로 판정한다.

---

### Phase 4: E2E 검증 게이트 및 매뉴얼 구축 (Verification Gate & Guide)

#### 4.1 `verify_migration.py`
- 정확히 10개 HTTP 엔드포인트(Nginx 80/8080, Model Gateway 8081/8090/8091, A-Team Pilos 대시보드, B-Team Oliview UI/API/올리챗/올원챗)와 Redis TCP PING 1개를 E2E 헬스체크.
- Gateway 포트는 CLI 인자(`--gateway-port`, `--secondary-gateway-port`)가 환경 변수(`MIGRATION_VERIFY_GATEWAY_PORT`, `MIGRATION_VERIFY_SECONDARY_GATEWAY_PORT`)보다 우선하며, 미지정 시 각각 80과 8080을 사용한다.
- `verification_report.json` 발행.

#### 4.2 `MIGRATION_GUIDE.md` [NEW]
- Windows $\rightarrow$ Ubuntu 24.04 LTS 마이그레이션 전주기 단계별 가이드, 하드웨어 튜닝, 트러블슈팅 문서화.

---

## Convergence 및 최종화 단계

`tasks.md`의 후속 Convergence 작업은 기본 구현 Phase 1–10 이후 순차 실행한다. 각 단계의 완료 조건은 다음 단계로 진행하기 전 테스트와 산출물 검증을 통과해야 한다.

### Phase 11–13: 교차 아티팩트·품질 게이트 수렴

- T038–T050: 시크릿 보호, 패키징·덤프·볼륨·부트스트랩·JIT·검증기 동작을 명세와 정렬.
- T051–T061: Green 스택, Mutex 복원, 포트·디스크·권한·계약 테스트 및 fallback 경로를 보강.
- T062–T064: SLA 및 Ubuntu 호환성 매트릭스, DB/Chroma 무결성 측정을 수행.

### Phase 14–20: 계약·실행·데이터 검증 수렴

- T065–T076: 암호화 archive, 외부 키 주입, Green DB, 복원·검증·하드웨어·사전 요구사항 계약을 통합.
- T077–T096: Green 필수 구성, 서비스 inventory, 실제 컨테이너/볼륨 resolver, View definer 정책, endpoint 11/11, manifest 및 data-integrity를 재검증.

### Phase 21–22: 최종 잔여 작업

- T097–T101: 생성된 DB/볼륨 산출물의 암호화 archive 포함, Compose bind 파일 보존, Non-AVX/CUDA JIT 전달, 실제 Green 대상 resolve, `--skip-gpu` CPU-only 및 `DEGRADED` 보고를 완료.
- T102: `--include-models`의 실제 모델 파일 포함, 파일별 크기·SHA-256 manifest/checksum 기록, 동일 경로 복원 및 계약 테스트를 완료.
- T103–T108: 정적 분석 품질 게이트, `--skip-gpu` CLI/manifest 계약, `DEGRADED` 보고서 schema, 보조 JIT fallback, canonical 산출물, 런타임 모델 루트 정렬을 완료.

### Convergence 의존성

```text
Phase 1–10
    → Phase 11–13
    → Phase 14–20
    → Phase 21
    → Phase 22
    → Phase 23
    → 최종 테스트·린트·헌법 적합성 게이트
```

---

## Verification Plan

### Automated Tests
1. **단위/통합 테스트**:
   ```bash
   pytest tests/test_migration_pack.py tests/test_migration_convergence.py tests/test_migration_pending.py tests/test_verification_report.py model_gateway/tests/unit/test_cpu_detector.py -v
   ```
2. **Feature touchpoint 정적 분석 및 타입/구문 검사**:
   ```bash
   uv run --with ruff --python 3.12 ruff check make_migration_pack.py migration_pack/scripts model_gateway/scripts/probe_hardware.py model_gateway/src/core/cpu_detector.py model_gateway/src/core/process_manager.py tests/test_migration_pending.py
   python -m compileall -q make_migration_pack.py migration_pack/scripts model_gateway/scripts model_gateway/src/core tests/test_migration_pending.py
   ```
3. **사전 검증 시뮬레이션 (Dry-Run)**:
   ```bash
   python make_migration_pack.py --dry-run
   ```
4. **11개 검사 E2E 헬스체크(10개 HTTP + Redis TCP PING)**:
   ```bash
   python migration_pack/scripts/verify_migration.py --gateway-port "${MIGRATION_VERIFY_GATEWAY_PORT:-80}" --secondary-gateway-port "${MIGRATION_VERIFY_SECONDARY_GATEWAY_PORT:-8080}"
   ```
   `tests/test_migration_convergence.py`와 canonical `migration_pack/verification_report.json`의 schema·data-integrity 결과도 함께 확인한다.

### Manual Verification
1. **Windows 패키징 검증**: `dist/`에 기본 `.tar.gz.enc`(선택 `.zip.enc`/`both`), `migration_manifest.json`, `checksums.sha256`가 생성되고 평문 시크릿이 없는지 확인.
2. **우분투 복원 검증**: Ubuntu 24.04 환경에서 외부 키 주입 후 `sudo ./bootstrap_restore.sh -y` 실행하고 기본/Green 스택의 모든 컨테이너 `Up (healthy)`를 확인.
3. **부트스트랩 SLA 검증**: 사전 준비 OS는 10분 이내, 클린 Ubuntu 24.04(드라이버·Docker 설치 포함)는 25분 이내인지 시작/완료 타임스탬프로 측정.
4. **Ubuntu 호환성 매트릭스**: 동일 팩을 Ubuntu 22.04와 24.04에서 실행하여 CRLF, 권한, Docker/GPU 런타임 차이를 기록.
5. **DuckDNS 갱신 검증**: `http://ezenitac.duckdns.org` 접속 및 `crontab -l` 5분 주기 등록 확인.
