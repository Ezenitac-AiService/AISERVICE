# Contract: Bootstrap Restore Script (`bootstrap_restore.sh`)

**Component**: `bootstrap_restore.sh`  
**Target OS**: Ubuntu Linux 22.04 / 24.04 LTS (x86_64 / aarch64)  
**Purpose**: 타겟 우분투 서버에서 원클릭으로 사전 인프라 점검, 권한 정규화, 볼륨 복원, DuckDNS 연동, Compose 오케스트레이션, 검증을 자동 수행하는 진입점 스크립트

---

## 1. CLI Usage & Arguments

```bash
sudo ./bootstrap_restore.sh [OPTIONS]
```

| Argument / Flag | Short | Default | Description |
|:---|:---:|:---:|:---|
| `--yes` | `-y` | `False` | 모든 대화형 확인(Docker/GPU 설치, 볼륨 덮어쓰기) 자동 승인 (무인 배포) |
| `--dry-run` | `-d` | `False` | 하드웨어 감지, 체크섬 검증, 포트 점검만 수행하고 실제 기동 중단 |
| `--skip-gpu` | - | `False` | GPU 드라이버 설치 및 GPU 가속을 건너뛰고 강제 CPU 모드로 기동 |
| `--skip-ddns` | - | `False` | DuckDNS IP 갱신 및 크론 등록 건너뛰기 |
| `--force-dump` | - | `False` | 물리 볼륨 복원 대신 논리 `mysqldump` 스트리밍 복원 강제 |
| `--key-file` | - | `MIGRATION_PACK_KEY_FILE` | 암호화 아카이브 복호화 키 경로. 키가 없으면 복원 실패 |
| `--help` | `-h` | - | 도움말 메시지 출력 |

---

## 2. Execution Pipeline Stages

1. **Stage 1 (System & Privilege Check)**:
   - Root / `sudo` 권한 확인.
   - 암호화 아카이브 복호화 키를 외부 보호 경로에서 확인하고 원문 키를 로그에 출력하지 않음.
   - 포트 `80`, `8080`, `3306`, `6379` 충돌 및 최소 25GB 디스크 여유를 검사하며, `--dry-run`에서도 실제 사전 검사를 수행.
   - `set -euo pipefail` 에러 트랩 활성화.
   - `chmod 600 .env` 보안 권한 적용 및 스크립트 `chmod +x` 일괄 부여.
   - CRLF 줄바꿈을 LF로 자동 변환.
2. **Stage 2 (Prerequisite Provisioning)**:
   - Docker Engine 및 Compose 플러그인 확인 $\rightarrow$ 미설치 시 공식 APT 저장소를 통해 자동 설치 (`install_prerequisites.sh`).
   - NVIDIA GPU 하드웨어(`lspci`) 감지 $\rightarrow$ 드라이버 및 `nvidia-container-toolkit` 자동 구성 및 `systemctl restart docker`.
3. **Stage 3 (Compose Normalization)**:
   - `normalize_compose.py` 실행: WSL2 전용 디바이스(`/dev/dxg`) 제거 및 Linux 표준 `nvidia` 런타임 매핑.
4. **Stage 4 (Volume & Database Mutex Restore)**:
   - Docker named volume 생성 및 tarball 압축 해제.
   - 기본 스택과 `bteam/docker-compose.green.yml`의 Green MySQL/Chroma 데이터 경로를 포함하여 인프라 컨테이너(`pilos_db`, `bteam_db`, `mysql-green`, `chroma-green`, `redis`, `vllm-serv`)를 우선 기동.
   - 데이터베이스 무결성 검증 (필요 시 논리 SQL 덤프 폴백 로드).
5. **Stage 5 (DuckDNS DDNS Automation)**:
   - `ddns/duck.sh` 실행 $\rightarrow$ IPv4 공인 IP 즉시 갱신 (`curl -4`).
   - Host `crontab`에 5분 주기 스케줄 멱등 등록.
6. **Stage 6 (Model Gateway Hardware JIT Compilation)**:
   - 타겟 CPU(i7-930: Non-AVX, SSE4.2) 및 GPU(GTX 1070: `sm_61`) 프로빙.
   - 필요 시 `build_llama.sh` 실행하여 Pascal/Nehalem 최적화 바이너리 JIT 컴파일.
7. **Stage 7 (Application Staged Launch & Verification)**:
   - 백엔드, 프론트엔드, 챗봇, 게이트웨이 순차 기동.
   - `verify_migration.py` 실행 $\rightarrow$ 10개 HTTP + Redis TCP PING 11개 검사 및 `verification_report.json` 발행.

---

## 3. Exit Codes

- `0`: 부트스트랩 및 10개 HTTP + Redis TCP PING 11개 검사 100% 성공.
- `1`: 하드웨어 호환성 오류 또는 치명적 패키지 설치 실패.
- `2`: Docker 또는 GPU 런타임 활성화 실패.
- `3`: 볼륨/데이터베이스 복원 실패.
- `4`: 서비스 헬스체크 검증 게이트 실패 (1개 이상 검사 비정상).
