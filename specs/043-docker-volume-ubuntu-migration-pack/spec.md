# Feature Specification: 043-docker-volume-ubuntu-migration-pack

**Feature Branch**: `043-docker-volume-ubuntu-migration-pack`  
**Created**: 2026-08-28  
**Status**: Draft  
**Input**: User description: "도커 볼륨을 포함해서 dbms의 db를 포함한 현재 작업폴더의 모든 서비스 구조를 그대로 우분투 서버에 마이그레이션 하는 내용으로 make_migration_pack을 고도화 하기 위한 리서치와 분석, 검토, 검증을 진행하고 스펙을 작성. duckdns에 ddns 연결하는것도 포함. 모델 게이트웨이는 이전한 플렛폼의 cpu 명령지원 gpu 세대 vram 용량에 맞춰서 필요하면 llama.cpp를 다시 빌드해야 함, 이전한 파일이 실행안된다고 멈추면 안됨. .env.example 만 옮기거나 해서 마이그레이션 된 플렛폼에서 .env 파일을 작성해야 한다거나 설정 값을 넣어줘야 하는 일이 발생하면 안됨. 동적으로 실제 플렛폼 아키텍처에 맞게 설정값을 작성하는 것들은 해당 기능을 통해 생성되게 해야 하고 누락되는 환경변수나 계정, 비번, api 키등이 있으면 안됨. 이번 마이그레이션은 같은 개발 모드인데 윈도우 플렛폼에서 리눅스 플렛폼으로 이전하는 것임. 완전 클린한 우분투 서버 24.04 lts의 경우 gpu 드라이버, cuda toolkit, cudnn 등이 아예 설치가 안되어있을 수도 있음. 마이그레이션 대상 플렛폼 아키텍처에 i7 930 cpu, 24gb ram, gtx 1070 8gb gpu가 포함되어 있음."

---

## Clarifications

### Session 2026-08-28

- **Q1: 타겟 우분투 서버에서 `bootstrap_restore.sh` 수행 시, 하드웨어 사양(CPU 명령어 지원, GPU 세대 및 VRAM 용량)에 따른 Model Gateway 및 llama.cpp 자동 감지 및 빌드 전략을 어떤 방식으로 구성할까요?**  
  $\rightarrow$ **A: 스마트 자동 적응형 (JIT Rebuild & Auto-Offload)**: 호환 바이너리로 1차 기동 시도 $\rightarrow$ 호환성 오류(`Illegal instruction`, CUDA 드라이버 불일치) 감지 시 타겟 호스트 CPU/GPU 아키텍처에 맞춰 `llama.cpp`를 자동 즉시 재빌드(JIT Rebuild)하며, VRAM 용량에 따라 GPU 레이어 오프로딩(`-ngl`)을 자동 튜닝하여 서버가 절대 멈추지 않고 상시 가동되도록 보장.
- **Q2: 우분투 타겟 서버에서 DuckDNS DDNS 동적 도메인 연동을 어떤 방식으로 자동 구성하고 유지할까요?**  
  $\rightarrow$ **A: 호스트 Cron 자동 등록 + 즉시 갱신**: `.env`에 `DUCKDNS_DOMAIN` 및 `DUCKDNS_TOKEN`이 설정된 경우 `bootstrap_restore.sh`가 우분투 `cron` 및 백그라운드 갱신 스크립트(`ddns/duck.sh`)를 5분 주기로 자동 등록하고 초기 IP 갱신을 즉시 수행.
- **Q3: 환경 변수(`.env`) 및 시크릿(DB 비밀번호, API 키, DuckDNS 토큰 등)의 이전 및 복원 정책을 어떻게 처리할까요?**  
  $\rightarrow$ **A: 실사용 환경 변수 100% 보존 및 암호화된 Zero-Config 무인 배포 (개발-to-개발 플랫폼 이전)**: 현재 작업 폴더의 실사용 `.env`(루트 및 `ddns/.env` 등)는 실제 값(DB 계정/비밀번호, Kiwoom API 키, DuckDNS 토큰, SMTP 암호 등)을 누락 없이 **암호화된 아카이브 안에** 포함한다. 복호화 키는 아카이브에 포함하지 않고 타겟 호스트의 보호된 경로 또는 동등한 비밀 주입 경로(`MIGRATION_PACK_KEY_FILE`)에서 제공하며, 키가 없으면 복원을 실패시킨다. 따라서 타겟 서버에서 사용자의 수동 입력/편집 없이 동작하되(Zero-Config), 원문 시크릿은 로그·매니페스트·체크섬·평문 전송에 노출하지 않고 압축 해제 후 `.env`에 `chmod 600`을 적용한다. 플랫폼별로 동적 조정이 필요한 설정(호스트 IP, GPU 디바이스 설정 등)만 부트스트랩 스크립트가 자동 감지하여 주입.
- **Q4: 완전 클린한 Ubuntu 24.04 LTS 환경에서 NVIDIA GPU 하드웨어가 감지되었으나 GPU 드라이버, CUDA Toolkit, `nvidia-container-toolkit`이 전혀 설치되어 있지 않은 경우, `bootstrap_restore.sh`가 어떻게 대응하도록 할까요?**  
  $\rightarrow$ **A: 부트스트랩 중 대화형/자동화 GPU 드라이버 & 툴킷 설치 (Option B 확정)**: 본 마이그레이션은 서비스 운영 모드가 아니므로 무중단보다 완전한 환경 구축이 우선임. 클린 Ubuntu 24.04 LTS에서 Docker 및 NVIDIA GPU 하드웨어를 감지하고, 드라이버/`nvidia-container-toolkit` 미설치 시 자동 설치(대화형 확인 또는 `--force`/`-y` 무인 설치)를 수행하여 Docker 데몬 런타임을 구성한 후 컨테이너 복원 및 기동으로 원활히 연결. GPU가 없는 CPU 전용 서버인 경우 CPU 최적화 모드로 자동 전환.
- **Q5: 5대 페르소나 1차 심층 분석 결과 도출된 6대 강건화 항목을 스펙에 통합 반영할까요?**  
  $\rightarrow$ **A: 전원 승인 (6대 강건화 항목 전격 통합)**:
    1. **WSL2 $\rightarrow$ Native Ubuntu Compose 디바이스 자동 정규화** (`/dev/dxg` 자동 제거 및 네이티브 NVIDIA 런타임 변환)
    2. **DB 복원 파이프라인 멱등성 및 이중화 충돌 방지 (Mutex Restoration)** (물리 볼륨 우선 복원 $\rightarrow$ 성공 시 중복 SQL 덤프 생략)
    3. **Model Gateway JIT 빌드 툴체인 및 Compute Capability(`sm_60`~`sm_90`) 자동 매핑**
    4. **클린 Ubuntu 24.04 파일 권한 정규화** (`.env`는 `chmod 600`, 스크립트는 `chmod +x`, DB 볼륨 UID/GID 호환)
    5. **DuckDNS IPv4 강제(`curl -4`) 및 5분 주기 크론 안정화**
    6. **복원 시간 예산 현실화** (클린 OS 25분 이내, 사전 준비 OS 10분 이내) 및 `set -euo pipefail` 멱등 에러 트랩
- **Q6: 5대 페르소나 2차 심층 분석 결과 도출된 4대 미세 보강 항목을 스펙에 최종 반영할까요?**  
  $\rightarrow$ **A: 전원 승인 (4대 미세 보강 항목 최종 통합)**:
    1. **APT 무인 환경 변수 표준화 (`DEBIAN_FRONTEND=noninteractive`)**: `needrestart` 대화창 자동 바이패스 및 완전 무인 패키지 설치 보장.
    2. **DB 볼륨 추출 안전 절차 (InnoDB Dirty Page 플러시)**: 라이브 MySQL 볼륨 백업 시 `FLUSH TABLES WITH READ LOCK` 또는 `docker pause` 적용으로 디스크-메모리 정합성 보장.
    3. **Model Gateway 계층형 런타임 폴백 (vLLM $\leftrightarrow$ llama.cpp)**: GPU vLLM $\rightarrow$ 저VRAM llama.cpp CUDA $\rightarrow$ AVX 비활성·SSE4.2 호환 CPU OpenBLAS 3단계 무정지 계층 폴백.
    4. **단계별 컨테이너 기동 시퀀스**: 인프라(DB, Redis, Model Gateway)의 완전한 Healthy 상태 확인 후 애플리케이션(UI, Backend, Chatbot)을 기동하여 Connection Refused 방지.
- **Q7: 타겟 호스트 하드웨어 사양(Intel i7-930, 24GB RAM, GTX 1070 8GB)에 특화된 빌드 및 런타임 제약사항을 명세에 반영할까요?**  
  $\rightarrow$ **A: 전격 반영**:
    - **CPU (Intel Core i7-930 Nehalem / Bloomfield)**: AVX/AVX2를 지원하지 않고 **SSE4.2까지만 지원**하므로, 일반적인 AVX/AVX2 사전 컴파일 바이너리 실행 시 `Illegal instruction (core dumped)` 오류가 100% 발생함. 따라서 `llama.cpp` 컴파일 시 `-march=native` (또는 `-DGGML_AVX=OFF -DGGML_AVX2=OFF -DGGML_FMA=OFF`)를 적용하여 Nehalem 아키텍처에 맞게 안전 빌드해야 함.
    - **GPU (NVIDIA GeForce GTX 1070 8GB Pascal)**: Compute Capability **`sm_61` (6.1)**에 해당하므로, CMake 빌드 플래그로 **`-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=61`**을 적용하여 Pascal Tensor 연산에 최적화함.
    - **VRAM (8GB GDDR5)**: Qwen 2B LLM (~2.5GB) + BGE-M3 임베딩 (~1.2GB) + BGE-Reranker (~1.2GB) 총 합계가 약 5.0GB로 `VRAM_SAFETY_LIMIT_MB=5000` 설정 하에 8GB VRAM 내에서 100% GPU 가속 완벽 수용.
    - **RAM (24GB DDR3)**: MySQL 8.0, Redis 7, ChromaDB v2, Nginx, 백엔드/프론트엔드 컨테이너 10개를 여유롭게 동시 구동.

---

## 1. 개요 및 비즈니스 배경 (Overview & Business Context)

AISERVICE는 A-Team(Pilos 주식 감정지수 및 수급 분석), B-Team(Oliview 올리브영 화장품 리뷰 전주기 파이프라인, ChromaDB v2 벡터 검색, 대시보드, 올리챗/올원챗), Model Gateway(vLLM/Qwen LLM, BGE-M3 임베딩, BGE-Reranker, Prompt Guard), Redis 세션 인프라, 통합 Nginx 게이트웨이 및 DuckDNS DDNS 데몬이 유기적으로 결합된 복합 멀티 에이전트 AI 서비스 생태계입니다.

현재 개발/실증 환경(Windows 호스트 및 WSL2/Docker Desktop)에서 **타겟 개발/실증 인프라인 우분투 서버 (Ubuntu 24.04 LTS, Intel Core i7-930 CPU, 24GB RAM, NVIDIA GeForce GTX 1070 8GB GPU)**로 서비스 전체를 1:1 이전하기 위해, 기존의 `make_migration_pack` 도구를 대폭 고도화합니다.

특히 타겟 호스트의 CPU(i7-930)가 **AVX/AVX2 명령어를 지원하지 않는 Nehalem 1세대 아키텍처(SSE4.2 지원)**이고, GPU가 **Pascal 아키텍처(GTX 1070 8GB, sm_61)**인 특성을 고려하여, 타겟 하드웨어에 최적화된 `llama.cpp` JIT 무중단 컴파일 및 8GB VRAM 최적 배분을 보장합니다.

본 피처의 핵심 범위:
1. **클린 Ubuntu 24.04 LTS 사전 환경 무인 점검 (`DEBIAN_FRONTEND=noninteractive`, Snap Docker 방지) 및 공식 Docker / NVIDIA GPU 드라이버 / `nvidia-container-toolkit` 자동 설치 프로비저닝**
2. **타겟 하드웨어(i7-930 Non-AVX SSE4.2 CPU + GTX 1070 sm_61 8GB GPU)에 맞춘 `llama.cpp` Pascal/Nehalem 최적화 자동 JIT 컴파일 및 8GB VRAM 내 3대 모델(Qwen 2B + BGE-M3 + Reranker) 100% GPU 가속 서빙**
3. **실사용 환경 변수(`.env`) 및 시크릿(DB 비밀번호, API 키, 토큰 등)의 암호화 보존 및 Zero-Config 자동 구성 (`chmod 600` 보안)**
4. **MySQL 데이터베이스 논리 덤프 및 물리 도커 볼륨(Docker Volume)의 Mutex 상호 배제 무손실 추출/복원 (InnoDB Dirty Page 플러시 적용)**
5. **ChromaDB v2 SQLite WAL 체크포인트 보존 및 Redis BGSAVE 상태의 완전 보존**
6. **현재 작업 폴더 내 모든 서비스 모듈(A-Team, B-Team, Model Gateway, Gateway, Config, Scripts)의 1:1 디렉터리 구조 미러링**
7. **WSL2 전용 경로(`/dev/dxg`, `/usr/lib/wsl`) 자동 감지 및 Native Ubuntu Compose 디렉티브 자동 정규화**
8. **DuckDNS DDNS 동적 도메인 IPv4 강제 연동 및 5분 주기 크론 멱등 동기화**
9. **우분투 환경에 맞춘 줄바꿈(CRLF $\rightarrow$ LF), 실행 권한(`chmod +x`), 소유권 정규화**
10. **단계적 오케스트레이션(인프라 Healthy 확인 후 앱 기동)을 통한 원클릭 멱등 자동 부트스트랩(`bootstrap_restore.sh`) 및 11개 검사 무결성 검증**

---

## 2. 사용자 시나리오 및 인수 테스트 (User Scenarios & Testing)

### User Story 1 - 클린 Ubuntu 24.04 LTS 환경 무인 자동 감지 및 인프라 프로비저닝 (Priority: P1) 🎯 MVP

타겟 서버가 방금 OS만 설치된 완전 클린한 Ubuntu 24.04 LTS 서버인 경우, `bootstrap_restore.sh`가 시스템 환경을 감지하여 Snap Docker 패키징을 배제하고 공식 APT 저장소를 통해 Docker Engine, Docker Compose plugin, 그리고 장착된 NVIDIA GTX 1070 GPU에 대한 드라이버 및 `nvidia-container-toolkit`을 자동으로 설치하고 Docker GPU 런타임을 등록하여 복원 사전 환경을 완벽하게 준비해야 합니다.

- **Why this priority**: 클린 우분투 서버에서 필수 패키지나 GPU 드라이버가 없어서 수동 설치를 반복하는 번거로움과 TUI 멈춤 현상을 없애고 마이그레이션 성공률을 100%로 보장하기 위함입니다.
- **Independent Test**: GPU 드라이버가 없는 클린 우분투 VM/호스트에서 `bootstrap_restore.sh` 실행 시 무인 패키지 설치가 동작하고 Docker와 NVIDIA 런타임이 정상 활성화되는지 확인합니다.
- **Acceptance Scenarios**:
  1. **Given** Docker가 없는 클린 Ubuntu 24.04에서, **When** 부트스트랩 스크립트가 실행되면, **Then** 대화창 멈춤 없이 공식 Docker Engine과 Compose 플러그인이 자동 설치된다.
  2. **Given** NVIDIA GTX 1070이 장착되었으나 드라이버/툴킷이 없는 환경에서, **When** 설치 옵션을 수락(또는 `-y` 지정)하면, **Then** 호환 드라이버와 `nvidia-container-toolkit`이 설치되고 Docker 데몬에 GPU 런타임이 등록된다.

---

### User Story 2 - 타겟 하드웨어(i7-930 SSE4.2 & GTX 1070 sm_61) 자율 적응 및 무중단 JIT 빌드 (Priority: P1) 🎯 MVP

타겟 우분투 서버의 CPU 아키텍처(i7-930: AVX 미지원, SSE4.2 지원)와 GPU 아키텍처(GTX 1070: Pascal `sm_61`, 8GB VRAM)를 런타임에 자동 감지하여, AVX 명령어 충돌(`Illegal instruction`)을 원천 방지하도록 `-march=native` 및 `CMAKE_CUDA_ARCHITECTURES=61` 플래그로 `llama.cpp`를 자동 컴파일하고, 8GB VRAM 예산(5.0GB 점유) 내에서 Qwen 2B LLM, BGE-M3 임베딩, BGE-Reranker를 100% GPU 가속으로 무정지 서빙해야 합니다.

- **Why this priority**: Nehalem 구형 CPU에서 현대 AVX 바이너리 실행 시 발생하는 `Illegal instruction` 크래시를 방지하고, GTX 1070의 8GB VRAM을 최적 활용하여 AI 모델 서빙의 완전성을 확보하기 위함입니다.
- **Independent Test**: i7-930 및 GTX 1070 환경에서 Model Gateway 기동 시 하드웨어를 자동 감지하여 `sm_61` / SSE4.2 최적화 컴파일을 완수하고 LLM 추론 API(8081)와 임베딩 API(8090)가 200 OK를 반환하는지 검증합니다.
- **Acceptance Scenarios**:
  1. **Given** AVX를 지원하지 않는 i7-930 CPU 환경에서, **When** Model Gateway가 기동되면, **Then** `-march=native`로 AVX 플래그를 배제하고 컴파일하여 `Illegal instruction` 에러 없이 정상 기동된다.
  2. **Given** GTX 1070 8GB GPU 환경에서, **When** Qwen 2B + BGE-M3 + Reranker 3종 모델이 로드되면, **Then** 8GB VRAM 내(~5.0GB)에서 OOM 없이 100% GPU 가속 추론을 제공한다.

---

### User Story 3 - 도커 볼륨 및 DBMS 데이터의 안전 패키징 및 Mutex 복원 (Priority: P1) 🎯 MVP

시스템 운영자 또는 배포 엔지니어는 단일 명령어(`make_migration_pack.py`)를 실행하여, MySQL의 메모리 Dirty Page를 플러시한 상태에서 기본 스택의 `pilos-db`(`pilos_v2`), `bteam_db`(`oliview_project`) 및 Green 스택의 `mysql-green`(`cosmetic_db`)에 대한 일관성 덤프(`.sql.gz`)와 물리 도커 볼륨 아카이브를 안전하게 추출 압축하고 SHA-256 무결성 체크섬을 자동 생성할 수 있어야 합니다. 타겟 호스트에서는 물리 볼륨 복원 성공 시 중복 SQL 덤프 실행을 건너뛰어 테이블 충돌을 방지합니다.

- **Why this priority**: DBMS 테이블 데이터(430만+ 건의 Pilos 시계열 토큰, 4.8만+ 건의 Oliview 화장품 리뷰 및 분석 보고서) 및 ChromaDB 1024차원 고차원 벡터 볼륨의 무손실 보존과 복원 시 중복 충돌 방지를 위함입니다.
- **Independent Test**: 패키징 후 `dist/` 내에 암호화된 기본 아카이브(`.tar.gz`, 필요 시 `.zip`)와 덤프/볼륨 산출물이 생성되고, 타겟 서버에서 키를 보호된 경로로 주입해 복호화한 뒤 물리 볼륨 복원 후 MySQL 테이블 중복 충돌 없이 100% 정상 로드되는지 확인합니다.
- **Acceptance Scenarios**:
  1. **Given** MySQL 컨테이너(`pilos-db`, `bteam_db`, `mysql-green`) 및 ChromaDB 볼륨이 존재하는 상태에서, **When** `make_migration_pack.py --include-volumes`를 실행하면, **Then** MySQL 논리 덤프와 `green_mysql_data`/`green_chroma_data`를 포함한 지정 물리 볼륨 아카이브가 생성되고 `checksums.sha256`에 등록된다.
  2. **Given** 타겟 우분투에서 물리 볼륨이 정상 복원되었을 때, **When** 부트스트랩 스크립트가 실행되면, **Then** 중복 SQL 덤프 실행을 생략하고 레코드 정합성을 검증한다.

---

### User Story 4 - 실사용 환경 변수 완전 이전 및 전체 작업 폴더 클린 번들링 (Priority: P1) 🎯 MVP

엔지니어는 현재 작업 폴더(`c:\AISERVICE`) 내의 모든 활성 서비스(`ateam`, `bteam`, `model_gateway`, `gateway`, `ddns`, `config`, `tests`, `docs`)와 실행 스크립트, 그리고 **실사용 환경 변수 파일(루트 `.env` 및 `ddns/.env`)의 실제 시크릿/설정값 일체**를 암호화된 아카이브 안에 누락 없이 1:1 구조로 보존하되, 불필요한 빌드 캐시(`.git`, `.venv`, `__pycache__`, `node_modules`, `dist`, `.pytest_cache`, 임시 로그)는 완벽히 제거한 클린 패키지를 생성해야 합니다.

- **Why this priority**: `.env.example`만 복사되어 사용자가 타겟 서버에서 비밀번호, API 키, 포트 등을 일일이 다시 입력해야 하는 번거로움과 누락 실수를 차단하면서도 전송·보관 중 원문 시크릿 노출을 방지하기 위함입니다.
- **Independent Test**: 번들링 완료 후 생성된 암호화 아카이브를 승인된 키로 검증했을 때 루트 `.env`와 `ddns/.env`의 실제 값이 복원되고, 평문 아카이브/로그/매니페스트에는 시크릿이 없으며, 불필요한 빌드 아티팩트는 0건인지 검증합니다.
- **Acceptance Scenarios**:
  1. **Given** 작업 폴더 전체를 번들링할 때, **When** 패키징을 수행하면, **Then** 루트 `.env`와 `ddns/.env`에 포함된 DB 계정, 키움 API 키, SMTP 암호, DuckDNS 토큰이 암호화된 번들에 누락 없이 보존되고 로그와 매니페스트에는 마스킹 값만 기록된다.
  2. **Given** 번들링 결과물을 검사할 때, **When** `.git`, `.venv`, `node_modules`, `__pycache__` 포함 여부를 스캔하면, **Then** 제외 대상 파일/폴더가 0건으로 검출된다.

---

### User Story 5 - 단계적 오케스트레이션을 통한 원클릭 Zero-Config 자동 복원 (Priority: P1) 🎯 MVP

타겟 우분투 서버에서 단일 실행 스크립트(`bootstrap_restore.sh`)를 실행하면, 사용자의 어떠한 추가 입력이나 파일 수정 없이, 줄바꿈 및 실행 권한(`chmod +x`) 정규화, `.env` 보안 권한(`chmod 600`) 부여, 도커 볼륨 및 데이터베이스 복원, 인프라(DB/Redis/Model Gateway) Healthy 확인 후 애플리케이션 컨테이너 순차 기동까지 완전 자동 완수되어야 합니다.

- **Why this priority**: 플랫폼 이전 시 사용자의 수동 개입을 0회로 만들고 컨테이너 간 의존성 기동 실패를 원천 방지하기 위함입니다.
- **Independent Test**: 깨끗한 우분투 환경에서 추가 파일 수정 없이 `bootstrap_restore.sh` 단독 실행만으로 도커 볼륨 프로비저닝, DB 복원, DuckDNS 갱신, Compose 전체 서비스가 Healthy 상태로 기동되는지 확인합니다.
- **Acceptance Scenarios**:
  1. **Given** 마이그레이션 아카이브가 풀린 우분투 서버에서, **When** `bash bootstrap_restore.sh`를 실행하면, **Then** 추가적인 `.env` 입력 요청 없이 도커 볼륨이 자동 생성되고 MySQL 덤프와 ChromaDB 벡터 데이터가 정상 로드된다.
  2. **Given** 인프라 컨테이너가 Healthy 상태가 되었을 때, **When** 애플리케이션 컨테이너가 순차 기동되면, **Then** Connection Refused 없이 모든 서비스 컨테이너가 정상 실행 상태가 된다.

---

### User Story 6 - DuckDNS DDNS IPv4 강제 연동 및 도메인 동기화 (Priority: P2)

타겟 우분투 서버에서 번들된 `.env`의 `DUCKDNS_DOMAIN`과 `DUCKDNS_TOKEN`을 인식하여, 복원 시점에 IPv4(`curl -4`)로 DuckDNS를 즉시 갱신하고, 우분투 호스트 레벨의 `cron`에 5분 주기 자동 갱신 스케줄을 멱등성 있게 등록하여 유동 IP 환경에서도 도메인(`ezenitac.duckdns.org`) 접속을 무중단 유지해야 합니다.

- **Why this priority**: 타겟 서버의 외부 네트워크 IP가 변경되거나 동적 IP를 사용하는 환경에서도 외부 접속 URL이 끊김 없이 유지되도록 하기 위함입니다.
- **Independent Test**: `bootstrap_restore.sh` 실행 후 DuckDNS 갱신 로그에 `OK`가 기록되고 호스트 crontab에 5분 주기 스케줄이 등록되었는지 확인합니다.
- **Acceptance Scenarios**:
  1. **Given** 번들된 `.env`에 DuckDNS 토큰과 도메인이 포함된 상태에서, **When** 부트스트랩이 실행되면, **Then** `curl -4`를 통해 즉시 IP 갱신 API가 호출되어 `OK` 응답을 받고 5분 주기 cronjob이 등록된다.

---

### User Story 7 - 전수 엔드포인트 E2E 헬스체크 및 마이그레이션 검증 게이트 (Priority: P2)

서비스 기동 완료 즉시 자동화된 검증기(`verify_migration.py`)가 실행되어, 정확히 **10개 HTTP 엔드포인트**(게이트웨이 80/8080, Model Gateway 8081/8090/8091, A-Team Pilos 대시보드, B-Team Oliview UI/API 및 올리챗/올원챗)와 **Redis TCP PING 1개**를 호출하고 HTTP 응답 상태(200 OK), Redis 응답 및 데이터 정합성을 검증하여 구조화된 검증 보고서(`verification_report.json`)를 발행해야 합니다.

- **Why this priority**: 마이그레이션 성공 여부를 정량적으로 즉시 판정하여 불완전한 배포나 데이터 유실을 조기에 탐지하기 위함입니다.
- **Independent Test**: 마이그레이션 완료 후 `verify_migration.py` 실행 시 10개 HTTP + Redis TCP로 구성된 11개 검사에서 100% Pass(11/11)를 달성하는지 확인합니다.
- **Acceptance Scenarios**:
  1. **Given** 모든 서비스 컨테이너가 기동된 후, **When** `verify_migration.py`를 실행하면, **Then** 10개 HTTP 엔드포인트와 Redis TCP PING의 응답 상태, 지연시간 및 데이터 정합성이 기록되고 최종 상태 `PASS`가 반환된다.
  2. **Given** 엔드포인트 중 1개라도 비정상 응답 시, **When** 검증기가 종료되면, **Then** 실패 사유와 엔드포인트 ID가 명시되고 Exit code 1을 반환한다.

---

## 3. 엣지 케이스 및 예외 처리 (Edge Cases)

- **EC-001 (대용량 MySQL 덤프 중단 및 메모리 OOM)**: 대용량 데이터(Pilos 3.4GB+, Oliview 950MB+) 덤프 및 복원 시 메모리 초과를 방지하기 위해 `--single-transaction`, `--quick`, `--max_allowed_packet=512M`, `--net_buffer_length=16384` 옵션 및 스트리밍 gzip 파이프라인을 적용.
- **EC-002 (클린 우분투 GPU 드라이버 미설치 및 needrestart 방해)**: 우분투 24.04 LTS에서 `apt` 실행 시 `DEBIAN_FRONTEND=noninteractive`를 강제하고 Snap Docker를 배제하며, 공식 드라이버 및 `nvidia-container-toolkit` 자동 설치를 무인 수행하여 Docker 데몬 런타임을 자동 재구성.
- **EC-003 (ChromaDB v2 SQLite 락 및 파일 정합성)**: 실행 중인 ChromaDB 컨테이너의 SQLite 파일(`chroma.sqlite3`) 백업 시 쓰기 락 충돌을 방지하기 위해 컨테이너 일시정지(`docker pause/unpause`) 또는 SQLite 온라인 백업 API/WAL 체크포인트를 수행한 후 볼륨 아카이빙.
- **EC-004 (포트 충돌 및 방화벽 차단)**: 우분투 호스트에서 80, 8080, 3306, 6379 포트가 이미 타 프로세스에 의해 점유된 경우, 부트스트랩 스크립트가 사전 포트 검사를 수행하고 충돌 프로세스 알림 및 `.env` 포트 재매핑을 안내.
- **EC-005 (기존 데이터베이스/볼륨 덮어쓰기 충돌)**: 타겟 우분투 서버에 동일한 이름의 볼륨이나 DB가 이미 존재하는 경우, 대화형 확인 프롬프트(`Overwrite existing data? [y/N]`)를 제공하고 무인 배포 모드(`--force` 또는 `-y`)를 지원.
- **EC-006 (디스크 공간 부족)**: 덤프 생성 및 볼륨 아카이브 추출 전 소스 및 타겟 호스트의 디스크 여유 공간(최소 25GB 이상)을 사전에 검사하여 디스크 풀(Disk Full)로 인한 파이프라인 중단 방지.
- **EC-007 (i7-930 Non-AVX CPU 명령어 충돌 및 Pascal sm_61 JIT 빌드)**: 타겟 CPU(i7-930)가 AVX를 지원하지 않으므로, 컴파일 시 `-march=native` (AVX 배제, SSE4.2 활성화) 및 `CMAKE_CUDA_ARCHITECTURES=61` 플래그를 적용하여 컴파일 및 런타임 `Illegal instruction` 에러를 원천 차단.
- **EC-008 (타겟 호스트 특정 환경변수 동적 오버라이드)**: 호스트의 IP나 특수 경로 변경이 필요한 경우, 기존 `.env`의 핵심 시크릿을 보존하면서 대상 호스트의 동적 매개변수만 안전하게 병합(`merge`)하여 덮어쓰기 손실 방지.
- **EC-009 (WSL2 전용 디바이스 마운트 오류)**: Native Ubuntu 환경에서 `/dev/dxg` 또는 `/usr/lib/wsl` 디렉티브로 인한 Docker Compose 파싱 에러 발생 시, 우분투용 정규화 필터가 Compose 파일에서 해당 볼륨/디바이스를 자동 제거하고 표준 `nvidia` 디바이스 매핑으로 교체.

---

## 4. 기능 요구사항 (Functional Requirements)

- **FR-001**: 시스템은 클린 Ubuntu 22.04 / 24.04 LTS 환경을 감지하여 `DEBIAN_FRONTEND=noninteractive` 모드로 Snap이 아닌 공식 APT Docker Engine, Docker Compose, NVIDIA 드라이버, `nvidia-container-toolkit`의 설치 여부를 판별하고 미설치 시 자동 설치 프로비저닝을 수행하는 사전 점검 기능을 제공해야 한다.
- **FR-002**: 시스템은 타겟 호스트의 하드웨어 사양(Intel i7-930 SSE4.2 CPU, NVIDIA GTX 1070 8GB GPU)을 감지하여, `-march=native` 및 `CMAKE_CUDA_ARCHITECTURES=61` 플래그로 `llama.cpp`를 Pascal/Nehalem에 최적화하여 자동 JIT 컴파일해야 한다.
- **FR-003**: 시스템은 MySQL 컨테이너(`pilos-db`, `bteam_db`, `mysql-green`)와 Green 스택(`bteam/docker-compose.green.yml`)의 `GREEN_DB_*` 설정을 대상으로 `FLUSH TABLES WITH READ LOCK` 또는 컨테이너 일시정지 기반으로 InnoDB Dirty Page를 안전하게 플러시한 후 구조, 데이터, 뷰, 트리거, 이벤트를 포함하는 무손실 압축 덤프(`.sql.gz`)를 추출하는 도구를 제공해야 한다.
- **FR-004**: 시스템은 Docker named volume(`ateam_db_data`, `bteam_bteam_mysql_data`, `green_mysql_data`, `green_chroma_data`, `aiservice_redis_data`)의 물리 데이터를 안전하게 백업 및 압축(`.tar.gz`, sparse file 지원)하는 볼륨 추출 기능을 제공해야 한다.
- **FR-005**: 시스템은 전체 작업 폴더(`c:\AISERVICE`)의 소스 코드와 설정 파일을 1:1로 미러링하되, `.git`, `.venv`, `node_modules`, `__pycache__` 등 불필요한 임시/캐시 디렉터리를 제외하는 클린 어셈블리 기능을 제공해야 한다.
- **FR-006**: 시스템은 실사용 환경 변수 파일(루트 `.env` 및 `ddns/.env`)의 실제 시크릿/설정값 일체를 암호화된 아카이브에 100% 누락 없이 번들링하고, 복호화 키를 아카이브 외부의 보호된 경로 또는 비밀 주입 경로에서 받아 타겟 서버에서 사용자의 수동 입력 없이 즉시 기동(Zero-Config)할 수 있도록 보장해야 한다. 원문 시크릿은 로그, 매니페스트, 체크섬 및 평문 전송에 기록하지 않는다.
- **FR-007**: 시스템은 번들 압축 해제 시 `.env` 파일에 `chmod 600` 보안 권한을 자동 적용하고, 모든 스크립트에 `chmod +x`를 부여해야 한다.
- **FR-008**: 시스템은 우분투 리눅스 타겟 환경에 최적화된 암호화 아카이브를 생성하는 `make_migration_pack.py` CLI를 제공해야 한다. 기본 `--format tar.gz`는 `*.tar.gz.enc`, `--format zip`은 동일 내용의 `*.zip.enc`를 생성하며, `--format both`는 두 개의 독립적인 암호화 아카이브를 생성한다(병렬 생성은 허용하되 필수는 아님). 각 아카이브는 동일한 manifest/checksum을 참조하고 외부 키 없이는 복호화할 수 없어야 한다.
- **FR-009**: 시스템은 모든 생성된 덤프 파일, 볼륨 아카이브, 소스 번들에 대한 SHA-256 해시 체크섬을 `migration_manifest.json` 및 `checksums.sha256`에 기록해야 한다.
- **FR-010**: 시스템은 타겟 우분투 서버에서 원클릭으로 실행 가능한 멱등 복원 및 부트스트랩 스크립트(`bootstrap_restore.sh`)를 제공해야 한다.
- **FR-011**: 부트스트랩 스크립트는 우분투 환경에서 모든 쉘 스크립트의 CRLF 줄바꿈을 LF로 자동 변환하고 `set -euo pipefail` 에러 트랩을 적용해야 한다.
- **FR-012**: 부트스트랩 스크립트는 Docker Compose 파일에서 Windows WSL 전용 디바이스(`/dev/dxg`, `/usr/lib/wsl`)를 자동 제거하고 Native Ubuntu GPU 런타임 설정으로 자동 변환해야 한다.
- **FR-013**: 부트스트랩 스크립트는 물리 볼륨 복원 성공 시 중복 SQL 덤프 복원을 건너뛰는 상호 배제(Mutex) 복원 로직을 적용하여 DB 테이블 충돌을 방지해야 한다.
- **FR-014**: NVIDIA GTX 1070이 감지되고 GPU 드라이버 및 컨테이너 런타임이 정상인 대상에서는 Model Gateway가 Qwen 2B LLM, BGE-M3 임베딩, BGE-Reranker 3종 모델을 OOM 없이 5.0GB VRAM 예산 안에서 100% GPU 가속으로 서빙해야 한다. GPU가 없거나 `--skip-gpu`가 지정되었거나 GPU 호환성 검증이 실패한 경우에는 CPU fallback chain으로 기동할 수 있지만, 검증 보고서에 `DEGRADED` 사유를 기록하며 이 경로는 SC-003의 GPU PASS로 산정하지 않는다.
- **FR-015**: 시스템은 번들된 `.env` 설정에 따라 타겟 우분투 서버에서 DuckDNS 동적 IP 갱신 데몬(`ddns/duck.sh`)을 `curl -4` 옵션과 함께 5분 주기 크론잡으로 자동 등록하고 초기 IP를 즉시 동기화해야 한다.
- **FR-016**: 부트스트랩 스크립트는 인프라 컨테이너(MySQL, Redis, Model Gateway)의 Healthy 상태를 확인한 후 애플리케이션 컨테이너를 순차 기동하는 단계별 오케스트레이션을 보장해야 한다.
- **FR-017**: 시스템은 복원 완료 후 즉시 10개 HTTP 엔드포인트와 Redis TCP PING으로 구성된 11개 주요 서비스 검사를 수행하고 결과를 `verification_report.json`으로 저장하는 자동 검증기(`verify_migration.py`)를 제공해야 한다.
- **FR-018**: 시스템은 마이그레이션 팩 구성, 우분투 서버 사전 요구사항, 복원 절차, GPU 환경 설정, 트러블슈팅을 다루는 `MIGRATION_GUIDE.md`를 포함해야 한다.
- **FR-019**: 시스템은 사전 검증 모드(`--dry-run`), 볼륨 포함 옵션(`--include-volumes`), 모델 가중치 포함 옵션(`--include-models`), GPU 설치·JIT·GPU Compose 경로를 생략하고 CPU-only 모드로 강제하는 옵션(`--skip-gpu`), 강제 덮어쓰기 옵션(`--force`)을 지원해야 한다. `--include-models`는 설정된 모델 루트의 파일을 아카이브에 포함하고 각 파일의 크기와 SHA-256을 manifest/checksum에 기록하며 복원 시 동일 경로로 배치해야 한다.

---

## 5. 핵심 엔티티 및 패키지 구조 (Key Entities & Package Structure)

### 5.1 마이그레이션 팩 번들 레이아웃
```text
AISERVICE_Migration_Pack/
├── .env                            # 복호화 후 생성되는 실사용 환경 변수 및 시크릿 (Zero-Config, chmod 600)
├── ateam/                          # A-Team Pilos 서비스 소스 및 설정
├── bteam/                          # B-Team Oliview 통합 파이프라인 및 서비스
│   ├── packages/core/              # 공통 코어 모듈
│   ├── pipelines/                  # 전주기 파이프라인 러너
│   ├── services/                   # 대시보드 및 챗봇 서비스
│   └── deployment/                 # Nginx 및 운영 설정
├── model_gateway/                  # vLLM/LLM/임베딩/리랭커 모델 서빙 게이트웨이
│   ├── src/                        # 서버 및 라우터 소스
│   ├── scripts/                    # llama.cpp 자동 빌드 (sm_61 & SSE4.2 지원) & GPU 프로빙
│   └── config/                     # 모델 매핑 및 하드웨어 튜닝 설정
├── gateway/                        # 통합 Nginx 역방향 프록시 게이트웨이
├── ddns/                           # DuckDNS 동적 DNS 갱신 데몬 (.env 포함, duck.sh)
├── config/                         # 공통 환경 설정 및 템플릿
├── tests/                          # E2E 및 단위/통합 테스트 스위트
├── migration_pack/                 # 마이그레이션 전용 자산 및 도구
│   ├── checksums.sha256             # clean source bundle 전체 파일 inventory 체크섬
│   ├── database/                   # 압축된 MySQL 덤프 파일 (.sql.gz)
│   │   ├── pilos_v2.sql.gz
│   │   ├── oliview_project.sql.gz
│   │   ├── cosmetic_db.sql.gz      # Green MySQL 논리 덤프
│   │   └── checksums.sha256             # DB dump/volume 산출물 전용 체크섬
│   ├── volumes/                    # Docker Volume 물리 아카이브 (.tar.gz)
│   │   ├── ateam_db_data.tar.gz
│   │   ├── bteam_bteam_mysql_data.tar.gz
│   │   ├── green_mysql_data.tar.gz
│   │   ├── green_chroma_data.tar.gz
│   │   └── aiservice_redis_data.tar.gz
│   ├── scripts/                    # 마이그레이션 & 복원 자동화 스크립트
│   │   ├── export_databases.py
│   │   ├── export_docker_volumes.py
│   │   ├── install_prerequisites.sh# 클린 우분투용 Docker/GPU 무인 자동 설치 도구
│   │   ├── normalize_compose.py    # WSL2 -> Native Ubuntu Compose 변환기
│   │   ├── bootstrap_restore.sh
│   │   ├── bootstrap_restore.py
│   │   └── verify_migration.py
│   ├── config/                     # 환경 변수 템플릿 (.env.template)
│   ├── migration_manifest.json     # 마이그레이션 매니페스트 v2.0
│   └── MIGRATION_GUIDE.md          # 우분투 마이그레이션 매뉴얼
├── docker-compose.yml              # 루트 통합 Compose 파일 (우분투 자동 변환 지원)
├── bteam/docker-compose.green.yml  # Green MySQL/Chroma 스택 정의
├── run_all_services.sh             # 우분투 서비스 통합 기동 스크립트
├── bootstrap_restore.sh            # 우분투 원클릭 복원 진입점 스크립트
└── README.md
```

### 5.2 마이그레이션 매니페스트 스키마 (`migration_manifest.json` v2.0)
- `manifest_version`: `"2.0.0"`
- `created_at`: ISO 8601 타임스탬프
- `source_environment`: 소스 OS, 플랫폼, 호스트명
- `target_environment`: `"Ubuntu Linux 24.04 LTS (i7-930 Nehalem, 24GB RAM, GTX 1070 8GB sm_61)"`
- `migration_mode`: `"DEV_PLATFORM_TRANSFER"`
- `zero_config_ready`: `true` (키는 아카이브 외부의 사전 보호 경로에서 주입되며 사용자 프롬프트는 없음)
- `target_hardware_profile`:
  - `cpu`: `"Intel Core i7-930 (SSE4.2, Non-AVX)"`
  - `gpu`: `"NVIDIA GeForce GTX 1070 8GB (Compute Capability 6.1 / sm_61)"`
  - `ram_mb`: `24576`
  - `vram_mb`: `8192`
  - `llama_cpp_flags`: `"-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=61 -march=native"`
- `clean_os_prerequisites`: Docker, NVIDIA Driver, nvidia-container-toolkit 자동 설치 지원
- `databases`: DB별 덤프 파일 경로, 크기, SHA-256 해시, 행 수(row counts)
- `volumes`: 볼륨별 아카이브 파일 경로, 대상 Docker 볼륨 이름, 크기, SHA-256 해시
- `secrets`: 원문 대신 암호화 상태와 외부 키 주입 방식만 기록하며 실제 토큰/비밀번호는 기록하지 않음
- `ddns_config`: DuckDNS 도메인 연동 여부 및 갱신 주기
- `services`: 패키징된 서비스 컴포넌트 목록
- `checksums`: 전체 아카이브 및 파일 무결성 해시 매트릭스

---

## 6. 성공 기준 (Success Criteria)

- **SC-001 (Zero-Configuration 복원)**: 타겟 우분투 서버에서 사용자가 `.env` 파일을 수동 편집하거나 설정값을 입력하는 횟수가 0회이며, 압축 해제 후 단일 스크립트 실행으로 100% 동작한다.
- **SC-002 (클린 OS 자동 프로비저닝)**: Docker 및 GPU 드라이버가 없는 클린 Ubuntu 24.04 LTS에서도 사전 점검 스크립트를 통해 `DEBIAN_FRONTEND=noninteractive` 모드로 필수 인프라가 100% 자동 설치 구성된다.
- **SC-003 (i7-930 / GTX 1070 하드웨어 최적화 무정지 가동)**: AVX를 지원하지 않는 i7-930 CPU와 Pascal GTX 1070 GPU 환경에서 `Illegal instruction` 크래시 없이 3대 AI 모델이 8GB VRAM 내에서 100% GPU 가속 가동된다.
- **SC-004 (데이터 무손실률 100%)**: 기본 MySQL 2개 DB(`pilos_v2`, `oliview_project`)와 Green 스택 MySQL(`cosmetic_db`)의 대상 테이블 레코드, 그리고 ChromaDB v2(`oliview_review_sentences_v2`)의 48,210+건 벡터가 우분투 서버에 100% 무손실 복원된다.
- **SC-005 (원클릭 부트스트랩 시간 SLA 달성)**: 사전 인프라 준비 완료 서버에서는 **10분 이내**, 완전 클린 Ubuntu 24.04 LTS 서버(드라이버 및 도커 신규 설치 포함)에서는 **25분 이내**에 전 서비스 기동을 완수한다.
- **SC-006 (11개 검사 100% 정상 가동)**: 복원 완료 후 `verify_migration.py` 실행 시 10개 HTTP 엔드포인트와 Redis TCP PING 전수 검사에서 오류율 0% (11/11 Pass)를 달성한다.
- **SC-007 (DuckDNS DDNS IPv4 자동 동기화)**: 부트스트랩 완료 즉시 공인 IP 갱신이 성공(`OK`)하고 5분 주기 크론 동기화가 활성화된다.
- **SC-008 (크로스 플랫폼 호환성)**: Windows에서 생성된 마이그레이션 팩이 Ubuntu 22.04 / 24.04 LTS 환경에서 어떠한 줄바꿈 오류(`\r`)나 권한 오류 없이 즉시 실행된다.
- **SC-009 (무결성 검증 통과)**: 모든 데이터베이스 덤프 및 볼륨 아카이브의 SHA-256 체크섬이 100% 일치한다.

---

## 7. 가정 및 제약사항 (Assumptions & Constraints)

- **마이그레이션 성격**: 본 마이그레이션은 동일 개발/실증(DEV/DEMO) 모드의 호스트 환경 이전(Windows $\rightarrow$ Ubuntu Linux)이므로, `.env` 내의 실사용 시크릿을 암호화된 번들에 포함하되 키는 외부 보호 경로에서 주입합니다. 복원 후 기능에는 원문 값을 사용하지만 로그·매니페스트·체크섬·평문 전송에는 기록하지 않습니다.
- **타겟 하드웨어 프로파일**: 타겟 서버는 Intel Core i7-930 CPU (Non-AVX, SSE4.2), 24GB RAM, NVIDIA GeForce GTX 1070 8GB GPU를 탑재한 Ubuntu 24.04 LTS 환경을 표준으로 합니다.
- **GPU 가속 환경**: NVIDIA GPU 장착 서버의 경우 부트스트랩 스크립트 또는 자동 설치 도구를 통해 `nvidia-container-toolkit`을 활성화합니다. GPU가 없거나 `--skip-gpu`가 지정된 경우 Compose의 GPU device/deploy/environment 설정을 제거한 CPU-only 모드로 실행하며, GPU 호환성 실패 시에도 CPU fallback을 허용하되 검증 보고서에는 `DEGRADED` 상태와 사유를 기록합니다. GTX 1070과 정상 GPU 런타임 조건에서만 SC-003의 100% GPU 가속 PASS를 인정합니다.
- **스토리지 여유 공간**: 덤프 생성 및 볼륨 아카이브 추출/압축 해제를 위해 소스 호스트 및 타겟 우분투 서버에 최소 25GB 이상의 디스크 여유 공간이 확보되어 있어야 합니다.
- **보안 및 아카이브 전송**: 실사용 시크릿이 포함된 마이그레이션 아카이브는 공용 네트워크에 공개되지 않도록 SSH/SCP 또는 개인 보안 채널을 통해 전송해야 합니다.
