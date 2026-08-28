# Phase 0 Research: 043-docker-volume-ubuntu-migration-pack

**Feature**: `043-docker-volume-ubuntu-migration-pack`  
**Date**: 2026-08-28  
**Context**: Windows 11 $\rightarrow$ Ubuntu 24.04 LTS (i7-930, 24GB RAM, GTX 1070 8GB) Zero-Config 마이그레이션 팩 고도화

---

## 1. 클린 Ubuntu 24.04 LTS 인프라 자동 프로비저닝 (Clean OS Auto-Provisioning)

### Research Question
클린 Ubuntu 24.04 LTS(Noble Numbat)에서 Snap Docker의 GPU 접근 차단 문제를 방지하고, 공식 Docker Engine 및 NVIDIA Container Toolkit을 완전 무인(`DEBIAN_FRONTEND=noninteractive`)으로 설치/설정하는 표준 절차는 무엇인가?

### Decision
`install_prerequisites.sh` 스크립트를 구현하여 다음 파이프라인을 자동 수행:
1. Snap Docker 감지 시 경고 및 공식 APT Docker로 교체.
2. `export DEBIAN_FRONTEND=noninteractive` 및 `needrestart` 대화창 자동 바이패스(`-o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold"`).
3. Docker 공식 APT 저장소(`https://download.docker.com/linux/ubuntu`)에서 `docker-ce`, `docker-ce-cli`, `containerd.io`, `docker-buildx-plugin`, `docker-compose-plugin` 설치.
4. NVIDIA 공식 저장소(`https://nvidia.github.io/libnvidia-container/stable/deb/`)에서 `nvidia-container-toolkit` 설치.
5. `nvidia-ctk runtime configure --runtime=docker`를 실행하여 `/etc/docker/daemon.json`에 `nvidia` 런타임 주입 후 `systemctl restart docker`.
6. 현재 사용자를 `docker` 그룹에 등록 (`usermod -aG docker $USER`).

### Rationale
- 2026년 Ubuntu 24.04 LTS의 기본 App Center는 Docker를 snap으로 설치하며, snap 샌드박스는 `/dev/nvidia*` 접근을 차단하여 GPU 가속이 불가능합니다.
- 공식 APT 패키지와 `nvidia-ctk` 도구를 사용하면 cgroups v2 환경에서도 GPU 런타임이 100% 안정적으로 등록됩니다.

### Alternatives Considered
- `get.docker.com` 범용 쉘 스크립트 실행: 편리하나 세부 설정 제어 및 미러링 네트워크에서의 에러 트랩이 어려워 공식 APT 저장소 직접 등록 방식 채택.

---

## 2. 타겟 하드웨어(i7-930 Non-AVX CPU & GTX 1070 sm_61 GPU) 최적화

### Research Question
AVX를 지원하지 않는 Nehalem 1세대 i7-930 CPU와 Pascal GTX 1070 8GB GPU 환경에서 `Illegal instruction` 크래시를 방지하고 8GB VRAM을 최적 배분하는 `llama.cpp` JIT 빌드 및 런타임 구성은 무엇인가?

### Decision
`model_gateway/scripts/build_llama.sh` 및 `model_gateway` 런타임에 다음 파라미터 적용:
1. **CPU 빌드 플래그**: Nehalem 아키텍처는 AVX/AVX2를 지원하지 않고 SSE4.2까지만 지원하므로, `-march=native -DGGML_AVX=OFF -DGGML_AVX2=OFF -DGGML_FMA=OFF -DGGML_F16C=OFF` 또는 CMake의 자동 하드웨어 감지 적용.
2. **GPU CUDA 빌드 플래그**: GTX 1070은 Compute Capability `sm_61` (Pascal)이므로 `cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=61`.
3. **8GB VRAM 파티셔닝 (`VRAM_SAFETY_LIMIT_MB=5000`)**:
   - `Qwen 2.5/3.5 2B LLM`: GGUF Q4_K_M / Q8_0 또는 FP16 $\rightarrow$ ~2.5GB 점유 (GPU 오프로드 `-ngl 99`)
   - `BGE-M3 Dense Embedding`: ~1.2GB 점유 (포트 8090)
   - `BGE-Reranker-v2-m3`: ~1.2GB 점유 (포트 8091)
   - **총 점유량**: 약 4.9~5.0GB $\rightarrow$ 8GB VRAM 내에서 100% GPU 가속 서빙 완료.

### Rationale
- 일반적인 현대 x86_64 바이너리는 AVX2를 기본 전제로 빌드되므로 i7-930에서 즉시 `SIGILL`로 사망합니다.
- Pascal 전용 `sm_61` 플래그와 Non-AVX CPU 플래그로 타겟 호스트에서 직접 JIT 컴파일함으로써 크래시를 원천 방지하고 최대의 하드웨어 처리량을 확보합니다.

### Alternatives Considered
- 순수 사전 컴파일 x86_64 범용 바이너리 배포: 구형 CPU에서 실행 불가하므로 JIT Rebuild 파이프라인 필수.

---

## 3. MySQL 8.0/8.4 및 ChromaDB v2 무손실 볼륨/덤프 추출

### Research Question
실행 중인 데이터베이스에서 데이터 파손(InnoDB Dirty Page, SQLite WAL 락) 없이 물리 볼륨과 논리 SQL 덤프를 안전하게 추출하고 상호 배제(Mutex)로 복원하는 방법은 무엇인가?

### Decision
1. **패키징 단계 (`export_databases.py` & `export_docker_volumes.py`)**:
   - MySQL: `mysqldump --single-transaction --quick --max_allowed_packet=512M`으로 논리 압축 덤프(`.sql.gz`) 생성. 물리 볼륨 추출 시 `FLUSH TABLES WITH READ LOCK` 또는 컨테이너 일시 정지(`docker pause`) 후 `tar --sparse -czf`로 sparse file을 보존하여 압축.
   - ChromaDB: `chroma.sqlite3`에 대해 SQLite WAL 체크포인트(`PRAGMA wal_checkpoint(TRUNCATE)`) 적용 후 볼륨 tarball 생성.
   - Redis: `redis-cli BGSAVE` 후 RDB 스냅샷 완료 대기 후 볼륨 tarball 생성.
2. **복원 단계 (`bootstrap_restore.sh` / `bootstrap_restore.py`)**:
   - **상호 배제 (Mutex) 복원**: 물리 볼륨 아카이브가 존재하면 Docker volume 디렉터리에 먼저 풀고, 컨테이너 기동 후 테이블 레코드 무결성이 확인되면 중복 SQL 덤프 로드를 건너뜀 (`Table already exists` 충돌 방지). 볼륨 아카이브가 없거나 실패 시에만 SQL 덤프 스트리밍 복원 수행.

### Rationale
- 라이브 상태에서 무단으로 InnoDB 파일을 복사하면 Crash Recovery 모드로 들어가거나 테이블스페이스가 손상될 위험이 있습니다.
- WAL 체크포인트와 Mutex 복원을 통해 430만 건의 Pilos 레코드와 4.8만 건의 ChromaDB 벡터를 100% 무손실 복원합니다.

---

## 4. WSL2 $\rightarrow$ Native Ubuntu Compose 디바이스 자동 정규화

### Research Question
Windows WSL2 전용 디렉티브(`/dev/dxg`, `/usr/lib/wsl`)를 포함한 `docker-compose.yml`을 Native Ubuntu 서버에서 오류 없이 실행하도록 변환하는 방법은 무엇인가?

### Decision
`normalize_compose.py` 필터 스크립트를 구현하여:
1. `docker-compose.yml`을 파싱하여 WSL2 전용 마운트(`/usr/lib/wsl/drivers`, `/dev/dxg`)를 제거.
2. GPU 서비스(`vllm-serv`, `model_gateway`)에 Linux 표준 `deploy.resources.reservations.devices: [{driver: nvidia, count: all, capabilities: [gpu]}]` 및 `runtime: nvidia`를 주입.
3. 변환된 compose 파일을 타겟 우분투에서 실행.

### Rationale
- 클린 Ubuntu에는 `/dev/dxg`가 없으므로 변환하지 않으면 compose 파싱 에러로 기동이 100% 중단됩니다.

---

## 5. Zero-Config 실사용 `.env` 및 DuckDNS DDNS 자동 연동

### Research Question
타겟 서버에서 사용자의 수동 텍스트 편집 없이 실제 시크릿을 온전히 전달하고 DuckDNS 갱신을 5분 주기 크론으로 자동화하는 구조는 무엇인가?

### Decision
1. `make_migration_pack.py`가 루트 `.env`와 `ddns/.env`의 실제 키값(DB 암호, 키움 API 키, DuckDNS 토큰 등)을 그대로 번들에 포함.
2. 번들 해제 시 `bootstrap_restore.sh`가 `.env`에 `chmod 600` 보안 권한을 적용.
3. `.env`의 `DUCKDNS_DOMAIN`과 `DUCKDNS_TOKEN`을 읽어:
   - `curl -4 -s "https://www.duckdns.org/update?domains=${DOMAIN}&token=${TOKEN}&ip="`로 즉시 공인 IP 갱신.
   - 호스트 `crontab`에 `*/5 * * * * curl -4 -s "https://www.duckdns.org/update?domains=${DOMAIN}&token=${TOKEN}&ip=" >/dev/null 2>&1`을 멱등성 있게 등록.

### Rationale
- 동일 개발 모드의 플랫폼 이전이므로 수동 `.env` 작성을 0회로 만들고 유동 IP 환경에서도 즉시 외부 도메인(`ezenitac.duckdns.org`) 접속을 유지합니다.
